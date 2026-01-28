"""
Table State system for tracking the flow of play around the table.

Manages spotlight, character states, action log, and round-robin turns
to create a more natural tabletop RPG experience.
"""

from dataclasses import dataclass, field
from typing import Optional
from collections import deque
from datetime import datetime


@dataclass
class CharacterState:
    """Tracks what a character is currently doing."""
    name: str
    current_action: str = "waiting"  # What they're doing right now
    talking_to: Optional[str] = None  # Who they're addressing
    stance: str = "neutral"  # alert, relaxed, defensive, aggressive, etc.
    last_spoke: Optional[str] = None  # Timestamp of last response

    def to_dict(self):
        return {
            "name": self.name,
            "current_action": self.current_action,
            "talking_to": self.talking_to,
            "stance": self.stance,
            "last_spoke": self.last_spoke
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            name=data["name"],
            current_action=data.get("current_action", "waiting"),
            talking_to=data.get("talking_to"),
            stance=data.get("stance", "neutral"),
            last_spoke=data.get("last_spoke")
        )


@dataclass
class ActionLogEntry:
    """A single entry in the action log."""
    timestamp: str
    actor: str  # Character name or "GM"
    action_type: str  # "narration", "dialogue", "action", "roll", etc.
    summary: str  # Brief description
    addressed_to: Optional[str] = None  # Who it was directed at

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "actor": self.actor,
            "action_type": self.action_type,
            "summary": self.summary,
            "addressed_to": self.addressed_to
        }

    @classmethod
    def from_dict(cls, data):
        return cls(**data)


class TableState:
    """
    Manages the state of play around the virtual table.

    Tracks:
    - Who has the spotlight (current speaker/actor)
    - Round-robin order for group responses
    - What each character is currently doing
    - Recent action log for context
    - Who the GM is addressing
    """

    def __init__(self):
        # Spotlight - who currently has the floor
        self.spotlight: Optional[str] = None

        # Round-robin for group responses
        self.round_robin_order: list = []  # PC names in order
        self.current_index: int = 0
        self.round_robin_active: bool = False

        # Character states
        self.character_states: dict = {}  # name -> CharacterState

        # Action log (recent actions for context)
        self.action_log: deque = deque(maxlen=10)  # Keep last 10 actions

        # Current addressing
        self.addressed_to: Optional[list] = None  # None = everyone, list = specific names

        # NPCs present but not in round-robin
        self.npc_names: list = []

    def set_round_robin_order(self, pc_names: list, npc_names: list = None):
        """Set the order for going around the table."""
        self.round_robin_order = list(pc_names)
        self.npc_names = list(npc_names) if npc_names else []
        self.current_index = 0

        # Initialize character states for all
        for name in pc_names + (npc_names or []):
            if name not in self.character_states:
                self.character_states[name] = CharacterState(name=name)

    def get_current_speaker(self) -> Optional[str]:
        """Get who should speak next in round-robin."""
        if not self.round_robin_order:
            return None
        if self.current_index >= len(self.round_robin_order):
            return None
        return self.round_robin_order[self.current_index]

    def advance_round_robin(self) -> tuple:
        """
        Move to the next speaker in round-robin.

        Returns:
            tuple: (next_speaker_name, is_round_complete)
        """
        if not self.round_robin_order:
            return None, True

        self.current_index += 1

        if self.current_index >= len(self.round_robin_order):
            # Round complete
            self.current_index = 0
            self.round_robin_active = False
            return None, True

        return self.round_robin_order[self.current_index], False

    def start_round_robin(self, addressed_to: list = None):
        """Start a new round-robin for group response."""
        self.current_index = 0
        self.round_robin_active = True
        self.addressed_to = addressed_to

        # If addressing specific characters, filter the order
        if addressed_to:
            # Reorder so addressed characters go first
            addressed_set = set(name.lower() for name in addressed_to)
            addressed_pcs = [n for n in self.round_robin_order if n.lower() in addressed_set]
            # Only the addressed PCs respond
            if addressed_pcs:
                self.round_robin_order_backup = self.round_robin_order.copy()
                self.round_robin_order = addressed_pcs

    def end_round_robin(self):
        """End the current round-robin."""
        self.round_robin_active = False
        self.addressed_to = None
        # Restore full order if we had filtered it
        if hasattr(self, 'round_robin_order_backup'):
            self.round_robin_order = self.round_robin_order_backup
            delattr(self, 'round_robin_order_backup')

    def set_spotlight(self, name: str):
        """Give the spotlight to a specific character."""
        self.spotlight = name
        self.round_robin_active = False

    def clear_spotlight(self):
        """Clear the spotlight (return to group mode)."""
        self.spotlight = None

    def update_character_state(self, name: str, action: str = None,
                                talking_to: str = None, stance: str = None):
        """Update a character's current state."""
        if name not in self.character_states:
            self.character_states[name] = CharacterState(name=name)

        state = self.character_states[name]
        if action:
            state.current_action = action
        if talking_to is not None:  # Allow clearing with empty string
            state.talking_to = talking_to if talking_to else None
        if stance:
            state.stance = stance
        state.last_spoke = datetime.now().isoformat()

    def get_character_state(self, name: str) -> Optional[CharacterState]:
        """Get a character's current state."""
        return self.character_states.get(name)

    def log_action(self, actor: str, action_type: str, summary: str,
                   addressed_to: str = None):
        """Add an entry to the action log."""
        entry = ActionLogEntry(
            timestamp=datetime.now().isoformat(),
            actor=actor,
            action_type=action_type,
            summary=summary,
            addressed_to=addressed_to
        )
        self.action_log.append(entry)

    def get_recent_actions(self, count: int = 5) -> list:
        """Get the most recent actions."""
        return list(self.action_log)[-count:]

    def get_context_summary(self) -> str:
        """Get a summary of recent context for agent prompts."""
        lines = []

        # Recent actions
        recent = self.get_recent_actions(5)
        if recent:
            lines.append("Recent events:")
            for entry in recent:
                if entry.addressed_to:
                    lines.append(f"  - {entry.actor} (to {entry.addressed_to}): {entry.summary}")
                else:
                    lines.append(f"  - {entry.actor}: {entry.summary}")

        return "\n".join(lines)

    def get_table_display(self) -> str:
        """Get formatted display of current table state."""
        lines = []
        lines.append("\n" + "=" * 60)
        lines.append("                      TABLE STATE")
        lines.append("=" * 60)

        # Spotlight/Addressing
        if self.spotlight:
            lines.append(f"  Spotlight: {self.spotlight}")
        elif self.round_robin_active:
            current = self.get_current_speaker()
            lines.append(f"  Round Robin: {current}'s turn ({self.current_index + 1}/{len(self.round_robin_order)})")
        else:
            lines.append("  Spotlight: Open (group)")

        if self.addressed_to:
            lines.append(f"  Addressing: {', '.join(self.addressed_to)}")

        lines.append("-" * 60)

        # Character states - PCs first
        lines.append("  CHARACTER STATES:")
        for name in self.round_robin_order:
            state = self.character_states.get(name)
            if state:
                action = state.current_action[:40] if state.current_action else "waiting"
                lines.append(f"    {name}: {action}")

        # NPCs
        for name in self.npc_names:
            state = self.character_states.get(name)
            if state:
                action = state.current_action[:40] if state.current_action else "waiting"
                lines.append(f"    [{name} - NPC]: {action}")

        lines.append("-" * 60)

        # Recent actions
        recent = self.get_recent_actions(5)
        if recent:
            lines.append("  RECENT ACTIONS:")
            for entry in recent:
                summary = entry.summary[:50] + "..." if len(entry.summary) > 50 else entry.summary
                lines.append(f"    > {entry.actor}: {summary}")

        lines.append("=" * 60)

        return "\n".join(lines)

    def to_dict(self):
        """Serialize table state."""
        return {
            "spotlight": self.spotlight,
            "round_robin_order": self.round_robin_order,
            "current_index": self.current_index,
            "round_robin_active": self.round_robin_active,
            "character_states": {n: s.to_dict() for n, s in self.character_states.items()},
            "action_log": [e.to_dict() for e in self.action_log],
            "addressed_to": self.addressed_to,
            "npc_names": self.npc_names
        }

    @classmethod
    def from_dict(cls, data):
        """Deserialize table state."""
        state = cls()
        state.spotlight = data.get("spotlight")
        state.round_robin_order = data.get("round_robin_order", [])
        state.current_index = data.get("current_index", 0)
        state.round_robin_active = data.get("round_robin_active", False)
        state.addressed_to = data.get("addressed_to")
        state.npc_names = data.get("npc_names", [])

        for name, state_data in data.get("character_states", {}).items():
            state.character_states[name] = CharacterState.from_dict(state_data)

        for entry_data in data.get("action_log", []):
            state.action_log.append(ActionLogEntry.from_dict(entry_data))

        return state


def extract_action_from_response(response: str) -> str:
    """
    Extract what a character is doing from their response.
    Uses simple heuristics to summarize the action.
    """
    # Clean up response
    response = response.strip()

    # If it's short, use as-is
    if len(response) <= 50:
        return response

    # Look for action indicators
    action_verbs = ["I ", "I'm ", "I'll ", "*"]

    for verb in action_verbs:
        if verb in response:
            # Find the sentence with the action
            sentences = response.replace("*", "").split(".")
            for sentence in sentences:
                if verb.strip() in sentence:
                    action = sentence.strip()[:50]
                    if action:
                        return action + "..." if len(sentence) > 50 else action

    # Fallback: first 50 chars
    return response[:50] + "..." if len(response) > 50 else response
