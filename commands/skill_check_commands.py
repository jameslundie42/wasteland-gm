"""
Command handlers for skill checks.
"""

from systems.skill_checks import get_skill_check_system


class SkillCheckCommands:
    """Handlers for skill check commands."""

    @staticmethod
    def make_skill_check(character, attribute, skill_name=None, difficulty='medium',
                        num_dice=2, focus=False):
        """
        Make a skill check for a character.

        Args:
            character: Character instance
            attribute: Attribute name
            skill_name: Optional skill name
            difficulty: Difficulty (0-5 or string)
            num_dice: Number of d20s (2-5)
            focus: Whether character has focus

        Returns:
            str: Formatted result
        """
        system = get_skill_check_system()

        result = system.make_skill_test(
            character, attribute, skill_name,
            difficulty=difficulty,
            num_dice=num_dice,
            focus=focus,
            return_result_object=True
        )

        return str(result)

    @staticmethod
    def make_gm_check(attribute_value, skill_value=0, difficulty='medium',
                     num_dice=2, context=""):
        """
        Make a skill check for GM/NPC.

        Args:
            attribute_value: Attribute value
            skill_value: Skill value
            difficulty: Difficulty (0-5 or string)
            num_dice: Number of d20s (2-5)
            context: Context for the roll

        Returns:
            str: Formatted result
        """
        system = get_skill_check_system()

        result = system.make_gm_skill_test(
            attribute_value, skill_value,
            difficulty=difficulty,
            num_dice=num_dice,
            context=context,
            return_result_object=True
        )

        return str(result)

    @staticmethod
    def make_opposed_check(character, opponent, attribute, skill_name=None,
                          num_dice_character=2, num_dice_opponent=2):
        """
        Make an opposed check between two characters.

        Args:
            character: Attacking character
            opponent: Defending character
            attribute: Attribute name
            skill_name: Optional skill name
            num_dice_character: Character's dice pool
            num_dice_opponent: Opponent's dice pool

        Returns:
            str: Formatted result
        """
        system = get_skill_check_system()

        result = system.make_opposed_test(
            character, opponent, attribute, skill_name,
            num_dice_character, num_dice_opponent
        )

        lines = []
        lines.append("\n=== Opposed Test ===")
        lines.append(f"{character.name} vs {opponent.name}")
        lines.append("")
        lines.append(str(result['character_result']))
        lines.append("")
        lines.append(str(result['opponent_result']))
        lines.append("")
        lines.append(f"Winner: {result['winner']} (margin: {result['margin']})")

        return "\n".join(lines)

    @staticmethod
    def make_gm_opposed_check(character, gm_attribute, gm_skill=0,
                             character_attribute=None, character_skill_name=None,
                             num_dice_character=2, num_dice_gm=2, context=""):
        """
        Make an opposed check between character and GM/NPC.

        Args:
            character: Character instance
            gm_attribute: GM's attribute value
            gm_skill: GM's skill value
            character_attribute: Character's attribute name
            character_skill_name: Character's skill name
            num_dice_character: Character's dice pool
            num_dice_gm: GM's dice pool
            context: Context for GM roll

        Returns:
            str: Formatted result
        """
        # Default to same attribute if not specified
        if character_attribute is None:
            character_attribute = "strength"  # Fallback

        system = get_skill_check_system()

        result = system.make_gm_opposed_test(
            character, gm_attribute, gm_skill,
            character_attribute, character_skill_name,
            num_dice_character, num_dice_gm, context
        )

        lines = []
        lines.append("\n=== Opposed Test ===")
        lines.append(f"{character.name} vs GM/NPC")
        lines.append("")
        lines.append(str(result['character_result']))
        lines.append("")
        lines.append(str(result['gm_result']))
        lines.append("")
        lines.append(f"Winner: {result['winner']} (margin: {result['margin']})")

        return "\n".join(lines)

    @staticmethod
    def roll_combat_dice(num_dice, damage_rating=0, context=""):
        """
        Roll Combat Dice for damage.

        Args:
            num_dice: Number of Combat Dice
            damage_rating: Base damage rating
            context: Context for the roll

        Returns:
            str: Formatted result
        """
        system = get_skill_check_system()

        result = system.roll_combat_dice(num_dice, damage_rating)

        lines = []
        if context:
            lines.append(f"=== {context} ===")
        else:
            lines.append("=== Combat Dice ===")

        lines.append(f"Dice Pool: {num_dice}CD")
        if damage_rating > 0:
            lines.append(f"Base Damage: {damage_rating}")

        lines.append(f"Rolls: {result['rolls']}")
        lines.append(f"Results: {', '.join(result['breakdown'])}")
        lines.append(f"Total Damage: {result['total_damage']}")

        if result['effects'] > 0:
            lines.append(f"Effects Triggered: {result['effects']}")

        return "\n".join(lines)

    @staticmethod
    def quick_check(character, attribute, difficulty='medium'):
        """
        Quick skill check with default settings.

        Args:
            character: Character instance
            attribute: Attribute name
            difficulty: Difficulty level

        Returns:
            str: Formatted result
        """
        return SkillCheckCommands.make_skill_check(
            character, attribute, None, difficulty, 2, False
        )

    @staticmethod
    def list_difficulties():
        """
        List available difficulty levels.

        Returns:
            str: Formatted list
        """
        system = get_skill_check_system()
        lines = ["=== Difficulty Levels ==="]
        for name, value in sorted(system.DIFFICULTY_LEVELS.items(), key=lambda x: x[1]):
            lines.append(f"  {name.replace('_', ' ').title()}: {value} successes")
        return "\n".join(lines)
