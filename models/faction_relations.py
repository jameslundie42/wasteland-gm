"""
Faction relations system for tracking relationships between factions.
Supports a 5-tier relation system from allied to hostile.
"""

import yaml
from enum import Enum
from pathlib import Path
from typing import Optional


class FactionRelation(Enum):
    """Relationship status between two factions."""
    ALLIED = "allied"       # +2: Fight together, share resources
    FRIENDLY = "friendly"   # +1: Trade bonuses, willing to help
    NEUTRAL = "neutral"     #  0: Default state
    UNFRIENDLY = "unfriendly"  # -1: Suspicious, higher prices
    HOSTILE = "hostile"     # -2: Attack on sight


# Mapping from relation to numeric modifier
RELATION_MODIFIERS = {
    FactionRelation.ALLIED: 2,
    FactionRelation.FRIENDLY: 1,
    FactionRelation.NEUTRAL: 0,
    FactionRelation.UNFRIENDLY: -1,
    FactionRelation.HOSTILE: -2,
}


class FactionRelations:
    """
    Manages faction-to-faction relationships.
    Singleton loaded from YAML, can be modified per-campaign.

    Relations are stored symmetrically - if A is hostile to B, B is hostile to A.
    """

    _instance: Optional['FactionRelations'] = None

    def __init__(self):
        # Matrix stored as dict[faction_a][faction_b] = FactionRelation
        self._relations: dict[str, dict[str, FactionRelation]] = {}

    @classmethod
    def get_instance(cls) -> 'FactionRelations':
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
            cls._instance.load_default()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset the singleton (for testing or loading new campaign)."""
        cls._instance = None

    def load_default(self):
        """Load default relations from the data file."""
        default_path = Path(__file__).parent.parent / "data" / "faction_relations.yaml"
        if default_path.exists():
            self.load(default_path)

    def load(self, path):
        """
        Load faction relations from a YAML file.

        Args:
            path: Path to YAML file with relations data
        """
        with open(path, 'r') as f:
            data = yaml.safe_load(f)

        self.from_dict(data)

    def from_dict(self, data: dict):
        """
        Load relations from a dictionary.

        Args:
            data: Dictionary with 'relations' key containing faction mappings
        """
        self._relations = {}

        relations_data = data.get("relations", {})
        for faction_a, relations in relations_data.items():
            if not isinstance(relations, dict):
                continue
            for faction_b, relation_str in relations.items():
                try:
                    relation = FactionRelation(relation_str.lower())
                    self.set_relation(faction_a, faction_b, relation)
                except (ValueError, AttributeError):
                    # Skip invalid relation strings
                    continue

    def to_dict(self) -> dict:
        """
        Convert relations to dictionary for serialization.

        Returns:
            dict: Relations data suitable for YAML export
        """
        relations_data = {}

        # Only store one direction to avoid duplication
        seen_pairs = set()

        for faction_a, relations in self._relations.items():
            faction_relations = {}
            for faction_b, relation in relations.items():
                pair = tuple(sorted([faction_a, faction_b]))
                if pair not in seen_pairs and relation != FactionRelation.NEUTRAL:
                    faction_relations[faction_b] = relation.value
                    seen_pairs.add(pair)

            if faction_relations:
                relations_data[faction_a] = faction_relations

        return {"relations": relations_data}

    def _normalize_faction(self, faction: str) -> str:
        """Normalize faction name for consistent lookup."""
        return faction.strip()

    def get_relation(self, faction_a: str, faction_b: str) -> FactionRelation:
        """
        Get the relation between two factions.

        Args:
            faction_a: First faction name
            faction_b: Second faction name

        Returns:
            FactionRelation: The relationship status (defaults to NEUTRAL)
        """
        faction_a = self._normalize_faction(faction_a)
        faction_b = self._normalize_faction(faction_b)

        # Same faction is always allied with itself
        if faction_a.lower() == faction_b.lower():
            return FactionRelation.ALLIED

        if faction_a in self._relations:
            if faction_b in self._relations[faction_a]:
                return self._relations[faction_a][faction_b]

        return FactionRelation.NEUTRAL

    def set_relation(self, faction_a: str, faction_b: str, relation: FactionRelation):
        """
        Set the relation between two factions (symmetric).

        Args:
            faction_a: First faction name
            faction_b: Second faction name
            relation: The relationship to set
        """
        faction_a = self._normalize_faction(faction_a)
        faction_b = self._normalize_faction(faction_b)

        # Initialize faction dicts if needed
        if faction_a not in self._relations:
            self._relations[faction_a] = {}
        if faction_b not in self._relations:
            self._relations[faction_b] = {}

        # Set symmetric relation
        self._relations[faction_a][faction_b] = relation
        self._relations[faction_b][faction_a] = relation

    def get_relation_modifier(self, faction_a: str, faction_b: str) -> int:
        """
        Get the numeric modifier for relations between factions.

        Args:
            faction_a: First faction name
            faction_b: Second faction name

        Returns:
            int: Modifier from -2 (hostile) to +2 (allied)
        """
        relation = self.get_relation(faction_a, faction_b)
        return RELATION_MODIFIERS[relation]

    def get_allies(self, faction: str) -> list[str]:
        """
        Get all factions allied with the given faction.

        Args:
            faction: Faction name

        Returns:
            list: Names of allied factions
        """
        faction = self._normalize_faction(faction)
        allies = []

        if faction in self._relations:
            for other, relation in self._relations[faction].items():
                if relation == FactionRelation.ALLIED:
                    allies.append(other)

        return allies

    def get_enemies(self, faction: str) -> list[str]:
        """
        Get all factions hostile to the given faction.

        Args:
            faction: Faction name

        Returns:
            list: Names of hostile factions
        """
        faction = self._normalize_faction(faction)
        enemies = []

        if faction in self._relations:
            for other, relation in self._relations[faction].items():
                if relation == FactionRelation.HOSTILE:
                    enemies.append(other)

        return enemies

    def get_factions_by_relation(self, faction: str, relation: FactionRelation) -> list[str]:
        """
        Get all factions with a specific relation to the given faction.

        Args:
            faction: Faction name
            relation: Relation type to filter by

        Returns:
            list: Names of factions with that relation
        """
        faction = self._normalize_faction(faction)
        result = []

        if faction in self._relations:
            for other, rel in self._relations[faction].items():
                if rel == relation:
                    result.append(other)

        return result

    def get_all_factions(self) -> list[str]:
        """
        Get all known faction names.

        Returns:
            list: All faction names in the relations matrix
        """
        factions = set(self._relations.keys())
        for relations in self._relations.values():
            factions.update(relations.keys())
        return sorted(factions)

    def get_relation_display(self, faction_a: str, faction_b: str) -> str:
        """
        Get a display string for the relation between factions.

        Args:
            faction_a: First faction name
            faction_b: Second faction name

        Returns:
            str: Human-readable relation description
        """
        relation = self.get_relation(faction_a, faction_b)
        modifier = RELATION_MODIFIERS[relation]

        sign = "+" if modifier > 0 else ""
        return f"{relation.value} ({sign}{modifier})"

    def get_price_modifier(self, seller_affiliation: str, buyer_affiliations: list[str]) -> float:
        """
        Calculate price modifier based on faction relations.
        Uses the best (most favorable) relation from buyer's affiliations.

        Args:
            seller_affiliation: Seller's primary faction
            buyer_affiliations: List of buyer's faction affiliations

        Returns:
            float: Price multiplier (0.8 for allied to 1.25 for hostile)
        """
        if not buyer_affiliations:
            return 1.0

        best_modifier = None

        for buyer_aff in buyer_affiliations:
            relation = self.get_relation(seller_affiliation, buyer_aff)
            modifier = RELATION_MODIFIERS[relation]

            if best_modifier is None or modifier > best_modifier:
                best_modifier = modifier

        # Convert modifier to price multiplier
        # +2 allied = -20% (0.8), +1 friendly = -10% (0.9)
        # 0 neutral = 0% (1.0)
        # -1 unfriendly = +10% (1.1), -2 hostile = +25% (1.25)
        if best_modifier is None:
            return 1.0
        elif best_modifier >= 2:
            return 0.8
        elif best_modifier == 1:
            return 0.9
        elif best_modifier == 0:
            return 1.0
        elif best_modifier == -1:
            return 1.1
        else:  # -2 or worse
            return 1.25
