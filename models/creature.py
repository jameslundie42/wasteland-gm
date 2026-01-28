"""
Creature template system for spawning generic enemies.

Creatures are lightweight entities that can participate in combat
via duck typing (they implement the same interface as Character).
They can be promoted to full Characters when narratively important.
"""

import yaml
import random
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

from models.body_parts import BodyParts


@dataclass
class LootEntry:
    """A single loot table entry."""
    item: str
    quantity: str = "1"  # Can be "1", "5-25", etc.
    chance: float = 1.0  # 1.0 = guaranteed, 0.3 = 30% chance

    def roll_quantity(self) -> int:
        """Roll for quantity based on quantity string."""
        if "-" in self.quantity:
            low, high = map(int, self.quantity.split("-"))
            return random.randint(low, high)
        return int(self.quantity)

    def roll_drop(self) -> Optional[tuple]:
        """Roll to see if item drops. Returns (item_name, quantity) or None."""
        if random.random() <= self.chance:
            return (self.item, self.roll_quantity())
        return None


@dataclass
class CreatureTemplate:
    """
    Defines an archetype for spawning creatures.
    Loaded from YAML, defines base stats, variance, loot, etc.
    """
    name: str
    category: str = "humanoid"  # humanoid, beast, robot, etc.

    # SPECIAL stats
    special_base: dict = field(default_factory=lambda: {
        "strength": 5, "perception": 5, "endurance": 5,
        "charisma": 5, "intelligence": 5, "agility": 5, "luck": 5
    })
    special_variance: int = 2

    # Level
    level_base: int = 1
    level_variance: int = 2

    # Combat
    skills: list = field(default_factory=list)
    affiliation: str = "Hostile"

    # Loot
    loot_guaranteed: list = field(default_factory=list)  # List of LootEntry
    loot_chance: list = field(default_factory=list)      # List of LootEntry

    # Body parts (None = use default for category)
    body_parts_definition: Optional[dict] = None

    # Name patterns for spawning
    name_patterns: list = field(default_factory=lambda: ["{name} #{n}"])

    # Description for GM reference
    description: str = ""

    # Personality and agent
    personality_traits: list = field(default_factory=list)
    default_agent: str = "npc_neutral"  # Agent filename (without .yaml)

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "CreatureTemplate":
        """Create template from YAML dict."""
        template = cls(name=name)

        template.category = data.get("category", "humanoid")
        template.description = data.get("description", "")

        # SPECIAL stats
        special_data = data.get("special", {})
        if "base" in special_data:
            template.special_base = special_data["base"]
        template.special_variance = special_data.get("variance", 2)

        # Level
        level_data = data.get("level", {})
        if isinstance(level_data, dict):
            template.level_base = level_data.get("base", 1)
            template.level_variance = level_data.get("variance", 2)
        else:
            template.level_base = int(level_data)
            template.level_variance = 0

        # Combat
        template.skills = data.get("skills", [])
        template.affiliation = data.get("affiliation", "Hostile")

        # Loot table
        loot_data = data.get("loot_table", {})
        template.loot_guaranteed = []
        for entry in loot_data.get("guaranteed", []):
            template.loot_guaranteed.append(LootEntry(
                item=entry["item"],
                quantity=str(entry.get("quantity", "1")),
                chance=1.0
            ))
        template.loot_chance = []
        for entry in loot_data.get("chance", []):
            template.loot_chance.append(LootEntry(
                item=entry["item"],
                quantity=str(entry.get("quantity", "1")),
                chance=entry.get("chance", 0.5)
            ))

        # Body parts
        template.body_parts_definition = data.get("body_parts")

        # Name patterns
        template.name_patterns = data.get("name_patterns", ["{name} #{n}"])

        # Personality and agent
        template.personality_traits = data.get("personality_traits", [])
        template.default_agent = data.get("default_agent", "npc_neutral")

        return template

    def get_body_type(self) -> str:
        """Get body type template name based on category."""
        # Map categories to body part template names
        category_to_body_type = {
            "humanoid": "humanoid",
            "beast": "beast",
            "insect": "insect",
            "deathclaw": "deathclaw",
            "robot": "robot",
        }
        return category_to_body_type.get(self.category, "humanoid")

    def get_body_parts_definition(self) -> Optional[dict]:
        """Get custom body parts definition if specified in template."""
        return self.body_parts_definition


class CreatureInstance:
    """
    A spawned creature instance from a template.
    Implements the Character-compatible interface for combat.
    """

    def __init__(self, template: CreatureTemplate, spawn_number: int = 1):
        self.template = template
        self.spawn_number = spawn_number

        # Generate name from pattern
        pattern = random.choice(template.name_patterns)
        self.name = pattern.format(name=template.name, n=spawn_number)

        # Roll stats with variance
        self.special = {}
        for stat, base_val in template.special_base.items():
            variance = random.randint(-template.special_variance, template.special_variance)
            self.special[stat] = max(1, min(10, base_val + variance))

        # Roll level
        level_variance = random.randint(0, template.level_variance)
        self.level = template.level_base + level_variance

        # Calculate health from Endurance + Luck + (Level - 1)
        max_hp = self.special.get("endurance", 5) + self.special.get("luck", 5) + (self.level - 1)
        self.health = {"current": max_hp, "max": max_hp}

        # Combat attributes
        self.skills = list(template.skills)
        self.affiliation = template.affiliation
        self.conditions = []
        self.aliases = []

        # Personality from template
        self.personality_traits = list(template.personality_traits)

        # Background generated from template
        self.background = template.description

        # Agent for NPC behavior (can be changed mid-game)
        self.player = self._load_agent(template.default_agent)

        # Body parts - use template definition or body_type from category
        custom_parts = template.get_body_parts_definition()
        if custom_parts:
            self.body_parts = BodyParts(part_definitions=custom_parts)
        else:
            self.body_parts = BodyParts(body_type=template.get_body_type())

        # Loot (pre-rolled on death)
        self._loot = None

        # Gear (equipped items for display/combat)
        self.gear = []

        # Minimal inventory interface for compatibility
        self._inventory_items = []

    def _load_agent(self, agent_name: str):
        """Load an agent by name. Returns Agent instance or 'GM' string."""
        if not agent_name:
            return "GM"

        from agent import Agent
        agents_dir = Path(__file__).parent.parent / "agents"

        # Try with and without .yaml extension
        agent_file = agents_dir / f"{agent_name}.yaml"
        if not agent_file.exists():
            agent_file = agents_dir / agent_name
        if not agent_file.exists():
            return "GM"

        try:
            return Agent.from_yaml(str(agent_file))
        except Exception:
            return "GM"

    def set_agent(self, agent_name: str) -> bool:
        """
        Change the creature's agent mid-game.

        Args:
            agent_name: Name of agent file (e.g., "npc_friendly", "npc_hostile")

        Returns:
            bool: True if agent was changed successfully
        """
        new_agent = self._load_agent(agent_name)
        if new_agent != "GM" or agent_name == "":
            self.player = new_agent
            return True
        return False

    # === Character-compatible interface ===

    def get_effective_stat(self, stat_name: str) -> int:
        """Get effective value of a SPECIAL stat."""
        return self.special.get(stat_name.lower(), 5)

    def get_base_stat(self, stat_name: str) -> int:
        """Get base value of a SPECIAL stat."""
        return self.special.get(stat_name.lower(), 5)

    def take_damage(self, damage: int) -> dict:
        """Apply damage to creature."""
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

    def heal(self, amount: int) -> dict:
        """Heal creature."""
        amount = max(0, int(amount))
        old_health = self.health["current"]
        self.health["current"] = min(self.health["current"] + amount, self.health["max"])
        actual_healed = self.health["current"] - old_health

        return {
            'healed': actual_healed,
            'current_health': self.health["current"],
            'max_health': self.health["max"]
        }

    def add_condition(self, condition: str) -> bool:
        """Add a condition to the creature."""
        if condition not in self.conditions:
            self.conditions.append(condition)
            return True
        return False

    def remove_condition(self, condition: str) -> bool:
        """Remove a condition from the creature."""
        if condition in self.conditions:
            self.conditions.remove(condition)
            return True
        return False

    def has_condition(self, condition: str) -> bool:
        """Check if creature has a condition."""
        return condition in self.conditions

    def is_dead(self) -> bool:
        """Check if creature is dead."""
        return self.health["current"] <= 0

    # === Creature-specific methods ===

    def roll_loot(self) -> list:
        """Roll loot drops. Returns list of (item_name, quantity) tuples."""
        if self._loot is not None:
            return self._loot

        self._loot = []

        # Guaranteed drops
        for entry in self.template.loot_guaranteed:
            drop = entry.roll_drop()
            if drop:
                self._loot.append(drop)

        # Chance drops
        for entry in self.template.loot_chance:
            drop = entry.roll_drop()
            if drop:
                self._loot.append(drop)

        return self._loot

    @property
    def inventory(self):
        """Minimal inventory interface for agent compatibility."""
        class MinimalInventory:
            def __init__(self, items):
                self.items = items
        return MinimalInventory(self._inventory_items)

    def promote_to_character(self, new_name: str = None):
        """
        Convert this creature to a full Character.
        Returns the Character instance.
        """
        from character import Character
        from models.special_stats import SPECIALStats

        name = new_name or self.name

        # Build SPECIAL dict for Character
        special_dict = {
            "base": self.special.copy(),
            "modifiers": []
        }

        character = Character(
            name=name,
            special=SPECIALStats.from_dict(special_dict),
            skills=self.skills.copy(),
            background=self.background or f"Former {self.template.name}.",
            personality_traits=self.personality_traits.copy(),
            level=self.level,
            health=self.health.copy(),
            conditions=self.conditions.copy(),
            body_parts=self.body_parts,
            player="GM",
            affiliation=self.affiliation,
            aliases=[self.name] if new_name and new_name != self.name else []
        )

        return character

    def get_info_text(self) -> str:
        """Get formatted info text for display."""
        lines = [f"\n=== {self.name} ({self.template.name}) ==="]
        lines.append(f"Category: {self.template.category}")
        lines.append(f"Level: {self.level}")
        lines.append(f"HP: {self.health['current']}/{self.health['max']}")
        lines.append(f"Affiliation: {self.affiliation}")

        lines.append("\nSPECIAL:")
        for stat, val in self.special.items():
            lines.append(f"  {stat.capitalize()}: {val}")

        if self.skills:
            lines.append(f"\nSkills: {', '.join(self.skills)}")

        if self.conditions:
            lines.append(f"\nConditions: {', '.join(self.conditions)}")

        if self.is_dead():
            lines.append("\n[DEAD]")
            loot = self.roll_loot()
            if loot:
                lines.append("Loot:")
                for item, qty in loot:
                    lines.append(f"  - {item} x{qty}")

        return "\n".join(lines)

    def __repr__(self):
        status = "DEAD" if self.is_dead() else f"HP {self.health['current']}/{self.health['max']}"
        return f"CreatureInstance('{self.name}', Lv{self.level}, {status})"


class CreatureRegistry:
    """
    Singleton registry for creature templates and active instances.
    Manages spawning, tracking, and cleanup.
    """

    _instance = None

    def __init__(self):
        self.templates = {}  # name -> CreatureTemplate
        self.active_creatures = {}  # name -> CreatureInstance
        self._spawn_counters = {}  # template_name -> int (for unique naming)
        self._load_templates()

    @classmethod
    def get_instance(cls) -> "CreatureRegistry":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_templates(self):
        """Load creature templates from YAML."""
        data_dir = Path(__file__).parent.parent / "data"
        creatures_file = data_dir / "creatures.yaml"

        if not creatures_file.exists():
            return

        with open(creatures_file, 'r') as f:
            data = yaml.safe_load(f)

        for name, template_data in data.get("templates", {}).items():
            self.templates[name.lower()] = CreatureTemplate.from_dict(name, template_data)

    def get_template(self, name: str) -> Optional[CreatureTemplate]:
        """Get template by name (case-insensitive)."""
        return self.templates.get(name.lower())

    def list_templates(self, category: str = None) -> list:
        """List available templates, optionally filtered by category."""
        templates = []
        for template in self.templates.values():
            if category is None or template.category == category:
                templates.append(template)
        return templates

    def spawn(self, template_name: str, count: int = 1) -> list:
        """
        Spawn creature(s) from template.

        Args:
            template_name: Name of template to spawn from
            count: Number of creatures to spawn

        Returns:
            List of spawned CreatureInstance objects
        """
        template = self.get_template(template_name)
        if not template:
            return []

        # Get spawn counter for this template
        counter_key = template.name.lower()
        if counter_key not in self._spawn_counters:
            self._spawn_counters[counter_key] = 0

        spawned = []
        for _ in range(count):
            self._spawn_counters[counter_key] += 1
            spawn_num = self._spawn_counters[counter_key]

            creature = CreatureInstance(template, spawn_num)

            # Ensure unique name
            base_name = creature.name
            suffix = 1
            while creature.name.lower() in self.active_creatures:
                creature.name = f"{base_name} ({suffix})"
                suffix += 1

            self.active_creatures[creature.name.lower()] = creature
            spawned.append(creature)

        return spawned

    def spawn_boss(self, template_name: str, boss_name: str) -> Optional[CreatureInstance]:
        """
        Spawn a unique boss creature with a specific name.

        Args:
            template_name: Template to base boss on
            boss_name: Unique name for the boss

        Returns:
            CreatureInstance or None if template not found
        """
        template = self.get_template(template_name)
        if not template:
            return None

        # Create creature with high spawn number (for better stats if variance allows)
        creature = CreatureInstance(template, spawn_number=999)
        creature.name = boss_name

        # Boost boss stats slightly
        for stat in creature.special:
            creature.special[stat] = min(10, creature.special[stat] + 1)

        # Recalculate health
        max_hp = creature.special.get("endurance", 5) + creature.special.get("luck", 5) + (creature.level - 1)
        max_hp = int(max_hp * 1.5)  # 50% more HP for bosses
        creature.health = {"current": max_hp, "max": max_hp}

        self.active_creatures[creature.name.lower()] = creature
        return creature

    def get_creature(self, name: str) -> Optional[CreatureInstance]:
        """Get active creature by name (case-insensitive)."""
        return self.active_creatures.get(name.lower())

    def remove_creature(self, name: str) -> bool:
        """Remove creature from registry."""
        key = name.lower()
        if key in self.active_creatures:
            del self.active_creatures[key]
            return True
        return False

    def get_active_creatures(self) -> list:
        """Get all active creatures."""
        return list(self.active_creatures.values())

    def clear_encounter(self):
        """Clear all active creatures (end of encounter cleanup)."""
        self.active_creatures.clear()

    def clear_dead(self) -> list:
        """Remove all dead creatures. Returns list of removed names."""
        dead = [name for name, c in self.active_creatures.items() if c.is_dead()]
        for name in dead:
            del self.active_creatures[name]
        return dead

    def reset_counters(self):
        """Reset spawn counters (e.g., new session)."""
        self._spawn_counters.clear()
