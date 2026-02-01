import re
import os
from pathlib import Path
from commands.inventory_commands import InventoryCommands
from agent import Agent
from character import Character
from systems.pricing import PricingSystem
from systems.skill_checks import get_skill_check_system, SkillDatabase, prompt_skill_choice
from systems.character_generator import create_character_interactive
from models.game_state import Campaign, CharacterPresence, CharacterRef
from models.creature import CreatureRegistry, CreatureInstance
from models.table_state import TableState, extract_action_from_response
from models.party_vote import PartyVote, generate_vote_prompt, parse_vote_response


class Session:
    """
    Manages gameplay commands and character interactions.

    Can operate in two modes:
    1. Simple mode: Characters added directly (legacy behavior)
    2. Campaign mode: Uses Campaign/Scene hierarchy for context management
    """

    def __init__(self, campaign=None, settings=None):
        self.characters = {}  # Loaded Character objects
        self._name_lookup = {}  # Maps lowercase name/alias -> character
        self.campaign = campaign  # Optional Campaign for hierarchical tracking
        self.settings = settings or {}  # Game settings
        self.table_state = TableState()  # Track play flow around the table
        self.current_vote = None  # Active PartyVote if any
        self.parallel_scenes = []  # Scenes happening simultaneously

    @property
    def current_scene(self):
        """Get current scene if in campaign mode."""
        return self.campaign.current_scene if self.campaign else None

    @property
    def in_combat(self):
        """Check if currently in combat."""
        scene = self.current_scene
        return scene.in_combat if scene else False

    def get_scene_characters(self):
        """
        Get characters relevant to current context.
        In campaign mode, only returns characters in current scene.
        In simple mode, returns all loaded characters.
        """
        scene = self.current_scene
        if scene:
            return [self.characters[name] for name in scene.present_characters
                    if name in self.characters]
        return list(self.characters.values())

    def add_character(self, character, to_scene=True):
        """
        Add a character to the session.

        Args:
            character: Character instance
            to_scene: If True and in campaign mode, add to current scene
        """
        self.characters[character.name] = character
        # Build lookup table for O(1) name resolution
        self._name_lookup[character.name.lower()] = character
        for alias in character.aliases:
            self._name_lookup[alias.lower()] = character

        # Register with campaign if present
        if self.campaign:
            # Determine if NPC and get agent name
            is_npc = False
            agent_name = ""
            if isinstance(character.player, Agent):
                is_npc = getattr(character.player, 'is_npc', False)
                if not is_npc:
                    agent_name = character.player.name if hasattr(character.player, 'name') else ""

            self.campaign.register_character(
                name=character.name,
                presence=CharacterPresence.ACTIVE,
                aliases=character.aliases,
                affiliations=character.affiliations,
                allies=character.allies,
                enemies=character.enemies,
                is_npc=is_npc,
                agent=agent_name
            )
            # Add to current session's active list
            if self.campaign.current_session:
                self.campaign.current_session.add_to_session(character.name)
                # Add to current scene if requested
                if to_scene and self.current_scene:
                    self.current_scene.add_character(character.name)

    def get_character(self, char_name):
        """
        Get character or creature by name or alias (case-insensitive). O(1) lookup.

        Args:
            char_name: Name or alias of character/creature

        Returns:
            Character or CreatureInstance, or None
        """
        # Check characters first
        result = self._name_lookup.get(char_name.lower())
        if result:
            return result

        # Check creatures
        registry = CreatureRegistry.get_instance()
        return registry.get_creature(char_name)

    def _load_character(self, parts):
        """
        Load a character from YAML file and add to session.

        Args:
            parts: List containing filename and optional agent name

        Returns:
            str: Result message
        """
        filename = parts[0]
        agent_name = parts[1] if len(parts) > 1 else None

        # Find the file
        chars_dir = Path(__file__).parent / "characters"

        # Try exact match first, then with .yaml extension
        if not filename.endswith(".yaml"):
            filename = f"{filename}.yaml"

        filepath = chars_dir / filename
        if not filepath.exists():
            # List available files
            available = [f.stem for f in chars_dir.glob("*.yaml")]
            return f"File not found: {filename}\nAvailable: {', '.join(available)}"

        try:
            character = Character.from_yaml(str(filepath))
        except Exception as e:
            return f"Error loading character: {e}"

        # Assign agent if specified
        if agent_name:
            agents_dir = Path(__file__).parent / "agents"
            agent_file = agents_dir / f"{agent_name}.yaml"
            if not agent_file.exists():
                # Try exact filename
                agent_file = agents_dir / agent_name
                if not agent_file.exists():
                    available = [f.stem for f in agents_dir.glob("*.yaml")]
                    return f"Agent not found: {agent_name}\nAvailable: {', '.join(available)}"

            try:
                agent = Agent.from_yaml(str(agent_file))
                character.player = agent
            except Exception as e:
                return f"Error loading agent: {e}"

        # Add to session
        self.add_character(character)

        player_info = character.player.name if isinstance(character.player, Agent) else character.player
        return f"Loaded {character.name} (Level {character.level}) - Player: {player_info}"

    def parse_character_from_parts(self, parts):
        """
        Find character name from beginning of parts list.
        Returns (character, remaining_parts) tuple.

        Args:
            parts: List of command parts

        Returns:
            tuple: (Character instance or None, remaining parts list)
        """
        # Try matching from longest to shortest
        for i in range(len(parts), 0, -1):
            potential_name = " ".join(parts[:i])
            character = self.get_character(potential_name)
            if character:
                return character, parts[i:]
        return None, parts

    def handle_command(self, command_str):
        """
        Handle a slash command.

        Args:
            command_str: Full command string (e.g., "/inventory Doc")

        Returns:
            str: Result message
        """
        parts = command_str[1:].split()  # Remove leading slash and split
        if not parts:
            return "Invalid command."

        command = parts[0].lower()

        # Inventory commands
        if command == "inventory" or command == "inv":
            if len(parts) < 2:
                return "Usage: /inventory <character_name>"
            # Join remaining parts for character name (handles "Doc Rivera")
            char_name = " ".join(parts[1:])
            character = self.get_character(char_name)
            if not character:
                return f"Character '{char_name}' not found."
            return InventoryCommands.show_inventory(character)

        elif command == "give":
            if len(parts) < 3:
                return "Usage: /give <character_name> <item_name> [quantity]"

            character, remaining = self.parse_character_from_parts(parts[1:])
            if not character:
                return f"Character not found. Available characters: {', '.join(self.characters.keys())}"

            if not remaining:
                return "Usage: /give <character_name> <item_name> [quantity]"

            # Check if last part is a number
            quantity = 1
            if remaining and remaining[-1].isdigit():
                quantity = int(remaining[-1])
                remaining = remaining[:-1]

            item_name = " ".join(remaining)
            return InventoryCommands.give_item(character, item_name, quantity)

        elif command == "take":
            if len(parts) < 3:
                return "Usage: /take <character_name> <item_name> [quantity]"

            character, remaining = self.parse_character_from_parts(parts[1:])
            if not character:
                return f"Character not found. Available characters: {', '.join(self.characters.keys())}"

            if not remaining:
                return "Usage: /take <character_name> <item_name> [quantity]"

            # Check if last part is a number
            quantity = 1
            if remaining and remaining[-1].isdigit():
                quantity = int(remaining[-1])
                remaining = remaining[:-1]

            item_name = " ".join(remaining)
            return InventoryCommands.take_item(character, item_name, quantity)

        elif command == "use":
            if len(parts) < 3:
                return "Usage: /use <character_name> <item_name> [on <target_name> [body_part]]"

            character, remaining = self.parse_character_from_parts(parts[1:])
            if not character:
                return f"Character not found. Available characters: {', '.join(self.characters.keys())}"

            if not remaining:
                return "Usage: /use <character_name> <item_name> [on <target_name> [body_part]]"

            # Check if "on" keyword is present for targeting another character
            target_character = None
            body_part = None

            if "on" in remaining:
                on_index = remaining.index("on")
                item_parts = remaining[:on_index]
                after_on = remaining[on_index + 1:]

                if after_on:
                    # Parse target character from after_on
                    target_character, body_part_parts = self.parse_character_from_parts(after_on)
                    if not target_character:
                        target_name = " ".join(after_on)
                        return f"Target character '{target_name}' not found."

                    # Remaining parts after character name are the body part
                    if body_part_parts:
                        body_part = " ".join(body_part_parts)

                item_name = " ".join(item_parts)
            else:
                item_name = " ".join(remaining)
                target_character = character  # Use on self

            return InventoryCommands.use_item(character, item_name, target_character, body_part)

        elif command == "weight":
            if len(parts) < 2:
                return "Usage: /weight <character_name>"
            char_name = " ".join(parts[1:])
            character = self.get_character(char_name)
            if not character:
                return f"Character '{char_name}' not found."
            return InventoryCommands.show_weight(character)

        elif command == "items":
            return InventoryCommands.list_available_items()

        # Body parts commands
        elif command == "bodyparts" or command == "limbs":
            if len(parts) < 2:
                return "Usage: /bodyparts <character_name>"
            char_name = " ".join(parts[1:])
            character = self.get_character(char_name)
            if not character:
                return f"Character '{char_name}' not found."
            return str(character.body_parts)

        elif command == "damage":
            if len(parts) < 4:
                return "Usage: /damage <character_name> <body_part> <amount>"

            character, remaining = self.parse_character_from_parts(parts[1:])
            if not character:
                return f"Character not found. Available characters: {', '.join(self.characters.keys())}"

            if len(remaining) < 2:
                return "Usage: /damage <character_name> <body_part> <amount>"

            # Last part should be the damage amount
            try:
                damage_amount = int(remaining[-1])
                body_part_name = " ".join(remaining[:-1])
            except ValueError:
                return "Damage amount must be a number."

            part = character.body_parts.get_part(body_part_name)
            if not part:
                available = ", ".join(character.body_parts.parts.keys())
                return f"Unknown body part '{body_part_name}'. Available: {available}"

            result = part.take_damage(damage_amount)
            msg = f"{character.name}'s {body_part_name} took {result['damage_taken']} damage"
            msg += f" ({result['current_health']}/{part.max_health} HP)"

            if result['newly_crippled']:
                msg += f"\n[WARNING] {character.name}'s {body_part_name.upper()} IS NOW CRIPPLED!"

            return msg

        # Character listing
        elif command == "characters":
            if not self.characters:
                return "No characters in session."

            scene = self.current_scene
            scene_chars = scene.present_characters if scene else []

            lines = ["\n=== Characters ==="]

            def format_char(char):
                """Format character/creature for display."""
                if isinstance(char, CreatureInstance):
                    status = "DEAD" if char.is_dead() else f"HP {char.health['current']}/{char.health['max']}"
                    return f"  - {char.name} (Lv{char.level}, {status}) [CREATURE]"
                else:
                    player = char.player.name if isinstance(char.player, Agent) else char.player
                    npc_tag = " [NPC]" if isinstance(char.player, Agent) and char.player.is_npc else ""
                    return f"  - {char.name} (Lv{char.level}, HP {char.health['current']}/{char.health['max']}, {player}){npc_tag}"

            # Show scene characters first if in campaign mode
            if scene:
                lines.append(f"\nIn Scene ({scene.name}):")
                for char in self.characters.values():
                    if char.name in scene_chars:
                        lines.append(format_char(char))

                # Show nearby characters (in session but not scene)
                nearby = [c for c in self.characters.values() if c.name not in scene_chars]
                if nearby:
                    lines.append("\nNearby (not in scene):")
                    for char in nearby:
                        if isinstance(char, CreatureInstance):
                            lines.append(f"  - {char.name} [CREATURE]")
                        else:
                            player = char.player.name if isinstance(char.player, Agent) else char.player
                            lines.append(f"  - {char.name} ({player})")
            else:
                # Simple mode - list all
                for char in self.characters.values():
                    lines.append(format_char(char))

            return "\n".join(lines)

        # Character info
        elif command == "info":
            if len(parts) < 2:
                return "Usage: /info <character_name>"
            char_name = " ".join(parts[1:])
            character = self.get_character(char_name)
            if not character:
                return f"Character '{char_name}' not found."
            # Handle both Character and CreatureInstance
            if isinstance(character, CreatureInstance):
                return character.get_info_text()
            else:
                character.print_info()
                return ""

        # Character creation
        elif command == "create" or command == "new":
            args = " ".join(parts[1:]) if len(parts) > 1 else ""
            return create_character_interactive(self, args)

        # Load character from file
        elif command == "load":
            if len(parts) < 2:
                return "Usage: /load <filename> [agent]"
            return self._load_character(parts[1:])

        # === CAMPAIGN/SCENE COMMANDS ===

        # Campaign management
        elif command == "campaign":
            return self._handle_campaign_command(parts[1:])

        # Scene management
        elif command == "scene":
            return self._handle_scene_command(parts[1:])

        # Combat management
        elif command == "combat" or command == "fight":
            return self._handle_combat_command(parts[1:])

        # Turn/action management
        elif command == "turn" or command == "next":
            return self._handle_turn_command(parts[1:])

        # Enter a character into scene
        elif command == "enter":
            if len(parts) < 2:
                return "Usage: /enter <character_name>"
            return self._enter_character(" ".join(parts[1:]))

        # Exit a character from scene
        elif command == "exit":
            if len(parts) < 2:
                return "Usage: /exit <character_name>"
            return self._exit_character(" ".join(parts[1:]))

        # === CREATURE COMMANDS ===

        # Spawn creatures
        elif command == "spawn":
            return self._handle_spawn_command(parts[1:])

        # List active creatures
        elif command == "creatures":
            return self._list_creatures()

        # Promote creature to character
        elif command == "promote":
            if len(parts) < 2:
                return "Usage: /promote <creature_name> [new_name]"
            return self._promote_creature(parts[1:])

        # Loot a dead creature
        elif command == "loot":
            if len(parts) < 2:
                return "Usage: /loot <creature_name> [to <character>]"
            return self._loot_creature(parts[1:])

        # Change agent for character/creature
        elif command == "agent":
            if len(parts) < 2:
                return self._list_agents()
            return self._change_agent(parts[1:])

        # === TABLE STATE COMMANDS ===

        # Show table state
        elif command == "table":
            return self._show_table_state()

        # Set spotlight on specific character
        elif command == "spotlight":
            if len(parts) < 2:
                self.table_state.clear_spotlight()
                return "Spotlight cleared. Returning to group mode."
            return self._set_spotlight(" ".join(parts[1:]))

        # Set character's current action/state
        elif command == "state":
            if len(parts) < 3:
                return "Usage: /state <character> <action description>"
            return self._set_character_state(parts[1], " ".join(parts[2:]))

        # Go around the table (round-robin responses)
        elif command == "around":
            return self._go_around_table(parts[1:] if len(parts) > 1 else None)

        # === VOTING COMMANDS ===

        # Start a party vote
        elif command == "vote":
            return self._handle_vote_command(parts[1:])

        # Switch between parallel scenes
        elif command == "parallel":
            return self._handle_parallel_command(parts[1:])

        # === SKILL CHECK COMMANDS ===

        # Manual skill check
        elif command == "check":
            if len(parts) < 3:
                return "Usage: /check <character> <skill>"
            return self._manual_check(parts[1:])

        # === FACTION COMMANDS ===

        # List all factions
        elif command == "factions":
            return self._list_factions()

        # Show faction details or set relation
        elif command == "faction":
            return self._handle_faction_command(parts[1:])

        # Add ally to character
        elif command == "ally":
            if len(parts) < 3:
                return "Usage: /ally <character> <target>"
            return self._add_ally(parts[1:])

        # Add enemy to character
        elif command == "enemy":
            if len(parts) < 3:
                return "Usage: /enemy <character> <target>"
            return self._add_enemy(parts[1:])

        # Help command
        elif command == "help" or command == "h":
            self._show_help_interactive()
            return ""  # Don't print anything after returning

        else:
            return f"Unknown command: /{command}. Type /help for available commands."

    def gm_character_command(self, char_name, command):
        """Handle GM commands directed at a specific character."""
        if char_name in self.characters:
            character = self.characters[char_name]
            print(f"Command to {char_name}: {command}")
            # TODO: Implement character-specific command handling
        else:
            print(f"Character '{char_name}' not found.")

    def _parse_mentions(self, text):
        """
        Parse leading @CharName mentions from text.
        Returns (list of matched Characters, remaining text).
        """
        targets = []
        remaining = text

        while remaining.startswith("@"):
            # Strip the @ and try to match a character name
            after_at = remaining[1:]
            words = after_at.split()
            matched = None

            # Try longest match first
            for i in range(len(words), 0, -1):
                potential_name = " ".join(words[:i])
                character = self.get_character(potential_name)
                if character:
                    matched = character
                    remaining = " ".join(words[i:]).lstrip()
                    break

            if matched:
                targets.append(matched)
            else:
                break

        return targets, remaining

    def gm_narrate(self, narration):
        """
        GM narrates and collects agent responses using table state for flow.

        Supports @CharName targeting:
          @Doc Rivera You hear footsteps behind you.
          @Doc Rivera @Marcus A grenade lands between you.

        Without @ prefix, uses round-robin for PC responses (going around the table).

        Spotlight mode: If spotlight is set, only that character responds.

        Behavior depends on npc_dialogue_mode setting (NPCs only):
          - "auto": NPC agents automatically generate dialogue
          - "manual": GM writes NPC dialogue, press Enter to auto-generate

        Player characters (is_npc=False) always use auto-generation.
        """
        targets, text = self._parse_mentions(narration)

        # Initialize table state if needed
        if not self.table_state.round_robin_order:
            self._initialize_table_state()

        # Log the narration
        addressed_names = ", ".join(c.name for c in targets) if targets else None
        self.table_state.log_action("GM", "narration", text[:50] + "..." if len(text) > 50 else text, addressed_names)

        # Print narration
        if targets:
            print(f"\nNarrator (to {', '.join(c.name for c in targets)}): {text}\n")
        else:
            scene = self.current_scene
            if scene:
                print(f"\nNarrator [{scene.name}]: {text}\n")
            else:
                print(f"\nNarrator: {text}\n")

        # Determine who responds
        is_broadcast = not targets

        # Check for spotlight mode
        if self.table_state.spotlight and not targets:
            spotlight_char = self.get_character(self.table_state.spotlight)
            if spotlight_char:
                targets = [spotlight_char]
                is_broadcast = False
                print(f"  [Spotlight on {self.table_state.spotlight}]\n")

        # Get characters to address
        characters_to_address = targets if targets else self.get_scene_characters()

        # Separate PCs and NPCs for round-robin
        pcs_to_respond = []
        npcs_to_respond = []

        for character in characters_to_address:
            if isinstance(character, str):
                continue
            if isinstance(character.player, Agent):
                is_npc = getattr(character.player, 'is_npc', False)

                # Skip NPCs on broadcasts (they only respond when targeted)
                if is_broadcast and is_npc:
                    continue

                if is_npc:
                    npcs_to_respond.append(character)
                else:
                    pcs_to_respond.append(character)

        # Check dialogue mode setting
        dialogue_mode = self.settings.get("npc_dialogue_mode", "auto")

        # Round-robin for PCs (each sees previous responses)
        previous_responses = []

        for i, character in enumerate(pcs_to_respond):
            # Build context including previous PC responses this round
            context_parts = [text]

            if previous_responses:
                context_parts.append("\n\nOther party members have responded:")
                for prev_name, prev_resp in previous_responses[-3:]:
                    # Truncate long responses in context
                    short_resp = prev_resp[:150] + "..." if len(prev_resp) > 150 else prev_resp
                    context_parts.append(f"  {prev_name}: {short_resp}")
                context_parts.append("\nNow it's your turn.")

            full_context = "\n".join(context_parts)

            roll = None
            if character.player.requires_roll:
                roll = self._prompt_roll(character)

            response = character.player.respond(character, full_context, roll=roll)

            display_text, actions, trades, checks = self._prepare_response(character, response, roll)

            # Update table state with character's action
            action_summary = extract_action_from_response(display_text)
            self.table_state.update_character_state(character.name, action=action_summary)
            self.table_state.log_action(character.name, "response", action_summary)

            # Store for context
            previous_responses.append((character.name, display_text))

            # Print dialogue
            print(f"{character.name}: {display_text}")

            # Process checks/actions/trades
            results = self._execute_pending(character, actions, trades, checks, roll)
            for line in results:
                print(line)

            # Check for agent-to-agent conversation
            self._handle_conversation(character, response, roll)

            # Small visual separator between PCs
            if i < len(pcs_to_respond) - 1:
                print()

        # Then NPCs respond (if targeted)
        for character in npcs_to_respond:
            roll = None
            if character.player.requires_roll:
                roll = self._prompt_roll(character)

            if dialogue_mode == "manual":
                response = self._get_manual_dialogue(character, text, roll)
            else:
                response = character.player.respond(character, text, roll=roll)

            display_text, actions, trades, checks = self._prepare_response(character, response, roll)

            # Update table state
            action_summary = extract_action_from_response(display_text)
            self.table_state.update_character_state(character.name, action=action_summary)
            self.table_state.log_action(character.name, "response", action_summary)

            print(f"{character.name}: {display_text}")

            results = self._execute_pending(character, actions, trades, checks, roll)
            for line in results:
                print(line)

            self._handle_conversation(character, response, roll)

    def _get_manual_dialogue(self, character, context, roll=None):
        """
        Prompt GM for character dialogue in manual mode.
        Press Enter without input to auto-generate.

        Args:
            character: The character responding
            context: The narration/context they're responding to
            roll: Optional roll result

        Returns:
            str: The dialogue response
        """
        print(f"  [{character.name}'s response - Enter to auto-generate, or type dialogue]")
        gm_dialogue = input(f"  {character.name}: ").strip()

        if gm_dialogue == "":
            # Auto-generate using agent
            print("  (generating...)")
            response = character.player.respond(character, context, roll=roll)
            return response
        else:
            # Use GM's dialogue
            return gm_dialogue

    def _prepare_response(self, character, response, roll):
        """Parse response, strip tags, return (display_text, actions, trades, checks)."""
        actions = self._parse_actions(response)
        trades = self._parse_trades(response)
        checks = self._parse_checks(response)
        display_text = self._strip_action_tags(response)
        return display_text, actions, trades, checks

    def _execute_pending(self, character, actions, trades, checks, roll):
        """Execute pending actions, trades, and checks after dialogue is shown."""
        results = []
        results.extend(self._process_checks(character, checks))
        results.extend(self._process_actions(character, actions))
        results.extend(self._process_trades(character, trades, roll))
        return results

    def _parse_address_tag(self, response):
        """Parse [TO: name] tag from response. Returns name or None."""
        match = re.search(r'\[TO:\s*(.+?)\]', response)
        return match.group(1).strip() if match else None

    def _find_addressed_agent(self, speaker, response):
        """Find if response explicitly addresses another agent via [TO: name] tag."""
        target_name = self._parse_address_tag(response)
        if not target_name:
            return None

        target = self.get_character(target_name)
        if not target or target == speaker:
            return None
        if not isinstance(target.player, Agent):
            return None
        return target

    def _handle_conversation(self, speaker, last_response, last_roll):
        """Handle agent-to-agent conversation loop."""
        addressed = self._find_addressed_agent(speaker, last_response)
        if not addressed:
            return

        current_speaker = speaker
        current_response = last_response

        while addressed:
            # Prompt GM to continue, guide, or end
            gm_input = input(
                f"  [{current_speaker.name} addressed {addressed.name}. "
                f"(y)es/(n)o/or type guidance]: "
            ).strip()

            if gm_input.lower() in ("n", "no", "end"):
                break
            if gm_input == "":
                gm_input = "y"  # Default to continue

            # Build context for addressed character
            if gm_input.lower() in ("y", "yes"):
                context = f"{current_speaker.name} says: {self._strip_action_tags(current_response)}"
            else:
                # GM provided guidance
                context = (
                    f"{current_speaker.name} says: {self._strip_action_tags(current_response)}\n"
                    f"[GM: {gm_input}]"
                )

            # Get roll for addressed character if needed
            roll = None
            if addressed.player.requires_roll:
                roll = self._prompt_roll(addressed)

            # Get response from addressed character
            response = addressed.player.respond(addressed, context, roll=roll)
            display_text, actions, trades, checks = self._prepare_response(addressed, response, roll)

            # Print dialogue first
            print(f"{addressed.name}: {display_text}")

            # Then process checks/actions/trades
            results = self._execute_pending(addressed, actions, trades, checks, roll)
            for line in results:
                print(line)

            # Check if this character addresses another agent
            next_addressed = self._find_addressed_agent(addressed, response)

            current_speaker = addressed
            current_response = response
            addressed = next_addressed

    def _prompt_roll(self, character):
        """Prompt the GM for a dice roll for a character."""
        while True:
            result = input(f"  Roll {character.player.roll_prompt} for {character.name}: ")
            try:
                return int(result)
            except ValueError:
                print("  Enter a number.")

    def _manual_check(self, parts):
        """
        Manually trigger a skill check for a character.
        Usage: /check <character> <skill>
        """
        character, remaining = self.parse_character_from_parts(parts)
        if not character:
            return f"Character not found. Available: {', '.join(self.characters.keys())}"

        if not remaining:
            return "Usage: /check <character> <skill>"

        skill_name = " ".join(remaining)

        # Process the check using existing logic
        results = self._process_checks(character, [skill_name])
        return "\n".join(results) if results else f"{character.name} completed {skill_name} check."

    def _parse_actions(self, response):
        """Parse [USE: item_name] action tags from a response."""
        return re.findall(r'\[USE:\s*(.+?)\]', response)

    def _parse_checks(self, response):
        """Parse [CHECK: skill] or [CHECK: action] tags from a response."""
        return re.findall(r'\[CHECK:\s*(.+?)\]', response)

    def _process_actions(self, character, actions):
        """Prompt GM to confirm each action and execute if approved."""
        results = []
        for item_name in actions:
            confirm = input(f"  {character.name} wants to use {item_name}. Allow? (y/n): ")
            if confirm.strip().lower() in ("y", "yes"):
                result = InventoryCommands.use_item(character, item_name)
                results.append(f"  [{result}]")
            else:
                results.append(f"  [{character.name} was unable to use {item_name}.]")
        return results

    def _process_checks(self, character, checks):
        """Process skill/action checks requested by agent."""
        results = []
        skill_system = get_skill_check_system()
        db = SkillDatabase.get_instance()

        for check_name in checks:
            # Check if it's an action (has associated skills)
            action = db.get_action(check_name)
            if action:
                skills = action.get("skills", [])
                skill = prompt_skill_choice(check_name, skills, character)
                stat = db.get_stat_for_skill(skill) or "charisma"
                action_type = action.get("type", "check")
                base_dc = action.get("base_dc", 10)
            else:
                # Treat as direct skill check
                skill_data = db.get_skill(check_name)
                if skill_data:
                    skill = skill_data["name"]
                    stat = skill_data.get("stat", "charisma")
                else:
                    skill = check_name
                    stat = "charisma"
                action_type = "check"
                base_dc = 10

            print(f"\n  === {character.name}: {skill} Check ===")

            # Ask GM for difficulty
            dc_input = input(f"  Difficulty (default {base_dc}, or 'skip'): ").strip()
            if dc_input.lower() == "skip":
                results.append(f"  [{skill} check skipped.]")
                continue

            try:
                dc = int(dc_input) if dc_input else base_dc
            except ValueError:
                dc = base_dc

            # Make the check
            check_result = skill_system.make_skill_test(
                character, stat, skill,
                difficulty=dc,
                num_dice=2,
                return_result_object=True
            )

            print(check_result)

            if check_result.passed:
                results.append(f"  [{skill} check PASSED ({check_result.successes} successes vs DC {dc})]")
            else:
                results.append(f"  [{skill} check FAILED ({check_result.successes} successes vs DC {dc})]")

        return results

    def _parse_trades(self, response):
        """Parse [GIVE: qty item_name TO target_name] tags from a response."""
        return re.findall(r'\[GIVE:\s*(\d+)\s+(.+?)\s+TO\s+(.+?)\]', response)

    def _process_trades(self, character, trades, roll=None):
        """Prompt GM to confirm each trade with pricing and skill checks."""
        results = []
        skill_system = get_skill_check_system()

        for qty_str, item_name, target_name in trades:
            qty = int(qty_str)
            target = self.get_character(target_name)
            if not target:
                results.append(f"  [Trade failed: character '{target_name}' not found.]")
                continue

            label = f"{qty}x {item_name}" if qty > 1 else item_name

            # Calculate base price
            pricing = PricingSystem.calculate_price(
                item_name, qty, seller=character, buyer=target, roll=roll
            )

            if pricing and pricing["total"] > 0:
                buyer_caps = target.inventory.get_item("Bottle Caps")
                buyer_balance = buyer_caps.quantity if buyer_caps else 0
                print(f"  Base price for {label}: {pricing['total']} caps ({pricing['breakdown']})")
                print(f"  {target.name} has {buyer_balance} caps.")

                # Offer skill check option
                action = input(f"  (y)es/(n)o/(b)arter check: ").strip().lower()

                if action in ("b", "barter"):
                    # Get available skills for barter action
                    db = SkillDatabase.get_instance()
                    skills = db.get_skills_for_action("barter")
                    skill = prompt_skill_choice("barter", skills, target)

                    # Run opposed check
                    barter_result = skill_system.make_barter_check(target, character, skill)
                    barter_mod = barter_result["price_modifier"]

                    # Apply barter modifier to price
                    final_price = round(pricing["total"] * barter_mod)
                    print(f"  Final price: {final_price} caps")

                    confirm = input(f"  Confirm sale at {final_price} caps? (y/n): ").strip().lower()
                    if confirm in ("y", "yes"):
                        pricing["total"] = final_price
                        action = "y"
                    else:
                        action = "n"
                elif action == "y" or action == "yes":
                    action = "y"
                else:
                    action = "n"

                confirm = action
            else:
                confirm = input(
                    f"  {character.name} wants to give {label} to {target.name}. Allow? (y/n): "
                ).strip().lower()

            if confirm in ("y", "yes"):
                # Check source has the item
                source_item = character.inventory.get_item(item_name)
                if not source_item or source_item.quantity < qty:
                    has = source_item.quantity if source_item else 0
                    results.append(
                        f"  [Trade failed: {character.name} only has {has}x {item_name}.]"
                    )
                    continue

                # Check buyer has enough caps
                if pricing and pricing["total"] > 0:
                    buyer_caps = target.inventory.get_item("Bottle Caps")
                    buyer_balance = buyer_caps.quantity if buyer_caps else 0
                    if buyer_balance < pricing["total"]:
                        results.append(
                            f"  [Trade failed: {target.name} can't afford {pricing['total']} caps (has {buyer_balance}).]"
                        )
                        continue

                # Transfer items: remove from seller, add to buyer
                character.inventory.remove_item(item_name, qty)
                InventoryCommands.give_item(target, item_name, qty)

                # Transfer caps if priced
                if pricing and pricing["total"] > 0:
                    target.inventory.remove_item("Bottle Caps", pricing["total"])
                    InventoryCommands.give_item(character, "Bottle Caps", pricing["total"])
                    results.append(
                        f"  [{character.name} sold {label} to {target.name} for {pricing['total']} caps.]"
                    )
                else:
                    results.append(f"  [{character.name} gave {label} to {target.name}.]")
            else:
                results.append(f"  [Trade declined.]")
        return results

    def _strip_action_tags(self, response):
        """Remove action tags from response text."""
        text = re.sub(r'\s*\[USE:\s*.+?\]', '', response)
        text = re.sub(r'\s*\[GIVE:\s*.+?\]', '', text)
        text = re.sub(r'\s*\[TO:\s*.+?\]', '', text)
        text = re.sub(r'\s*\[CHECK:\s*.+?\]', '', text)
        return text.strip()

    # === CAMPAIGN/SCENE/COMBAT COMMAND HANDLERS ===

    def _handle_campaign_command(self, parts):
        """Handle /campaign subcommands."""
        if not parts:
            return self._show_campaign_status()

        action = parts[0].lower()

        if action == "new":
            name = " ".join(parts[1:]) if len(parts) > 1 else None
            return self._new_campaign(name)
        elif action == "save":
            return self._save_campaign()
        elif action == "load":
            if len(parts) < 2:
                return "Usage: /campaign load <filename>"
            return self._load_campaign(parts[1])
        elif action == "session":
            name = " ".join(parts[1:]) if len(parts) > 1 else None
            return self._new_game_session(name)
        elif action == "sync":
            return self._sync_characters_to_campaign()
        else:
            return """
/campaign                  - Show campaign status
/campaign new [name]       - Create new campaign (quick)
/campaign new wizard       - Interactive campaign setup
/campaign save             - Save campaign to file
/campaign load <file>      - Load campaign from file
/campaign session [name]   - Start new session in campaign
/campaign sync             - Register all loaded characters with campaign
"""

    def _show_campaign_status(self):
        """Show current campaign/session/scene status."""
        if not self.campaign:
            return "No active campaign. Use /campaign new to create one."

        lines = [f"\n=== Campaign: {self.campaign.name} ==="]

        # Separate PCs and NPCs
        pcs = [ref for ref in self.campaign.characters.values() if not ref.is_npc]
        npcs = [ref for ref in self.campaign.characters.values() if ref.is_npc]

        if pcs:
            lines.append(f"\nPlayer Characters ({len(pcs)}):")
            for ref in pcs:
                agent_str = f" ({ref.agent})" if ref.agent else ""
                lines.append(f"  - {ref.name}{agent_str}")

        if npcs:
            lines.append(f"\nNotable NPCs ({len(npcs)}):")
            for ref in npcs:
                lines.append(f"  - {ref.name}")

        lines.append(f"\nSessions: {len(self.campaign.sessions)}")

        session = self.campaign.current_session
        if session:
            lines.append(f"\n--- Session: {session.name} ---")
            lines.append(f"Active characters: {', '.join(session.active_characters) or 'none'}")

            scene = session.current_scene
            if scene:
                lines.append(f"\n--- Scene: {scene.name} ---")
                if scene.location:
                    lines.append(f"Location: {scene.location}")
                lines.append(f"Present: {', '.join(scene.present_characters) or 'none'}")
                if scene.in_combat:
                    r = scene.round
                    lines.append(f"\n[COMBAT] Round {r.number}, {r.current_character}'s turn")
                    lines.append(f"Initiative: {' > '.join(r.initiative_order)}")
            else:
                lines.append("\nNo active scene. Use /scene new to create one.")
        else:
            lines.append("\nNo active session. Use /campaign session to start one.")

        return "\n".join(lines)

    def _new_campaign(self, args=None):
        """Create a new campaign. Use 'wizard' for interactive setup."""
        if args and args.lower() == "wizard":
            return self._campaign_wizard()

        name = args if args else "Wasteland Campaign"
        self.campaign = Campaign(name=name)
        self.campaign.new_session("Session 1")
        return f"Created campaign: {name}\n(Use '/campaign new wizard' for interactive setup)"

    def _campaign_wizard(self):
        """Interactive wizard for creating a new campaign."""
        print("\n" + "=" * 50)
        print("       CAMPAIGN CREATION WIZARD")
        print("=" * 50)
        print("\nLet's set up your new campaign step by step.")
        print("Press Enter to skip any optional section.\n")

        # === CAMPAIGN NAME ===
        print("--- Campaign Name ---")
        name = input("Campaign name: ").strip()
        if not name:
            name = "Wasteland Campaign"
            print(f"  Using: {name}")

        self.campaign = Campaign(name=name)

        # === PLAYER CHARACTERS ===
        print("\n--- Player Characters ---")
        print("Add player characters with their AI agents.")
        print("Available agents: veteran_marcus, newbie_alex, optimizer_sam,")
        print("                  chaos_riley, method_jordan, casual_casey")
        print("Type 'done' when finished, or Enter to skip.\n")

        # List available character files
        chars_dir = Path(__file__).parent / "characters"
        available_chars = [f.stem for f in chars_dir.glob("*.yaml")] if chars_dir.exists() else []
        if available_chars:
            print(f"Available character files: {', '.join(available_chars[:10])}")
            if len(available_chars) > 10:
                print(f"  ...and {len(available_chars) - 10} more")
            print()

        pc_count = 0
        while True:
            pc_input = input(f"PC {pc_count + 1} (name or filename): ").strip()
            if not pc_input or pc_input.lower() == "done":
                break

            # Try to find character file
            char_file = None
            char_name = pc_input

            # Check if it's a filename
            test_path = chars_dir / f"{pc_input}.yaml"
            if test_path.exists():
                char_file = str(test_path)
                # Load to get actual name
                try:
                    char = Character.from_yaml(char_file)
                    char_name = char.name
                except Exception:
                    pass

            # Ask for agent
            agent_input = input(f"  Agent for {char_name} (or Enter for veteran_marcus): ").strip()
            agent = agent_input if agent_input else "veteran_marcus"

            # Register with campaign
            self.campaign.register_character(
                name=char_name,
                file_path=char_file,
                presence=CharacterPresence.ACTIVE,
                is_npc=False,
                agent=agent
            )
            print(f"  Added: {char_name} ({agent})")
            pc_count += 1

        # === NOTABLE NPCs ===
        print("\n--- Notable NPCs ---")
        print("Add important NPCs the party will interact with.")
        print("Type 'done' when finished, or Enter to skip.\n")

        npc_count = 0
        while True:
            npc_input = input(f"NPC {npc_count + 1} (name or filename): ").strip()
            if not npc_input or npc_input.lower() == "done":
                break

            # Try to find character file
            char_file = None
            char_name = npc_input

            test_path = chars_dir / f"{npc_input}.yaml"
            if test_path.exists():
                char_file = str(test_path)
                try:
                    char = Character.from_yaml(char_file)
                    char_name = char.name
                except Exception:
                    pass

            # Ask for notes
            notes = input(f"  Notes for {char_name} (optional): ").strip()

            # Register with campaign
            self.campaign.register_character(
                name=char_name,
                file_path=char_file,
                presence=CharacterPresence.KNOWN,
                is_npc=True,
                notes=notes
            )
            print(f"  Added: {char_name}")
            npc_count += 1

        # === STARTING LOCATION ===
        print("\n--- Starting Location ---")
        location_name = input("Starting location name (or Enter to skip): ").strip()
        location_desc = ""
        if location_name:
            location_desc = input("  Brief description: ").strip()
            self.campaign.locations[location_name] = {
                "description": location_desc,
                "known_dangers": ""
            }
            print(f"  Added location: {location_name}")

        # === FACTIONS ===
        print("\n--- Factions ---")
        print("Add major factions in your campaign.")
        print("Type 'done' when finished, or Enter to skip.\n")

        faction_count = 0
        while True:
            faction_name = input(f"Faction {faction_count + 1} name: ").strip()
            if not faction_name or faction_name.lower() == "done":
                break

            disposition = input(f"  Disposition (hostile/neutral/friendly): ").strip().lower()
            if disposition not in ("hostile", "neutral", "friendly"):
                disposition = "neutral"

            faction_notes = input(f"  Notes (optional): ").strip()

            self.campaign.factions[faction_name] = {
                "disposition": disposition,
                "notes": faction_notes
            }
            print(f"  Added: {faction_name} ({disposition})")
            faction_count += 1

        # === STARTING QUEST ===
        print("\n--- Starting Quest ---")
        quest_name = input("Main quest name (or Enter to skip): ").strip()
        if quest_name:
            quest_desc = input("  Description: ").strip()

            print("  Objectives (one per line, empty line to finish):")
            objectives = []
            while True:
                obj = input("    - ").strip()
                if not obj:
                    break
                objectives.append(obj)

            self.campaign.quests.append({
                "name": quest_name,
                "status": "active",
                "description": quest_desc,
                "objectives": objectives
            })
            print(f"  Added quest: {quest_name}")

        # === CAMPAIGN NOTES ===
        print("\n--- Campaign Notes ---")
        notes = input("Any additional notes (or Enter to skip): ").strip()
        if notes:
            self.campaign.notes = notes

        # === CREATE FIRST SESSION ===
        session_name = input("\nFirst session name (or Enter for 'Session 1'): ").strip()
        if not session_name:
            session_name = "Session 1"

        session = self.campaign.new_session(session_name)

        # Add all PCs to the session
        for ref in self.campaign.characters.values():
            if not ref.is_npc:
                session.add_to_session(ref.name)

        # Create starting scene if location was specified
        if location_name:
            scene = session.new_scene(
                name=f"Opening Scene",
                location=location_name,
                description=location_desc
            )
            # Add all session characters to scene
            for char_name in session.active_characters:
                scene.add_character(char_name)

        # === SUMMARY ===
        print("\n" + "=" * 50)
        print("       CAMPAIGN CREATED!")
        print("=" * 50)
        print(f"\nCampaign: {name}")

        pcs = [r for r in self.campaign.characters.values() if not r.is_npc]
        npcs = [r for r in self.campaign.characters.values() if r.is_npc]

        if pcs:
            print(f"\nPlayer Characters ({len(pcs)}):")
            for ref in pcs:
                print(f"  - {ref.name} ({ref.agent})")

        if npcs:
            print(f"\nNotable NPCs ({len(npcs)}):")
            for ref in npcs:
                print(f"  - {ref.name}")

        if self.campaign.locations:
            print(f"\nLocations: {', '.join(self.campaign.locations.keys())}")

        if self.campaign.factions:
            print(f"Factions: {', '.join(self.campaign.factions.keys())}")

        if self.campaign.quests:
            print(f"Quests: {', '.join(q['name'] for q in self.campaign.quests)}")

        # Ask to save
        print()
        save_choice = input("Save campaign to file? (y/n): ").strip().lower()
        if save_choice in ("y", "yes"):
            path = self.campaign.save()
            print(f"Saved to: {path}")

        return f"\nCampaign '{name}' is ready! Use /campaign to view status."

    def _save_campaign(self):
        """Save campaign to file."""
        if not self.campaign:
            return "No active campaign."
        path = self.campaign.save()
        return f"Campaign saved to {path}"

    def _load_campaign(self, filename):
        """Load campaign from file."""
        campaigns_dir = Path(__file__).parent / "campaigns"
        if not filename.endswith(".yaml"):
            filename = f"{filename}.yaml"
        filepath = campaigns_dir / filename
        if not filepath.exists():
            available = [f.stem for f in campaigns_dir.glob("*.yaml")] if campaigns_dir.exists() else []
            return f"File not found: {filename}\nAvailable: {', '.join(available) or 'none'}"

        self.campaign = Campaign.load(str(filepath))

        # Reload active characters
        session = self.campaign.current_session
        agents_dir = Path(__file__).parent / "agents"
        if session:
            for name in session.active_characters:
                ref = self.campaign.characters.get(name)
                if ref and ref.file_path:
                    char = Character.from_yaml(ref.file_path)

                    # Attach agent if specified in campaign (for PCs)
                    if ref.agent and not ref.is_npc:
                        agent_file = agents_dir / f"{ref.agent}.yaml"
                        if agent_file.exists():
                            try:
                                char.player = Agent.from_yaml(str(agent_file))
                            except Exception as e:
                                print(f"  Warning: Could not load agent {ref.agent}: {e}")

                    # For NPCs, load appropriate NPC agent
                    elif ref.is_npc:
                        # Default to npc_neutral for NPCs
                        agent_file = agents_dir / "npc_neutral.yaml"
                        if agent_file.exists():
                            try:
                                char.player = Agent.from_yaml(str(agent_file))
                            except Exception:
                                pass

                    self.characters[name] = char
                    self._name_lookup[name.lower()] = char
                    for alias in char.aliases:
                        self._name_lookup[alias.lower()] = char

        return f"Loaded campaign: {self.campaign.name}"

    def _new_game_session(self, name=None):
        """Start a new session within the campaign."""
        if not self.campaign:
            return "No active campaign. Use /campaign new first."
        session = self.campaign.new_session(name)
        return f"Started session: {session.name}"

    def _sync_characters_to_campaign(self):
        """Register all loaded characters with the campaign."""
        if not self.campaign:
            return "No active campaign."

        synced_pcs = []
        synced_npcs = []
        for name, char in self.characters.items():
            # Skip creatures
            if isinstance(char, CreatureInstance):
                continue

            # Check if already registered
            if name not in self.campaign.characters:
                # Determine file path if saved
                chars_dir = Path(__file__).parent / "characters"
                safe_name = name.lower().replace(" ", "_")
                filepath = chars_dir / f"{safe_name}.yaml"
                file_path = str(filepath) if filepath.exists() else None

                # Determine if NPC based on player agent's is_npc attribute
                is_npc = False
                agent_name = ""
                if isinstance(char.player, Agent):
                    is_npc = getattr(char.player, 'is_npc', False)
                    if not is_npc:
                        # It's a PC - get the agent name
                        agent_name = char.player.name if hasattr(char.player, 'name') else ""

                self.campaign.register_character(
                    name=name,
                    file_path=file_path,
                    presence=CharacterPresence.ACTIVE,
                    aliases=char.aliases,
                    affiliation=char.affiliation,
                    is_npc=is_npc,
                    agent=agent_name
                )

                if is_npc:
                    synced_npcs.append(name)
                else:
                    synced_pcs.append(name)

                # Also add to current session's active list
                if self.campaign.current_session:
                    self.campaign.current_session.add_to_session(name)

        if synced_pcs or synced_npcs:
            parts = []
            if synced_pcs:
                parts.append(f"{len(synced_pcs)} PC(s): {', '.join(synced_pcs)}")
            if synced_npcs:
                parts.append(f"{len(synced_npcs)} NPC(s): {', '.join(synced_npcs)}")
            return f"Synced {'; '.join(parts)}"
        return "All characters already registered with campaign."

    def _handle_scene_command(self, parts):
        """Handle /scene subcommands."""
        if not self.campaign:
            return "No active campaign. Use /campaign new first."

        session = self.campaign.current_session
        if not session:
            return "No active session. Use /campaign session first."

        if not parts:
            return self._show_scene_status()

        action = parts[0].lower()

        if action == "new":
            name = parts[1] if len(parts) > 1 else "New Scene"
            location = " ".join(parts[2:]) if len(parts) > 2 else ""
            return self._new_scene(name, location)
        elif action == "set":
            if len(parts) < 3:
                return "Usage: /scene set <property> <value>"
            return self._set_scene_property(parts[1], " ".join(parts[2:]))
        elif action == "list":
            return self._list_scenes()
        elif action == "goto":
            if len(parts) < 2:
                return "Usage: /scene goto <index>"
            try:
                idx = int(parts[1])
                return self._goto_scene(idx)
            except ValueError:
                return "Scene index must be a number."
        else:
            return """
/scene                     - Show current scene status
/scene new <name> [loc]    - Create new scene
/scene set location <loc>  - Set scene location
/scene set desc <text>     - Set scene description
/scene list                - List all scenes in session
/scene goto <index>        - Switch to scene by index
"""

    def _show_scene_status(self):
        """Show current scene details."""
        scene = self.current_scene
        if not scene:
            return "No active scene. Use /scene new to create one."

        lines = [f"\n=== Scene: {scene.name} ==="]
        if scene.location:
            lines.append(f"Location: {scene.location}")
        if scene.description:
            lines.append(f"Description: {scene.description}")
        lines.append(f"\nPresent characters ({len(scene.present_characters)}):")
        for name in scene.present_characters:
            char = self.characters.get(name)
            if char:
                player_info = char.player.name if isinstance(char.player, Agent) else char.player
                lines.append(f"  - {name} ({player_info})")
            else:
                lines.append(f"  - {name} (not loaded)")

        if scene.in_combat:
            r = scene.round
            lines.append(f"\n[COMBAT] Round {r.number}")
            lines.append(f"Current turn: {r.current_character}")
            turn = r.current_turn
            if turn:
                lines.append(f"Actions remaining: {turn.actions_remaining}")

        return "\n".join(lines)

    def _new_scene(self, name, location=""):
        """Create a new scene."""
        session = self.campaign.current_session
        scene = session.new_scene(name, location)

        # Add all active characters to scene by default
        for char_name in session.active_characters:
            scene.add_character(char_name)
            ref = self.campaign.characters.get(char_name)
            if ref:
                ref.presence = CharacterPresence.ACTIVE

        return f"Created scene: {name}" + (f" at {location}" if location else "")

    def _set_scene_property(self, prop, value):
        """Set a scene property."""
        scene = self.current_scene
        if not scene:
            return "No active scene."

        if prop == "location" or prop == "loc":
            scene.location = value
            return f"Scene location set to: {value}"
        elif prop == "description" or prop == "desc":
            scene.description = value
            return f"Scene description updated."
        elif prop == "name":
            scene.name = value
            return f"Scene renamed to: {value}"
        else:
            return f"Unknown property: {prop}. Use: location, description, name"

    def _list_scenes(self):
        """List all scenes in current session."""
        session = self.campaign.current_session
        if not session.scenes:
            return "No scenes in this session."

        lines = ["\n=== Scenes ==="]
        for i, scene in enumerate(session.scenes):
            current = " <-- current" if i == session.current_scene_index else ""
            lines.append(f"  {i}: {scene.name}" + (f" ({scene.location})" if scene.location else "") + current)
        return "\n".join(lines)

    def _goto_scene(self, index):
        """Switch to a different scene."""
        session = self.campaign.current_session
        if index < 0 or index >= len(session.scenes):
            return f"Invalid scene index. Valid: 0-{len(session.scenes) - 1}"

        session.current_scene_index = index
        scene = session.current_scene

        # Update character presence
        for name, ref in self.campaign.characters.items():
            if name in scene.present_characters:
                ref.presence = CharacterPresence.ACTIVE
            elif name in session.active_characters:
                ref.presence = CharacterPresence.NEARBY
            else:
                ref.presence = CharacterPresence.KNOWN

        return f"Switched to scene: {scene.name}"

    def _enter_character(self, char_name):
        """Add character to current scene."""
        scene = self.current_scene
        if not scene:
            return "No active scene."

        char = self.get_character(char_name)
        if not char:
            # Check if known to campaign
            ref = self.campaign.get_character_ref(char_name) if self.campaign else None
            if ref and ref.file_path:
                # Load the character
                char = Character.from_yaml(ref.file_path)
                self.characters[char.name] = char
                self._name_lookup[char.name.lower()] = char
                for alias in char.aliases:
                    self._name_lookup[alias.lower()] = char
            else:
                return f"Character '{char_name}' not found. Use /load to load from file."

        scene.add_character(char.name)
        if self.campaign:
            ref = self.campaign.characters.get(char.name)
            if ref:
                ref.presence = CharacterPresence.ACTIVE
            self.campaign.current_session.add_to_session(char.name)

        # Add to combat if in combat
        if scene.in_combat:
            scene.round.add_combatant(char.name)
            return f"{char.name} enters the scene and joins combat."

        return f"{char.name} enters the scene."

    def _exit_character(self, char_name):
        """Remove character from current scene."""
        scene = self.current_scene
        if not scene:
            return "No active scene."

        char = self.get_character(char_name)
        if not char:
            return f"Character '{char_name}' not found."

        if char.name not in scene.present_characters:
            return f"{char.name} is not in this scene."

        scene.remove_character(char.name)

        # Update presence to NEARBY (still in session)
        if self.campaign:
            ref = self.campaign.characters.get(char.name)
            if ref:
                ref.presence = CharacterPresence.NEARBY

        return f"{char.name} exits the scene."

    def _handle_combat_command(self, parts):
        """Handle /combat subcommands."""
        scene = self.current_scene
        if not scene:
            return "No active scene. Use /scene new first."

        if not parts:
            if scene.in_combat:
                return self._show_combat_status()
            return """
/combat start              - Begin combat
/combat end                - End combat
/combat add <character>    - Add combatant
/combat remove <character> - Remove combatant
/combat init <char> <val>  - Set initiative (for ordering)
"""

        action = parts[0].lower()

        if action == "start" or action == "begin":
            return self._start_combat()
        elif action == "end" or action == "stop":
            return self._end_combat()
        elif action == "add":
            if len(parts) < 2:
                return "Usage: /combat add <character>"
            return self._add_combatant(" ".join(parts[1:]))
        elif action == "remove" or action == "rm":
            if len(parts) < 2:
                return "Usage: /combat remove <character>"
            return self._remove_combatant(" ".join(parts[1:]))
        else:
            return f"Unknown combat action: {action}"

    def _show_combat_status(self):
        """Show combat status."""
        scene = self.current_scene
        if not scene or not scene.in_combat:
            return "Not in combat."

        r = scene.round
        lines = [f"\n=== Combat - Round {r.number} ==="]
        lines.append(f"Current turn: {r.current_character}")

        turn = r.current_turn
        if turn:
            lines.append(f"Actions remaining: {turn.actions_remaining}")

        lines.append("\nInitiative order:")
        for i, name in enumerate(r.initiative_order):
            marker = " <--" if i == r.current_turn_index else ""
            char = self.characters.get(name)
            if char:
                hp = f"HP {char.health['current']}/{char.health['max']}"
            else:
                hp = ""
            lines.append(f"  {i + 1}. {name} {hp}{marker}")

        return "\n".join(lines)

    def _start_combat(self):
        """Start combat in current scene."""
        scene = self.current_scene
        if scene.in_combat:
            return "Already in combat."

        if not scene.present_characters:
            return "No characters in scene to start combat."

        scene.start_combat()

        # Prompt for initiative order
        print("\n=== Combat Started ===")
        print("Current order (scene order):", ", ".join(scene.round.initiative_order))
        reorder = input("Enter new order (comma-separated names) or Enter to keep: ").strip()

        if reorder:
            names = [n.strip() for n in reorder.split(",")]
            # Validate names
            valid_names = []
            for name in names:
                char = self.get_character(name)
                if char and char.name in scene.present_characters:
                    valid_names.append(char.name)
            if valid_names:
                scene.round.initiative_order = valid_names
                scene.round.turns = {n: scene.round.turns.get(n, type(scene.round.turns.get(list(scene.round.turns.keys())[0]))(character_name=n)) for n in valid_names}

        return f"Combat begun! Round 1, {scene.round.current_character}'s turn."

    def _end_combat(self):
        """End combat."""
        scene = self.current_scene
        if not scene or not scene.in_combat:
            return "Not in combat."

        rounds = scene.round.number
        scene.end_combat()
        return f"Combat ended after {rounds} rounds."

    def _add_combatant(self, char_name):
        """Add character to combat."""
        scene = self.current_scene
        if not scene or not scene.in_combat:
            return "Not in combat. Use /combat start first."

        char = self.get_character(char_name)
        if not char:
            return f"Character '{char_name}' not found."

        if char.name not in scene.present_characters:
            scene.add_character(char.name)

        scene.round.add_combatant(char.name)
        return f"{char.name} joins combat."

    def _remove_combatant(self, char_name):
        """Remove character from combat."""
        scene = self.current_scene
        if not scene or not scene.in_combat:
            return "Not in combat."

        char = self.get_character(char_name)
        if not char:
            return f"Character '{char_name}' not found."

        scene.round.remove_combatant(char.name)
        return f"{char.name} removed from combat."

    def _handle_turn_command(self, parts):
        """Handle /turn or /next command."""
        scene = self.current_scene
        if not scene or not scene.in_combat:
            return "Not in combat."

        r = scene.round

        if not parts or parts[0].lower() == "next":
            # Advance to next turn
            next_char, new_round = r.next_turn()
            if new_round:
                return f"\n=== Round {r.number} ===\n{next_char}'s turn."
            return f"{next_char}'s turn."

        action = parts[0].lower()

        if action == "action" or action == "act":
            # Use an action
            turn = r.current_turn
            if not turn:
                return "No active turn."
            if turn.actions_remaining <= 0:
                return f"{turn.character_name} has no actions remaining."
            turn.use_action()
            return f"{turn.character_name} uses an action. {turn.actions_remaining} remaining."

        elif action == "minor":
            turn = r.current_turn
            if not turn:
                return "No active turn."
            turn.use_minor_action()
            return f"{turn.character_name} uses a minor action."

        elif action == "status":
            return self._show_combat_status()

        else:
            return """
/turn                      - Show current turn
/turn next (or /next)      - Advance to next turn
/turn action               - Use a major action
/turn minor                - Use a minor action
/turn status               - Show combat status
"""

    # === CREATURE COMMAND HANDLERS ===

    def _handle_spawn_command(self, parts):
        """Handle /spawn subcommands."""
        registry = CreatureRegistry.get_instance()

        if not parts:
            return """
/spawn <template> [count]  - Spawn creature(s) from template
/spawn list [category]     - List available templates
/spawn boss <template> <name> - Spawn unique boss
/spawn clear               - Remove all creatures
/spawn clear dead          - Remove only dead creatures
"""

        action = parts[0].lower()

        if action == "list":
            category = parts[1] if len(parts) > 1 else None
            return self._list_templates(category)

        elif action == "boss":
            if len(parts) < 3:
                return "Usage: /spawn boss <template> <boss_name>"
            template_name = parts[1]
            boss_name = " ".join(parts[2:])
            return self._spawn_boss(template_name, boss_name)

        elif action == "clear":
            if len(parts) > 1 and parts[1].lower() == "dead":
                removed = registry.clear_dead()
                if removed:
                    return f"Removed {len(removed)} dead creatures."
                return "No dead creatures to remove."
            else:
                count = len(registry.get_active_creatures())
                registry.clear_encounter()
                return f"Cleared {count} creatures from encounter."

        else:
            # /spawn <template> [count]
            template_name = parts[0]
            count = 1
            if len(parts) > 1:
                try:
                    count = int(parts[1])
                except ValueError:
                    return f"Invalid count: {parts[1]}"

            return self._spawn_creatures(template_name, count)

    def _list_templates(self, category=None):
        """List available creature templates."""
        registry = CreatureRegistry.get_instance()
        templates = registry.list_templates(category)

        if not templates:
            if category:
                return f"No templates found for category: {category}"
            return "No creature templates loaded. Check data/creatures.yaml"

        lines = ["\n=== Creature Templates ==="]

        # Group by category
        by_category = {}
        for t in templates:
            cat = t.category
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(t)

        for cat, cat_templates in sorted(by_category.items()):
            lines.append(f"\n{cat.upper()}:")
            for t in cat_templates:
                lines.append(f"  {t.name} (Lv{t.level_base}-{t.level_base + t.level_variance})")

        return "\n".join(lines)

    def _spawn_creatures(self, template_name, count):
        """Spawn creatures from template."""
        registry = CreatureRegistry.get_instance()

        # Check template exists
        template = registry.get_template(template_name)
        if not template:
            available = [t.name for t in registry.list_templates()]
            return f"Unknown template: {template_name}\nAvailable: {', '.join(available[:10])}"

        creatures = registry.spawn(template_name, count)

        if not creatures:
            return f"Failed to spawn creatures from template: {template_name}"

        # Add to scene if in campaign mode
        scene = self.current_scene
        for creature in creatures:
            self._add_creature_to_scene(creature)

        names = [c.name for c in creatures]
        msg = f"Spawned {len(creatures)} {template.name}(s): {', '.join(names)}"

        # Show HP for reference
        if creatures:
            hp = creatures[0].health
            msg += f"\n  HP: {hp['current']}/{hp['max']} each"

        return msg

    def _spawn_boss(self, template_name, boss_name):
        """Spawn a unique boss creature."""
        registry = CreatureRegistry.get_instance()

        creature = registry.spawn_boss(template_name, boss_name)
        if not creature:
            available = [t.name for t in registry.list_templates()]
            return f"Unknown template: {template_name}\nAvailable: {', '.join(available[:10])}"

        self._add_creature_to_scene(creature)

        return f"Spawned boss: {creature.name} (Lv{creature.level}, HP {creature.health['current']}/{creature.health['max']})"

    def _add_creature_to_scene(self, creature):
        """Add a creature to the current scene and combat if applicable."""
        # Add to characters dict for unified lookup
        self.characters[creature.name] = creature
        self._name_lookup[creature.name.lower()] = creature

        # Add to scene
        scene = self.current_scene
        if scene:
            scene.add_character(creature.name)

            # Add to combat if in combat
            if scene.in_combat:
                scene.round.add_combatant(creature.name)

    def _list_creatures(self):
        """List all active creatures in the encounter."""
        registry = CreatureRegistry.get_instance()
        creatures = registry.get_active_creatures()

        if not creatures:
            return "No active creatures in encounter."

        lines = ["\n=== Active Creatures ==="]

        # Group by template
        by_template = {}
        for c in creatures:
            t_name = c.template.name
            if t_name not in by_template:
                by_template[t_name] = []
            by_template[t_name].append(c)

        for t_name, t_creatures in sorted(by_template.items()):
            lines.append(f"\n{t_name}:")
            for c in t_creatures:
                status = "DEAD" if c.is_dead() else f"HP {c.health['current']}/{c.health['max']}"
                conds = f" [{', '.join(c.conditions)}]" if c.conditions else ""
                lines.append(f"  - {c.name} (Lv{c.level}) - {status}{conds}")

        total_alive = len([c for c in creatures if not c.is_dead()])
        total_dead = len(creatures) - total_alive
        lines.append(f"\nTotal: {len(creatures)} ({total_alive} alive, {total_dead} dead)")

        return "\n".join(lines)

    def _promote_creature(self, parts):
        """Promote a creature to a full Character."""
        registry = CreatureRegistry.get_instance()

        # Parse creature name (might be multi-word)
        creature_name = parts[0]
        new_name = None

        # Check if there's a new name specified
        if len(parts) > 1:
            # Try to find the creature first
            creature = registry.get_creature(creature_name)
            if creature:
                new_name = " ".join(parts[1:])
            else:
                # Maybe the creature name is multi-word
                for i in range(len(parts), 0, -1):
                    potential_name = " ".join(parts[:i])
                    creature = registry.get_creature(potential_name)
                    if creature:
                        creature_name = potential_name
                        if i < len(parts):
                            new_name = " ".join(parts[i:])
                        break
        else:
            creature = registry.get_creature(creature_name)

        if not creature:
            return f"Creature '{creature_name}' not found. Use /creatures to list active creatures."

        if creature.is_dead():
            return f"{creature.name} is dead and cannot be promoted. (Consider /loot instead)"

        # Create the Character
        character = creature.promote_to_character(new_name)

        # Remove from creature registry
        registry.remove_creature(creature.name)

        # Remove old creature from session tracking
        if creature.name in self.characters:
            del self.characters[creature.name]
        if creature.name.lower() in self._name_lookup:
            del self._name_lookup[creature.name.lower()]

        # Add as proper character
        self.add_character(character)

        # Save character to file
        chars_dir = Path(__file__).parent / "characters"
        chars_dir.mkdir(exist_ok=True)
        safe_name = character.name.lower().replace(" ", "_")
        filepath = chars_dir / f"{safe_name}.yaml"
        character.save_to_yaml(str(filepath))

        return f"Promoted {creature.name} to Character: {character.name}\nSaved to: {filepath}"

    def _loot_creature(self, parts):
        """Loot a dead creature."""
        registry = CreatureRegistry.get_instance()

        # Parse: <creature_name> [to <character>]
        creature_name = None
        target_char = None

        if "to" in parts:
            to_idx = parts.index("to")
            creature_name = " ".join(parts[:to_idx])
            target_name = " ".join(parts[to_idx + 1:])
            target_char = self.get_character(target_name)
            if not target_char:
                return f"Character '{target_name}' not found."
            if isinstance(target_char, CreatureInstance):
                return "Cannot give loot to a creature. Specify a Character."
        else:
            creature_name = " ".join(parts)

        creature = registry.get_creature(creature_name)
        if not creature:
            return f"Creature '{creature_name}' not found."

        if not creature.is_dead():
            return f"{creature.name} is not dead! (HP {creature.health['current']}/{creature.health['max']})"

        # Roll loot
        loot = creature.roll_loot()

        if not loot:
            # Remove dead creature
            registry.remove_creature(creature.name)
            if creature.name in self.characters:
                del self.characters[creature.name]
            if creature.name.lower() in self._name_lookup:
                del self._name_lookup[creature.name.lower()]
            return f"{creature.name} had no loot."

        lines = [f"\n=== Loot from {creature.name} ==="]
        for item_name, qty in loot:
            lines.append(f"  - {item_name} x{qty}")

        # Give to target if specified
        if target_char:
            lines.append(f"\nGiving to {target_char.name}:")
            for item_name, qty in loot:
                result = InventoryCommands.give_item(target_char, item_name, qty)
                lines.append(f"  {result}")

        # Remove dead creature
        registry.remove_creature(creature.name)
        if creature.name in self.characters:
            del self.characters[creature.name]
        if creature.name.lower() in self._name_lookup:
            del self._name_lookup[creature.name.lower()]

        # Remove from scene
        scene = self.current_scene
        if scene and creature.name in scene.present_characters:
            scene.remove_character(creature.name)

        lines.append(f"\n{creature.name} removed from encounter.")

        return "\n".join(lines)

    # === AGENT COMMAND HANDLERS ===

    def _list_agents(self):
        """List available NPC agents."""
        agents_dir = Path(__file__).parent / "agents"
        if not agents_dir.exists():
            return "No agents directory found."

        # Find all NPC agents (npc_*.yaml)
        npc_agents = sorted(agents_dir.glob("npc_*.yaml"))

        if not npc_agents:
            return "No NPC agents found."

        lines = ["\n=== Available NPC Agents ==="]
        lines.append("Use: /agent <creature/character> <agent_name>\n")

        for agent_file in npc_agents:
            agent_name = agent_file.stem
            try:
                agent = Agent.from_yaml(str(agent_file))
                lines.append(f"  {agent_name}: {agent.name}")
            except Exception:
                lines.append(f"  {agent_name}: (error loading)")

        lines.append("\nDisposition-based agents:")
        lines.append("  npc_hostile  - Aggressive, threatening behavior")
        lines.append("  npc_neutral  - Guarded, transactional behavior")
        lines.append("  npc_friendly - Helpful, cooperative behavior")

        return "\n".join(lines)

    def _change_agent(self, parts):
        """Change the agent for a character or creature."""
        if len(parts) < 2:
            return "Usage: /agent <creature/character> <agent_name>"

        # Parse target and agent name
        # Agent name is always last, target may be multi-word
        agent_name = parts[-1]
        target_name = " ".join(parts[:-1])

        # Find the target (creature or character)
        target = self.get_character(target_name)
        if not target:
            return f"Character/creature '{target_name}' not found."

        # Validate agent exists
        agents_dir = Path(__file__).parent / "agents"
        agent_file = agents_dir / f"{agent_name}.yaml"
        if not agent_file.exists():
            available = [f.stem for f in agents_dir.glob("npc_*.yaml")]
            return f"Agent not found: {agent_name}\nAvailable NPC agents: {', '.join(available)}"

        # Handle creature vs character differently
        if isinstance(target, CreatureInstance):
            if target.set_agent(agent_name):
                # Get agent display name
                try:
                    agent = Agent.from_yaml(str(agent_file))
                    agent_display = agent.name
                except Exception:
                    agent_display = agent_name
                return f"Changed {target.name}'s agent to: {agent_display}"
            else:
                return f"Failed to change agent for {target.name}."
        else:
            # Regular Character
            try:
                agent = Agent.from_yaml(str(agent_file))
                target.player = agent
                return f"Changed {target.name}'s agent to: {agent.name}"
            except Exception as e:
                return f"Error loading agent: {e}"

    # === TABLE STATE HANDLERS ===

    def _show_table_state(self):
        """Display current table state."""
        return self.table_state.get_table_display()

    def _set_spotlight(self, char_name):
        """Set the spotlight on a specific character."""
        char = self.get_character(char_name)
        if not char:
            return f"Character not found: {char_name}"

        self.table_state.set_spotlight(char.name)
        return f"Spotlight on {char.name}. Only they will respond to narration."

    def _set_character_state(self, char_name, action):
        """Set a character's current action/state."""
        char = self.get_character(char_name)
        if not char:
            return f"Character not found: {char_name}"

        self.table_state.update_character_state(char.name, action=action)
        return f"{char.name}: {action}"

    def _go_around_table(self, prompt_parts=None):
        """
        Initiate round-robin responses from all PCs.
        Optionally with a prompt/question for them to respond to.
        """
        # Get PCs in scene
        scene_chars = self.get_scene_characters()
        pcs = [c for c in scene_chars if isinstance(c.player, Agent) and not getattr(c.player, 'is_npc', False)]
        npcs = [c for c in scene_chars if isinstance(c.player, Agent) and getattr(c.player, 'is_npc', False)]

        if not pcs:
            return "No player characters in the scene."

        # Set up table state
        pc_names = [c.name for c in pcs]
        npc_names = [c.name for c in npcs]
        self.table_state.set_round_robin_order(pc_names, npc_names)

        # If there's a prompt, add it to the log
        prompt = " ".join(prompt_parts) if prompt_parts else None
        if prompt:
            self.table_state.log_action("GM", "question", prompt)
            print(f"\nGM asks: {prompt}\n")

        # Start round-robin
        self.table_state.start_round_robin()

        # Go around the table
        responses = []
        while self.table_state.round_robin_active:
            current_speaker = self.table_state.get_current_speaker()
            if not current_speaker:
                break

            char = self.get_character(current_speaker)
            if not char or not isinstance(char.player, Agent):
                self.table_state.advance_round_robin()
                continue

            # Build context with previous responses
            context = self.table_state.get_context_summary()
            if responses:
                context += "\n\nOther players have responded:"
                for name, resp in responses[-3:]:  # Last 3 responses
                    context += f"\n  {name}: {resp[:100]}..."

            # Get response
            print(f"{current_speaker}'s turn...")

            try:
                # Build prompt for agent
                agent_prompt = ""
                if prompt:
                    agent_prompt = f"The GM asks the group: {prompt}\n\n"
                if context:
                    agent_prompt += f"{context}\n\n"
                agent_prompt += "It's your turn to respond. What do you do or say?"

                response = char.player.respond(char, agent_prompt)

                # Update table state
                action_summary = extract_action_from_response(response)
                self.table_state.update_character_state(current_speaker, action=action_summary)
                self.table_state.log_action(current_speaker, "response", action_summary)

                responses.append((current_speaker, response))

                # Print response
                print(f"\n{current_speaker}: {response}\n")

            except Exception as e:
                print(f"  [{current_speaker} failed to respond: {e}]")

            # Move to next speaker
            next_speaker, round_complete = self.table_state.advance_round_robin()
            if round_complete:
                break

        self.table_state.end_round_robin()

        return f"\n--- Round complete. {len(responses)} characters responded. ---"

    def _initialize_table_state(self):
        """Initialize table state with current scene characters."""
        scene_chars = self.get_scene_characters()

        pcs = []
        npcs = []

        for char in scene_chars:
            if isinstance(char.player, Agent):
                if getattr(char.player, 'is_npc', False):
                    npcs.append(char.name)
                else:
                    pcs.append(char.name)

        self.table_state.set_round_robin_order(pcs, npcs)

    # === VOTING HANDLERS ===

    def _handle_vote_command(self, parts):
        """
        Handle /vote commands.

        Usage:
            /vote <question>          - Start interactive vote setup
            /vote split <question>    - Start split-party vote
            /vote status              - Show current vote status
            /vote resolve             - Resolve current vote
            /vote cancel              - Cancel current vote
        """
        if not parts:
            return self._show_vote_help()

        action = parts[0].lower()

        if action == "status":
            return self._show_vote_status()
        elif action == "resolve":
            return self._resolve_vote()
        elif action == "cancel":
            self.current_vote = None
            return "Vote cancelled."
        elif action == "split":
            # Split party vote
            question = " ".join(parts[1:]) if len(parts) > 1 else None
            return self._start_vote(question, mode="split")
        else:
            # Majority vote - entire args is the question
            question = " ".join(parts)
            return self._start_vote(question, mode="majority")

    def _show_vote_help(self):
        """Show vote command help."""
        return """
=== Party Voting ===

Start a vote:
  /vote <question>            - Majority vote (party acts together)
  /vote split <question>      - Split vote (party can divide)

Manage votes:
  /vote status                - Show current vote
  /vote resolve               - Resolve and apply results
  /vote cancel                - Cancel current vote

Examples:
  /vote Do we fight or negotiate?
  /vote split Who investigates where?
"""

    def _start_vote(self, question, mode="majority"):
        """Start an interactive vote."""
        if not question:
            return "Please provide a question: /vote <question>"

        print(f"\n{'=' * 50}")
        print(f"  STARTING {'SPLIT' if mode == 'split' else 'MAJORITY'} VOTE")
        print(f"  Question: {question}")
        print(f"{'=' * 50}")
        print("\nEnter options one per line. Empty line when done.")
        print("(Minimum 2 options required)\n")

        options = []
        while True:
            opt = input(f"  Option {len(options) + 1}: ").strip()
            if not opt:
                if len(options) >= 2:
                    break
                else:
                    print("  (Need at least 2 options)")
                    continue
            options.append(opt)

        if len(options) < 2:
            return "Vote cancelled - need at least 2 options."

        # Create the vote
        self.current_vote = PartyVote(question, options, mode=mode)

        # Display the vote
        print(self.current_vote.get_display())

        # Get votes from PCs
        return self._collect_votes()

    def _collect_votes(self):
        """Collect votes from all PCs."""
        if not self.current_vote:
            return "No active vote."

        scene_chars = self.get_scene_characters()
        pcs = [c for c in scene_chars if isinstance(c.player, Agent)
               and not getattr(c.player, 'is_npc', False)]

        if not pcs:
            return "No player characters to vote."

        print(f"\n--- Collecting votes from {len(pcs)} players ---\n")

        for char in pcs:
            # Generate vote prompt
            traits = getattr(char, 'personality_traits', [])
            prompt = generate_vote_prompt(self.current_vote, char.name, traits)

            try:
                # Get agent's vote
                response = char.player.respond(char, prompt, roll=None)

                # Parse the vote
                vote_num = parse_vote_response(response, len(self.current_vote.options))

                if vote_num:
                    self.current_vote.cast_vote(char.name, vote_num)
                    opt = self.current_vote.options[vote_num]
                    print(f"  {char.name} votes [{vote_num}] {opt.description}")
                    # Show their reasoning (truncated)
                    reason = response.split('-', 1)[-1].strip() if '-' in response else response
                    if reason and len(reason) < 100:
                        print(f"    \"{reason}\"")
                else:
                    print(f"  {char.name}: Could not parse vote from response")

            except Exception as e:
                print(f"  {char.name}: Error getting vote - {e}")

        # Show results
        print(self.current_vote.get_display(show_votes=True))

        if self.current_vote.mode == "split":
            return "\nUse /vote resolve to split the party, or /vote cancel to abort."
        else:
            return "\nUse /vote resolve to apply the decision, or /vote cancel to abort."

    def _show_vote_status(self):
        """Show current vote status."""
        if not self.current_vote:
            return "No active vote. Use /vote <question> to start one."

        return self.current_vote.get_display(show_votes=True)

    def _resolve_vote(self):
        """Resolve the current vote and apply results."""
        if not self.current_vote:
            return "No active vote to resolve."

        result = self.current_vote.resolve()

        # Display results
        print(self.current_vote.get_result_display())

        if self.current_vote.mode == "majority":
            # Log to table state
            self.table_state.log_action(
                "Party",
                "decision",
                f"Decided: {result['description']}"
            )
            self.current_vote = None
            return f"\nThe party has decided: {result['description']}"

        else:  # split mode
            # Create parallel scenes
            return self._create_parallel_scenes(result['groups'])

    def _create_parallel_scenes(self, groups):
        """Create parallel scenes for a split party."""
        if not self.campaign:
            self.current_vote = None
            return "Cannot split party without an active campaign. Groups noted but no scenes created."

        session = self.campaign.current_session
        if not session:
            self.current_vote = None
            return "No active session. Groups noted but no scenes created."

        current_scene = session.current_scene
        base_location = current_scene.location if current_scene else "Unknown"

        # Clear parallel scenes
        self.parallel_scenes = []

        print(f"\n--- Creating parallel scenes ---\n")

        for group_num, group_data in groups.items():
            # Ask for scene details
            print(f"Group {group_num}: {group_data['description']}")
            print(f"  Members: {', '.join(group_data['members'])}")

            scene_name = input(f"  Scene name [{group_data['description'][:30]}]: ").strip()
            if not scene_name:
                scene_name = group_data['description'][:30]

            scene_location = input(f"  Location [{base_location}]: ").strip()
            if not scene_location:
                scene_location = base_location

            scene_desc = input(f"  Brief description: ").strip()

            # Create the scene
            scene = session.new_scene(
                name=scene_name,
                location=scene_location,
                description=scene_desc
            )

            # Add group members to scene
            for member_name in group_data['members']:
                scene.add_character(member_name)

            # Track as parallel scene
            self.parallel_scenes.append({
                "scene_index": len(session.scenes) - 1,
                "group_num": group_num,
                "description": group_data['description'],
                "members": group_data['members'],
                "completed": False
            })

            print(f"  Created scene: {scene_name}\n")

        # Set first parallel scene as current
        if self.parallel_scenes:
            session.current_scene_index = self.parallel_scenes[0]["scene_index"]

        self.current_vote = None

        # Log the split
        self.table_state.log_action(
            "Party",
            "split",
            f"Split into {len(self.parallel_scenes)} groups"
        )

        return self._show_parallel_status()

    def _handle_parallel_command(self, parts):
        """
        Handle /parallel commands for managing split party scenes.

        Usage:
            /parallel              - Show parallel scene status
            /parallel next         - Switch to next parallel scene
            /parallel <number>     - Switch to specific scene
            /parallel rejoin       - Rejoin all groups
        """
        if not parts:
            return self._show_parallel_status()

        action = parts[0].lower()

        if action == "next":
            return self._next_parallel_scene()
        elif action == "rejoin":
            return self._rejoin_party()
        elif action.isdigit():
            return self._switch_parallel_scene(int(action))
        else:
            return """
/parallel              - Show status of parallel scenes
/parallel next         - Switch to next group's scene
/parallel <number>     - Switch to specific scene (1, 2, etc.)
/parallel rejoin       - Rejoin all groups into one scene
"""

    def _show_parallel_status(self):
        """Show status of parallel scenes."""
        if not self.parallel_scenes:
            return "No parallel scenes active. Use /vote split to divide the party."

        session = self.campaign.current_session if self.campaign else None
        current_idx = session.current_scene_index if session else -1

        lines = ["\n" + "=" * 50]
        lines.append("  PARALLEL SCENES (Happening Simultaneously)")
        lines.append("=" * 50)

        for i, ps in enumerate(self.parallel_scenes, 1):
            current = " <-- CURRENT" if ps["scene_index"] == current_idx else ""
            status = "[DONE]" if ps["completed"] else "[ACTIVE]"
            lines.append(f"\n  [{i}] {ps['description']} {status}{current}")
            lines.append(f"      Members: {', '.join(ps['members'])}")

        lines.append("\n" + "=" * 50)
        lines.append("  Use /parallel next or /parallel <number> to switch")
        lines.append("  Use /parallel rejoin when both groups are ready")
        lines.append("=" * 50)

        return "\n".join(lines)

    def _next_parallel_scene(self):
        """Switch to the next parallel scene."""
        if not self.parallel_scenes:
            return "No parallel scenes active."

        session = self.campaign.current_session if self.campaign else None
        if not session:
            return "No active session."

        current_idx = session.current_scene_index

        # Find current parallel scene
        current_ps_idx = None
        for i, ps in enumerate(self.parallel_scenes):
            if ps["scene_index"] == current_idx:
                current_ps_idx = i
                break

        # Move to next
        if current_ps_idx is not None:
            next_idx = (current_ps_idx + 1) % len(self.parallel_scenes)
        else:
            next_idx = 0

        next_ps = self.parallel_scenes[next_idx]
        session.current_scene_index = next_ps["scene_index"]

        # Update table state for new scene
        self._initialize_table_state()

        return f"\n--- Switching to: {next_ps['description']} ---\n" + \
               f"Members: {', '.join(next_ps['members'])}\n"

    def _switch_parallel_scene(self, scene_num):
        """Switch to a specific parallel scene by number."""
        if not self.parallel_scenes:
            return "No parallel scenes active."

        if scene_num < 1 or scene_num > len(self.parallel_scenes):
            return f"Invalid scene number. Use 1-{len(self.parallel_scenes)}."

        session = self.campaign.current_session if self.campaign else None
        if not session:
            return "No active session."

        ps = self.parallel_scenes[scene_num - 1]
        session.current_scene_index = ps["scene_index"]

        # Update table state for new scene
        self._initialize_table_state()

        return f"\n--- Switching to: {ps['description']} ---\n" + \
               f"Members: {', '.join(ps['members'])}\n"

    def _rejoin_party(self):
        """Rejoin all parallel groups into a single scene."""
        if not self.parallel_scenes:
            return "No parallel scenes to rejoin."

        session = self.campaign.current_session if self.campaign else None
        if not session:
            return "No active session."

        # Gather all members
        all_members = []
        for ps in self.parallel_scenes:
            all_members.extend(ps['members'])

        # Create a rejoined scene
        print("\n--- Rejoining the party ---\n")

        scene_name = input("Rejoin scene name [Regrouped]: ").strip() or "Regrouped"
        scene_location = input("Location: ").strip() or "Unknown"
        scene_desc = input("Description: ").strip()

        scene = session.new_scene(
            name=scene_name,
            location=scene_location,
            description=scene_desc
        )

        # Add all members
        for member in all_members:
            scene.add_character(member)

        # Clear parallel scenes
        self.parallel_scenes = []

        # Update table state
        self._initialize_table_state()

        # Log the rejoin
        self.table_state.log_action(
            "Party",
            "rejoin",
            f"Party regrouped at {scene_location}"
        )

        return f"\nThe party has regrouped. All {len(all_members)} members present."

    # === FACTION COMMAND HANDLERS ===

    def _list_factions(self):
        """List all factions and their relations."""
        from models.faction_relations import FactionRelations, FactionRelation

        relations = FactionRelations.get_instance()
        factions = relations.get_all_factions()

        if not factions:
            return "No factions defined. Create data/faction_relations.yaml to define faction relations."

        lines = ["\n=== Factions ===\n"]

        for faction in factions:
            allies = relations.get_allies(faction)
            enemies = relations.get_enemies(faction)
            friendly = relations.get_factions_by_relation(faction, FactionRelation.FRIENDLY)
            unfriendly = relations.get_factions_by_relation(faction, FactionRelation.UNFRIENDLY)

            lines.append(f"**{faction}**")
            if allies:
                lines.append(f"  Allied: {', '.join(allies)}")
            if friendly:
                lines.append(f"  Friendly: {', '.join(friendly)}")
            if unfriendly:
                lines.append(f"  Unfriendly: {', '.join(unfriendly)}")
            if enemies:
                lines.append(f"  Hostile: {', '.join(enemies)}")
            lines.append("")

        return "\n".join(lines)

    def _handle_faction_command(self, parts):
        """Handle /faction command variants."""
        from models.faction_relations import FactionRelations, FactionRelation

        if not parts:
            return "Usage: /faction <name> OR /faction relation <A> <B> [relation]"

        # Check for 'relation' subcommand
        if parts[0].lower() == "relation":
            if len(parts) < 3:
                return "Usage: /faction relation <faction_a> <faction_b> [relation]"
            return self._handle_faction_relation(parts[1:])

        # Show faction details
        faction_name = " ".join(parts)
        return self._show_faction(faction_name)

    def _show_faction(self, faction_name):
        """Show details about a specific faction."""
        from models.faction_relations import FactionRelations, FactionRelation

        relations = FactionRelations.get_instance()
        factions = relations.get_all_factions()

        # Find matching faction (case-insensitive)
        matched = None
        for f in factions:
            if f.lower() == faction_name.lower():
                matched = f
                break

        if not matched:
            # Show available factions
            return f"Unknown faction: {faction_name}\nKnown factions: {', '.join(factions)}"

        lines = [f"\n=== {matched} ===\n"]

        # Relations
        allies = relations.get_allies(matched)
        enemies = relations.get_enemies(matched)
        friendly = relations.get_factions_by_relation(matched, FactionRelation.FRIENDLY)
        unfriendly = relations.get_factions_by_relation(matched, FactionRelation.UNFRIENDLY)

        lines.append("Relations:")
        if allies:
            lines.append(f"  Allied (+2): {', '.join(allies)}")
        if friendly:
            lines.append(f"  Friendly (+1): {', '.join(friendly)}")
        if unfriendly:
            lines.append(f"  Unfriendly (-1): {', '.join(unfriendly)}")
        if enemies:
            lines.append(f"  Hostile (-2): {', '.join(enemies)}")

        # Find members (characters with this affiliation)
        members = []
        for char in self.characters.values():
            affiliations = getattr(char, 'affiliations', [getattr(char, 'affiliation', '')])
            if matched in affiliations or matched.lower() in [a.lower() for a in affiliations]:
                members.append(char.name)

        if members:
            lines.append(f"\nMembers in session: {', '.join(members)}")

        return "\n".join(lines)

    def _handle_faction_relation(self, parts):
        """View or set relation between two factions."""
        from models.faction_relations import FactionRelations, FactionRelation

        relations = FactionRelations.get_instance()

        # Parse faction names - could be multi-word
        # Try to find where faction_b starts
        faction_a = parts[0]
        remaining = parts[1:]

        # Check if last part is a relation type
        relation_types = ['allied', 'friendly', 'neutral', 'unfriendly', 'hostile']
        new_relation = None

        if remaining and remaining[-1].lower() in relation_types:
            new_relation_str = remaining[-1].lower()
            remaining = remaining[:-1]
            new_relation = FactionRelation(new_relation_str)

        if not remaining:
            return "Usage: /faction relation <faction_a> <faction_b> [relation]"

        faction_b = " ".join(remaining)

        # If setting new relation
        if new_relation:
            relations.set_relation(faction_a, faction_b, new_relation)
            return f"Set relation: {faction_a} <-> {faction_b}: {new_relation.value}"

        # Just viewing
        current = relations.get_relation(faction_a, faction_b)
        modifier = relations.get_relation_modifier(faction_a, faction_b)
        sign = "+" if modifier > 0 else ""

        return f"{faction_a} <-> {faction_b}: {current.value} ({sign}{modifier})"

    def _add_ally(self, parts):
        """Add target to character's allies list."""
        character, remaining = self.parse_character_from_parts(parts)
        if not character:
            return f"Character not found. Available: {', '.join(self.characters.keys())}"

        if not remaining:
            return "Usage: /ally <character> <target>"

        target_name = " ".join(remaining)

        if character.add_ally(target_name):
            return f"Added {target_name} to {character.name}'s allies."
        else:
            return f"{target_name} is already an ally of {character.name}."

    def _add_enemy(self, parts):
        """Add target to character's enemies list."""
        character, remaining = self.parse_character_from_parts(parts)
        if not character:
            return f"Character not found. Available: {', '.join(self.characters.keys())}"

        if not remaining:
            return "Usage: /enemy <character> <target>"

        target_name = " ".join(remaining)

        if character.add_enemy(target_name):
            return f"Added {target_name} to {character.name}'s enemies."
        else:
            return f"{target_name} is already an enemy of {character.name}."

    def _clear_screen(self):
        """Clear the terminal screen."""
        os.system('cls' if os.name == 'nt' else 'clear')

    def _get_help_sections(self):
        """Return help organized into navigable sections."""
        return {
            "1": ("Narration & Basics", """
  (type text)               - Narrate to all characters
  @<character> (text)       - Narrate to a specific character
  @<char1> @<char2> (text)  - Narrate to multiple characters
  /quit                     - Exit the game
  /characters               - List all active characters
  /info <character>         - Show detailed character information"""),

            "2": ("Character Creation", """
  /create                   - Show creation help
  /create random [name]     - Generate random character
  /create input             - Interactive character creation
  /create <description>     - AI generates from description
  /create npc random        - Generate random NPC
  /create npc <description> - AI generates NPC from description
  /load <file> [agent]      - Load character from YAML, optionally assign agent"""),

            "3": ("Inventory & Items", """
  /inventory <character>    - Show character's inventory
  /inv <character>          - Short form of /inventory
  /give <character> <item> [qty] - Give item to character
  /take <character> <item> [qty] - Take item from character
  /use <character> <item>   - Use item on self
  /use <char> <item> on <target> - Use item on another character
  /use <char> <item> on <target> <part> - Use on body part
  /weight <character>       - Show carry weight info
  /items                    - List all available items"""),

            "4": ("Combat & Checks", """
  /bodyparts <character>    - Show body parts status
  /damage <char> <part> <amt> - Damage a specific body part
  /check <character> <skill> - Manually trigger a skill check
  /combat start             - Begin combat in current scene
  /combat end               - End combat
  /combat add <char>        - Add combatant
  /combat remove <char>     - Remove combatant
  /next                     - Advance to next turn
  /turn action              - Use a major action
  /turn minor               - Use a minor action"""),

            "5": ("Campaign & Scenes", """
  /campaign                 - Show campaign/session/scene status
  /campaign new [name]      - Create new campaign (quick)
  /campaign new wizard      - Interactive campaign setup wizard
  /campaign save            - Save campaign to file
  /campaign load <file>     - Load campaign from file
  /campaign session [name]  - Start new session in campaign
  /scene                    - Show current scene status
  /scene new <name> [loc]   - Create new scene
  /scene set location <loc> - Set scene location
  /enter <character>        - Bring character into scene
  /exit <character>         - Remove character from scene"""),

            "6": ("Creatures & NPCs", """
  /spawn <template> [count] - Spawn creature(s) from template
  /spawn list [category]    - List available templates
  /spawn boss <template> <name> - Spawn unique boss creature
  /spawn clear              - Remove all creatures
  /spawn clear dead         - Remove only dead creatures
  /creatures                - List all active creatures
  /promote <creature> [name]- Convert creature to full Character
  /loot <creature>          - Show loot from dead creature
  /loot <creature> to <char>- Give loot to character
  /agent                    - List available NPC agents
  /agent <target> <agent>   - Change creature/character agent"""),

            "7": ("Table & Spotlight", """
  /table                    - Show current table state
  /spotlight <character>    - Give spotlight to character (only they respond)
  /spotlight                - Clear spotlight (return to group)
  /state <char> <action>    - Set what a character is currently doing
  /around [question]        - Go around table, each PC responds in turn"""),

            "8": ("Voting & Split Party", """
  /vote <question>          - Start majority vote (party acts together)
  /vote split <question>    - Start split vote (party can divide)
  /vote status              - Show current vote
  /vote resolve             - Apply vote results
  /vote cancel              - Cancel current vote
  /parallel                 - Show parallel scene status
  /parallel next            - Switch to next group's scene
  /parallel <number>        - Switch to specific scene
  /parallel rejoin          - Rejoin all groups into one scene"""),

            "9": ("Factions & Relations", """
  /factions                 - List all factions and their relations
  /faction <name>           - Show faction details (allies, enemies, members)
  /faction relation <A> <B> - View relation between factions
  /faction relation <A> <B> <type> - Set relation type
                              (allied/friendly/neutral/unfriendly/hostile)
  /ally <char> <target>     - Add target to character's allies
  /enemy <char> <target>    - Add target to character's enemies"""),
        }

    def _show_help_interactive(self):
        """Display interactive help menu with navigation."""
        sections = self._get_help_sections()
        current_view = "menu"  # "menu" or section number

        while True:
            self._clear_screen()

            if current_view == "menu":
                print("=" * 50)
                print("                    HELP MENU")
                print("=" * 50)
                print()
                for key, (title, _) in sections.items():
                    print(f"  [{key}] {title}")
                print()
                print("-" * 50)
                print("  [a] Show all commands")
                print("  [q] Return to game")
                print("-" * 50)
                choice = input("\nSelect section: ").strip().lower()

                if choice == 'q' or choice == 'quit' or choice == 'exit':
                    self._clear_screen()
                    return
                elif choice == 'a' or choice == 'all':
                    current_view = "all"
                elif choice in sections:
                    current_view = choice
            elif current_view == "all":
                print("=" * 50)
                print("               ALL COMMANDS")
                print("=" * 50)
                for key, (title, content) in sections.items():
                    print(f"\n--- {title} ---")
                    print(content)
                print()
                print("-" * 50)
                print("  [b] Back to menu    [q] Return to game")
                print("-" * 50)
                choice = input("\nSelect: ").strip().lower()

                if choice == 'q' or choice == 'quit' or choice == 'exit':
                    self._clear_screen()
                    return
                elif choice == 'b' or choice == 'back' or choice == 'menu':
                    current_view = "menu"
            else:
                # Showing a specific section
                title, content = sections[current_view]
                print("=" * 50)
                print(f"  {title.upper()}")
                print("=" * 50)
                print(content)
                print()
                print("-" * 50)
                print("  [b] Back to menu    [q] Return to game")

                # Show prev/next navigation
                keys = list(sections.keys())
                idx = keys.index(current_view)
                nav = []
                if idx > 0:
                    nav.append(f"[p] Prev: {sections[keys[idx-1]][0]}")
                if idx < len(keys) - 1:
                    nav.append(f"[n] Next: {sections[keys[idx+1]][0]}")
                if nav:
                    print("  " + "    ".join(nav))

                print("-" * 50)
                choice = input("\nSelect: ").strip().lower()

                if choice == 'q' or choice == 'quit' or choice == 'exit':
                    self._clear_screen()
                    return
                elif choice == 'b' or choice == 'back' or choice == 'menu':
                    current_view = "menu"
                elif choice == 'p' or choice == 'prev':
                    if idx > 0:
                        current_view = keys[idx - 1]
                elif choice == 'n' or choice == 'next':
                    if idx < len(keys) - 1:
                        current_view = keys[idx + 1]
                elif choice in sections:
                    current_view = choice

    def get_help_text(self):
        """Get help text for available commands (legacy method)."""
        sections = self._get_help_sections()
        lines = ["=== Available Commands ==="]
        for title, content in sections.values():
            lines.append(f"\n{title.upper()}:")
            lines.append(content)
        return "\n".join(lines)
