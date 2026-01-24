"""
Inventory class for managing character inventory.
"""

from .item import Item


class Inventory:
    """
    Manages character inventory with weight and capacity constraints.

    Attributes:
        items: List of Item objects
        owner: Reference to owning Character
    """

    def __init__(self, owner, items=None):
        """
        Initialize inventory.

        Args:
            owner: Reference to the Character that owns this inventory
            items: Optional list of Item objects
        """
        self.owner = owner
        self.items = items or []

    @property
    def total_weight(self):
        """Calculate total carried weight."""
        return sum(item.total_weight for item in self.items)

    @property
    def max_capacity(self):
        """
        Calculate max capacity from Strength.
        Formula: Strength * 25 + 150
        """
        if self.owner is None:
            return 200  # Default capacity

        strength = self.owner.get_effective_stat("strength")
        return strength * 25 + 150

    @property
    def is_overencumbered(self):
        """Check if carrying too much weight."""
        return self.total_weight > self.max_capacity

    @property
    def available_capacity(self):
        """Get available carry weight."""
        return max(0, self.max_capacity - self.total_weight)

    def add_item(self, item, quantity=None):
        """
        Add item to inventory, handle stacking.

        Args:
            item: Item instance or item name
            quantity: Optional quantity override

        Returns:
            dict: Result with 'success', 'added', 'remaining', 'message'
        """
        if not isinstance(item, Item):
            raise TypeError("item must be an Item instance")

        # Override quantity if specified
        if quantity is not None:
            item.quantity = quantity

        # Check weight capacity
        new_weight = item.total_weight
        if self.total_weight + new_weight > self.max_capacity:
            return {
                'success': False,
                'added': 0,
                'remaining': item.quantity,
                'message': f"Cannot add {item.name}: would exceed carry capacity"
            }

        # Try to stack with existing items
        if item.max_stack is not None:
            for existing_item in self.items:
                if existing_item.can_stack_with(item):
                    # Stack as much as possible
                    added = existing_item.add_quantity(item.quantity)
                    remaining = item.quantity - added

                    if remaining > 0:
                        # Still have items left, create new stack
                        new_item = Item(
                            name=item.name,
                            item_type=item.item_type,
                            weight=item.weight,
                            value=item.value,
                            quantity=remaining,
                            max_stack=item.max_stack,
                            consumable=item.consumable,
                            effects=item.effects,
                            description=item.description
                        )
                        self.items.append(new_item)

                    return {
                        'success': True,
                        'added': item.quantity,
                        'remaining': 0,
                        'message': f"Added {item.quantity}x {item.name}"
                    }

        # No existing stack found, add as new item
        self.items.append(item)
        return {
            'success': True,
            'added': item.quantity,
            'remaining': 0,
            'message': f"Added {item.quantity}x {item.name}"
        }

    def remove_item(self, item_name, quantity=1):
        """
        Remove item from inventory.

        Args:
            item_name: Name of item to remove
            quantity: Quantity to remove

        Returns:
            dict: Result with 'success', 'removed', 'message'
        """
        remaining_to_remove = quantity

        # Remove from stacks until we've removed enough
        items_to_delete = []
        for i, item in enumerate(self.items):
            if item.name.lower() == item_name.lower() and remaining_to_remove > 0:
                removed = item.remove_quantity(remaining_to_remove)
                remaining_to_remove -= removed

                # Mark empty stacks for deletion
                if item.quantity == 0:
                    items_to_delete.append(i)

        # Remove empty stacks
        for i in reversed(items_to_delete):
            del self.items[i]

        removed_count = quantity - remaining_to_remove

        if removed_count > 0:
            return {
                'success': True,
                'removed': removed_count,
                'message': f"Removed {removed_count}x {item_name}"
            }
        else:
            return {
                'success': False,
                'removed': 0,
                'message': f"Item not found: {item_name}"
            }

    def get_item(self, item_name):
        """
        Find item by name.

        Args:
            item_name: Name of item to find

        Returns:
            Item: First matching item, or None
        """
        for item in self.items:
            if item.name.lower() == item_name.lower():
                return item
        return None

    def has_item(self, item_name, quantity=1):
        """
        Check if inventory contains item in sufficient quantity.

        Args:
            item_name: Name of item
            quantity: Required quantity

        Returns:
            bool: True if item exists in sufficient quantity
        """
        total_quantity = 0
        for item in self.items:
            if item.name.lower() == item_name.lower():
                total_quantity += item.quantity

        return total_quantity >= quantity

    def get_item_quantity(self, item_name):
        """
        Get total quantity of an item.

        Args:
            item_name: Name of item

        Returns:
            int: Total quantity across all stacks
        """
        total = 0
        for item in self.items:
            if item.name.lower() == item_name.lower():
                total += item.quantity
        return total

    def list_items(self):
        """
        Get list of all items with quantities.

        Returns:
            list: List of dicts with item info
        """
        items_dict = {}

        # Consolidate quantities across stacks
        for item in self.items:
            if item.name in items_dict:
                items_dict[item.name]['quantity'] += item.quantity
            else:
                items_dict[item.name] = {
                    'name': item.name,
                    'type': item.item_type,
                    'quantity': item.quantity,
                    'weight': item.weight,
                    'value': item.value
                }

        return list(items_dict.values())

    def to_dict(self):
        """Serialize to JSON-compatible dict."""
        return {
            'items': [item.to_dict() for item in self.items]
        }

    @classmethod
    def from_dict(cls, data, owner):
        """
        Deserialize from dict.

        Args:
            data: Dictionary containing inventory data
            owner: Character that owns this inventory

        Returns:
            Inventory: New Inventory instance
        """
        items = []

        if isinstance(data, dict) and 'items' in data:
            # New format: dict with 'items' list
            for item_data in data['items']:
                items.append(Item.from_dict(item_data))
        elif isinstance(data, list):
            # Old format: list of item names like ["Stimpak x3", "10mm Pistol"]
            # This will be converted to proper Item objects later
            # For now, return empty inventory (will be handled in Character class)
            pass

        inventory = cls(owner=owner, items=items)
        return inventory

    def __repr__(self):
        return f"Inventory({len(self.items)} items, {self.total_weight:.1f}/{self.max_capacity} lbs)"

    def __str__(self):
        if not self.items:
            return "Empty inventory"

        lines = [f"Inventory ({self.total_weight:.1f}/{self.max_capacity} lbs):"]
        items_list = self.list_items()

        for item_info in items_list:
            if item_info['quantity'] > 1:
                lines.append(f"  - {item_info['name']} x{item_info['quantity']} ({item_info['weight'] * item_info['quantity']:.1f} lbs)")
            else:
                lines.append(f"  - {item_info['name']} ({item_info['weight']:.1f} lbs)")

        if self.is_overencumbered:
            lines.append("  [OVERENCUMBERED]")

        return "\n".join(lines)
