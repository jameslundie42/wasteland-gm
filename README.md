# Wasteland GM

**V.A.U.L.T. - Virtual Agent Utility for Learning Tabletop**

A Fallout-themed tabletop RPG framework that orchestrates AI players (Claude via Anthropic API) controlled by a human Game Master. Implements the 2d20 system for skill checks and features full character management, dynamic NPC behavior, creature encounters, party voting, and split-party mechanics.

![Fallout Themed](https://img.shields.io/badge/Theme-Fallout%202d20-blue)
![Python](https://img.shields.io/badge/Language-Python%203-green)
![Claude API](https://img.shields.io/badge/AI-Claude%203.5-orange)

---

## 🎮 Features

### Core Gameplay
- **AI-Driven Characters**: Each player character is controlled by Claude with customizable personalities, skills, and behavior
- **2d20 Skill System**: Full Fallout 2d20 mechanics - Target Number (Attribute + Skill), dice pools, critical successes, complications, and AP generation
- **Dynamic Narration**: GM narrates scenes, characters respond in-character, with automatic skill check detection via tags
- **Rich Character Stats**: SPECIAL attributes (1-10 scale), skills, perks, health tracking, radiation, conditions, body part damage
- **Inventory Management**: Full item economy with weight calculations, pricing system, barter checks, trading between characters

### Advanced Features
- **Creature System**: Spawn enemies from templates, track combat encounters, promote creatures to full NPCs
- **Combat Tracking**: Initiative order, round-robin turn management, action economy
- **Party Voting**: Majority votes and split-party votes with automatic scene management
- **Parallel Scenes**: Handle split parties simultaneously, manage different scenes and rejoin groups
- **Faction System**: Track faction relations, character allegiances, allies/enemies lists
- **NPC Dialogue**: Configurable auto-generate or manual GM dialogue modes
- **Campaign Management**: Multi-session campaigns with persistent character state, location tracking, quest logging

### AI Integration
- **Prompt Caching**: Anthropic prompt caching for ~90% cost reduction on cached static content (skills, perks, character identity)
- **History Summarization**: Automatic conversation summary to keep token usage efficient (old exchanges summarized via Haiku)
- **Multi-Turn Conversations**: Characters can address each other, creating dialogue chains
- **Agent-to-Agent Interaction**: AI players respond to each other's statements with optional GM guidance

---

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Anthropic API key (get one at [console.anthropic.com](https://console.anthropic.com))

### Installation

1. Clone the repository:
```bash
git clone https://github.com/jameslundie42/wasteland-gm.git
cd wasteland-gm
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up your Anthropic API key:
```bash
# Create a .env file in the project root
echo "ANTHROPIC_API_KEY=your_api_key_here" > .env
```

4. Run the game:
```bash
python main.py
```

### Basic Gameplay Flow

1. **Main Menu**: Create new campaign or load existing
2. **Campaign Setup** (optional wizard):
   - Define player characters and AI agents
   - Set up locations, factions, initial quests
3. **Start Session**: Create scenes and add characters
4. **GM Narration**: Type narrative text or commands
5. **Character Responses**: AI characters respond in-character, parsed for actions
6. **Resolution**: Skill checks, trades, and combat managed automatically

### Example Narration

```
GM: Doc and Marcus enter an abandoned vault.
    They see terminal screens with flickering text.
    What do you do?

Doc: I approach the nearest terminal cautiously,
    [CHECK: science] trying to understand what happened here.

Marcus: I scan the room for any signs of life or danger.
    [CHECK: perception]
```

---

## 📖 Project Structure

```
wasteland-gm/
├── main.py                 # Game loop entry point with main menu
├── session.py             # Game orchestrator - narration, commands, game flow
├── character.py           # Character domain model (SPECIAL stats, skills, inventory)
├── agent.py              # Claude API abstraction with prompt caching
├── requirements.txt      # Python dependencies
│
├── agents/               # AI agent configurations
│   ├── default.yaml      # Default player agent with skill guidance
│   └── npc_*.yaml        # NPC agent variations (hostile, neutral, friendly)
│
├── characters/           # Character YAML files
│   ├── doc.yaml         # Doc Rivera (example player character)
│   └── jack.yaml        # Jack (example NPC)
│
├── data/                 # Game data (YAML/JSON)
│   ├── skills.yaml       # Skill definitions + SPECIAL mapping
│   ├── perks.yaml        # 17 perks with requirements and effects
│   ├── actions.yaml      # Named actions for skill check triggers
│   ├── items.yaml        # 25+ items with properties (consumables, weapons, armor)
│   └── item_database.py  # Singleton loader for items
│
├── models/               # Data models
│   ├── special_stats.py  # SPECIAL stat calculations with modifiers
│   ├── stat_modifier.py  # Temporary stat modifiers
│   ├── inventory.py      # Character inventory management
│   ├── body_parts.py     # Body part damage tracking
│   ├── item.py          # Item data structure
│   ├── game_state.py    # Campaign, session, scene hierarchies
│   ├── table_state.py   # Play flow and table state tracking
│   ├── creature.py      # Creature/NPC templates and instances
│   ├── faction_relations.py # Faction relation tracking
│   └── party_vote.py    # Voting system for split decisions
│
├── systems/              # Game rule systems
│   ├── skill_checks.py   # 2d20 mechanics implementation
│   ├── dice_roller.py    # Dice rolling (local RNG + API calls)
│   ├── pricing.py        # Item pricing with modifiers
│   ├── stat_system.py    # Stat calculations
│   └── character_generator.py # Interactive character creation
│
├── commands/             # Command handlers
│   ├── inventory_commands.py  # /give, /take, /use, /weight
│   └── skill_check_commands.py # /check command handling
│
├── .github/
│   └── copilot-instructions.md # AI agent development guide
│
└── README.md            # This file
```

---

## 🎯 Core Systems

### Character Model
- **SPECIAL Stats** (1-10): Strength, Perception, Endurance, Charisma, Intelligence, Agility, Luck
- **Skills**: Player-defined skill lists (Guns, Melee, Medicine, Survival, Perception, Science, etc.)
- **Perks**: Special abilities with requirements and effects (17 perks organized by category)
- **Health**: `Endurance + Luck + (Level - 1)` HP, tracked separately from radiation
- **Radiation**: 0-1000 scale with Rad-Away treatment
- **Conditions**: Persistent statuses (crippled, poisoned, etc.)
- **Body Parts**: Individual limb tracking with separate HP per limb
- **Inventory**: Weight-based capacity, item stacking, consumable effects

### 2d20 Skill System
- **Target Number (TN)** = Attribute + Skill
- **Roll**: 2d20 base, buy up to 3 more dice with AP (max 5d20 total)
- **Success**: Roll ≤ TN
- **Critical**: Roll of 1 = 2 successes
- **Complication**: Roll of 20 (still can succeed if ≤ TN)
- **Difficulty**: 0-5 successes needed
- **Extra Successes**: Generate Action Points for next turn

### Agent Behavior
- **System Prompt**: Split into static (cached by Anthropic) and dynamic portions
  - **Static (Cached)**: Agent config, character identity, background, skills, perks
  - **Dynamic (Fresh)**: HP, inventory, radiation, conditions, conversation history
- **Response Tags**: Characters use `[CHECK: skill]`, `[USE: item]`, `[GIVE: qty TO name]` to trigger actions
- **History Management**: Last N exchanges kept; older messages summarized via Claude Haiku

---

## 📋 Commands Reference

### Narration & Basics
```
(type text)              # Narrate to all characters in scene
@<character> (text)      # Narrate to specific character
@<char1> @<char2> (text) # Narrate to multiple characters
/characters              # List all active characters
/info <character>        # Show detailed character info
/help                    # Interactive help menu
```

### Character Management
```
/create                  # Show character creation options
/create random [name]    # Generate random character
/create input           # Interactive character creation
/load <file> [agent]    # Load character from YAML
/agent                  # List available NPC agents
/agent <target> <agent> # Change character/creature agent
```

### Inventory & Items
```
/inventory <character>   # Show inventory
/give <char> <item> [qty] # Give item to character
/take <char> <item> [qty] # Take item from character
/use <char> <item>       # Use item on self
/use <char> <item> on <target> # Use item on another
/weight <character>      # Show carry weight info
/items                   # List all available items
```

### Combat & Checks
```
/bodyparts <character>   # Show body parts status
/damage <char> <part> <amt> # Damage specific body part
/check <character> <skill> # Manually trigger skill check
/combat start            # Begin combat
/combat add <char>       # Add combatant
/next                    # Advance to next turn
/turn action             # Use major action
```

### Campaign & Scenes
```
/campaign                # Show campaign status
/campaign new [name]     # Create new campaign
/campaign new wizard     # Interactive setup
/campaign save           # Save to file
/campaign load <file>    # Load from file
/scene new <name> [loc]  # Create new scene
/enter <character>       # Add character to scene
/exit <character>        # Remove character from scene
```

### Creatures & NPCs
```
/spawn <template> [count] # Spawn creatures
/spawn list              # List templates
/creatures               # List active creatures
/promote <creature> [name] # Convert to Character
/loot <creature>         # Show loot from dead creature
```

### Table & Voting
```
/table                   # Show table state
/spotlight <character>   # Give spotlight to one character
/around [question]       # Go around table for responses
/vote <question>         # Start majority vote
/vote split <question>   # Start split-party vote
/vote resolve            # Apply vote results
/parallel                # Show parallel scenes
/parallel next           # Switch to next scene
/parallel rejoin         # Rejoin split party
```

### Factions
```
/factions                # List all factions
/faction <name>          # Show faction details
/ally <char> <target>    # Add ally
/enemy <char> <target>   # Add enemy
```

---

## 🛠️ Development

### Adding a New Perk
1. Add entry to `data/perks.yaml`:
```yaml
Perk Name:
  category: combat  # or survival, dialogue, utility, faction
  description: "What this perk does"
  requirements:
    strength: 5
    skill: Guns
  effects:
    damage_bonus: 0.15
```

2. Characters automatically load perks from YAML:
```python
char.add_perk("Perk Name")  # Add to character
char.has_perk("Perk Name")  # Check if they have it
```

### Adding a New Item
1. Add to `data/items.yaml`:
```yaml
items:
  Item Name:
    item_type: consumable  # or weapon, armor, misc, medical
    weight: 0.5
    value: 50  # in caps
    max_stack: 99
    consumable: true
    effects:
      heal: 25
    description: "Item description"
```

2. ItemDatabase loads automatically on startup

### Creating a Custom Agent
1. Create `agents/custom_agent.yaml`:
```yaml
name: "Agent Display Name"
system_prompt: "Behavioral instructions and character background..."
traits:
  - trait1
  - trait2
model: "claude-3-5-sonnet-20241022"
temperature: 0.7
max_tokens: 300
max_history: 10
voice: "Dialogue style guidance..."
```

2. Assign to character:
```python
char.player = Agent.from_yaml('agents/custom_agent.yaml')
```

---

## 📚 Key Documentation

- **[Copilot Instructions](.github/copilot-instructions.md)** - Comprehensive AI agent development guide
- **[Claude Code Instructions](.claude)** - Instructions for Claude Code
- **Character.from_yaml()** - Load characters from YAML files with full state
- **Agent.respond()** - Get Claude responses for characters
- **Session.gm_narrate()** - Process GM narration and character responses
- **SkillCheckSystem** - 2d20 mechanics implementation

---

## 🎨 Architecture Highlights

### Data-Driven Design
All game content stored in YAML/JSON files, not hardcoded:
- **skills.yaml**: Skill definitions (name, SPECIAL attribute, description)
- **perks.yaml**: Perk database with requirements and effects
- **items.yaml**: Item properties (type, weight, value, effects)
- **actions.yaml**: Named actions triggering skill checks
- **agents/\*.yaml**: NPC/player AI configurations
- **characters/\*.yaml**: Full character state snapshots

### Singleton Patterns
- `SkillDatabase.get_instance()` - O(1) skill/action lookups
- `ItemDatabase.get_instance()` - O(1) item data lookups
- `DiceRoller.get_instance()` - Centralized RNG state
- `CreatureRegistry.get_instance()` - Active creature management

### Prompt Caching Optimization
Anthropic prompt caching reduces costs by ~90% on repeated content:
- Static system prompt (agent config + character identity) is cached
- Conversation history cached at last message boundary
- Dynamic state (HP, inventory) refreshed per turn
- Older exchanges summarized with Haiku before removal

### Flexible Character Loading
Characters support multiple input formats for backward compatibility:
- Legacy: list of items → converted to Inventory object
- Modern: dict or Inventory object directly
- YAML files with full state preservation via `from_yaml()`

---

## 🔧 Technologies

- **Python 3.8+**: Core language
- **YAML**: Configuration and data format
- **Anthropic API**: Claude 3.5 Sonnet for AI players
- **Fallout 2d20 System**: Game mechanics framework

---

## 📜 License & Attribution

**Fallout** is a trademark of Bethesda Softworks LLC, a ZeniMax Media company.  
This project is not affiliated with Bethesda Softworks LLC.

**2d20 System** is a trademark of Modiphius Entertainment.  
This project is not affiliated with Modiphius Entertainment.

---

## 🤝 Contributing

Contributions are welcome! Areas for enhancement:
- More creature templates and encounters
- Additional perks and skill checks
- Extended faction system with dynamic relations
- Combat visual improvements
- Quest system with objectives and rewards
- Save/load game state persistence

---

## 📞 Support

For issues, questions, or feedback:
1. Check `.github/copilot-instructions.md` for architecture overview
2. Review existing character/agent YAML files for examples
3. Test new features with provided test scripts
4. Use `/help` command in-game for interactive help menu

---

## 🎮 Example Campaign

**Campaign: "The Vault Opening"**

**Player Characters:**
- Doc Rivera (Doctor, Survival/Medicine focused) - controlled by `default.yaml` agent
- Marcus Steel (Soldier, Combat/Guns focused) - custom combat agent

**NPCs:**
- Jack the Trader (Neutral, trades items) - `npc_trader.yaml` agent
- Enclave Commander (Hostile faction) - `npc_hostile.yaml` agent

**Starting Scene:**
- Location: Vault 13 entrance
- Objective: Investigate strange transmissions from vault
- Encounters: Radroaches (easy), Vault door locked (science check)

**Progression:**
- Skill checks to bypass security
- Party vote: Fight or negotiate with vault dwellers
- Split party investigation (parallel scenes)
- Faction relations with Brotherhood of Steel

---

**Happy gaming, Wastelander!**

*"War. War never changes."* 🎭

