import json
import anthropic


class Agent:
    """
    AI player agent that controls one or more characters via the Anthropic Claude API.

    The agent defines *how* a character is played (style, personality approach, model settings)
    while the Character class defines *what* the character is (stats, inventory, background).

    Attributes:
        name: Agent name (e.g. "Cautious Player", "Aggressive Berserker")
        system_prompt: Custom instructions for how this agent plays
        traits: Behavioral traits (e.g. ["cautious", "verbose", "pacifist"])
        format_rules: Response format rules (e.g. ["respond in first person"])
        model: Claude model to use (default "claude-sonnet-4-20250514")
        temperature: Response randomness 0.0-1.0 (default 0.7)
        max_tokens: Response length limit (default 300)
        history: Rolling conversation history [{role, content}, ...]
    """

    def __init__(self, name, system_prompt, traits=None, format_rules=None,
                 model="claude-sonnet-4-20250514", temperature=0.7, max_tokens=300):
        self.name = name
        self.system_prompt = system_prompt
        self.traits = traits or []
        self.format_rules = format_rules or []
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.history = []
        self.client = anthropic.Anthropic()

    def build_system_prompt(self, character):
        """
        Combine agent config + character sheet into a system message.

        Args:
            character: Character instance to build prompt for

        Returns:
            str: Complete system prompt
        """
        parts = [self.system_prompt]

        if self.traits:
            parts.append(f"\nYour behavioral traits: {', '.join(self.traits)}")

        if self.format_rules:
            rules = "\n".join(f"- {rule}" for rule in self.format_rules)
            parts.append(f"\nResponse format rules:\n{rules}")

        # Character sheet
        inventory_items = []
        for item in character.inventory.items:
            if item.quantity > 1:
                inventory_items.append(f"{item.name} x{item.quantity}")
            else:
                inventory_items.append(item.name)
        inventory_summary = ", ".join(inventory_items) if inventory_items else "empty"

        conditions_str = ", ".join(character.conditions) if character.conditions else "none"

        char_section = (
            f"\nYou are playing the character: {character.name}"
            f"\nBackground: {character.background}"
            f"\nPersonality: {', '.join(character.personality_traits)}"
            f"\nSkills: {', '.join(character.skills)}"
            f"\nCurrent state: HP {character.health['current']}/{character.health['max']}, "
            f"{character.radiation} rads, conditions: {conditions_str}"
            f"\nInventory: {inventory_summary}"
        )
        parts.append(char_section)

        return "\n".join(parts)

    def respond(self, character, narration):
        """
        Generate an in-character response to GM narration.

        Calls the Claude API with the agent's configuration and character context,
        then appends both the narration and response to conversation history.

        Args:
            character: Character instance this agent is playing
            narration: The GM's narration text

        Returns:
            str: The agent's in-character response
        """
        system = self.build_system_prompt(character)
        messages = self.history + [{"role": "user", "content": narration}]

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system,
            messages=messages
        )

        assistant_text = response.content[0].text

        # Append to history
        self.history.append({"role": "user", "content": narration})
        self.history.append({"role": "assistant", "content": assistant_text})

        return assistant_text

    def clear_history(self):
        """Clear the conversation history."""
        self.history = []

    def to_dict(self):
        """
        Convert agent configuration to dictionary (excludes history).

        Returns:
            dict: Agent configuration
        """
        return {
            "name": self.name,
            "system_prompt": self.system_prompt,
            "traits": self.traits,
            "format_rules": self.format_rules,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }

    def save_to_json(self, path):
        """
        Save agent configuration to a JSON file.

        Args:
            path: File path to save to
        """
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def from_json(cls, json_path):
        """
        Create an Agent from a JSON file.

        Args:
            json_path: Path to JSON file

        Returns:
            Agent: New Agent instance
        """
        with open(json_path, 'r') as f:
            data = json.load(f)
        return cls(**data)

    def __repr__(self):
        return f"Agent(name='{self.name}', model='{self.model}')"
