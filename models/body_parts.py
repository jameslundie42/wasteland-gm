"""
Body parts system for tracking limb damage and conditions.
"""


class BodyPart:
    """
    Represents a single body part.

    Attributes:
        name: Part name (e.g., "head", "left arm")
        health: Current health (0-100, 0 = crippled)
        max_health: Maximum health (default 100)
        conditions: List of conditions affecting this part
        hit_chance_modifier: Modifier to hit chance when targeting
        damage_multiplier: Damage multiplier for this part
    """

    def __init__(self, name, max_health=100, hit_chance_modifier=0, damage_multiplier=1.0):
        self.name = name
        self.max_health = max_health
        self.health = max_health
        self.conditions = []
        self.hit_chance_modifier = hit_chance_modifier
        self.damage_multiplier = damage_multiplier

    @property
    def is_crippled(self):
        """Check if this body part is crippled."""
        return self.health <= 0 or "crippled" in self.conditions

    def take_damage(self, damage):
        """
        Apply damage to this body part.

        Args:
            damage: Amount of damage

        Returns:
            dict: Result with damage_taken, is_crippled
        """
        # Check if already crippled BEFORE applying damage
        was_crippled = self.is_crippled

        old_health = self.health
        self.health = max(0, self.health - damage)
        actual_damage = old_health - self.health

        # Cripple if health reaches 0 and wasn't already crippled
        newly_crippled = False
        if self.health <= 0 and not was_crippled:
            self.conditions.append("crippled")
            newly_crippled = True

        return {
            'damage_taken': actual_damage,
            'current_health': self.health,
            'is_crippled': self.is_crippled,
            'newly_crippled': newly_crippled
        }

    def heal(self, amount):
        """
        Heal this body part.

        Args:
            amount: Amount to heal

        Returns:
            dict: Result with healed amount
        """
        old_health = self.health
        self.health = min(self.max_health, self.health + amount)
        actual_healed = self.health - old_health

        return {
            'healed': actual_healed,
            'current_health': self.health,
            'is_crippled': self.is_crippled
        }

    def add_condition(self, condition):
        """Add a condition to this body part."""
        if condition not in self.conditions:
            self.conditions.append(condition)

    def remove_condition(self, condition):
        """Remove a condition from this body part."""
        if condition in self.conditions:
            self.conditions.remove(condition)

            # If crippled is removed and health is 0, restore some health
            if condition == "crippled" and self.health == 0:
                self.health = min(25, self.max_health)

    def to_dict(self):
        """Serialize to JSON-compatible dict."""
        return {
            'name': self.name,
            'health': self.health,
            'max_health': self.max_health,
            'conditions': self.conditions,
            'hit_chance_modifier': self.hit_chance_modifier,
            'damage_multiplier': self.damage_multiplier
        }

    @classmethod
    def from_dict(cls, data):
        """Deserialize from dict."""
        part = cls(
            name=data['name'],
            max_health=data.get('max_health', 100),
            hit_chance_modifier=data.get('hit_chance_modifier', 0),
            damage_multiplier=data.get('damage_multiplier', 1.0)
        )
        part.health = data.get('health', part.max_health)
        part.conditions = data.get('conditions', [])
        return part

    def __repr__(self):
        status = "CRIPPLED" if self.is_crippled else f"{self.health}/{self.max_health} HP"
        return f"BodyPart('{self.name}', {status})"


class BodyParts:
    """
    Manages all body parts for a character.

    Standard humanoid parts:
    - head
    - torso
    - left arm
    - right arm
    - left leg
    - right leg
    """

    HUMANOID_PARTS = {
        'head': {'hit_chance_modifier': -20, 'damage_multiplier': 2.0},
        'torso': {'hit_chance_modifier': 0, 'damage_multiplier': 1.0},
        'left arm': {'hit_chance_modifier': -10, 'damage_multiplier': 0.75},
        'right arm': {'hit_chance_modifier': -10, 'damage_multiplier': 0.75},
        'left leg': {'hit_chance_modifier': -10, 'damage_multiplier': 0.75},
        'right leg': {'hit_chance_modifier': -10, 'damage_multiplier': 0.75}
    }

    def __init__(self, part_definitions=None):
        """
        Initialize body parts.

        Args:
            part_definitions: Dict of part names to stats, or None for humanoid
        """
        self.parts = {}

        if part_definitions is None:
            part_definitions = self.HUMANOID_PARTS

        for name, stats in part_definitions.items():
            self.parts[name] = BodyPart(
                name=name,
                hit_chance_modifier=stats.get('hit_chance_modifier', 0),
                damage_multiplier=stats.get('damage_multiplier', 1.0)
            )

    def get_part(self, part_name):
        """
        Get body part by name (case-insensitive).

        Args:
            part_name: Name of body part

        Returns:
            BodyPart or None
        """
        for name, part in self.parts.items():
            if name.lower() == part_name.lower():
                return part
        return None

    def get_crippled_parts(self):
        """Get list of all crippled body parts."""
        return [part for part in self.parts.values() if part.is_crippled]

    def heal_part(self, part_name, amount):
        """
        Heal a specific body part.

        Args:
            part_name: Name of body part
            amount: Amount to heal

        Returns:
            dict: Result or None if part not found
        """
        part = self.get_part(part_name)
        if part:
            return part.heal(amount)
        return None

    def damage_part(self, part_name, damage):
        """
        Damage a specific body part.

        Args:
            part_name: Name of body part
            damage: Amount of damage

        Returns:
            dict: Result or None if part not found
        """
        part = self.get_part(part_name)
        if part:
            return part.take_damage(damage)
        return None

    def cure_crippled_part(self, part_name):
        """
        Cure a crippled body part.

        Args:
            part_name: Name of body part

        Returns:
            bool: True if cured
        """
        part = self.get_part(part_name)
        if part and part.is_crippled:
            part.remove_condition("crippled")
            return True
        return False

    def cure_all_crippled_parts(self):
        """
        Cure all crippled body parts.

        Returns:
            list: Names of cured parts
        """
        cured = []
        for part in self.get_crippled_parts():
            part.remove_condition("crippled")
            cured.append(part.name)
        return cured

    def to_dict(self):
        """Serialize to JSON-compatible dict."""
        return {
            'parts': {name: part.to_dict() for name, part in self.parts.items()}
        }

    @classmethod
    def from_dict(cls, data):
        """Deserialize from dict."""
        body_parts = cls(part_definitions={})

        if 'parts' in data:
            for name, part_data in data['parts'].items():
                body_parts.parts[name] = BodyPart.from_dict(part_data)
        else:
            # Old format or missing data - create default humanoid
            body_parts = cls()

        return body_parts

    def __repr__(self):
        crippled_count = len(self.get_crippled_parts())
        return f"BodyParts({len(self.parts)} parts, {crippled_count} crippled)"

    def __str__(self):
        lines = ["Body Status:"]
        for name, part in self.parts.items():
            status = f"  {name.capitalize()}: "
            if part.is_crippled:
                status += "[CRIPPLED]"
            else:
                status += f"{part.health}/{part.max_health} HP"

            if part.conditions:
                other_conditions = [c for c in part.conditions if c != "crippled"]
                if other_conditions:
                    status += f" ({', '.join(other_conditions)})"

            lines.append(status)

        return "\n".join(lines)
