"""
Character generation system for creating PCs and NPCs.

Supports three modes:
- random: Generate random stats with point-buy system
- input: Interactive prompts for each field
- description: AI generates character from natural language
"""

import random
import json
import yaml
import anthropic
from pathlib import Path


# Available skills from skills.yaml
AVAILABLE_SKILLS = [
    "Barter", "Speech", "Medicine", "Science", "Repair",
    "Lockpick", "Survival", "Sneak", "Guns", "Melee",
    "Unarmed", "Gambling"
]

# Common affiliations in the Wasteland
AFFILIATIONS = [
    "Independent", "Settlers", "Traders Guild", "Brotherhood",
    "Raiders", "Enclave", "NCR", "Minutemen", "Institute"
]

# Starting inventory templates
STARTING_GEAR = {
    "combat": ["10mm Pistol", "Combat Knife", "Stimpak x2", "Bottle Caps x50"],
    "medic": ["Stimpak x3", "Doctor's Bag", "Rad-X x2", "10mm Pistol", "Bottle Caps x75"],
    "trader": ["Bottle Caps x200", "Stimpak", "10mm Pistol", "Purified Water x3"],
    "scout": ["Hunting Rifle", "Binoculars", "Stimpak x2", "Purified Water x2", "Bottle Caps x30"],
    "basic": ["10mm Pistol", "Stimpak", "Bottle Caps x25"]
}


class CharacterGenerator:
    """Generates characters with random, input, or AI-driven methods."""

    def __init__(self):
        self.client = anthropic.Anthropic()

    def generate_random(self, name=None, is_npc=False):
        """
        Generate a character with random stats using point-buy.

        Args:
            name: Optional name, generates random if not provided
            is_npc: If True, generates simpler NPC with fewer details

        Returns:
            dict: Character data ready for Character constructor
        """
        if not name:
            name = self._random_name()

        special = self._random_special()
        skills = self._random_skills(3 if not is_npc else 2)
        personality = self._random_personality(3 if not is_npc else 1)
        affiliation = random.choice(AFFILIATIONS)
        gear_type = random.choice(list(STARTING_GEAR.keys()))
        inventory = STARTING_GEAR[gear_type].copy()

        background = f"A {affiliation.lower()} wanderer making their way through the Wasteland."
        if is_npc:
            background = f"An NPC affiliated with {affiliation}."

        return {
            "name": name,
            "aliases": self._generate_aliases(name),
            "affiliation": affiliation,
            "special": special,
            "skills": skills,
            "background": background,
            "personality_traits": personality,
            "inventory": inventory
        }

    def generate_from_description(self, description, is_npc=False):
        """
        Use AI to generate character stats from a natural language description.

        Args:
            description: Natural language character description
            is_npc: If True, generates simpler NPC

        Returns:
            dict: Character data ready for Character constructor
        """
        char_type = "NPC" if is_npc else "player character"

        prompt = f"""Generate a Fallout RPG {char_type} based on this description:

"{description}"

Return a JSON object with these fields:
- name: Full character name
- aliases: Array of 1-3 short names/nicknames (first name, last name, or nickname)
- affiliation: One of {AFFILIATIONS}
- special: Object with strength, perception, endurance, charisma, intelligence, agility, luck (each 1-10, total should be ~28)
- skills: Array of 2-4 skills from {AVAILABLE_SKILLS} that fit the character
- background: 2-3 sentence backstory
- personality_traits: Array of 2-4 brief personality traits (5-10 words each)
- inventory: Array of starting items like ["10mm Pistol", "Stimpak x2", "Bottle Caps x50"]

Respond with ONLY valid JSON, no explanation."""

        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}]
        )

        try:
            # Parse JSON response
            json_text = response.content[0].text.strip()
            # Handle potential markdown code blocks
            if json_text.startswith("```"):
                json_text = json_text.split("```")[1]
                if json_text.startswith("json"):
                    json_text = json_text[4:]
            data = json.loads(json_text)

            # Validate and sanitize
            return self._validate_character_data(data)
        except (json.JSONDecodeError, KeyError) as e:
            print(f"  [AI generation failed: {e}. Falling back to random.]")
            return self.generate_random(is_npc=is_npc)

    def interactive_create(self, is_npc=False):
        """
        Interactively prompt user for character details.

        Args:
            is_npc: If True, asks fewer questions for NPC

        Returns:
            dict: Character data ready for Character constructor
        """
        print("\n=== Character Creation ===\n")

        # Name
        name = input("Name: ").strip()
        if not name:
            name = self._random_name()
            print(f"  Using random name: {name}")

        # Aliases
        alias_input = input("Aliases (comma-separated, or Enter for auto): ").strip()
        if alias_input:
            aliases = [a.strip() for a in alias_input.split(",")]
        else:
            aliases = self._generate_aliases(name)
            print(f"  Auto-generated aliases: {', '.join(aliases)}")

        # Affiliation
        print(f"\nAffiliations: {', '.join(AFFILIATIONS)}")
        affiliation = input("Affiliation (or Enter for Independent): ").strip()
        if not affiliation or affiliation not in AFFILIATIONS:
            affiliation = "Independent"

        # SPECIAL
        print("\n--- SPECIAL Stats ---")
        print("Enter values 1-10 for each (total budget: 28 points)")
        special = self._input_special()

        # Skills
        print(f"\n--- Skills ---")
        print(f"Available: {', '.join(AVAILABLE_SKILLS)}")
        skill_count = 2 if is_npc else 3
        skills_input = input(f"Tag skills ({skill_count}, comma-separated): ").strip()
        if skills_input:
            skills = [s.strip() for s in skills_input.split(",")][:skill_count]
            # Validate skills
            skills = [s for s in skills if s in AVAILABLE_SKILLS]
        else:
            skills = self._random_skills(skill_count)
            print(f"  Random skills: {', '.join(skills)}")

        # Background
        print("\n--- Background ---")
        background = input("Background (or Enter for basic): ").strip()
        if not background:
            background = f"A {affiliation.lower()} survivor in the Wasteland."

        # Personality
        print("\n--- Personality ---")
        trait_count = 2 if is_npc else 3
        traits_input = input(f"Personality traits ({trait_count}, comma-separated, or Enter for random): ").strip()
        if traits_input:
            personality = [t.strip() for t in traits_input.split(",")][:trait_count]
        else:
            personality = self._random_personality(trait_count)
            print(f"  Random traits: {', '.join(personality)}")

        # Inventory
        print("\n--- Starting Gear ---")
        print(f"Templates: {', '.join(STARTING_GEAR.keys())}")
        gear_choice = input("Gear template (or Enter for basic): ").strip().lower()
        if gear_choice in STARTING_GEAR:
            inventory = STARTING_GEAR[gear_choice].copy()
        else:
            inventory = STARTING_GEAR["basic"].copy()

        return {
            "name": name,
            "aliases": aliases,
            "affiliation": affiliation,
            "special": special,
            "skills": skills,
            "background": background,
            "personality_traits": personality,
            "inventory": inventory
        }

    def _random_name(self):
        """Generate a random Wasteland-appropriate name."""
        first_names = [
            "Jack", "Sarah", "Marcus", "Elena", "Vex", "Cole", "Maya",
            "Rex", "Ada", "Cass", "Duke", "Nora", "Hank", "Zoe", "Grim"
        ]
        last_names = [
            "Stone", "Rivers", "Ash", "Wolf", "Cross", "Steele", "Vance",
            "Cooper", "Black", "Graves", "Swift", "Kane", "Burke", "Hayes"
        ]
        nicknames = [
            "the Wanderer", "Scrapper", "Doc", "Gearhead", "Ace",
            "Ghost", "Lucky", "Patches", "Sparks", "Whisper"
        ]

        style = random.choice(["full", "nickname", "title"])
        if style == "full":
            return f"{random.choice(first_names)} {random.choice(last_names)}"
        elif style == "nickname":
            return random.choice(first_names)
        else:
            return f"{random.choice(first_names)} {random.choice(nicknames)}"

    def _generate_aliases(self, name):
        """Generate aliases from a full name."""
        aliases = []
        parts = name.split()

        if len(parts) >= 2:
            aliases.append(parts[0])  # First name
            aliases.append(parts[-1])  # Last name or title
        elif len(parts) == 1:
            # Single name, maybe add a nickname
            aliases.append(name[:3].capitalize())  # Shortened version

        return aliases

    def _random_special(self):
        """Generate random SPECIAL stats with point-buy (28 total)."""
        stats = ["strength", "perception", "endurance", "charisma",
                 "intelligence", "agility", "luck"]

        # Start with 4 in each stat (28 points total with 7 stats)
        special = {stat: 4 for stat in stats}

        # Distribute remaining points randomly
        remaining = 28 - (4 * 7)  # 0 if starting at 4 each
        remaining = 7  # Actually give 7 extra points to distribute

        while remaining > 0:
            stat = random.choice(stats)
            if special[stat] < 10:
                special[stat] += 1
                remaining -= 1

        return special

    def _input_special(self):
        """Interactively input SPECIAL stats."""
        stats = ["strength", "perception", "endurance", "charisma",
                 "intelligence", "agility", "luck"]
        special = {}
        total = 0

        for stat in stats:
            while True:
                try:
                    val = input(f"  {stat.capitalize()} [{28 - total} remaining]: ").strip()
                    if not val:
                        val = 4  # Default
                    else:
                        val = int(val)

                    if 1 <= val <= 10:
                        special[stat] = val
                        total += val
                        break
                    else:
                        print("    Must be 1-10")
                except ValueError:
                    print("    Enter a number")

        return special

    def _random_skills(self, count):
        """Pick random skills."""
        return random.sample(AVAILABLE_SKILLS, min(count, len(AVAILABLE_SKILLS)))

    def _random_personality(self, count):
        """Generate random personality traits."""
        traits = [
            "Cautious and calculating",
            "Quick to trust",
            "Suspicious of strangers",
            "Dry sense of humor",
            "Optimistic despite everything",
            "Cynical about human nature",
            "Fiercely loyal",
            "Always looking for an angle",
            "Prefers actions over words",
            "Talks too much when nervous",
            "Haunted by past mistakes",
            "Believes in second chances",
            "Values caps above all",
            "Protects the weak",
            "Survival comes first"
        ]
        return random.sample(traits, min(count, len(traits)))

    def _validate_character_data(self, data):
        """Validate and sanitize AI-generated character data."""
        # Ensure required fields
        validated = {
            "name": data.get("name", self._random_name()),
            "aliases": data.get("aliases", []),
            "affiliation": data.get("affiliation", "Independent"),
            "special": {},
            "skills": [],
            "background": data.get("background", "A Wasteland survivor."),
            "personality_traits": data.get("personality_traits", []),
            "inventory": data.get("inventory", STARTING_GEAR["basic"])
        }

        # Validate SPECIAL
        special_data = data.get("special", {})
        for stat in ["strength", "perception", "endurance", "charisma",
                     "intelligence", "agility", "luck"]:
            val = special_data.get(stat, 5)
            validated["special"][stat] = max(1, min(10, int(val)))

        # Validate skills
        for skill in data.get("skills", []):
            if skill in AVAILABLE_SKILLS:
                validated["skills"].append(skill)
        if not validated["skills"]:
            validated["skills"] = self._random_skills(2)

        # Validate affiliation
        if validated["affiliation"] not in AFFILIATIONS:
            validated["affiliation"] = "Independent"

        # Generate aliases if empty
        if not validated["aliases"]:
            validated["aliases"] = self._generate_aliases(validated["name"])

        return validated

    def save_character(self, char_data, filename=None, is_npc=False):
        """
        Save character data to YAML file.

        Args:
            char_data: Character dictionary
            filename: Optional filename (auto-generated if not provided)
            is_npc: If True, marks as NPC in filename

        Returns:
            str: Path to saved file
        """
        if not filename:
            # Generate filename from name
            safe_name = char_data["name"].lower().replace(" ", "_")
            safe_name = "".join(c for c in safe_name if c.isalnum() or c == "_")
            filename = f"{safe_name}.yaml"

        chars_dir = Path(__file__).parent.parent / "characters"
        chars_dir.mkdir(exist_ok=True)
        filepath = chars_dir / filename

        with open(filepath, 'w') as f:
            yaml.dump(char_data, f, default_flow_style=False, sort_keys=False)

        return str(filepath)


def create_character_interactive(session, args):
    """
    Handle /create command from session.

    Args:
        session: Session instance
        args: Command arguments string

    Returns:
        str: Result message
    """
    generator = CharacterGenerator()
    parts = args.strip().split(maxsplit=1)
    mode = parts[0].lower() if parts else "help"

    # Check for NPC prefix
    is_npc = False
    if mode == "npc":
        is_npc = True
        parts = parts[1].split(maxsplit=1) if len(parts) > 1 else []
        mode = parts[0].lower() if parts else "random"

    if mode == "help" or mode == "":
        return """
=== Character Creation ===

Usage:
  /create random [name]     - Random stats (optional name)
  /create input             - Interactive prompts
  /create <description>     - AI generates from description

  /create npc random [name] - Quick random NPC
  /create npc <description> - AI generates NPC from description

Examples:
  /create random
  /create random Jack Stone
  /create input
  /create A grizzled ex-Brotherhood soldier turned mercenary
  /create npc random
  /create npc A nervous trader with too many secrets
"""

    char_data = None

    if mode == "random":
        name = parts[1] if len(parts) > 1 else None
        char_data = generator.generate_random(name=name, is_npc=is_npc)
        print(f"\n  Generated random {'NPC' if is_npc else 'character'}: {char_data['name']}")

    elif mode == "input":
        char_data = generator.interactive_create(is_npc=is_npc)

    else:
        # Treat entire args as description (for AI generation)
        description = args.strip()
        if is_npc:
            description = parts[1] if len(parts) > 1 else parts[0]
        print(f"\n  Generating {'NPC' if is_npc else 'character'} from description...")
        char_data = generator.generate_from_description(description, is_npc=is_npc)

    if not char_data:
        return "Character creation cancelled."

    # Show preview
    print(f"\n  === {char_data['name']} ===")
    print(f"  Affiliation: {char_data['affiliation']}")
    print(f"  SPECIAL: S:{char_data['special']['strength']} P:{char_data['special']['perception']} "
          f"E:{char_data['special']['endurance']} C:{char_data['special']['charisma']} "
          f"I:{char_data['special']['intelligence']} A:{char_data['special']['agility']} "
          f"L:{char_data['special']['luck']}")
    print(f"  Skills: {', '.join(char_data['skills'])}")
    print(f"  Background: {char_data['background'][:80]}...")

    # Confirm save
    confirm = input("\n  Save character? (y/n/edit): ").strip().lower()

    if confirm == "edit":
        # Allow editing via interactive mode
        char_data = generator.interactive_create(is_npc=is_npc)
        confirm = "y"

    if confirm in ("y", "yes"):
        filepath = generator.save_character(char_data, is_npc=is_npc)
        return f"Character saved to {filepath}"
    else:
        return "Character creation cancelled."
