import re
from pathlib import Path
from commands.inventory_commands import InventoryCommands
from agent import Agent
from character import Character
from systems.pricing import PricingSystem
from systems.skill_checks import get_skill_check_system, SkillDatabase, prompt_skill_choice
from systems.character_generator import create_character_interactive
from models.game_state import Campaign, CharacterPresence, CharacterRef
from models.creature import CreatureRegistry, CreatureInstance


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
            self.campaign.register_character(
                name=character.name,
                presence=CharacterPresence.ACTIVE,
                aliases=character.aliases,
                affiliation=character.affiliation
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

        # Help command
        elif command == "help" or command == "h":
            return self.get_help_text()

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
        GM narrates and collects agent responses.
        Prints dialogue directly, then prompts for actions/trades.

        Supports @CharName targeting:
          @Doc Rivera You hear footsteps behind you.
          @Doc Rivera @Marcus A grenade lands between you.

        Without @ prefix, broadcasts to characters in current scene
        (or all characters if not using campaign mode).

        Behavior depends on npc_dialogue_mode setting (NPCs only):
          - "auto": NPC agents automatically generate dialogue
          - "manual": GM writes NPC dialogue, press Enter to auto-generate

        Player characters (is_npc=False) always use auto-generation.
        """
        targets, text = self._parse_mentions(narration)

        if targets:
            print(f"\nNarrator (to {', '.join(c.name for c in targets)}): {text}\n")
        else:
            scene = self.current_scene
            if scene:
                print(f"\nNarrator [{scene.name}]: {text}\n")
            else:
                print(f"\nNarrator: {text}\n")

        is_broadcast = not targets
        # Use scene characters if in campaign mode, otherwise all characters
        characters_to_address = targets if targets else self.get_scene_characters()

        # Check dialogue mode setting
        dialogue_mode = self.settings.get("npc_dialogue_mode", "auto")

        for character in characters_to_address:
            if isinstance(character, str):
                continue
            if isinstance(character.player, Agent):
                # Skip NPC agents on broadcasts (they only respond when targeted)
                if is_broadcast and character.player.is_npc:
                    continue

                roll = None
                if character.player.requires_roll:
                    roll = self._prompt_roll(character)

                # Handle dialogue based on mode
                # Manual mode only applies to NPCs (GM-controlled characters)
                # Player characters always use auto-generation
                is_npc = character.player.is_npc if hasattr(character.player, 'is_npc') else False

                if dialogue_mode == "manual" and is_npc:
                    response = self._get_manual_dialogue(character, text, roll)
                else:
                    # Auto mode or player character - agent generates response
                    response = character.player.respond(character, text, roll=roll)

                display_text, actions, trades, checks = self._prepare_response(character, response, roll)

                # Print dialogue first
                print(f"{character.name}: {display_text}")

                # Then process checks/actions/trades
                results = self._execute_pending(character, actions, trades, checks, roll)
                for line in results:
                    print(line)

                # Check for agent-to-agent conversation
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
/campaign new [name]       - Create new campaign
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
        lines.append(f"Characters known: {len(self.campaign.characters)}")
        lines.append(f"Sessions: {len(self.campaign.sessions)}")

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

    def _new_campaign(self, name=None):
        """Create a new campaign."""
        if not name:
            name = "Wasteland Campaign"
        self.campaign = Campaign(name=name)
        self.campaign.new_session("Session 1")
        return f"Created campaign: {name}"

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
        if session:
            for name in session.active_characters:
                ref = self.campaign.characters.get(name)
                if ref and ref.file_path:
                    char = Character.from_yaml(ref.file_path)
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

        synced = []
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

                self.campaign.register_character(
                    name=name,
                    file_path=file_path,
                    presence=CharacterPresence.ACTIVE,
                    aliases=char.aliases,
                    affiliation=char.affiliation
                )
                synced.append(name)

                # Also add to current session's active list
                if self.campaign.current_session:
                    self.campaign.current_session.add_to_session(name)

        if synced:
            return f"Synced {len(synced)} character(s) to campaign: {', '.join(synced)}"
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

    def get_help_text(self):
        """Get help text for available commands."""
        return """
=== Available Commands ===

NARRATION:
  (type text)               - Narrate to all characters
  @<character> (text)       - Narrate to a specific character
  @<char1> @<char2> (text)  - Narrate to multiple characters

GAME MANAGEMENT:
  /quit                     - Exit the game
  /help                     - Show this help message
  /characters               - List all active characters
  /info <character>         - Show detailed character information

CHARACTER CREATION:
  /create                   - Show creation help
  /create random [name]     - Generate random character
  /create input             - Interactive character creation
  /create <description>     - AI generates from description
  /create npc random        - Generate random NPC
  /create npc <description> - AI generates NPC from description
  /load <file> [agent]      - Load character from YAML, optionally assign agent

INVENTORY:
  /inventory <character>    - Show character's inventory
  /inv <character>          - Short form of /inventory
  /give <character> <item> [qty] - Give item to character
  /take <character> <item> [qty] - Take item from character
  /use <character> <item>   - Use item on self
  /use <character> <item> on <target> - Use item on another character
  /use <character> <item> on <target> <part> - Use item on target's body part
  /weight <character>       - Show carry weight info
  /items                    - List all available items

BODY PARTS:
  /bodyparts <character>    - Show body parts status
  /limbs <character>        - Alias for /bodyparts
  /damage <character> <part> <amt> - Damage a specific body part

CAMPAIGN (for context management):
  /campaign                 - Show campaign/session/scene status
  /campaign new [name]      - Create new campaign
  /campaign save            - Save campaign to file
  /campaign load <file>     - Load campaign from file
  /campaign session [name]  - Start new session in campaign
  /campaign sync            - Register loaded characters with campaign

SCENE:
  /scene                    - Show current scene status
  /scene new <name> [loc]   - Create new scene
  /scene set location <loc> - Set scene location
  /scene list               - List all scenes in session
  /enter <character>        - Bring character into scene
  /exit <character>         - Remove character from scene

COMBAT:
  /combat start             - Begin combat in current scene
  /combat end               - End combat
  /combat add <char>        - Add combatant
  /combat remove <char>     - Remove combatant
  /next                     - Advance to next turn
  /turn action              - Use a major action
  /turn minor               - Use a minor action

CREATURES:
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
  /agent <target> <agent>   - Change creature/character agent

Examples:
  /campaign new Wasteland Adventures
  /scene new Dusty Crossroads Outside Megaton
  /enter Jack
  /combat start
  /spawn Raider 3
  /damage "Raider #1" torso 15
  /loot "Raider #1" to Jack
  /promote "Raider #2" Scarface
  /next
"""
