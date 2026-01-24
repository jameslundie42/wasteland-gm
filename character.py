import json
from models.special_stats import SPECIALStats
from models.inventory import Inventory
from models.stat_modifier import StatModifier
from models.body_parts import BodyParts
from data.item_database import ItemDatabase


class Character:
    """
    Character class with full stat tracking and inventory management.

    Attributes:
        name: Character name
        player: "GM" for human-controlled NPCs, or an Agent instance for AI-controlled characters
        special: SPECIALStats object
        skills: List of skill names
        background: Character background text
        personality_traits: List of personality traits
        inventory: Inventory object
        level: Character level
        experience: Current XP
        health: Dict with current and max health
        radiation: Current radiation level (0-1000)
        conditions: List of active conditions
        body_parts: BodyParts object for tracking limb damage
    """

    def __init__(self, name, special, skills, background, personality_traits,
                 inventory=None, level=1, experience=0, health=None,
                 radiation=0, conditions=None, body_parts=None, player="GM"):
        self.name = name
        self.player = player

        # Handle both dict and SPECIALStats object for backward compatibility
        if isinstance(special, dict):
            self.special = SPECIALStats(special)
        else:
            self.special = special

        self.skills = skills or []
        self.background = background
        self.personality_traits = personality_traits or []

        # Initialize inventory
        if inventory is None:
            self.inventory = Inventory(owner=self)
        elif isinstance(inventory, list):
            # Convert old list format to Inventory object
            self.inventory = self._convert_legacy_inventory(inventory)
            self.inventory.owner = self
        elif isinstance(inventory, Inventory):
            self.inventory = inventory
            self.inventory.owner = self
        elif isinstance(inventory, dict):
            self.inventory = Inventory.from_dict(inventory, owner=self)
        else:
            self.inventory = Inventory(owner=self)

        self.level = level
        self.experience = experience

        # Calculate max health from Endurance
        # Formula: Luck + Endurance + (Level - 1)
        max_health = (self.get_base_stat("endurance") + self.get_base_stat("luck")) + \
                    ((self.level - 1))

        if health is None:
            self.health = {"current": max_health, "max": max_health}
        elif isinstance(health, dict):
            self.health = health
            # Ensure max health is set
            if "max" not in self.health:
                self.health["max"] = max_health
        else:
            self.health = {"current": max_health, "max": max_health}

        self.radiation = radiation
        self.conditions = conditions or []

        # Initialize body parts
        if body_parts is None:
            self.body_parts = BodyParts()  # Default humanoid
        elif isinstance(body_parts, BodyParts):
            self.body_parts = body_parts
        elif isinstance(body_parts, dict):
            self.body_parts = BodyParts.from_dict(body_parts)
        else:
            self.body_parts = BodyParts()

    def get_effective_stat(self, stat_name):
        """
        Get effective value of a SPECIAL stat.

        Args:
            stat_name: Name of the stat

        Returns:
            int: Effective stat value with modifiers applied
        """
        return self.special.get_effective_stat(stat_name)

    def get_base_stat(self, stat_name):
        """
        Get base value of a SPECIAL stat.

        Args:
            stat_name: Name of the stat

        Returns:
            int: Base stat value without modifiers
        """
        return self.special.get_base_stat(stat_name)

    def add_stat_modifier(self, modifier):
        """
        Add a temporary stat modifier.

        Args:
            modifier: StatModifier instance

        Returns:
            bool: True if modifier was added
        """
        return self.special.add_modifier(modifier)

    def remove_stat_modifier(self, source, stat_name=None):
        """
        Remove stat modifiers by source.

        Args:
            source: Source of the modifier
            stat_name: Optional stat name to filter by

        Returns:
            int: Number of modifiers removed
        """
        return self.special.remove_modifier(source, stat_name)

    def update_modifiers(self):
        """
        Remove expired modifiers.

        Returns:
            list: List of expired modifiers that were removed
        """
        return self.special.update_modifiers()

    def take_damage(self, damage):
        """
        Apply damage to character.

        Args:
            damage: Amount of damage to take

        Returns:
            dict: Result with 'damage_taken', 'current_health', 'is_dead'
        """
        damage = max(0, int(damage))
        self.health["current"] -= damage
        is_dead = self.health["current"] <= 0

        if is_dead:
            self.health["current"] = 0

        return {
            'damage_taken': damage,
            'current_health': self.health["current"],
            'max_health': self.health["max"],
            'is_dead': is_dead
        }

    def heal(self, amount):
        """
        Heal character.

        Args:
            amount: Amount of HP to restore

        Returns:
            dict: Result with 'healed', 'current_health'
        """
        amount = max(0, int(amount))
        old_health = self.health["current"]
        self.health["current"] = min(self.health["current"] + amount,
                                     self.health["max"])
        actual_healed = self.health["current"] - old_health

        return {
            'healed': actual_healed,
            'current_health': self.health["current"],
            'max_health': self.health["max"]
        }

    def add_radiation(self, rads):
        """
        Add radiation.

        Args:
            rads: Amount of radiation to add

        Returns:
            int: New radiation level
        """
        self.radiation = min(self.radiation + rads, 1000)
        return self.radiation

    def remove_radiation(self, rads):
        """
        Remove radiation (Rad-Away).

        Args:
            rads: Amount of radiation to remove

        Returns:
            int: New radiation level
        """
        self.radiation = max(self.radiation - rads, 0)
        return self.radiation

    def gain_experience(self, xp):
        """
        Add experience and check for level up.

        Args:
            xp: Amount of XP to gain

        Returns:
            dict: Result with 'gained', 'total', 'leveled_up', 'new_level'
        """
        self.experience += xp
        leveled_up = False
        new_level = self.level

        # Simple level up formula: level * 100 XP per level
        xp_for_next_level = self.level * 100

        while self.experience >= xp_for_next_level:
            self.experience -= xp_for_next_level
            self.level_up()
            leveled_up = True
            new_level = self.level
            xp_for_next_level = self.level * 100

        return {
            'gained': xp,
            'total': self.experience,
            'leveled_up': leveled_up,
            'new_level': new_level
        }

    def level_up(self):
        """
        Handle level up process.

        Returns:
            dict: Result with level info
        """
        self.level += 1

        # Increase max health by 5
        self.health["max"] += 5
        self.health["current"] += 5  # Also heal 5 HP on level up

        return {
            'new_level': self.level,
            'new_max_health': self.health["max"]
        }

    def add_condition(self, condition):
        """
        Add a condition to the character.

        Args:
            condition: Condition name

        Returns:
            bool: True if condition was added
        """
        if condition not in self.conditions:
            self.conditions.append(condition)
            return True
        return False

    def remove_condition(self, condition):
        """
        Remove a condition from the character.

        Args:
            condition: Condition name

        Returns:
            bool: True if condition was removed
        """
        if condition in self.conditions:
            self.conditions.remove(condition)
            return True
        return False

    def has_condition(self, condition):
        """
        Check if character has a condition.

        Args:
            condition: Condition name

        Returns:
            bool: True if character has the condition
        """
        return condition in self.conditions

    def _convert_legacy_inventory(self, inventory_list):
        """
        Convert old inventory format (list of strings) to new Inventory object.

        Args:
            inventory_list: List of item strings like ["Stimpak x3", "10mm Pistol"]

        Returns:
            Inventory: New Inventory instance
        """
        inventory = Inventory(owner=self)
        item_db = ItemDatabase.get_instance()

        for item_string in inventory_list:
            # Parse "Item Name x3" format
            parts = item_string.rsplit(' x', 1)
            item_name = parts[0].strip()
            quantity = int(parts[1]) if len(parts) > 1 else 1

            # Try to create item from database
            item = item_db.create_item(item_name, quantity)
            if item:
                inventory.add_item(item)

        return inventory

    @classmethod
    def from_json(cls, json_path):
        """
        Create a Character from a JSON file (backward compatible).

        Args:
            json_path: Path to JSON file

        Returns:
            Character: New Character instance
        """
        with open(json_path, 'r') as f:
            data = json.load(f)

        # Handle backward compatibility
        if 'special' in data and isinstance(data['special'], dict):
            if 'base' not in data['special']:
                # Old format: convert to new format
                data['special'] = SPECIALStats.from_dict(data['special'])
            else:
                # New format
                data['special'] = SPECIALStats.from_dict(data['special'])

        return cls(**data)

    def to_dict(self):
        """Convert character to dictionary for JSON serialization."""
        return {
            'name': self.name,
            'player': self.player if isinstance(self.player, str) else self.player.name,
            'level': self.level,
            'experience': self.experience,
            'special': self.special.to_dict(),
            'skills': self.skills,
            'background': self.background,
            'personality_traits': self.personality_traits,
            'health': self.health,
            'radiation': self.radiation,
            'conditions': self.conditions,
            'inventory': self.inventory.to_dict(),
            'body_parts': self.body_parts.to_dict()
        }

    def save_to_json(self, json_path):
        """
        Save character to JSON file.

        Args:
            json_path: Path to save file
        """
        with open(json_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    def print_info(self):
        """Print detailed information about the character."""
        print(f"\n=== {self.name} ===")
        print(f"Player: {self.player}")
        print(f"Level: {self.level}")
        print(f"Experience: {self.experience}")
        print(f"\nHealth: {self.health['current']}/{self.health['max']} HP")
        print(f"Radiation: {self.radiation} rads")

        print(f"\nSPECIAL:")
        print(str(self.special))

        print(f"\nSkills: {', '.join(self.skills)}")

        if self.conditions:
            print(f"\nConditions: {', '.join(self.conditions)}")

        # Show body parts status
        crippled_parts = self.body_parts.get_crippled_parts()
        if crippled_parts:
            print(f"\n{self.body_parts}")

        print(f"\n{self.inventory}")

        print(f"\nBackground: {self.background}")
        print(f"\nPersonality Traits:")
        for trait in self.personality_traits:
            print(f"  - {trait}")

    def __repr__(self):
        return f"Character(name='{self.name}', level={self.level}, player='{self.player}')"


if __name__ == "__main__":
    # Create character from doc.json
    doc = Character.from_json('characters/doc.json')
    doc.print_info()
