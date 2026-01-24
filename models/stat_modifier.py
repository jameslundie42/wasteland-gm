"""
StatModifier class for temporary stat modifications.
"""

from datetime import datetime, timedelta


class StatModifier:
    """
    Represents a temporary modification to a character stat.

    Attributes:
        stat_name: Name of stat being modified (e.g., "strength")
        value: Modifier value (can be positive or negative)
        duration: Duration in seconds (None for permanent)
        source: What caused this modifier (e.g., "Buffout", "Crippled Arm")
        modifier_type: Type of modifier ("flat" or "multiplier")
        stackable: Whether multiple of same source can stack
        applied_at: When the modifier was applied
        expires_at: When the modifier expires
    """

    def __init__(self, stat_name, value, duration=None, source="Unknown",
                 modifier_type="flat", stackable=False):
        self.stat_name = stat_name.lower()
        self.value = value
        self.duration = duration
        self.source = source
        self.modifier_type = modifier_type
        self.stackable = stackable
        self.applied_at = datetime.now()

        if duration is not None:
            self.expires_at = self.applied_at + timedelta(seconds=duration)
        else:
            self.expires_at = None

    def is_expired(self, current_time=None):
        """
        Check if modifier has expired.

        Args:
            current_time: Time to check against (defaults to now)

        Returns:
            bool: True if expired
        """
        if self.expires_at is None:
            return False

        check_time = current_time or datetime.now()
        return check_time >= self.expires_at

    def remaining_duration(self, current_time=None):
        """
        Get remaining duration in seconds.

        Args:
            current_time: Time to check against (defaults to now)

        Returns:
            float: Remaining seconds, or None for permanent modifiers
        """
        if self.expires_at is None:
            return None

        check_time = current_time or datetime.now()
        if check_time >= self.expires_at:
            return 0

        return (self.expires_at - check_time).total_seconds()

    def to_dict(self):
        """Serialize to JSON-compatible dict."""
        return {
            'stat_name': self.stat_name,
            'value': self.value,
            'duration': self.duration,
            'source': self.source,
            'modifier_type': self.modifier_type,
            'stackable': self.stackable,
            'applied_at': self.applied_at.isoformat() if self.applied_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None
        }

    @classmethod
    def from_dict(cls, data):
        """
        Deserialize from dict.

        Args:
            data: Dictionary containing modifier data

        Returns:
            StatModifier: New StatModifier instance
        """
        modifier = cls(
            stat_name=data['stat_name'],
            value=data['value'],
            duration=data.get('duration'),
            source=data.get('source', 'Unknown'),
            modifier_type=data.get('modifier_type', 'flat'),
            stackable=data.get('stackable', False)
        )

        # Restore timestamps if provided
        if 'applied_at' in data and data['applied_at']:
            modifier.applied_at = datetime.fromisoformat(data['applied_at'])
        if 'expires_at' in data and data['expires_at']:
            modifier.expires_at = datetime.fromisoformat(data['expires_at'])

        return modifier

    def __repr__(self):
        sign = '+' if self.value >= 0 else ''
        duration_str = f", {self.duration}s" if self.duration else ", permanent"
        return f"StatModifier({self.stat_name} {sign}{self.value} from {self.source}{duration_str})"

    def __str__(self):
        sign = '+' if self.value >= 0 else ''
        return f"{self.source}: {sign}{self.value} {self.stat_name}"
