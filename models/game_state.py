"""
Game state hierarchy: Campaign -> Session -> Scene -> Round -> Turn

Manages character presence and context loading to minimize token usage.
"""

import yaml
from pathlib import Path
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


class CharacterPresence(Enum):
    """How much context to load for a character."""
    ACTIVE = "active"      # Full stats, inventory, history - in current scene
    NEARBY = "nearby"      # In session but not scene - name + basic info only
    KNOWN = "known"        # Mentioned/encountered - name + notes only
    UNKNOWN = "unknown"    # Not yet encountered - no context


@dataclass
class CharacterRef:
    """
    Lightweight reference to a character with presence state.
    Full Character objects only loaded when needed.
    """
    name: str
    presence: CharacterPresence = CharacterPresence.UNKNOWN
    file_path: Optional[str] = None  # Path to YAML if exists
    notes: str = ""  # Brief notes for KNOWN characters
    aliases: list = field(default_factory=list)
    affiliations: list = field(default_factory=lambda: ["Unknown"])
    allies: list = field(default_factory=list)
    enemies: list = field(default_factory=list)
    is_npc: bool = False  # True for NPCs, False for Player Characters
    agent: str = ""  # Agent name for PCs (e.g., "veteran_marcus")

    # Cached full character (only loaded when ACTIVE)
    _character: Optional[object] = field(default=None, repr=False)

    @property
    def affiliation(self):
        """Primary affiliation for backward compatibility."""
        return self.affiliations[0] if self.affiliations else "Unknown"

    def get_character(self):
        """Load full character if ACTIVE and not cached."""
        if self.presence != CharacterPresence.ACTIVE:
            return None
        if self._character is None and self.file_path:
            from character import Character
            self._character = Character.from_yaml(self.file_path)
        return self._character

    def unload(self):
        """Unload cached character to free memory."""
        self._character = None

    def to_dict(self):
        data = {
            "name": self.name,
            "presence": self.presence.value,
            "file_path": self.file_path,
            "notes": self.notes,
            "aliases": self.aliases,
            "affiliations": self.affiliations
        }
        # Only include allies/enemies if non-empty
        if self.allies:
            data["allies"] = self.allies
        if self.enemies:
            data["enemies"] = self.enemies
        # Only include is_npc if True (NPCs)
        if self.is_npc:
            data["is_npc"] = True
        # Only include agent if set (PCs)
        if self.agent:
            data["agent"] = self.agent
        return data

    @classmethod
    def from_dict(cls, data):
        # Handle legacy single affiliation format
        affiliations = data.get("affiliations")
        if affiliations is None:
            legacy_aff = data.get("affiliation", "Unknown")
            affiliations = [legacy_aff] if isinstance(legacy_aff, str) else legacy_aff

        return cls(
            name=data["name"],
            presence=CharacterPresence(data.get("presence", "unknown")),
            file_path=data.get("file_path"),
            notes=data.get("notes", ""),
            aliases=data.get("aliases", []),
            affiliations=affiliations,
            allies=data.get("allies", []),
            enemies=data.get("enemies", []),
            is_npc=data.get("is_npc", False),
            agent=data.get("agent", "")
        )


@dataclass
class Turn:
    """A single character's turn in combat."""
    character_name: str
    actions_total: int = 2  # Fallout 2d20: 2 actions per turn
    actions_used: int = 0
    minor_actions_used: int = 0

    @property
    def actions_remaining(self):
        return self.actions_total - self.actions_used

    def use_action(self, count=1):
        self.actions_used = min(self.actions_used + count, self.actions_total)

    def use_minor_action(self):
        self.minor_actions_used += 1

    def reset(self):
        self.actions_used = 0
        self.minor_actions_used = 0


@dataclass
class Round:
    """A combat round with initiative order."""
    number: int = 1
    initiative_order: list = field(default_factory=list)  # List of character names
    current_turn_index: int = 0
    turns: dict = field(default_factory=dict)  # name -> Turn

    @property
    def current_character(self):
        if not self.initiative_order:
            return None
        return self.initiative_order[self.current_turn_index]

    @property
    def current_turn(self):
        char = self.current_character
        return self.turns.get(char) if char else None

    def add_combatant(self, name, initiative=0):
        """Add character to initiative order (sorted by initiative desc)."""
        if name not in self.initiative_order:
            self.initiative_order.append(name)
            self.turns[name] = Turn(character_name=name)
            # Sort by initiative (would need to store initiative values for proper sorting)

    def remove_combatant(self, name):
        """Remove character from combat."""
        if name in self.initiative_order:
            idx = self.initiative_order.index(name)
            self.initiative_order.remove(name)
            del self.turns[name]
            if self.current_turn_index >= len(self.initiative_order):
                self.current_turn_index = 0

    def next_turn(self):
        """Advance to next turn, returns (character_name, new_round)."""
        if not self.initiative_order:
            return None, False

        self.current_turn_index += 1
        new_round = False

        if self.current_turn_index >= len(self.initiative_order):
            self.current_turn_index = 0
            self.number += 1
            new_round = True
            # Reset all turns
            for turn in self.turns.values():
                turn.reset()

        return self.current_character, new_round

    def to_dict(self):
        return {
            "number": self.number,
            "initiative_order": self.initiative_order,
            "current_turn_index": self.current_turn_index
        }


@dataclass
class Scene:
    """
    A specific scene within a session - a location and situation.
    Only characters present in the scene get full context.
    """
    name: str = "Unnamed Scene"
    location: str = ""
    description: str = ""
    present_characters: list = field(default_factory=list)  # Names of characters in scene
    round: Optional[Round] = None  # None if not in combat

    @property
    def in_combat(self):
        return self.round is not None

    def add_character(self, name):
        """Add character to scene."""
        if name not in self.present_characters:
            self.present_characters.append(name)

    def remove_character(self, name):
        """Remove character from scene."""
        if name in self.present_characters:
            self.present_characters.remove(name)
            if self.round:
                self.round.remove_combatant(name)

    def start_combat(self, initiative_order=None):
        """Begin combat in this scene."""
        self.round = Round()
        if initiative_order:
            for name in initiative_order:
                self.round.add_combatant(name)
        else:
            # Add all present characters
            for name in self.present_characters:
                self.round.add_combatant(name)

    def end_combat(self):
        """End combat."""
        self.round = None

    def to_dict(self):
        data = {
            "name": self.name,
            "location": self.location,
            "description": self.description,
            "present_characters": self.present_characters
        }
        if self.round:
            data["round"] = self.round.to_dict()
        return data

    @classmethod
    def from_dict(cls, data):
        scene = cls(
            name=data.get("name", "Unnamed Scene"),
            location=data.get("location", ""),
            description=data.get("description", ""),
            present_characters=data.get("present_characters", [])
        )
        if "round" in data:
            scene.round = Round(**data["round"])
        return scene


@dataclass
class SessionState:
    """
    A play session - a subset of characters actively involved.
    Manages which characters are loaded vs referenced.
    """
    name: str = "Unnamed Session"
    started: str = field(default_factory=lambda: datetime.now().isoformat())
    scenes: list = field(default_factory=list)  # List of Scene objects
    current_scene_index: int = -1
    session_notes: str = ""

    # Characters active this session (full load when in scene)
    active_characters: list = field(default_factory=list)  # Names

    @property
    def current_scene(self) -> Optional[Scene]:
        if 0 <= self.current_scene_index < len(self.scenes):
            return self.scenes[self.current_scene_index]
        return None

    def new_scene(self, name, location="", description=""):
        """Create a new scene and make it current."""
        scene = Scene(name=name, location=location, description=description)
        self.scenes.append(scene)
        self.current_scene_index = len(self.scenes) - 1
        return scene

    def add_to_session(self, name):
        """Mark character as active for this session."""
        if name not in self.active_characters:
            self.active_characters.append(name)

    def remove_from_session(self, name):
        """Remove character from session."""
        if name in self.active_characters:
            self.active_characters.remove(name)
        # Also remove from current scene
        if self.current_scene and name in self.current_scene.present_characters:
            self.current_scene.remove_character(name)

    def to_dict(self):
        return {
            "name": self.name,
            "started": self.started,
            "scenes": [s.to_dict() for s in self.scenes],
            "current_scene_index": self.current_scene_index,
            "session_notes": self.session_notes,
            "active_characters": self.active_characters
        }

    @classmethod
    def from_dict(cls, data):
        session = cls(
            name=data.get("name", "Unnamed Session"),
            started=data.get("started", datetime.now().isoformat()),
            current_scene_index=data.get("current_scene_index", -1),
            session_notes=data.get("session_notes", ""),
            active_characters=data.get("active_characters", [])
        )
        session.scenes = [Scene.from_dict(s) for s in data.get("scenes", [])]
        return session


@dataclass
class Campaign:
    """
    Top-level game state - persistent across sessions.
    Tracks all known characters, locations, and story state.
    """
    name: str = "Unnamed Campaign"
    created: str = field(default_factory=lambda: datetime.now().isoformat())

    # All known characters (lightweight refs, loaded on demand)
    characters: dict = field(default_factory=dict)  # name -> CharacterRef

    # Session history
    sessions: list = field(default_factory=list)  # List of SessionState
    current_session_index: int = -1

    # World state
    locations: dict = field(default_factory=dict)  # name -> description
    factions: dict = field(default_factory=dict)   # name -> notes
    quests: list = field(default_factory=list)     # Active quests
    notes: str = ""

    @property
    def current_session(self) -> Optional[SessionState]:
        if 0 <= self.current_session_index < len(self.sessions):
            return self.sessions[self.current_session_index]
        return None

    @property
    def current_scene(self) -> Optional[Scene]:
        session = self.current_session
        return session.current_scene if session else None

    def register_character(self, name, file_path=None, presence=CharacterPresence.KNOWN,
                          notes="", aliases=None, affiliation=None, affiliations=None,
                          allies=None, enemies=None, is_npc=False, agent=""):
        """Add or update a character reference."""
        # Handle legacy single affiliation
        if affiliations is None:
            if affiliation is not None:
                affiliations = [affiliation] if isinstance(affiliation, str) else affiliation
            else:
                affiliations = ["Unknown"]

        if name in self.characters:
            ref = self.characters[name]
            if file_path:
                ref.file_path = file_path
            if notes:
                ref.notes = notes
            if aliases:
                ref.aliases = aliases
            if affiliations and affiliations != ["Unknown"]:
                ref.affiliations = affiliations
            if allies is not None:
                ref.allies = allies
            if enemies is not None:
                ref.enemies = enemies
            ref.presence = presence
            ref.is_npc = is_npc
            if agent:
                ref.agent = agent
        else:
            self.characters[name] = CharacterRef(
                name=name,
                presence=presence,
                file_path=file_path,
                notes=notes,
                aliases=aliases or [],
                affiliations=affiliations,
                allies=allies or [],
                enemies=enemies or [],
                is_npc=is_npc,
                agent=agent
            )
        return self.characters[name]

    def get_character_ref(self, name_or_alias):
        """Find character by name or alias."""
        name_lower = name_or_alias.lower()
        for ref in self.characters.values():
            if ref.name.lower() == name_lower:
                return ref
            if name_lower in [a.lower() for a in ref.aliases]:
                return ref
        return None

    def new_session(self, name=None):
        """Start a new session."""
        if not name:
            name = f"Session {len(self.sessions) + 1}"
        session = SessionState(name=name)
        self.sessions.append(session)
        self.current_session_index = len(self.sessions) - 1
        return session

    def get_active_characters(self):
        """Get full Character objects for characters in current scene."""
        scene = self.current_scene
        if not scene:
            return []

        characters = []
        for name in scene.present_characters:
            ref = self.characters.get(name)
            if ref and ref.presence == CharacterPresence.ACTIVE:
                char = ref.get_character()
                if char:
                    characters.append(char)
        return characters

    def get_nearby_characters(self):
        """Get CharacterRefs for session-active but not scene-present characters."""
        session = self.current_session
        scene = self.current_scene
        if not session:
            return []

        nearby = []
        scene_chars = scene.present_characters if scene else []

        for name in session.active_characters:
            if name not in scene_chars:
                ref = self.characters.get(name)
                if ref:
                    nearby.append(ref)
        return nearby

    def save(self, path=None):
        """Save campaign to YAML."""
        if not path:
            safe_name = self.name.lower().replace(" ", "_")
            path = Path(__file__).parent.parent / "campaigns" / f"{safe_name}.yaml"

        path = Path(path)
        path.parent.mkdir(exist_ok=True)

        # Separate PCs and NPCs for cleaner YAML
        player_characters = {}
        notable_npcs = {}
        for name, ref in self.characters.items():
            if ref.is_npc:
                notable_npcs[name] = ref.to_dict()
            else:
                player_characters[name] = ref.to_dict()

        data = {
            "name": self.name,
            "created": self.created,
            "player_characters": player_characters,
            "notable_npcs": notable_npcs,
            "sessions": [s.to_dict() for s in self.sessions],
            "current_session_index": self.current_session_index,
            "locations": self.locations,
            "factions": self.factions,
            "quests": self.quests,
            "notes": self.notes
        }

        with open(path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        return str(path)

    @classmethod
    def load(cls, path):
        """Load campaign from YAML."""
        with open(path, 'r') as f:
            data = yaml.safe_load(f)

        campaign = cls(
            name=data.get("name", "Unnamed Campaign"),
            created=data.get("created", datetime.now().isoformat()),
            current_session_index=data.get("current_session_index", -1),
            locations=data.get("locations", {}),
            factions=data.get("factions", {}),
            quests=data.get("quests", []),
            notes=data.get("notes", "")
        )

        # Load character refs - support both new and legacy formats
        # New format: player_characters + notable_npcs
        # Legacy format: characters
        if "player_characters" in data or "notable_npcs" in data:
            # New format
            for name, ref_data in data.get("player_characters", {}).items():
                ref_data["is_npc"] = False
                campaign.characters[name] = CharacterRef.from_dict(ref_data)
            for name, ref_data in data.get("notable_npcs", {}).items():
                ref_data["is_npc"] = True
                campaign.characters[name] = CharacterRef.from_dict(ref_data)
        else:
            # Legacy format
            for name, ref_data in data.get("characters", {}).items():
                campaign.characters[name] = CharacterRef.from_dict(ref_data)

        # Load sessions
        campaign.sessions = [SessionState.from_dict(s) for s in data.get("sessions", [])]

        return campaign

    def __repr__(self):
        return f"Campaign(name='{self.name}', characters={len(self.characters)}, sessions={len(self.sessions)})"
