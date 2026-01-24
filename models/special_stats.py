"""
SPECIALStats class for managing character SPECIAL statistics.
"""

from .stat_modifier import StatModifier


class SPECIALStats:
    """
    Manages SPECIAL stats with base values, modifiers, and effective values.

    Attributes:
        base_stats: Dict of base stat values
        modifiers: List of active StatModifier objects
    """

    STAT_NAMES = ["strength", "perception", "endurance", "charisma",
                  "intelligence", "agility", "luck"]
    MIN_STAT = 1
    MAX_STAT = 10

    def __init__(self, base_stats=None):
        """
        Initialize SPECIAL stats.

        Args:
            base_stats: Dict of base stat values (default all 5)
        """
        if base_stats is None:
            self.base_stats = {stat: 5 for stat in self.STAT_NAMES}
        else:
            self.base_stats = {stat.lower(): value for stat, value in base_stats.items()}

        self.modifiers = []
        self._validate_stats()

    def _validate_stats(self):
        """Ensure all stats are valid."""
        for stat in self.STAT_NAMES:
            if stat not in self.base_stats:
                self.base_stats[stat] = 5

            # Clamp values to valid range
            self.base_stats[stat] = max(self.MIN_STAT,
                                       min(self.MAX_STAT, self.base_stats[stat]))

    def get_base_stat(self, stat_name):
        """
        Get base value of a stat.

        Args:
            stat_name: Name of the stat

        Returns:
            int: Base stat value
        """
        stat_name = stat_name.lower()
        if stat_name not in self.STAT_NAMES:
            raise ValueError(f"Invalid stat name: {stat_name}")
        return self.base_stats[stat_name]

    def get_effective_stat(self, stat_name):
        """
        Calculate effective stat with all modifiers applied.

        Args:
            stat_name: Name of the stat

        Returns:
            int: Effective stat value
        """
        stat_name = stat_name.lower()
        if stat_name not in self.STAT_NAMES:
            raise ValueError(f"Invalid stat name: {stat_name}")

        base = self.base_stats[stat_name]
        flat_modifiers = 0
        multiplier = 1.0

        # Apply all active modifiers for this stat
        for modifier in self.modifiers:
            if modifier.stat_name == stat_name and not modifier.is_expired():
                if modifier.modifier_type == "flat":
                    flat_modifiers += modifier.value
                elif modifier.modifier_type == "multiplier":
                    multiplier *= (1.0 + modifier.value / 100.0)

        # Calculate effective value: (base + flat) * multiplier
        effective = int((base + flat_modifiers) * multiplier)

        # Clamp to valid range
        return max(self.MIN_STAT, min(self.MAX_STAT, effective))

    def add_modifier(self, modifier):
        """
        Add a stat modifier.

        Args:
            modifier: StatModifier instance

        Returns:
            bool: True if modifier was added
        """
        if not isinstance(modifier, StatModifier):
            raise TypeError("modifier must be a StatModifier instance")

        # If not stackable, remove existing modifiers from same source
        if not modifier.stackable:
            self.remove_modifier(modifier.source, modifier.stat_name)

        self.modifiers.append(modifier)
        return True

    def remove_modifier(self, source, stat_name=None):
        """
        Remove modifiers by source and optionally stat name.

        Args:
            source: Source of the modifier to remove
            stat_name: Optional stat name to filter by

        Returns:
            int: Number of modifiers removed
        """
        initial_count = len(self.modifiers)

        if stat_name:
            stat_name = stat_name.lower()
            self.modifiers = [m for m in self.modifiers
                            if not (m.source == source and m.stat_name == stat_name)]
        else:
            self.modifiers = [m for m in self.modifiers if m.source != source]

        return initial_count - len(self.modifiers)

    def update_modifiers(self, current_time=None):
        """
        Remove expired modifiers.

        Args:
            current_time: Time to check against (defaults to now)

        Returns:
            list: List of expired modifiers that were removed
        """
        expired = [m for m in self.modifiers if m.is_expired(current_time)]
        self.modifiers = [m for m in self.modifiers if not m.is_expired(current_time)]
        return expired

    def set_base_stat(self, stat_name, value):
        """
        Set base stat value (for leveling).

        Args:
            stat_name: Name of the stat
            value: New base value

        Returns:
            bool: True if stat was updated
        """
        stat_name = stat_name.lower()
        if stat_name not in self.STAT_NAMES:
            raise ValueError(f"Invalid stat name: {stat_name}")

        # Clamp to valid range
        value = max(self.MIN_STAT, min(self.MAX_STAT, value))
        self.base_stats[stat_name] = value
        return True

    def get_modifiers_for_stat(self, stat_name):
        """
        Get all active modifiers for a specific stat.

        Args:
            stat_name: Name of the stat

        Returns:
            list: List of StatModifier objects
        """
        stat_name = stat_name.lower()
        return [m for m in self.modifiers
                if m.stat_name == stat_name and not m.is_expired()]

    def to_dict(self):
        """Serialize to JSON-compatible dict."""
        return {
            'base': self.base_stats.copy(),
            'modifiers': [m.to_dict() for m in self.modifiers]
        }

    @classmethod
    def from_dict(cls, data):
        """
        Deserialize from dict.

        Args:
            data: Dictionary containing SPECIAL stats data

        Returns:
            SPECIALStats: New SPECIALStats instance
        """
        # Handle both new format (with 'base' and 'modifiers') and old format (flat dict)
        if 'base' in data:
            base_stats = data['base']
            stats = cls(base_stats)

            # Load modifiers if present
            if 'modifiers' in data:
                for mod_data in data['modifiers']:
                    modifier = StatModifier.from_dict(mod_data)
                    stats.modifiers.append(modifier)
        else:
            # Old format: treat entire dict as base stats
            stats = cls(data)

        return stats

    def __repr__(self):
        return f"SPECIALStats({self.base_stats})"

    def __str__(self):
        lines = []
        for stat in self.STAT_NAMES:
            base = self.base_stats[stat]
            effective = self.get_effective_stat(stat)
            if base != effective:
                lines.append(f"{stat.capitalize()}: {base} (effective: {effective})")
            else:
                lines.append(f"{stat.capitalize()}: {base}")
        return "\n".join(lines)
