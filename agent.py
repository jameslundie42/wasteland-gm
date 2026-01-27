import yaml
import anthropic


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

    def __init__(self, name, system_prompt, traits=None, format_rules=None,
                 model="claude-sonnet-4-20250514", temperature=0.7, max_tokens=300,
                 requires_roll=False, roll_prompt="d20", price_modifiers=None,
                 max_history=10, is_npc=False):
        self.name = name
        self.system_prompt = system_prompt
        self.traits = traits or []
        self.format_rules = format_rules or []
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
        """
        traits = ", ".join(self.traits + character.personality_traits)
        static_parts = [
            self.system_prompt,
            f"Character: {character.name}. {character.background}",
            f"Traits: {traits}.",
            f"Skills: {', '.join(character.skills)}."
        ]
        
        # Include perks if character has them
        if character.perks:
            static_parts.append(f"Perks: {', '.join(character.perks)}.")
        
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
