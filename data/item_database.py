"""
Item database manager for loading and creating items.
"""

import json
import os
from models.item import Item


class ItemDatabase:
    """
    Singleton database manager for game items.
    """

    _instance = None

    def __init__(self, database_path=None):
        """
        Initialize item database.

        Args:
            database_path: Path to items.json file
        """
        if database_path is None:
            # Default to data/items.json relative to this file
            current_dir = os.path.dirname(os.path.abspath(__file__))
            database_path = os.path.join(current_dir, 'items.json')

        self.database_path = database_path
        self.items = self._load_items()

    @classmethod
    def get_instance(cls, database_path=None):
        """
        Get singleton instance of ItemDatabase.

        Args:
            database_path: Optional path to database file

        Returns:
            ItemDatabase: Singleton instance
        """
        if cls._instance is None:
            cls._instance = cls(database_path)
        return cls._instance

    def _load_items(self):
        """
        Load items from JSON database.

        Returns:
            dict: Dictionary of item data
        """
        try:
            with open(self.database_path, 'r') as f:
                data = json.load(f)
                return data.get('items', {})
        except FileNotFoundError:
            print(f"Warning: Item database not found at {self.database_path}")
            return {}
        except json.JSONDecodeError as e:
            print(f"Error loading item database: {e}")
            return {}

    def get_item_data(self, item_name):
        """
        Get item data by name.

        Args:
            item_name: Name of item

        Returns:
            dict: Item data, or None if not found
        """
        # Case-insensitive lookup
        for name, data in self.items.items():
            if name.lower() == item_name.lower():
                return data.copy()
        return None

    def create_item(self, item_name, quantity=1):
        """
        Create Item instance from database.

        Args:
            item_name: Name of item to create
            quantity: Quantity to create

        Returns:
            Item: New Item instance, or None if item not found
        """
        item_data = self.get_item_data(item_name)
        if item_data is None:
            return None

        # Add name and quantity to data
        item_data['name'] = item_name
        item_data['quantity'] = quantity

        return Item.from_dict(item_data)

    def item_exists(self, item_name):
        """
        Check if item exists in database.

        Args:
            item_name: Name of item

        Returns:
            bool: True if item exists
        """
        return self.get_item_data(item_name) is not None

    def list_items_by_type(self, item_type=None):
        """
        List all items, optionally filtered by type.

        Args:
            item_type: Optional type to filter by

        Returns:
            list: List of item names
        """
        if item_type is None:
            return list(self.items.keys())

        filtered = []
        for name, data in self.items.items():
            if data.get('item_type') == item_type:
                filtered.append(name)

        return filtered

    def get_all_item_types(self):
        """
        Get list of all unique item types.

        Returns:
            list: List of item types
        """
        types = set()
        for data in self.items.values():
            types.add(data.get('item_type', 'misc'))
        return sorted(list(types))

    def search_items(self, search_term):
        """
        Search for items by name or description.

        Args:
            search_term: Term to search for

        Returns:
            list: List of matching item names
        """
        search_term = search_term.lower()
        matches = []

        for name, data in self.items.items():
            if (search_term in name.lower() or
                search_term in data.get('description', '').lower()):
                matches.append(name)

        return matches

    def __repr__(self):
        return f"ItemDatabase({len(self.items)} items)"

    def __str__(self):
        lines = [f"Item Database ({len(self.items)} items):"]
        types = self.get_all_item_types()

        for item_type in types:
            items = self.list_items_by_type(item_type)
            lines.append(f"  {item_type}: {len(items)} items")

        return "\n".join(lines)
