"""
Body parts system for tracking limb damage and conditions.
"""
import yaml
from pathlib import Path


class BodyPartTemplates:
    """
    Singleton that loads and caches body part templates.
    """
    _instance = None
    _templates = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        if BodyPartTemplates._templates is None:
            self._load_templates()

    def _load_templates(self):
        """Load templates from YAML file."""
        template_path = Path(__file__).parent.parent / "data" / "body_part_templates.yaml"
        if template_path.exists():
            with open(template_path, 'r') as f:
                data = yaml.safe_load(f)
                BodyPartTemplates._templates = data.get('templates', {})
        else:
            # Fallback to hardcoded humanoid if file missing
            BodyPartTemplates._templates = {
                'humanoid': {
                    'parts': {
                        'head': {'hit_chance_modifier': -20, 'damage_multiplier': 2.0},
                        'torso': {'hit_chance_modifier': 0, 'damage_multiplier': 1.0},
                        'left arm': {'hit_chance_modifier': -10, 'damage_multiplier': 0.75},
                        'right arm': {'hit_chance_modifier': -10, 'damage_multiplier': 0.75},
                        'left leg': {'hit_chance_modifier': -10, 'damage_multiplier': 0.75},
                        'right leg': {'hit_chance_modifier': -10, 'damage_multiplier': 0.75}
                    }
                }
            }

    def get_template(self, body_type):
        """Get a body part template by name."""
        return BodyPartTemplates._templates.get(body_type)

    def list_templates(self):
        """List available template names."""
        return list(BodyPartTemplates._templates.keys())


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

    @property
    def is_damaged(self):
        """Check if this body part has any damage or conditions."""
        return self.health < self.max_health or len(self.conditions) > 0

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
        """Serialize to JSON-compatible dict (full format for backward compat)."""
        return {
            'name': self.name,
            'health': self.health,
            'max_health': self.max_health,
            'conditions': self.conditions,
            'hit_chance_modifier': self.hit_chance_modifier,
            'damage_multiplier': self.damage_multiplier
        }

    def to_delta_dict(self):
        """
        Serialize only damage state (health/conditions).
        Returns None if part is at full health with no conditions.
        """
        if not self.is_damaged:
            return None

        delta = {}
        if self.health < self.max_health:
            delta['health'] = self.health
        if self.conditions:
            delta['conditions'] = self.conditions
        return delta if delta else None

    @classmethod
    def from_dict(cls, data):
        """Deserialize from dict (full format)."""
        part = cls(
            name=data['name'],
            max_health=data.get('max_health', 100),
            hit_chance_modifier=data.get('hit_chance_modifier', 0),
            damage_multiplier=data.get('damage_multiplier', 1.0)
        )
        part.health = data.get('health', part.max_health)
        part.conditions = data.get('conditions', [])
        return part

    def apply_delta(self, delta):
        """Apply damage delta to this part."""
        if delta:
            if 'health' in delta:
                self.health = delta['health']
            if 'conditions' in delta:
                self.conditions = delta['conditions']

    def __repr__(self):
        status = "CRIPPLED" if self.is_crippled else f"{self.health}/{self.max_health} HP"
        return f"BodyPart('{self.name}', {status})"


class BodyParts:
    """
    Manages all body parts for a character.

    Supports template-based initialization with compact delta storage.
    """

    # Kept for backward compatibility
    HUMANOID_PARTS = {
        'head': {'hit_chance_modifier': -20, 'damage_multiplier': 2.0},
        'torso': {'hit_chance_modifier': 0, 'damage_multiplier': 1.0},
        'left arm': {'hit_chance_modifier': -10, 'damage_multiplier': 0.75},
        'right arm': {'hit_chance_modifier': -10, 'damage_multiplier': 0.75},
        'left leg': {'hit_chance_modifier': -10, 'damage_multiplier': 0.75},
        'right leg': {'hit_chance_modifier': -10, 'damage_multiplier': 0.75}
    }

    def __init__(self, part_definitions=None, body_type=None):
        """
        Initialize body parts.

        Args:
            part_definitions: Dict of part names to stats (legacy)
            body_type: Template name to load from (e.g., "humanoid")
        """
        self.parts = {}
        self.body_type = body_type or "humanoid"

        # If body_type specified, load from template
        if body_type:
            templates = BodyPartTemplates.get_instance()
            template = templates.get_template(body_type)
            if template:
                part_definitions = template.get('parts', {})
            else:
                # Unknown template, fall back to humanoid
                part_definitions = self.HUMANOID_PARTS
                self.body_type = "humanoid"

        # Use humanoid as default if nothing specified
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

    def get_damaged_parts(self):
        """Get list of all damaged body parts."""
        return [part for part in self.parts.values() if part.is_damaged]

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
        """
        Serialize to compact format.
        Only includes body_type and damaged parts.
        """
        data = {'body_type': self.body_type}

        # Only include parts with damage or conditions
        damage = {}
        for name, part in self.parts.items():
            delta = part.to_delta_dict()
            if delta:
                damage[name] = delta

        if damage:
            data['body_part_damage'] = damage

        return data

    def to_dict_full(self):
        """Serialize to full format (legacy, for backward compat)."""
        return {
            'parts': {name: part.to_dict() for name, part in self.parts.items()}
        }

    @classmethod
    def from_dict(cls, data):
        """
        Deserialize from dict. Supports both compact and legacy formats.

        Compact format:
            body_type: humanoid
            body_part_damage:
              left arm: {health: 45, conditions: [broken]}

        Legacy format:
            parts:
              head: {name: head, health: 100, max_health: 100, ...}
        """
        # Check for compact format
        if 'body_type' in data:
            body_type = data['body_type']
            body_parts = cls(body_type=body_type)

            # Apply damage deltas
            damage = data.get('body_part_damage', {})
            for part_name, delta in damage.items():
                part = body_parts.get_part(part_name)
                if part:
                    part.apply_delta(delta)

            return body_parts

        # Legacy format with full parts data
        if 'parts' in data:
            body_parts = cls(part_definitions={})
            for name, part_data in data['parts'].items():
                body_parts.parts[name] = BodyPart.from_dict(part_data)
            # Try to detect body type from parts
            body_parts.body_type = cls._detect_body_type(body_parts.parts)
            return body_parts

        # Empty or invalid - create default humanoid
        return cls()

    @classmethod
    def _detect_body_type(cls, parts):
        """Try to detect body type from part names."""
        part_names = set(parts.keys())

        if 'tail' in part_names:
            return 'deathclaw'
        if 'thorax' in part_names or 'abdomen' in part_names:
            return 'insect'
        if 'combat inhibitor' in part_names:
            return 'robot'
        if 'body' in part_names and 'front left leg' in part_names:
            return 'beast'
        return 'humanoid'

    def __repr__(self):
        crippled_count = len(self.get_crippled_parts())
        return f"BodyParts({self.body_type}, {len(self.parts)} parts, {crippled_count} crippled)"

    def __str__(self):
        lines = [f"Body Status ({self.body_type}):"]
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
