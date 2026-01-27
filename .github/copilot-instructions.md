# Wasteland GM - AI Coding Agent Guide

## Project Overview
**Wasteland GM** is a Fallout-themed tabletop RPG framework using the 2d20 system. It orchestrates AI players (Claude via Anthropic API) controlling characters in a game session managed by a human Game Master.

### Architecture
```
main.py (game loop entry)
  ├── Session (orchestrates game flow, character lookup, commands)
  ├── Character (player data: stats, inventory, conditions, perks)
  ├── Agent (Claude interaction, prompt engineering, history management)
  └── System modules (dice rolls, skill checks, pricing, stat calculations)
```

## Character Model (character.py)
**Core domain model** - Characters are persistent entities with:
- **SPECIAL stats** (Strength 1-10 scaling): `special.get_base_stat()`, `get_effective_stat()` (with modifiers)
- **Skills** (Guns, Melee, Medicine, etc.) - list of names, used in 2d20 rolls
- **Perks** - special abilities with requirements/effects (see data/perks.yaml)
- **Inventory** - Inventory object managing items with quantity tracking
- **Health/Radiation** - HP calculated as `endurance + luck + (level-1)`, radiation 0-1000
- **Body Parts** - track crippled limbs separately
- **Conditions** - persistent statuses (crippled, poisoned, etc.)

**YAML Serialization Pattern**: Characters save/load from `characters/*.yaml` with full state preservation. Constructor accepts both dict and object forms for backward compatibility.

```python
# Creating characters (used in main.py)
doc = Character.from_yaml('characters/doc.yaml')
doc.player = agent_instance  # Assign controlling agent
```

## Agent Model (agent.py)
**Claude API abstraction** - Manages multi-turn conversations with prompt engineering:
- **System prompt** split into static (cached) + dynamic (HP, inventory, recent history)
  - **Cached (static)**: Agent config, character identity, background, traits, **skills, perks** (these don't change)
  - **Dynamic (not cached)**: HP, inventory, radiation, conditions, history summary (change frequently)
- **History management**: Keeps last N exchanges; older messages summarized with Haiku
- **Anthropic caching**: Static portions use prompt caching for cost efficiency (~90% cost reduction on cached content)
- **Tags in responses**: `[CHECK: skill]`, `[USE: item]`, `[GIVE: qty TO name]` trigger Session actions

**Key methods**:
- `respond(character, narration)` - returns character's action/dialogue
- `_summarize_messages()` - uses Claude to compact old conversation
- Traits + character personality merged in system prompt

**Skill guidance for Agent prompts**: Include clear skill→context mappings in YAML to guide Claude:
- **Perception**: spot/hear/sense environmental details
- **Survival**: track, forage, identify creatures, wilderness knowledge
- **Guns/Melee**: combat attacks
- **Medicine**: heal injuries, diagnose conditions, treat poison/radiation
- **Science**: identify technology, hack terminals, analyze data
- **Lockpick**: open locked containers/doors
- **Sneak**: avoid detection, stealth movement
- **Barter/Speech**: negotiate, persuade, intimidate, deceive

## Session Management (session.py)
**Game orchestrator** - Links GM input to character actions:
- **Character lookup**: O(1) via `_name_lookup` dict (names + aliases, case-insensitive)
- **Command routing**: `/inventory Doc`, `/give`, `/help`, `/quit`
- **Skill checks**: Detects `[CHECK: skill]` tags, validates, rolls 2d20, applies success/complication logic
- **Automatic parsing**: Extracts character names from multi-word commands

**Usage flow**:
1. GM types narrative or command
2. Session routes to `gm_narrate()` or `handle_command()`
3. For narration: each character's agent gets response prompt, tags are parsed
4. Tags trigger Session methods (inventory, skill checks, commerce)

## Game Systems

### Skill Checks (systems/skill_checks.py)
**2d20 mechanics from Fallout RPG**:
- Target Number = SPECIAL stat + Skill rank
- Roll 2d20, buy up to 3 more dice with Action Points (max 5d20)
- Success = roll ≤ TN; Crit (roll 1) = 2 successes; Complication = roll 20
- Difficulty = successes needed (0-5); extras generate AP

**Data-driven**: Skills defined in `data/skills.yaml` (attribute-mapped). Actions with skill requirements in `data/actions.yaml`.

### Pricing System (systems/pricing.py)
- Base prices in `data/items.json`
- Agent price modifiers in YAML: `price_modifiers: {key: 1.25}`
- Methods: `get_buy_price()`, `get_sell_price()`, handles modifier stacking

### Stat Calculations (systems/stat_system.py, models/)
- **SPECIALStats**: tracks base + modifiers (temporary stat buffs)
- **StatModifier**: duration-based (expires after N rounds)
- **BodyParts**: track individual limb health (head, torso, etc.)

## Data Files (conventions)

| File | Format | Purpose | Note |
|------|--------|---------|------|
| `data/skills.yaml` | Key-value pairs | Skill definitions + SPECIAL mapping | Modify to add skills |
| `data/perks.yaml` | Nested: name→category/description/requirements/effects | Perk database | Just added; extensible format |
| `data/items.json` | Nested: name→type/weight/value/effects | Item database | Used by ItemDatabase singleton |
| `data/actions.yaml` | Named actions with skill requirements | GM action prompts | For skill check triggers |
| `characters/*.yaml` | Full character state snapshot | Player/NPC data | Load with `Character.from_yaml()` |
| `agents/*.yaml` | Agent config (prompt, traits, model params) | AI behavior definition | Claude model + temperature + history size |

## Development Workflow

### Adding Features
1. **New skills**: Add to `data/skills.yaml` with `stat` and `description`
2. **New perks**: Add to `data/perks.yaml` with `category`, `description`, `requirements`, `effects`
3. **New character**: Create `characters/name.yaml` following `doc.yaml` template
4. **New agent**: Create `agents/name.yaml` with system_prompt, traits, model config
5. **Character stat changes**: Edit Character YAML or use methods like `char.add_stat_modifier()`, `char.take_damage()`

### Running
```bash
python main.py  # Starts interactive game loop
```

### Testing Character State
```python
from character import Character
doc = Character.from_yaml('characters/doc.yaml')
doc.print_info()  # Full character dump (includes perks)
```

## Critical Patterns

### Backward Compatibility
- Character constructor accepts `dict` or `SPECIALStats` for `special` param
- Inventory handles list (legacy), dict, or Inventory object
- from_yaml() auto-handles all formats—preserve this flexibility

### Singleton Patterns
- `SkillDatabase.get_instance()` - loads skills/actions YAML once
- `ItemDatabase.get_instance()` - loads items.json once
- `DiceRoller.get_instance()` - ensures single RNG state

### YAML as Config
- Character/Agent/Skill data always in YAML files (not hardcoded)
- Extensible: new perks/items/actions don't require code changes
- Follow nesting (perks have category, requirements, effects; skills have stat, description)

### String Interpolation in Agent Prompts
- Use f-strings to inject character state (name, HP, inventory, traits)
- Static portions cached by Anthropic; dynamic portions fresh per turn
- System prompt structure: `{agent config}\n{character identity}\n{game state}`

## Common Workflows for AI

### Extend Character Abilities
- Add perk methods mirror condition methods: `add_perk()`, `remove_perk()`, `has_perk()`
- Add stat modifiers via `character.add_stat_modifier(StatModifier(...))`

### Add NPC Behavior
- Create `agents/npc_name.yaml` with custom system_prompt
- Assign to character: `npc.player = Agent.from_yaml('agents/npc_name.yaml')`
- Use different models/temperatures for varied NPC personality

### New Game Mechanics
- **Dice rolls**: Use `DiceRoller.get_instance().roll_dice(num_dice, sides)`
- **Skill checks**: Trigger via `[CHECK: skill]` tag in agent response
- **Pricing**: Call `PricingSystem.get_buy_price(item_name, modifier_dict)`

## Key Files to Reference
- **Character domain**: [character.py](../character.py) (SPECIAL, perks, health, serialization)
- **Agent interaction**: [agent.py](../agent.py) (Claude prompting, history, caching)
- **Game loop**: [main.py](../main.py), [session.py](../session.py) (flow orchestration)
- **2d20 rules**: [systems/skill_checks.py](../systems/skill_checks.py) (mechanics implementation)
- **Stat tracking**: [models/special_stats.py](../models/special_stats.py), [models/stat_modifier.py](../models/stat_modifier.py)
