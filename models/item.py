"""
Item class for representing game items.
"""


class Item:
    """
    Represents an item in the game world.

    Attributes:
        name: Item name
        item_type: Category (weapon, consumable, armor, medical, chem, misc)
        weight: Weight in pounds
        value: Base value in caps
        quantity: Current quantity (default 1)
        max_stack: Maximum stack size (None for unstackable)
        consumable: Whether item is consumed on use
        effects: Dict of stat effects when used/equipped
        description: Item description
    """

    def __init__(self, name, item_type, weight, value, quantity=1, max_stack=None,
                 consumable=False, effects=None, description=""):
        self.name = name
        self.item_type = item_type
        self.weight = weight
        self.value = value
        self.quantity = quantity
        self.max_stack = max_stack
        self.consumable = consumable
        self.effects = effects or {}
        self.description = description

    @property
    def total_weight(self):
        """Calculate total weight for stacked items."""
        return self.weight * self.quantity

    @property
    def total_value(self):
        """Calculate total value for stacked items."""
        return self.value * self.quantity

    def can_stack_with(self, other_item):
        """
        Check if this item can stack with another.

        Args:
            other_item: Another Item instance

        Returns:
            bool: True if items can stack
        """
        if not isinstance(other_item, Item):
            return False

        # Items can stack if they have the same name and are stackable
        return (self.name == other_item.name and
                self.max_stack is not None and
                other_item.max_stack is not None)

    def add_quantity(self, amount):
        """
        Add to item quantity.

        Args:
            amount: Quantity to add

        Returns:
            int: Amount actually added (may be limited by max_stack)
        """
        if self.max_stack is None:
            return 0

        available_space = self.max_stack - self.quantity
        amount_to_add = min(amount, available_space)
        self.quantity += amount_to_add
        return amount_to_add

    def remove_quantity(self, amount):
        """
        Remove from item quantity.

        Args:
            amount: Quantity to remove

        Returns:
            int: Amount actually removed
        """
        amount_to_remove = min(amount, self.quantity)
        self.quantity -= amount_to_remove
        return amount_to_remove

    def to_dict(self):
        """Serialize to JSON-compatible dict."""
        return {
            'name': self.name,
            'item_type': self.item_type,
            'weight': self.weight,
            'value': self.value,
            'quantity': self.quantity,
            'max_stack': self.max_stack,
            'consumable': self.consumable,
            'effects': self.effects,
            'description': self.description
        }

    @classmethod
    def from_dict(cls, data):
        """
        Deserialize from dict.

        Args:
            data: Dictionary containing item data

        Returns:
            Item: New Item instance
        """
        return cls(
            name=data['name'],
            item_type=data['item_type'],
            weight=data['weight'],
            value=data['value'],
            quantity=data.get('quantity', 1),
            max_stack=data.get('max_stack'),
            consumable=data.get('consumable', False),
            effects=data.get('effects', {}),
            description=data.get('description', '')
        )

    def __repr__(self):
        if self.quantity > 1:
            return f"Item('{self.name}' x{self.quantity})"
        return f"Item('{self.name}')"

    def __str__(self):
        if self.quantity > 1:
            return f"{self.name} x{self.quantity}"
        return self.name
