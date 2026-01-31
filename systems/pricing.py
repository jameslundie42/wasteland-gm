"""
Pricing system for trade transactions.
Calculates item prices based on base value and modifiers.
"""

from data.item_database import ItemDatabase


# Personality trait keywords mapped to price multipliers
PERSONALITY_MODIFIERS = {
    "greedy": 1.2,
    "stingy": 1.2,
    "shrewd": 1.15,
    "always looking for a deal": 1.1,
    "generous": 0.8,
    "charitable": 0.8,
    "fair": 1.0,
    "honest": 0.95,
    "loyal to paying customers": 0.9,
}

# Roll ranges mapped to price multipliers (d20)
ROLL_MODIFIERS = {
    (1, 5): 1.3,
    (6, 10): 1.1,
    (11, 15): 0.9,
    (16, 20): 0.7,
}


class PricingSystem:
    """Calculates trade prices with modifiers."""

    @staticmethod
    def get_roll_modifier(roll):
        """Get price modifier for a d20 roll."""
        if roll is None:
            return 1.0
        for (low, high), modifier in ROLL_MODIFIERS.items():
            if low <= roll <= high:
                return modifier
        return 1.0

    @staticmethod
    def get_personality_modifier(character):
        """
        Get price modifier based on seller's personality traits.
        Checks both character personality_traits and agent traits.
        """
        modifier = 1.0
        traits_to_check = []

        # Check character personality traits
        traits_to_check.extend(t.lower() for t in character.personality_traits)

        # Check agent behavioral traits if available
        from agent import Agent
        if isinstance(character.player, Agent):
            traits_to_check.extend(t.lower() for t in character.player.traits)

        for trait in traits_to_check:
            for keyword, mod in PERSONALITY_MODIFIERS.items():
                if keyword in trait:
                    modifier *= mod
                    break  # Only one match per trait

        return modifier

    @staticmethod
    def get_affiliation_modifier(seller, buyer):
        """
        Get price modifier based on buyer's affiliations.
        Uses seller's agent price_modifiers config first, then falls back
        to faction relations system. Uses the best (most favorable) modifier
        from any matching affiliation.
        """
        from agent import Agent
        from models.faction_relations import FactionRelations

        # Get buyer's affiliations (support both old and new format)
        buyer_affiliations = getattr(buyer, 'affiliations', None)
        if buyer_affiliations is None:
            buyer_affiliations = [getattr(buyer, 'affiliation', 'Independent')]

        # First check seller's agent price_modifiers
        if isinstance(seller.player, Agent):
            price_mods = seller.player.price_modifiers
            if price_mods:
                best_modifier = None
                for aff in buyer_affiliations:
                    if aff in price_mods:
                        mod = price_mods[aff]
                        if best_modifier is None or mod < best_modifier:
                            best_modifier = mod
                if best_modifier is not None:
                    return best_modifier

        # Fall back to faction relations system
        seller_affiliation = getattr(seller, 'affiliation', 'Independent')
        relations = FactionRelations.get_instance()
        return relations.get_price_modifier(seller_affiliation, buyer_affiliations)

    @staticmethod
    def calculate_price(item_name, quantity, seller, buyer, roll=None):
        """
        Calculate the final price for a trade.

        Args:
            item_name: Name of item being sold
            quantity: Number of items
            seller: Character selling the item
            buyer: Character buying the item
            roll: Optional d20 roll result

        Returns:
            dict with 'total', 'base_unit', 'base_total',
            'affiliation_mod', 'personality_mod', 'roll_mod', 'breakdown'
        """
        item_db = ItemDatabase.get_instance()
        item_data = item_db.get_item_data(item_name)

        if not item_data:
            return None

        base_unit = item_data.get("value", 0)
        base_total = base_unit * quantity

        affiliation_mod = PricingSystem.get_affiliation_modifier(seller, buyer)
        personality_mod = PricingSystem.get_personality_modifier(seller)
        roll_mod = PricingSystem.get_roll_modifier(roll)

        total = round(base_total * affiliation_mod * personality_mod * roll_mod)

        # Build breakdown string
        parts = [f"base: {base_total} caps"]
        if affiliation_mod != 1.0:
            pct = round((affiliation_mod - 1.0) * 100)
            sign = "+" if pct > 0 else ""
            parts.append(f"affiliation: {sign}{pct}%")
        if personality_mod != 1.0:
            pct = round((personality_mod - 1.0) * 100)
            sign = "+" if pct > 0 else ""
            parts.append(f"personality: {sign}{pct}%")
        if roll_mod != 1.0:
            pct = round((roll_mod - 1.0) * 100)
            sign = "+" if pct > 0 else ""
            parts.append(f"roll: {sign}{pct}%")

        breakdown = ", ".join(parts)

        return {
            "total": total,
            "base_unit": base_unit,
            "base_total": base_total,
            "affiliation_mod": affiliation_mod,
            "personality_mod": personality_mod,
            "roll_mod": roll_mod,
            "breakdown": breakdown,
        }
