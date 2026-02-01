import yaml
import anthropic
from pathlib import Path


# Cache loaded game data at module level
_skills_data = None
_perks_data = None


def _load_skills_data():
    """Load skills data from YAML (cached)."""
    global _skills_data
    if _skills_data is None:
        data_dir = Path(__file__).parent / "data"
        with open(data_dir / "skills.yaml", "r") as f:
            _skills_data = yaml.safe_load(f).get("skills", {})
    return _skills_data


def _load_perks_data():
    """Load perks data from YAML (cached)."""
    global _perks_data
    if _perks_data is None:
        data_dir = Path(__file__).parent / "data"
        with open(data_dir / "perks.yaml", "r") as f:
            _perks_data = yaml.safe_load(f).get("perks", {})
    return _perks_data


# Static world context to pad cached content (contributes to 1024 token minimum)
# This comprehensive context ensures the static prompt exceeds Anthropic's caching threshold
WORLD_CONTEXT = """Setting: Post-apocalyptic Wasteland, 200 years after nuclear war. The Great War of 2077 left the world in ruins. Civilization slowly rebuilds in scattered settlements while mutated creatures, raiders, and old-world dangers lurk in the irradiated wastes. Bottle caps serve as currency. Pre-war technology is valuable and often dangerous. Radiation has created mutants, ghouls, and strange flora. Factions vie for control of resources and territory.

Major Factions:
- NCR (New California Republic): Democratic government rebuilding civilization, militaristic but lawful
- Brotherhood of Steel: Tech-hoarding military order, protects dangerous technology from misuse
- Raiders: Violent gangs that prey on travelers and settlements
- Settlers: Independent communities trying to survive and rebuild
- Traders Guild: Merchant caravans connecting settlements, value profit and safe routes
- Enclave: Remnants of pre-war US government, view wastelanders as impure

Game System: Fallout 2d20 RPG
- Skill checks use [CHECK: skill_name] tag when attempting difficult actions
- Use items with [USE: item_name] or [USE: item ON target] tags
- Give items with [GIVE: quantity item_name TO character] tag
- Speak in-character, describe actions in third person
- React to dice roll results when provided
- Critical success (natural 1): exceptional outcome, generates bonus
- Complication (natural 20): something goes wrong, even on success
- Difficulty ranges from 0 (trivial) to 5 (nearly impossible)

SPECIAL Attributes (1-10 scale):
- Strength: Physical power, melee damage, carry weight, breaking objects
- Perception: Awareness, accuracy, detecting hidden things, spotting danger
- Endurance: Stamina, health points, radiation resistance, disease resistance
- Charisma: Persuasion, bartering, leadership, intimidation
- Intelligence: Problem-solving, medicine, science, hacking, crafting
- Agility: Speed, stealth, ranged accuracy, reflexes, dodging
- Luck: Critical chance, finding items, gambling, general fortune

Common Wasteland Hazards:
- Radiation: Accumulates from irradiated zones, food, and creatures. High rads cause sickness and death.
- Dehydration: Clean water is precious. Purified water heals and sustains.
- Chems: Stimpaks heal wounds. Rad-X protects from radiation. RadAway removes rads. Med-X dulls pain.
- Creatures: Radroaches, mole rats, feral ghouls, super mutants, deathclaws, and more.

Roleplay Guidelines:
- Stay in character at all times during the scene
- Your character has their own knowledge, beliefs, and limitations
- React authentically to the situation based on your personality and background
- Use skill check tags [CHECK: skill] when attempting something difficult or uncertain
- Describe actions clearly so the GM can adjudicate outcomes
- Collaborate with other characters but maintain your own agency
- Accept failure gracefully and let it drive interesting story developments
- Your character can be wrong, scared, or make mistakes
- Small details and character moments make the story come alive

Combat Considerations:
- Describe intent and approach, let dice determine outcome
- Use cover and terrain when available
- Consider non-combat solutions when appropriate
- Injuries and conditions affect your capabilities
- Conserve ammunition and supplies in extended conflicts
- Retreat is sometimes the wisest choice

Social Interactions:
- Your reputation precedes you based on faction affiliations
- Past actions may be remembered by NPCs
- Barter skill affects prices, Speech affects persuasion
- Some NPCs may refuse to deal with certain factions
- Information is valuable currency in the Wasteland

Available Skills Reference:
- Barter (CHA): Negotiate prices and trade deals, haggle for better rates
- Speech (CHA): Persuade, intimidate, deceive, or inspire others through words
- Medicine (INT): Heal wounds, treat conditions, diagnose illness, perform surgery
- Science (INT): Hack terminals, analyze technology, craft chems, understand pre-war tech
- Repair (INT): Fix weapons, armor, machines, and jury-rig solutions
- Lockpick (PER): Open locked containers, doors, and safes without keys
- Survival (PER): Track creatures, forage for food, navigate wilderness, identify flora/fauna
- Sneak (AGI): Move unseen and unheard, pickpocket, set ambushes
- Guns (AGI): Accuracy with firearms, gun maintenance, ammunition identification
- Melee (AGI): Close combat with bladed and blunt weapons, blocking, parrying
- Unarmed (STR): Hand-to-hand combat, grappling, martial arts
- Gambling (LCK): Games of chance, reading opponents, knowing when to fold

Condition Effects:
- Wounded: Reduced effectiveness until healed
- Irradiated: Accumulating radiation sickness
- Exhausted: Penalties to all physical actions
- Poisoned: Ongoing damage until treated
- Crippled Limb: Specific penalties based on body part
- Starving/Dehydrated: Growing desperation for sustenance"""


class Agent:
    """
    AI player agent that controls characters via Claude API.

    Attributes:
        name: Agent name
        system_prompt: Instructions for how this agent plays
        traits: Behavioral traits list
        model: Claude model (default "claude-sonnet-4-20250514")
        temperature: 0.0-1.0 (default 0.7)
        max_tokens: Response length limit (default 300)
        max_history: Max exchanges to keep (default 10)
        history: Rolling conversation history
    """

    # Class-level settings
    debug_cache = False  # Toggle cache usage logging

    def __init__(self, name, system_prompt, traits=None, format_rules=None,
                 model="claude-sonnet-4-20250514", temperature=0.7, max_tokens=300,
                 requires_roll=False, roll_prompt="d20", price_modifiers=None,
                 max_history=10, is_npc=False, voice=None):
        self.name = name
        self.system_prompt = system_prompt
        self.traits = traits or []
        self.format_rules = format_rules or []
        self.voice = voice  # Dialogue style guidance for unique character voice
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.requires_roll = requires_roll
        self.roll_prompt = roll_prompt
        self.price_modifiers = price_modifiers or {}
        self.max_history = max_history  # Max exchanges to keep (1 exchange = 2 messages)
        self.is_npc = is_npc  # If True, only responds when explicitly targeted
        self.history = []
        self.history_summary = ""  # Rolling summary of older conversation
        self.client = anthropic.Anthropic()

    def _build_static_system(self, character):
        """
        Build the static portion of the system prompt (agent config + character identity).
        This content is stable between calls and benefits from caching.

        Note: Anthropic prompt caching requires minimum 1024 tokens. We include world context,
        skill descriptions, and perk details to ensure we meet this threshold.
        """
        traits = ", ".join(self.traits + character.personality_traits)
        static_parts = [
            # World context and game rules (stable, adds ~200 tokens)
            WORLD_CONTEXT,
            "",
            # Agent behavior instructions
            self.system_prompt,
            "",
            # Character identity
            f"Character: {character.name}. {character.background}",
            f"Traits: {traits}.",
        ]

        # Include format rules if agent has them
        if self.format_rules:
            static_parts.append("Format rules: " + "; ".join(self.format_rules))

        # Include skill descriptions (adds tokens and context)
        skills_data = _load_skills_data()
        skill_descriptions = []
        for skill in character.skills:
            skill_info = skills_data.get(skill)
            if skill_info:
                desc = skill_info.get("description", "")
                stat = skill_info.get("stat", "").upper()
                skill_descriptions.append(f"  - {skill} ({stat}): {desc}")
            else:
                skill_descriptions.append(f"  - {skill}")

        if skill_descriptions:
            static_parts.append("Skills:\n" + "\n".join(skill_descriptions))
        else:
            static_parts.append(f"Skills: {', '.join(character.skills)}.")

        # Include full perk descriptions (adds tokens and context)
        if character.perks:
            perks_data = _load_perks_data()
            perk_descriptions = []
            for perk in character.perks:
                perk_info = perks_data.get(perk)
                if perk_info:
                    desc = perk_info.get("description", "")
                    perk_descriptions.append(f"  - {perk}: {desc}")
                else:
                    perk_descriptions.append(f"  - {perk}")
            static_parts.append("Perks:\n" + "\n".join(perk_descriptions))

        # Include voice/style guidance for distinctive dialogue
        if self.voice:
            static_parts.append(f"Voice style:\n{self.voice}")

        return "\n".join(static_parts)

    def _build_dynamic_system(self, character):
        """Build dynamic state (HP, inventory, history summary). Not cached."""
        items = [f"{i.name} x{i.quantity}" if i.quantity > 1 else i.name
                 for i in character.inventory.items]
        inv = ", ".join(items) or "empty"
        cond = ", ".join(character.conditions) or "none"
        state = (
            f"HP {character.health['current']}/{character.health['max']}, "
            f"{character.radiation} rads, {cond}. Inventory: {inv}"
        )
        if self.history_summary:
            state = f"Previously: {self.history_summary}\n{state}"
        return state

    def _summarize_messages(self, messages, existing_summary=""):
        """
        Summarize conversation messages into a compact form using Haiku.
        If existing_summary is provided, incorporates it into the new summary.
        """
        if not messages:
            return existing_summary

        # Format messages for summarization
        lines = []
        for msg in messages:
            role = "GM" if msg["role"] == "user" else "Character"
            lines.append(f"{role}: {msg['content']}")
        conversation = "\n".join(lines)

        prompt = "Summarize this RPG conversation in 2-3 sentences, focusing on key events, decisions, and information exchanged:"
        if existing_summary:
            prompt = f"Previous context: {existing_summary}\n\n{prompt}"

        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            temperature=0,
            messages=[{"role": "user", "content": f"{prompt}\n\n{conversation}"}]
        )
        return response.content[0].text

    def _trim_history(self):
        """Trim history, summarizing old messages before discarding."""
        max_messages = self.max_history * 2
        if len(self.history) <= max_messages:
            return

        # Messages to be trimmed
        trim_count = len(self.history) - max_messages
        to_summarize = self.history[:trim_count]

        # Summarize old messages and update rolling summary
        self.history_summary = self._summarize_messages(to_summarize, self.history_summary)

        # Keep only recent history
        self.history = self.history[-max_messages:]

    def build_system_prompt(self, character):
        """
        Combine agent config + character sheet into a system message.

        Args:
            character: Character instance to build prompt for

        Returns:
            str: Complete system prompt (for non-cached usage)
        """
        return self._build_static_system(character) + "\n" + self._build_dynamic_system(character)

    def respond(self, character, narration, roll=None):
        """
        Generate an in-character response to GM narration.

        Uses prompt caching to reduce token costs:
        - Static system prompt (agent config + character identity) is cached
        - Conversation history is cached at the last message boundary
        - Dynamic state (HP, inventory) is not cached since it changes

        Args:
            character: Character instance this agent is playing
            narration: The GM's narration text
            roll: Optional dice roll result (int) that influences the response

        Returns:
            str: The agent's in-character response
        """
        if roll is not None:
            narration = f"{narration}\n[Dice roll: {roll}]"

        system = [
            {
                "type": "text",
                "text": self._build_static_system(character),
                "cache_control": {"type": "ephemeral"}
            },
            {
                "type": "text",
                "text": self._build_dynamic_system(character)
            }
        ]

        # Build messages with cache breakpoint on last history message
        messages = []
        for msg in self.history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        if messages:
            last = messages[-1]
            last["content"] = [{
                "type": "text",
                "text": last["content"],
                "cache_control": {"type": "ephemeral"}
            }]

        messages.append({"role": "user", "content": narration})

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system,
            messages=messages
        )

        # Debug: Log cache usage when enabled
        if Agent.debug_cache:
            usage = response.usage
            cache_created = getattr(usage, 'cache_creation_input_tokens', 0)
            cache_read = getattr(usage, 'cache_read_input_tokens', 0)
            print(f"  [Cache: created={cache_created}, read={cache_read}, input={usage.input_tokens}]")

        assistant_text = response.content[0].text

        # Append to history and trim (with summarization) if needed
        self.history.append({"role": "user", "content": narration})
        self.history.append({"role": "assistant", "content": assistant_text})
        self._trim_history()

        return assistant_text

    def clear_history(self):
        """Clear the conversation history and summary."""
        self.history = []
        self.history_summary = ""

    def to_dict(self):
        """
        Convert agent configuration to dictionary (excludes history).

        Returns:
            dict: Agent configuration
        """
        data = {
            "name": self.name,
            "system_prompt": self.system_prompt,
            "traits": self.traits,
            "format_rules": self.format_rules,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }
        if self.voice:
            data["voice"] = self.voice
        if self.requires_roll:
            data["requires_roll"] = self.requires_roll
            data["roll_prompt"] = self.roll_prompt
        if self.max_history != 10:
            data["max_history"] = self.max_history
        if self.price_modifiers:
            data["price_modifiers"] = self.price_modifiers
        if self.is_npc:
            data["is_npc"] = self.is_npc
        return data

    def save_to_yaml(self, path):
        """
        Save agent configuration to a YAML file.

        Args:
            path: File path to save to
        """
        with open(path, 'w') as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False)

    @classmethod
    def from_yaml(cls, yaml_path):
        """
        Create an Agent from a YAML file.

        Args:
            yaml_path: Path to YAML file

        Returns:
            Agent: New Agent instance
        """
        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f)
        return cls(**data)

    def __repr__(self):
        return f"Agent(name='{self.name}', model='{self.model}')"
