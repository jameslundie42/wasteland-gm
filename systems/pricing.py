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
        Get price modifier based on buyer's affiliation.
        Uses seller's agent price_modifiers config.
        """
        from agent import Agent
        if not isinstance(seller.player, Agent):
            return 1.0

        price_mods = seller.player.price_modifiers
        if not price_mods:
            return 1.0

        return price_mods.get(buyer.affiliation, 1.0)

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
