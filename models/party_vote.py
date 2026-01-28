"""
Party voting system for group decisions.

Supports two modes:
- Majority Vote: Group decides together, majority wins
- Split Vote: Party can divide, creating parallel scenes
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class VoteOption:
    """A single option in a vote."""
    number: int
    description: str
    votes: list = field(default_factory=list)  # List of character names

    def add_vote(self, character_name: str):
        if character_name not in self.votes:
            self.votes.append(character_name)

    @property
    def vote_count(self):
        return len(self.votes)


class PartyVote:
    """
    Manages a party vote with multiple options.

    Modes:
    - "majority": Most votes wins, party acts together
    - "split": Party divides based on votes, creates parallel scenes
    """

    def __init__(self, question: str, options: list, mode: str = "majority"):
        self.question = question
        self.mode = mode  # "majority" or "split"
        self.options = {}
        self.timestamp = datetime.now().isoformat()
        self.is_complete = False
        self.result = None

        for i, opt_desc in enumerate(options, 1):
            self.options[i] = VoteOption(number=i, description=opt_desc)

    def cast_vote(self, character_name: str, option_number: int) -> bool:
        """Cast a vote for an option. Returns True if successful."""
        if option_number not in self.options:
            return False

        # Remove any existing vote from this character
        for opt in self.options.values():
            if character_name in opt.votes:
                opt.votes.remove(character_name)

        self.options[option_number].add_vote(character_name)
        return True

    def get_vote(self, character_name: str) -> Optional[int]:
        """Get which option a character voted for."""
        for num, opt in self.options.items():
            if character_name in opt.votes:
                return num
        return None

    def get_results(self) -> dict:
        """Get vote tallies."""
        return {
            num: {
                "description": opt.description,
                "votes": opt.votes.copy(),
                "count": opt.vote_count
            }
            for num, opt in self.options.items()
        }

    def get_winner(self) -> Optional[VoteOption]:
        """Get the winning option (for majority mode)."""
        if not self.options:
            return None

        max_votes = 0
        winner = None
        for opt in self.options.values():
            if opt.vote_count > max_votes:
                max_votes = opt.vote_count
                winner = opt

        return winner

    def get_split_groups(self) -> dict:
        """
        Get groups for split mode.
        Returns dict of option_number -> list of character names
        Only includes options with at least one vote.
        """
        groups = {}
        for num, opt in self.options.items():
            if opt.votes:
                groups[num] = {
                    "description": opt.description,
                    "members": opt.votes.copy()
                }
        return groups

    def resolve(self) -> dict:
        """
        Resolve the vote and return results.

        For majority: Returns the winning option
        For split: Returns groups and their chosen actions
        """
        self.is_complete = True

        if self.mode == "majority":
            winner = self.get_winner()
            if winner:
                self.result = {
                    "mode": "majority",
                    "winner": winner.number,
                    "description": winner.description,
                    "votes": winner.votes.copy(),
                    "all_results": self.get_results()
                }
            else:
                self.result = {
                    "mode": "majority",
                    "winner": None,
                    "description": "No votes cast",
                    "all_results": self.get_results()
                }
        else:  # split mode
            groups = self.get_split_groups()
            self.result = {
                "mode": "split",
                "groups": groups,
                "all_results": self.get_results()
            }

        return self.result

    def get_display(self, show_votes: bool = False) -> str:
        """Get formatted display of the vote."""
        lines = []
        lines.append(f"\n{'=' * 50}")
        lines.append(f"  PARTY VOTE: {self.question}")
        lines.append(f"  Mode: {'Majority Rule' if self.mode == 'majority' else 'Split Party'}")
        lines.append(f"{'=' * 50}")

        for num, opt in self.options.items():
            vote_str = f" ({opt.vote_count} votes)" if show_votes else ""
            lines.append(f"  [{num}] {opt.description}{vote_str}")
            if show_votes and opt.votes:
                lines.append(f"      Voters: {', '.join(opt.votes)}")

        lines.append(f"{'=' * 50}")

        return "\n".join(lines)

    def get_result_display(self) -> str:
        """Get formatted display of vote results."""
        if not self.is_complete:
            return "Vote not yet resolved."

        lines = []
        lines.append(f"\n{'=' * 50}")
        lines.append(f"  VOTE RESULTS: {self.question}")
        lines.append(f"{'=' * 50}")

        if self.mode == "majority":
            lines.append(f"\n  The party decides: {self.result['description']}")
            lines.append(f"  Votes: {', '.join(self.result['votes'])}")

            # Show full tally
            lines.append(f"\n  Full tally:")
            for num, data in self.result['all_results'].items():
                lines.append(f"    [{num}] {data['description']}: {data['count']} votes")

        else:  # split
            lines.append(f"\n  The party splits up:")
            for num, group in self.result['groups'].items():
                members = ', '.join(group['members'])
                lines.append(f"\n  Group {num}: {group['description']}")
                lines.append(f"    Members: {members}")

        lines.append(f"\n{'=' * 50}")

        return "\n".join(lines)


def generate_vote_prompt(vote: PartyVote, character_name: str, character_traits: list = None) -> str:
    """
    Generate a prompt for an AI agent to vote.

    Args:
        vote: The PartyVote instance
        character_name: Name of the character voting
        character_traits: Optional personality traits to consider

    Returns:
        str: Prompt for the agent
    """
    prompt_parts = [
        f"The party needs to make a decision: {vote.question}",
        f"\nOptions:"
    ]

    for num, opt in vote.options.items():
        prompt_parts.append(f"  {num}. {opt.description}")

    if vote.mode == "split":
        prompt_parts.append(f"\nThis is a SPLIT vote - the party may divide based on preferences.")
        prompt_parts.append("Choose which group you want to join.")
    else:
        prompt_parts.append(f"\nThis is a MAJORITY vote - the party will do what most people choose.")

    if character_traits:
        prompt_parts.append(f"\nConsider your character's personality: {', '.join(character_traits)}")

    prompt_parts.append(f"\nAs {character_name}, which option do you choose?")
    prompt_parts.append("Respond with ONLY the option number (1, 2, 3, etc.) and a brief reason.")
    prompt_parts.append("Format: [NUMBER] - reason")

    return "\n".join(prompt_parts)


def parse_vote_response(response: str, num_options: int) -> Optional[int]:
    """
    Parse a vote response to extract the chosen option number.

    Args:
        response: The agent's response
        num_options: Number of valid options

    Returns:
        int or None: The chosen option number, or None if invalid
    """
    import re

    # Look for patterns like "1", "[1]", "Option 1", "1.", "1 -", etc.
    patterns = [
        r'^\[?(\d+)\]?',  # [1] or 1 at start
        r'Option\s*(\d+)',  # Option 1
        r'^(\d+)\s*[-.]',  # 1. or 1 -
        r'choose\s*(?:option\s*)?(\d+)',  # choose 1, choose option 1
        r'vote\s*(?:for\s*)?(?:option\s*)?(\d+)',  # vote for 1
    ]

    for pattern in patterns:
        match = re.search(pattern, response, re.IGNORECASE)
        if match:
            num = int(match.group(1))
            if 1 <= num <= num_options:
                return num

    # Fallback: look for any single digit in valid range
    for char in response:
        if char.isdigit():
            num = int(char)
            if 1 <= num <= num_options:
                return num

    return None
