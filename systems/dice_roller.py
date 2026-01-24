"""
Dice rolling service for character actions.
Uses online dice rolling API for fairness.
"""

import random
import requests
from datetime import datetime


class DiceRoller:
    """
    Handles dice rolling for the game.

    - Character actions: Use dice rolling API (random.org or fallback to random)
    - GM/NPC actions: Prompt GM to roll manually
    """

    def __init__(self, use_api=True):
        """
        Initialize dice roller.

        Args:
            use_api: Whether to use online API (True) or local random (False)
        """
        self.use_api = use_api
        self.api_url = "https://www.random.org/integers/"
        self.last_roll_time = None

    def roll_d20(self, num_dice=1, agent_name=None):
        """
        Roll d20 dice.

        Args:
            num_dice: Number of d20s to roll
            agent_name: Name of character rolling (for logging)

        Returns:
            list: List of dice results
        """
        if self.use_api:
            try:
                return self._roll_via_api(num_dice, 20)
            except Exception as e:
                print(f"API roll failed ({e}), using local random")
                return self._roll_local(num_dice, 20)
        else:
            return self._roll_local(num_dice, 20)

    def _roll_via_api(self, num_dice, die_size):
        """
        Roll dice using random.org API.

        Args:
            num_dice: Number of dice
            die_size: Size of die (20 for d20)

        Returns:
            list: List of dice results
        """
        params = {
            'num': num_dice,
            'min': 1,
            'max': die_size,
            'col': 1,
            'base': 10,
            'format': 'plain',
            'rnd': 'new'
        }

        response = requests.get(self.api_url, params=params, timeout=5)
        response.raise_for_status()

        results = [int(x) for x in response.text.strip().split('\n')]
        self.last_roll_time = datetime.now()

        return results

    def _roll_local(self, num_dice, die_size):
        """
        Roll dice using local random.

        Args:
            num_dice: Number of dice
            die_size: Size of die

        Returns:
            list: List of dice results
        """
        return [random.randint(1, die_size) for _ in range(num_dice)]

    def prompt_gm_roll(self, num_dice, die_size, context=""):
        """
        Prompt GM to roll dice manually.

        Args:
            num_dice: Number of dice to roll
            die_size: Size of die
            context: Context for why they're rolling

        Returns:
            list: List of dice results entered by GM
        """
        print(f"\n=== GM ROLL REQUIRED ===")
        print(f"Context: {context}")
        print(f"Please roll {num_dice}d{die_size} and enter the results.")

        results = []
        for i in range(num_dice):
            while True:
                try:
                    roll_input = input(f"Die {i+1} result (1-{die_size}): ")
                    result = int(roll_input)
                    if 1 <= result <= die_size:
                        results.append(result)
                        break
                    else:
                        print(f"Invalid: must be between 1 and {die_size}")
                except ValueError:
                    print("Invalid: please enter a number")

        return results

    def roll_2d20(self, agent_name=None):
        """
        Roll 2d20 for character skill check.

        Args:
            agent_name: Name of character rolling

        Returns:
            dict: Roll results with both dice
        """
        rolls = self.roll_d20(num_dice=2, agent_name=agent_name)

        return {
            'die1': rolls[0],
            'die2': rolls[1],
            'rolls': rolls,
            'highest': max(rolls),
            'lowest': min(rolls),
            'sum': sum(rolls),
            'average': sum(rolls) / 2
        }

    def gm_roll_2d20(self, context=""):
        """
        Prompt GM to roll 2d20.

        Args:
            context: Why they're rolling

        Returns:
            dict: Roll results
        """
        rolls = self.prompt_gm_roll(2, 20, context)

        return {
            'die1': rolls[0],
            'die2': rolls[1],
            'rolls': rolls,
            'highest': max(rolls),
            'lowest': min(rolls),
            'sum': sum(rolls),
            'average': sum(rolls) / 2
        }


# Global instance
_dice_roller = None

def get_dice_roller():
    """Get global dice roller instance."""
    global _dice_roller
    if _dice_roller is None:
        _dice_roller = DiceRoller(use_api=True)
    return _dice_roller
