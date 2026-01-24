"""
Inventory management commands.
"""

from data.item_database import ItemDatabase


class InventoryCommands:
    """
    Command handlers for inventory operations.

    Commands:
    - /inventory [character_name] - Show inventory
    - /give [character_name] [item_name] [quantity] - Add item
    - /take [character_name] [item_name] [quantity] - Remove item
    - /use [character_name] [item_name] - Use item
    - /weight [character_name] - Show carry weight
    """

    @staticmethod
    def show_inventory(character):
        """
        Display character's inventory.

        Args:
            character: Character instance

        Returns:
            str: Formatted inventory display
        """
        if not character.inventory.items:
            return f"{character.name}'s inventory is empty."

        lines = [f"\n=== {character.name}'s Inventory ==="]
        lines.append(f"Carry Weight: {character.inventory.total_weight:.1f}/{character.inventory.max_capacity} lbs")

        if character.inventory.is_overencumbered:
            lines.append("[OVERENCUMBERED - Movement penalties apply]")

        lines.append("\nItems:")

        items_list = character.inventory.list_items()
        for item_info in sorted(items_list, key=lambda x: x['type']):
            name = item_info['name']
            qty = item_info['quantity']
            weight = item_info['weight'] * qty
            value = item_info['value'] * qty
            item_type = item_info['type']

            if qty > 1:
                lines.append(f"  [{item_type}] {name} x{qty} ({weight:.1f} lbs, {value} caps)")
            else:
                lines.append(f"  [{item_type}] {name} ({weight:.1f} lbs, {value} caps)")

        return "\n".join(lines)

    @staticmethod
    def give_item(character, item_name, quantity=1):
        """
        Add item to character's inventory.

        Args:
            character: Character instance
            item_name: Name of item
            quantity: Quantity to add

        Returns:
            str: Result message
        """
        item_db = ItemDatabase.get_instance()

        # Get item from database
        item = item_db.create_item(item_name, quantity)
        if not item:
            return f"Error: Item '{item_name}' not found in database."

        # Try to add to inventory
        result = character.inventory.add_item(item, quantity)

        if result['success']:
            return f"Added {result['added']}x {item_name} to {character.name}'s inventory."
        else:
            return f"Failed to add {item_name}: {result['message']}"

    @staticmethod
    def take_item(character, item_name, quantity=1):
        """
        Remove item from character's inventory.

        Args:
            character: Character instance
            item_name: Name of item
            quantity: Quantity to remove

        Returns:
            str: Result message
        """
        result = character.inventory.remove_item(item_name, quantity)

        if result['success']:
            return f"Removed {result['removed']}x {item_name} from {character.name}'s inventory."
        else:
            return f"Failed to remove {item_name}: {result['message']}"

    @staticmethod
    def use_item(character, item_name, target_character=None, body_part=None):
        """
        Use/consume an item.

        Args:
            character: Character instance (who is using the item)
            item_name: Name of item to use
            target_character: Optional target character (defaults to user)
            body_part: Optional body part name to target

        Returns:
            str: Result message
        """
        # Default to using on self
        if target_character is None:
            target_character = character

        # Get the item from user's inventory
        item = character.inventory.get_item(item_name)
        if not item:
            return f"{character.name} doesn't have {item_name}."

        if not item.consumable:
            return f"{item_name} is not consumable."

        # Apply effects to target
        from systems.stat_system import StatSystem
        effects_msg = StatSystem.apply_item_effect(target_character, item, body_part)

        # Remove one from user's inventory
        result = character.inventory.remove_item(item_name, 1)

        if result['success']:
            target_str = ""
            if character.name == target_character.name:
                if body_part:
                    target_str = f"on their {body_part}"
                else:
                    target_str = ""
            else:
                if body_part:
                    target_str = f"on {target_character.name}'s {body_part}"
                else:
                    target_str = f"on {target_character.name}"

            if target_str:
                return f"{character.name} used {item_name} {target_str}. {effects_msg}"
            else:
                return f"{character.name} used {item_name}. {effects_msg}"
        else:
            return f"Error using {item_name}: {result['message']}"

    @staticmethod
    def show_weight(character):
        """
        Display weight information.

        Args:
            character: Character instance

        Returns:
            str: Weight information
        """
        total = character.inventory.total_weight
        maximum = character.inventory.max_capacity
        available = character.inventory.available_capacity
        percentage = (total / maximum * 100) if maximum > 0 else 0

        lines = [f"\n=== {character.name}'s Carry Weight ==="]
        lines.append(f"Current: {total:.1f} lbs")
        lines.append(f"Maximum: {maximum} lbs")
        lines.append(f"Available: {available:.1f} lbs")
        lines.append(f"Usage: {percentage:.1f}%")

        if character.inventory.is_overencumbered:
            lines.append("\n[WARNING] OVERENCUMBERED!")
            lines.append("You are carrying too much weight.")
            lines.append("Drop some items to restore normal movement.")

        return "\n".join(lines)

    @staticmethod
    def list_available_items():
        """
        List all items available in the database.

        Returns:
            str: Formatted list of available items
        """
        item_db = ItemDatabase.get_instance()
        types = item_db.get_all_item_types()

        lines = ["\n=== Available Items ==="]

        for item_type in types:
            items = item_db.list_items_by_type(item_type)
            lines.append(f"\n{item_type.upper()}:")
            for item_name in sorted(items):
                item_data = item_db.get_item_data(item_name)
                lines.append(f"  - {item_name} ({item_data['weight']} lbs, {item_data['value']} caps)")

        return "\n".join(lines)
