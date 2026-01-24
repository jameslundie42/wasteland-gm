"""
Stat modification system for handling item effects and conditions.
"""

import random
from models.stat_modifier import StatModifier


class StatSystem:
    """
    Manages stat modifications, buffs, debuffs, and conditions.
    """

    @staticmethod
    def apply_item_effect(character, item, body_part=None):
        """
        Apply item effects to character.

        Args:
            character: Character instance
            item: Item instance
            body_part: Optional body part name to target

        Returns:
            str: Description of effects applied
        """
        if not item.effects:
            return "No effect."

        messages = []

        for effect_name, effect_data in item.effects.items():
            if effect_name == "heal":
                # Instant healing
                if body_part:
                    # Heal specific body part
                    part = character.body_parts.get_part(body_part)
                    if part:
                        result = part.heal(effect_data)
                        messages.append(f"Healed {body_part} for {result['healed']} HP ({result['current_health']}/{part.max_health})")
                        # Also heal overall HP by a portion
                        character.heal(effect_data // 2)
                    else:
                        messages.append(f"Unknown body part: {body_part}")
                else:
                    # Heal overall HP
                    result = character.heal(effect_data)
                    messages.append(f"Healed {result['healed']} HP ({result['current_health']}/{result['max_health']})")

            elif effect_name == "remove_radiation":
                # Remove radiation
                old_rads = character.radiation
                character.remove_radiation(effect_data)
                removed = old_rads - character.radiation
                messages.append(f"Removed {removed} rads (now at {character.radiation})")

            elif effect_name == "remove_condition":
                # Remove a condition
                condition = effect_data
                if condition == "crippled":
                    # Special handling for crippled condition
                    if body_part:
                        # Cure specific body part
                        part = character.body_parts.get_part(body_part)
                        if part and part.is_crippled:
                            part.remove_condition("crippled")
                            messages.append(f"Cured crippled {body_part}")
                        elif part:
                            messages.append(f"{body_part.capitalize()} is not crippled")
                        else:
                            messages.append(f"Unknown body part: {body_part}")
                    else:
                        # Cure all crippled body parts
                        cured = character.body_parts.cure_all_crippled_parts()
                        if cured:
                            messages.append(f"Cured crippled limbs: {', '.join(cured)}")
                        else:
                            messages.append("No crippled limbs to cure")
                elif character.has_condition(condition):
                    character.remove_condition(condition)
                    messages.append(f"Cured condition: {condition}")
                else:
                    messages.append(f"No {condition} condition to cure")

            elif effect_name == "radiation_resistance":
                # Temporary radiation resistance buff
                modifier = StatModifier(
                    "radiation_resistance",
                    effect_data["value"],
                    duration=effect_data["duration"],
                    source=item.name,
                    modifier_type="flat"
                )
                character.add_stat_modifier(modifier)
                duration_min = effect_data["duration"] / 60
                messages.append(f"+{effect_data['value']}% radiation resistance for {duration_min:.1f} minutes")

            elif effect_name == "damage_resistance":
                # Temporary damage resistance buff
                modifier = StatModifier(
                    "damage_resistance",
                    effect_data["value"],
                    duration=effect_data["duration"],
                    source=item.name,
                    modifier_type="flat"
                )
                character.add_stat_modifier(modifier)
                duration_min = effect_data["duration"] / 60
                messages.append(f"+{effect_data['value']}% damage resistance for {duration_min:.1f} minutes")

            elif effect_name == "addiction_chance":
                # Check for addiction
                chance = effect_data
                if random.random() < chance:
                    condition = f"{item.name.lower()}_addiction"
                    character.add_condition(condition)
                    messages.append(f"[WARNING] Addicted to {item.name}!")

            elif effect_name in ["strength", "perception", "endurance", "charisma",
                               "intelligence", "agility", "luck"]:
                # SPECIAL stat modifier
                if isinstance(effect_data, dict):
                    # Temporary modifier with duration
                    modifier = StatModifier(
                        effect_name,
                        effect_data["value"],
                        duration=effect_data.get("duration"),
                        source=item.name,
                        modifier_type="flat"
                    )
                    character.add_stat_modifier(modifier)

                    if effect_data.get("duration"):
                        duration_sec = effect_data["duration"]
                        if duration_sec >= 60:
                            duration_str = f"{duration_sec/60:.1f} minutes"
                        else:
                            duration_str = f"{duration_sec} seconds"
                        messages.append(f"+{effect_data['value']} {effect_name.capitalize()} for {duration_str}")
                    else:
                        messages.append(f"+{effect_data['value']} {effect_name.capitalize()} (permanent)")
                else:
                    # Permanent modifier
                    current_base = character.get_base_stat(effect_name)
                    character.special.set_base_stat(effect_name, current_base + effect_data)
                    messages.append(f"+{effect_data} {effect_name.capitalize()} (permanent)")

        return " ".join(messages) if messages else "No effect."

    @staticmethod
    def apply_condition(character, condition_name, description="", effects=None):
        """
        Apply a condition to a character.

        Args:
            character: Character instance
            condition_name: Name of the condition
            description: Description of the condition
            effects: List of StatModifier objects to apply

        Returns:
            str: Result message
        """
        if character.has_condition(condition_name):
            return f"{character.name} already has {condition_name}."

        character.add_condition(condition_name)

        if effects:
            for modifier in effects:
                character.add_stat_modifier(modifier)

        return f"{character.name} is now {condition_name}. {description}"

    @staticmethod
    def remove_condition(character, condition_name):
        """
        Remove a condition from a character.

        Args:
            character: Character instance
            condition_name: Name of the condition

        Returns:
            str: Result message
        """
        if not character.has_condition(condition_name):
            return f"{character.name} doesn't have {condition_name}."

        character.remove_condition(condition_name)

        # Remove associated modifiers
        character.remove_stat_modifier(condition_name)

        return f"{condition_name} removed from {character.name}."

    @staticmethod
    def update_all_modifiers(character):
        """
        Update and remove expired modifiers.

        Args:
            character: Character instance

        Returns:
            list: List of expired modifiers
        """
        expired = character.update_modifiers()

        if expired:
            print(f"\nExpired effects for {character.name}:")
            for modifier in expired:
                print(f"  - {modifier.source} ({modifier.stat_name})")

        return expired
