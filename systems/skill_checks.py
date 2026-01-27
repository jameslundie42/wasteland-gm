"""
Skill check system implementing Fallout 2d20 mechanics.

Core Mechanics:
- Target Number (TN) = Attribute + Skill
- Roll 2d20 base, can buy up to 3 more with AP (max 5d20)
- Success = roll ≤ TN
- Critical Success = roll of 1 counts as 2 successes
- Complication = roll of 20 (still can succeed if ≤ TN)
- Difficulty = number of successes needed (0-5)
- Extra successes beyond difficulty generate Action Points
"""

import yaml
from pathlib import Path
from systems.dice_roller import get_dice_roller


class SkillDatabase:
    """Loads and provides access to skills and actions data."""

    _instance = None

    def __init__(self):
        data_dir = Path(__file__).parent.parent / "data"

        with open(data_dir / "skills.yaml", "r") as f:
            self._skills = yaml.safe_load(f)["skills"]

        with open(data_dir / "actions.yaml", "r") as f:
            self._actions = yaml.safe_load(f)["actions"]

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_skill(self, skill_name):
        """Get skill data by name (case-insensitive)."""
        for name, data in self._skills.items():
            if name.lower() == skill_name.lower():
                return {"name": name, **data}
        return None

    def get_action(self, action_name):
        """Get action data by name (case-insensitive)."""
        for name, data in self._actions.items():
            if name.lower() == action_name.lower():
                return {"name": name, **data}
        return None

    def get_skills_for_action(self, action_name):
        """Get list of applicable skills for an action."""
        action = self.get_action(action_name)
        if action:
            return action.get("skills", [])
        return []

    def get_stat_for_skill(self, skill_name):
        """Get the SPECIAL stat associated with a skill."""
        skill = self.get_skill(skill_name)
        if skill:
            return skill.get("stat")
        return None


def prompt_skill_choice(action_name, available_skills, character=None):
    """
    Prompt to choose a skill when multiple are available.

    Args:
        action_name: Name of the action
        available_skills: List of skill names
        character: Optional character (to show their skills)

    Returns:
        Selected skill name
    """
    if len(available_skills) == 1:
        return available_skills[0]

    print(f"  Choose skill for {action_name}:")
    for i, skill in enumerate(available_skills, 1):
        has_skill = ""
        if character:
            if skill.lower() in [s.lower() for s in character.skills]:
                has_skill = " (trained)"
        print(f"    {i}. {skill}{has_skill}")

    while True:
        choice = input("  Enter number (default 1): ").strip()
        if choice == "":
            return available_skills[0]
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(available_skills):
                return available_skills[idx]
        except ValueError:
            pass
        print("  Invalid choice.")


class SkillCheckResult:
    """Result of a skill check."""

    def __init__(self, rolls, target_number, difficulty, successes,
                 critical_successes, complications, action_points_generated,
                 passed, character_name=None, attribute=None, skill=None):
        self.rolls = rolls
        self.target_number = target_number
        self.difficulty = difficulty
        self.successes = successes
        self.critical_successes = critical_successes
        self.complications = complications
        self.action_points_generated = action_points_generated
        self.passed = passed
        self.character_name = character_name
        self.attribute = attribute
        self.skill = skill

    def __str__(self):
        """Format result as string."""
        lines = []

        if self.character_name:
            lines.append(f"=== {self.character_name}'s Skill Check ===")
        else:
            lines.append(f"=== Skill Check ===")

        if self.attribute and self.skill:
            lines.append(f"Test: {self.attribute.upper()} + {self.skill}")

        lines.append(f"Target Number: {self.target_number}")
        lines.append(f"Difficulty: {self.difficulty}")
        lines.append(f"Dice Pool: {len(self.rolls)}d20")
        lines.append(f"Rolls: {self.rolls}")

        # Show successes breakdown
        success_str = f"Successes: {self.successes}"
        if self.critical_successes > 0:
            success_str += f" ({self.critical_successes} critical)"
        lines.append(success_str)

        if self.complications > 0:
            lines.append(f"⚠️  Complications: {self.complications}")

        # Result
        if self.passed:
            lines.append(f"✓ SUCCESS")
            if self.action_points_generated > 0:
                lines.append(f"Action Points Generated: {self.action_points_generated}")
        else:
            lines.append(f"✗ FAILURE (needed {self.difficulty} successes)")

        return "\n".join(lines)


class SkillCheckSystem:
    """
    Manages skill checks using Fallout 2d20 mechanics.

    Key Features:
    - Character rolls use automated dice rolling (API or random)
    - GM rolls prompt for manual dice input
    - Full 2d20 system: TN, difficulty, dice pool, AP generation
    """

    DIFFICULTY_LEVELS = {
        'trivial': 0,
        'easy': 1,
        'medium': 2,
        'hard': 3,
        'very_hard': 4,
        'nearly_impossible': 5
    }

    def __init__(self):
        self.dice_roller = get_dice_roller()

    def calculate_target_number(self, character, attribute, skill_name=None):
        """
        Calculate Target Number for a skill check.

        Args:
            character: Character instance
            attribute: Attribute name (strength, perception, etc.)
            skill_name: Optional skill name (if None, uses attribute only)

        Returns:
            int: Target Number
        """
        # Get base attribute value
        attribute_value = character.get_effective_stat(attribute.lower())

        # Get skill value if provided
        skill_value = 0
        if skill_name:
            # For now, check if skill is in character's skill list (count as +1)
            # In future, this could be expanded to skill ranks
            if skill_name.lower() in [s.lower() for s in character.skills]:
                skill_value = 1

        return attribute_value + skill_value

    def count_successes(self, rolls, target_number):
        """
        Count successes from dice rolls.

        Args:
            rolls: List of d20 results
            target_number: Target Number

        Returns:
            tuple: (total_successes, critical_successes, complications)
        """
        total_successes = 0
        critical_successes = 0
        complications = 0

        for roll in rolls:
            if roll == 1:
                # Critical success = 2 successes
                total_successes += 2
                critical_successes += 1
            elif roll <= target_number:
                # Normal success
                total_successes += 1

            if roll == 20:
                # Complication (can still succeed if 20 ≤ TN)
                complications += 1

        return total_successes, critical_successes, complications

    def make_skill_test(self, character, attribute, skill_name=None, difficulty=2,
                       num_dice=2, focus=False, return_result_object=False):
        """
        Make a skill test for a character (automated dice rolling).

        Args:
            character: Character instance
            attribute: Attribute name
            skill_name: Optional skill name
            difficulty: Difficulty level (0-5 or string like 'medium')
            num_dice: Number of d20s to roll (2-5)
            focus: Whether character has focus (reroll 1s and 2s once)
            return_result_object: If True, return SkillCheckResult object

        Returns:
            SkillCheckResult or dict: Test result
        """
        # Convert string difficulty to number
        if isinstance(difficulty, str):
            difficulty = self.DIFFICULTY_LEVELS.get(difficulty.lower(), 2)

        # Clamp dice pool to 2-5
        num_dice = max(2, min(5, num_dice))

        # Calculate Target Number
        target_number = self.calculate_target_number(character, attribute, skill_name)

        # Roll dice (automated for character)
        rolls = self.dice_roller.roll_d20(num_dice=num_dice, agent_name=character.name)

        # Apply focus if applicable (reroll 1s and 2s once)
        if focus:
            rerolled = []
            for i, roll in enumerate(rolls):
                if roll <= 2:
                    new_roll = self.dice_roller.roll_d20(num_dice=1, agent_name=character.name)[0]
                    rerolled.append(f"die {i+1}: {roll}→{new_roll}")
                    rolls[i] = new_roll
            if rerolled:
                print(f"Focus rerolls: {', '.join(rerolled)}")

        # Count successes
        total_successes, critical_successes, complications = self.count_successes(rolls, target_number)

        # Check if passed
        passed = total_successes >= difficulty

        # Calculate Action Points generated
        action_points = max(0, total_successes - difficulty) if passed else 0

        # Create result
        result = SkillCheckResult(
            rolls=rolls,
            target_number=target_number,
            difficulty=difficulty,
            successes=total_successes,
            critical_successes=critical_successes,
            complications=complications,
            action_points_generated=action_points,
            passed=passed,
            character_name=character.name,
            attribute=attribute,
            skill=skill_name
        )

        if return_result_object:
            return result

        return {
            'rolls': rolls,
            'target_number': target_number,
            'difficulty': difficulty,
            'successes': total_successes,
            'critical_successes': critical_successes,
            'complications': complications,
            'action_points': action_points,
            'passed': passed
        }

    def make_gm_skill_test(self, attribute_value, skill_value=0, difficulty=2,
                          num_dice=2, context="", return_result_object=False):
        """
        Make a skill test for GM/NPC (manual dice input).

        Args:
            attribute_value: Attribute value
            skill_value: Skill value (default 0)
            difficulty: Difficulty level (0-5 or string)
            num_dice: Number of d20s to roll
            context: Context for the roll
            return_result_object: If True, return SkillCheckResult object

        Returns:
            SkillCheckResult or dict: Test result
        """
        # Convert string difficulty to number
        if isinstance(difficulty, str):
            difficulty = self.DIFFICULTY_LEVELS.get(difficulty.lower(), 2)

        # Clamp dice pool
        num_dice = max(2, min(5, num_dice))

        # Calculate Target Number
        target_number = attribute_value + skill_value

        # Prompt GM for manual roll
        full_context = f"{context}\nTarget Number: {target_number}, Difficulty: {difficulty}"
        rolls = self.dice_roller.prompt_gm_roll(num_dice, 20, full_context)

        # Count successes
        total_successes, critical_successes, complications = self.count_successes(rolls, target_number)

        # Check if passed
        passed = total_successes >= difficulty

        # Calculate Action Points
        action_points = max(0, total_successes - difficulty) if passed else 0

        # Create result
        result = SkillCheckResult(
            rolls=rolls,
            target_number=target_number,
            difficulty=difficulty,
            successes=total_successes,
            critical_successes=critical_successes,
            complications=complications,
            action_points_generated=action_points,
            passed=passed
        )

        if return_result_object:
            return result

        return {
            'rolls': rolls,
            'target_number': target_number,
            'difficulty': difficulty,
            'successes': total_successes,
            'critical_successes': critical_successes,
            'complications': complications,
            'action_points': action_points,
            'passed': passed
        }

    def make_opposed_test(self, character, opponent, attribute, skill_name=None,
                         num_dice_character=2, num_dice_opponent=2):
        """
        Make an opposed test between two characters.

        Args:
            character: Attacking character
            opponent: Defending character
            attribute: Attribute to use
            skill_name: Optional skill name
            num_dice_character: Dice pool for character
            num_dice_opponent: Dice pool for opponent

        Returns:
            dict: Result with both rolls and winner
        """
        # Character makes their test
        character_result = self.make_skill_test(
            character, attribute, skill_name,
            difficulty=0,  # No base difficulty for opposed
            num_dice=num_dice_character,
            return_result_object=True
        )

        # Opponent makes defense test
        opponent_result = self.make_skill_test(
            opponent, attribute, skill_name,
            difficulty=0,
            num_dice=num_dice_opponent,
            return_result_object=True
        )

        # Defender's successes become attacker's difficulty
        character_result.difficulty = opponent_result.successes
        character_result.passed = character_result.successes >= character_result.difficulty
        character_result.action_points_generated = max(0, character_result.successes - character_result.difficulty)

        return {
            'character_result': character_result,
            'opponent_result': opponent_result,
            'winner': character.name if character_result.passed else opponent.name,
            'margin': abs(character_result.successes - opponent_result.successes)
        }

    def make_gm_opposed_test(self, character, gm_attribute, gm_skill=0,
                           character_attribute=None, character_skill_name=None,
                           num_dice_character=2, num_dice_gm=2, context=""):
        """
        Make an opposed test between character and GM/NPC.

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
            dict: Result with both rolls and winner
        """
        # Character makes their test (automated)
        character_result = self.make_skill_test(
            character, character_attribute, character_skill_name,
            difficulty=0,
            num_dice=num_dice_character,
            return_result_object=True
        )

        # GM makes defense test (manual)
        gm_result = self.make_gm_skill_test(
            gm_attribute, gm_skill,
            difficulty=0,
            num_dice=num_dice_gm,
            context=f"{context} (Opposed test vs {character.name})",
            return_result_object=True
        )

        # Defender's successes become attacker's difficulty
        character_result.difficulty = gm_result.successes
        character_result.passed = character_result.successes >= character_result.difficulty
        character_result.action_points_generated = max(0, character_result.successes - character_result.difficulty)

        return {
            'character_result': character_result,
            'gm_result': gm_result,
            'winner': character.name if character_result.passed else "GM",
            'margin': abs(character_result.successes - gm_result.successes)
        }

    def roll_combat_dice(self, num_dice, damage_rating=0):
        """
        Roll Combat Dice (CD) for damage.

        Combat Die faces:
        - 1: 1 damage
        - 2: 2 damage
        - 3-4: Blank
        - 5-6: 1 damage + effect

        Args:
            num_dice: Number of Combat Dice to roll
            damage_rating: Base damage rating to add

        Returns:
            dict: Damage total, effects triggered, individual rolls
        """
        rolls = self.dice_roller._roll_local(num_dice, 6)

        total_damage = damage_rating
        effects = 0
        damage_breakdown = []

        for roll in rolls:
            if roll == 1:
                total_damage += 1
                damage_breakdown.append("1 dmg")
            elif roll == 2:
                total_damage += 2
                damage_breakdown.append("2 dmg")
            elif roll == 3 or roll == 4:
                damage_breakdown.append("blank")
            elif roll == 5 or roll == 6:
                total_damage += 1
                effects += 1
                damage_breakdown.append("1 dmg + effect")

        return {
            'rolls': rolls,
            'breakdown': damage_breakdown,
            'total_damage': total_damage,
            'effects': effects
        }

    def make_barter_check(self, buyer, seller, skill_name="Barter"):
        """
        Make an opposed barter check for trading.

        Args:
            buyer: Character buying
            seller: Character selling
            skill_name: Skill to use (default Barter)

        Returns:
            dict with 'winner', 'price_modifier', 'margin', 'buyer_result', 'seller_result'
        """
        db = SkillDatabase.get_instance()
        stat = db.get_stat_for_skill(skill_name) or "charisma"

        print(f"\n  === Opposed {skill_name} Check ===")
        print(f"  {buyer.name} (buyer) vs {seller.name} (seller)")

        # Both make skill tests
        buyer_result = self.make_skill_test(
            buyer, stat, skill_name,
            difficulty=0,
            num_dice=2,
            return_result_object=True
        )
        print(f"  {buyer.name}: {buyer_result.rolls} -> {buyer_result.successes} successes")

        seller_result = self.make_skill_test(
            seller, stat, skill_name,
            difficulty=0,
            num_dice=2,
            return_result_object=True
        )
        print(f"  {seller.name}: {seller_result.rolls} -> {seller_result.successes} successes")

        margin = buyer_result.successes - seller_result.successes

        # Price modifier based on margin
        # Buyer wins: lower price, Seller wins: higher price
        # Each success difference = 10% modifier
        if margin > 0:
            winner = buyer
            price_modifier = 1.0 - (margin * 0.1)  # Buyer wins, price goes down
            price_modifier = max(0.5, price_modifier)  # Cap at 50% discount
        elif margin < 0:
            winner = seller
            price_modifier = 1.0 + (abs(margin) * 0.1)  # Seller wins, price goes up
            price_modifier = min(1.5, price_modifier)  # Cap at 50% markup
        else:
            winner = None
            price_modifier = 1.0  # Tie, base price

        pct = round((price_modifier - 1.0) * 100)
        sign = "+" if pct > 0 else ""
        if winner:
            print(f"  Winner: {winner.name} ({sign}{pct}% price)")
        else:
            print(f"  Tie! Base price applies.")

        return {
            'winner': winner,
            'price_modifier': price_modifier,
            'margin': abs(margin),
            'buyer_result': buyer_result,
            'seller_result': seller_result
        }


# Global instance
_skill_check_system = None

def get_skill_check_system():
    """Get global skill check system instance."""
    global _skill_check_system
    if _skill_check_system is None:
        _skill_check_system = SkillCheckSystem()
    return _skill_check_system
