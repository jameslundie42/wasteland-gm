# Perks System Documentation

## Overview
The Perks system has been successfully integrated into the Character class. Perks are special abilities and bonuses that provide unique mechanics and benefits to characters.

## Features Added

### Character Class Updates
- Added `perks` attribute to the Character class to track a character's perks
- Added `add_perk(perk)` method to add a perk to a character
- Added `remove_perk(perk)` method to remove a perk from a character
- Added `has_perk(perk)` method to check if a character has a perk
- Updated `to_dict()` method to include perks in serialization
- Updated `from_yaml()` method to load perks from YAML character files
- Updated `print_info()` method to display character perks

### Perks YAML File
Created `data/perks.yaml` with 17 perks organized by category:

#### Combat Perks (5)
- **Bloody Mess**: 15% bonus damage with all weapons (requires Luck 5)
- **Sharpshooter**: +20% accuracy with ranged weapons (requires Perception 6, Guns 40)
- **Melee Master**: +25% damage with melee weapons (requires Strength 7, Melee 50)
- **Iron Fist**: +15% unarmed damage (requires Strength 6, Unarmed 30)
- **Evasion**: +10% dodge chance during combat (requires Agility 7, Sneak 40)

#### Survival Perks (4)
- **Rad Resistance**: 50% radiation resistance (requires Endurance 6)
- **Survival Instinct**: 25% less damage from environmental sources (requires Endurance 7, Survival 50)
- **Chemist**: 25% increased potency for crafted chems (requires Intelligence 6, Science 40)
- **Scavenger**: 25% more items when looting (requires Perception 6, Survival 40)

#### Dialogue Perks (2)
- **Smooth Talker**: +10% success on speech checks (requires Charisma 7, Speech 50)
- **Honest Trade**: 25% better prices when buying/selling (requires Charisma 6, Barter 40)

#### Utility Perks (4)
- **Fast Learner**: 10% bonus to experience gained (requires Intelligence 7)
- **Technician**: +20% bonus to hacking and lockpicking (requires Intelligence 6, Repair 30)
- **Lucky**: +1 luck bonus (requires Luck 6)
- **Night Eyes**: Can see clearly in darkness (requires Perception 6)

#### Faction Perks (2)
- **Ranger**: Faction reputation with wasteland rangers (requires Agility 6, Survival 50)
- **Smooth Criminal**: Faction reputation with criminal underworld (requires Agility 7, Sneak 60)

## Usage Examples

### Creating a Character with Perks
```python
from character import Character

char = Character(
    name="Wasteland Wanderer",
    special={'strength': 8, 'perception': 7, 'endurance': 7, 
             'charisma': 6, 'intelligence': 6, 'agility': 7, 'luck': 5},
    skills=['Guns', 'Melee', 'Medicine'],
    perks=['Bloody Mess', 'Fast Learner'],  # Add perks here
    background="A survivor of the wastes",
    personality_traits=["Brave", "Clever"]
)
```

### Managing Perks
```python
# Check if character has a perk
if char.has_perk('Bloody Mess'):
    print("Character has Bloody Mess!")

# Add a new perk
char.add_perk('Iron Fist')

# Remove a perk
char.remove_perk('Fast Learner')

# View all perks
print(char.perks)
```

### Loading/Saving Characters with Perks
```python
# Load from YAML
char = Character.from_yaml('characters/doc.yaml')

# Save to YAML (includes perks)
char.save_to_yaml('characters/doc.yaml')

# Convert to dictionary (includes perks)
char_data = char.to_dict()
```

### Displaying Character Info
```python
# Print info (includes perks section)
char.print_info()
```

## YAML File Structure
Each perk in `data/perks.yaml` has:
- **category**: Type of perk (combat, survival, dialogue, utility, faction)
- **description**: Human-readable description of the perk's effect
- **requirements**: Dict of stat/skill requirements needed to take the perk
- **effects**: Dict of game effects/bonuses provided by the perk

## Integration Notes
- Perks are optional when creating a character (defaults to empty list)
- Existing character YAML files without perks will load without error
- The system is backward compatible with existing character saves
- Perks are included in character serialization (to_dict, save_to_yaml)
