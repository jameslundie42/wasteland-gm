from commands.inventory_commands import InventoryCommands
from agent import Agent


class Session:
    def __init__(self):
        self.characters = {}

    def add_character(self, character):
        """Add a character to the session."""
        self.characters[character.name] = character

    def get_character(self, char_name):
        """
        Get character by name (case-insensitive).

        Args:
            char_name: Name of character

        Returns:
            Character instance or None
        """
        for name, character in self.characters.items():
            if name.lower() == char_name.lower():
                return character
        return None

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
            lines = ["\n=== Active Characters ==="]
            for character in self.characters.values():
                lines.append(f"  - {character.name} (Level {character.level}, {character.health['current']}/{character.health['max']} HP, Player: {character.player})")
            return "\n".join(lines)

        # Character info
        elif command == "info":
            if len(parts) < 2:
                return "Usage: /info <character_name>"
            char_name = " ".join(parts[1:])
            character = self.get_character(char_name)
            if not character:
                return f"Character '{char_name}' not found."
            character.print_info()
            return ""

        # Help command
        elif command == "help":
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

    def gm_narrate(self, narration):
        """GM narrates to all characters and collects their responses."""
        print(f"\nNarrator: {narration}\n")
        responses = {}

        for char_name, character in self.characters.items():
            if isinstance(character.player, Agent):
                response = character.player.respond(character, narration)
                responses[char_name] = response

        return responses

    def get_help_text(self):
        """Get help text for available commands."""
        return """
=== Available Commands ===

GAME MANAGEMENT:
  /quit                     - Exit the game
  /help                     - Show this help message
  /characters               - List all active characters
  /info <character>         - Show detailed character information

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

Examples:
  /inventory Doc Rivera
  /give Doc Rivera Stimpak 5
  /use Doc Rivera Stimpak
  /use Doc Rivera Stimpak on Marcus
  /use Doc Rivera Doctor's Bag on Marcus left arm
  /bodyparts Doc Rivera
  /damage Doc Rivera left leg 50
"""
