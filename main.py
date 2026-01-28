from dotenv import load_dotenv
load_dotenv()

import os
import yaml
from pathlib import Path
from session import Session
from character import Character
from agent import Agent
from models.game_state import Campaign

LOGO = r"""
             +==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+
            //                                                                                       //
           //     FFFFFFFFFFFF               lllll  lllll                                           //
          //      FFFFFFFFFFFF              lllll  lllll                               ttttt       //
         //     FFFFF                      lllll  lllll      o                       ttttt        //
        //     FFFFF        aaaaaaaaaa   lllll  lllll  ooooo  ooo   uuuuu   uuu  tttttttttttt    //
       //    FFFFFFFFFF  aaaaa  aaaaa   lllll  lllll ooooo  ooooo  uuuuu  uuuuu    ttttt        //
      //    FFFFFFFFFF          aaaaa  lllll  lllll  oo    ooooo  uuuuu  uuuuu    ttttt        //
     //    FFFFF        aaaaaaaaaaaa  lllll  lllll  o        o  uuuuu   uuuuu    ttttt        //
    //    FFFFF       aaaaa  aaaaa   lllll  lllll  ooooo  ooo  uuuuu   uuuuu    ttttt        //
   //   FFFFF        aaaaaaaaaaaaaa lllll  lllll   oooo  ooo   uuuuuuuuuuuu      ttttttt    //
  //                                                  o                                    //
 +==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+==+

            #########################################################################
            #                                                                       #
            #                            V.A.U.L.T.                                 #
            #            Virtual Agent Utility for Learning Tabletop                #
            #                Developed by Jimmie Lundie & Claude                    #
            #                                                                       #
            #########################################################################

            Fallout is a trademark of Bethesda Softworks LLC, a ZeniMax Media company.
            This project is not affiliated with Bethesda Softworks LLC.
            The 2d20 system is a trademark of Modiphius Entertainment.
            This project is not affiliated with Modiphius Entertainment.
"""

MAIN_MENU = """
            +=======================================+
            |           >>> MAIN MENU <<<           |
            +=======================================+
            |                                       |
            |   [1]  New Campaign                   |
            |   [2]  Load Campaign                  |
            |   [3]  Settings                       |
            |   [4]  Exit                           |
            |                                       |
            +=======================================+
"""

# Default settings
DEFAULT_SETTINGS = {
    "auto_save": True,
    "auto_save_interval": 10,  # minutes
    "default_player_agent": "default.yaml",
    "default_npc_agent": "npc_trader.yaml",
    "show_dice_rolls": True,
    "npc_dialogue_mode": "auto",  # "auto" = agents handle NPC dialogue, "manual" = GM writes dialogue
}

SETTINGS_FILE = Path(__file__).parent / "settings.yaml"


def load_settings():
    """Load settings from file or return defaults."""
    if SETTINGS_FILE.exists():
        with open(SETTINGS_FILE, 'r') as f:
            saved = yaml.safe_load(f) or {}
            # Merge with defaults (in case new settings were added)
            settings = DEFAULT_SETTINGS.copy()
            settings.update(saved)
            return settings
    return DEFAULT_SETTINGS.copy()


def save_settings(settings):
    """Save settings to file."""
    with open(SETTINGS_FILE, 'w') as f:
        yaml.dump(settings, f, default_flow_style=False)


def clear_screen():
    """Clear the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def show_main_menu():
    """Display main menu and get user choice."""
    print(MAIN_MENU)
    while True:
        choice = input("            Select option [1-4]: ").strip()
        if choice in ['1', '2', '3', '4']:
            return choice
        print("            Invalid choice. Please enter 1, 2, 3, or 4.")


def create_new_campaign(settings):
    """Create a new campaign and return the session."""
    print("\n" + "=" * 60)
    print("                    NEW CAMPAIGN")
    print("=" * 60)

    # Get campaign name
    name = input("\n  Campaign name: ").strip()
    if not name:
        name = "Wasteland Campaign"

    # Create campaign and session
    session = Session(settings=settings)
    session.campaign = Campaign(name=name)
    session.campaign.new_session("Session 1")

    print(f"\n  Created campaign: {name}")

    # Ask about loading starter characters
    print("\n  Would you like to load starter characters?")
    print("    [1] Yes - Load Doc Rivera and Jack the Trader")
    print("    [2] No  - Start with empty campaign")

    choice = input("\n  Select [1-2]: ").strip()

    if choice == '1':
        load_starter_characters(session, settings)

    # Create initial scene
    print("\n  Creating initial scene...")
    scene_name = input("  Scene name (or Enter for 'Opening Scene'): ").strip()
    if not scene_name:
        scene_name = "Opening Scene"

    location = input("  Location (or Enter for 'The Wasteland'): ").strip()
    if not location:
        location = "The Wasteland"

    session.campaign.current_session.new_scene(scene_name, location)

    # Sync any loaded characters to campaign
    session.handle_command('/campaign sync')

    print(f"\n  Campaign '{name}' is ready!")
    return session


def load_starter_characters(session, settings):
    """Load the default starter characters."""
    agents_dir = Path(__file__).parent / "agents"
    chars_dir = Path(__file__).parent / "characters"

    # Load agents
    player_agent_file = agents_dir / settings.get("default_player_agent", "default.yaml")
    npc_agent_file = agents_dir / settings.get("default_npc_agent", "npc_trader.yaml")

    try:
        player_agent = Agent.from_yaml(str(player_agent_file))
    except Exception as e:
        print(f"  Warning: Could not load player agent: {e}")
        player_agent = None

    try:
        npc_agent = Agent.from_yaml(str(npc_agent_file))
    except Exception as e:
        print(f"  Warning: Could not load NPC agent: {e}")
        npc_agent = None

    # Load characters
    doc_file = chars_dir / "doc.yaml"
    jack_file = chars_dir / "jack.yaml"

    if doc_file.exists():
        try:
            doc = Character.from_yaml(str(doc_file))
            if player_agent:
                doc.player = player_agent
            session.add_character(doc)
            print(f"    Loaded: {doc.name}")
        except Exception as e:
            print(f"  Warning: Could not load Doc Rivera: {e}")

    if jack_file.exists():
        try:
            jack = Character.from_yaml(str(jack_file))
            if npc_agent:
                jack.player = npc_agent
            session.add_character(jack)
            print(f"    Loaded: {jack.name}")
        except Exception as e:
            print(f"  Warning: Could not load Jack: {e}")


def load_campaign_menu(settings):
    """Show load campaign menu and return the session."""
    campaigns_dir = Path(__file__).parent / "campaigns"

    print("\n" + "=" * 60)
    print("                   LOAD CAMPAIGN")
    print("=" * 60)

    # List available campaigns
    if not campaigns_dir.exists():
        print("\n  No campaigns directory found.")
        input("\n  Press Enter to return to main menu...")
        return None

    campaign_files = list(campaigns_dir.glob("*.yaml"))

    if not campaign_files:
        print("\n  No saved campaigns found.")
        input("\n  Press Enter to return to main menu...")
        return None

    print("\n  Available campaigns:\n")
    for i, file in enumerate(campaign_files, 1):
        # Try to read campaign name from file
        try:
            with open(file, 'r') as f:
                data = yaml.safe_load(f)
                name = data.get('name', file.stem)
                sessions = len(data.get('sessions', []))
                chars = len(data.get('characters', {}))
        except:
            name = file.stem
            sessions = '?'
            chars = '?'

        print(f"    [{i}] {name}")
        print(f"        File: {file.name} | Sessions: {sessions} | Characters: {chars}")

    print(f"\n    [0] Back to main menu")

    # Get choice
    while True:
        choice = input(f"\n  Select campaign [0-{len(campaign_files)}]: ").strip()

        if choice == '0':
            return None

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(campaign_files):
                return load_campaign_file(campaign_files[idx], settings)
        except ValueError:
            pass

        print("  Invalid choice.")


def load_campaign_file(filepath, settings):
    """Load a campaign from file and return the session."""
    print(f"\n  Loading {filepath.name}...")

    session = Session(settings=settings)

    try:
        session.campaign = Campaign.load(str(filepath))
    except Exception as e:
        print(f"  Error loading campaign: {e}")
        input("\n  Press Enter to return to main menu...")
        return None

    # Reload active characters
    chars_loaded = 0
    agents_dir = Path(__file__).parent / "agents"

    current_session = session.campaign.current_session
    if current_session:
        for name in current_session.active_characters:
            ref = session.campaign.characters.get(name)
            if ref and ref.file_path and Path(ref.file_path).exists():
                try:
                    char = Character.from_yaml(ref.file_path)

                    # Attach agent if specified in campaign (for PCs)
                    if ref.agent and not ref.is_npc:
                        agent_file = agents_dir / f"{ref.agent}.yaml"
                        if agent_file.exists():
                            try:
                                char.player = Agent.from_yaml(str(agent_file))
                            except Exception as e:
                                print(f"  Warning: Could not load agent {ref.agent}: {e}")

                    # For NPCs, load appropriate NPC agent
                    elif ref.is_npc:
                        agent_file = agents_dir / "npc_neutral.yaml"
                        if agent_file.exists():
                            try:
                                char.player = Agent.from_yaml(str(agent_file))
                            except Exception:
                                pass

                    session.characters[name] = char
                    session._name_lookup[name.lower()] = char
                    for alias in char.aliases:
                        session._name_lookup[alias.lower()] = char
                    chars_loaded += 1
                except Exception as e:
                    print(f"  Warning: Could not load {name}: {e}")

    # Initialize table state with loaded characters
    session._initialize_table_state()

    print(f"\n  Campaign loaded: {session.campaign.name}")
    print(f"  Characters loaded: {chars_loaded}")

    # Show PCs and NPCs
    pcs = [name for name in session.table_state.round_robin_order]
    npcs = [name for name in session.table_state.npc_names]
    if pcs:
        print(f"  Player Characters: {', '.join(pcs)}")
    if npcs:
        print(f"  Notable NPCs: {', '.join(npcs)}")

    if current_session:
        print(f"  Current session: {current_session.name}")
        if current_session.current_scene:
            print(f"  Current scene: {current_session.current_scene.name}")

    return session


def settings_menu(settings):
    """Display and modify settings."""
    while True:
        print("\n" + "=" * 60)
        print("                      SETTINGS")
        print("=" * 60)

        print(f"""
    [1] Auto-save:              {settings['auto_save']}
    [2] Auto-save interval:     {settings['auto_save_interval']} minutes
    [3] Default player agent:   {settings['default_player_agent']}
    [4] Default NPC agent:      {settings['default_npc_agent']}
    [5] Show dice rolls:        {settings['show_dice_rolls']}
    [6] NPC dialogue mode:      {settings['npc_dialogue_mode']}

    [S] Save settings
    [R] Reset to defaults
    [0] Back to main menu
        """)

        choice = input("  Select option: ").strip().lower()

        if choice == '0':
            return settings

        elif choice == '1':
            settings['auto_save'] = not settings['auto_save']
            print(f"  Auto-save set to: {settings['auto_save']}")

        elif choice == '2':
            try:
                val = int(input("  Enter interval in minutes: ").strip())
                if val > 0:
                    settings['auto_save_interval'] = val
            except ValueError:
                print("  Invalid number.")

        elif choice == '3':
            agents = list((Path(__file__).parent / "agents").glob("*.yaml"))
            print("\n  Available agents:")
            for i, a in enumerate(agents, 1):
                print(f"    [{i}] {a.name}")
            try:
                idx = int(input("  Select: ").strip()) - 1
                if 0 <= idx < len(agents):
                    settings['default_player_agent'] = agents[idx].name
            except (ValueError, IndexError):
                print("  Invalid choice.")

        elif choice == '4':
            agents = list((Path(__file__).parent / "agents").glob("*.yaml"))
            print("\n  Available agents:")
            for i, a in enumerate(agents, 1):
                print(f"    [{i}] {a.name}")
            try:
                idx = int(input("  Select: ").strip()) - 1
                if 0 <= idx < len(agents):
                    settings['default_npc_agent'] = agents[idx].name
            except (ValueError, IndexError):
                print("  Invalid choice.")

        elif choice == '5':
            settings['show_dice_rolls'] = not settings['show_dice_rolls']
            print(f"  Show dice rolls set to: {settings['show_dice_rolls']}")

        elif choice == '6':
            print("\n  NPC Dialogue Mode (only affects GM-controlled NPCs, not player characters):")
            print("    [1] auto   - NPCs respond automatically via their agents")
            print("    [2] manual - GM writes NPC dialogue (press Enter to auto-generate)")
            mode_choice = input("\n  Select mode [1-2]: ").strip()
            if mode_choice == '1':
                settings['npc_dialogue_mode'] = 'auto'
                print("  Mode set to: auto")
            elif mode_choice == '2':
                settings['npc_dialogue_mode'] = 'manual'
                print("  Mode set to: manual")
                print("  Tip: Press Enter without typing to auto-generate an NPC response.")

        elif choice == 's':
            save_settings(settings)
            print("  Settings saved!")

        elif choice == 'r':
            settings = DEFAULT_SETTINGS.copy()
            print("  Settings reset to defaults.")


def run_game_session(session):
    """Run the main game loop."""
    print("\n" + "=" * 60)
    print("              ENTERING GAME SESSION")
    print("=" * 60)

    # Show loaded characters
    if session.characters:
        print("\n  Characters in session:")
        for char in session.characters.values():
            player_name = char.player.name if hasattr(char.player, 'name') else char.player
            print(f"    - {char.name} (Lv{char.level}) - {player_name}")

    print("\n  Type /help for available commands.")
    print("  Use @CharName to address specific characters.")
    print("  Type /quit to return to main menu.")

    # Show dialogue mode hint
    dialogue_mode = session.settings.get("npc_dialogue_mode", "auto")
    if dialogue_mode == "manual":
        print("\n  [NPC dialogue: manual - You write NPC responses. Press Enter to auto-generate.]")
    else:
        print("\n  [NPC dialogue: auto - NPCs respond automatically.]")
    print()

    # Game loop
    while True:
        try:
            gm_input = input("GM: ")
        except EOFError:
            break
        except KeyboardInterrupt:
            print("\n")
            continue

        # Skip empty input
        if not gm_input.strip():
            continue

        if gm_input.startswith("/"):
            # Handle GM commands
            cmd = gm_input.lower().strip()
            if cmd in ["/quit", "/exit", "/q", "/menu"]:
                # Offer to save before quitting
                if session.campaign:
                    save = input("Save campaign before exiting? (y/n): ").strip().lower()
                    if save in ['y', 'yes']:
                        result = session.handle_command('/campaign save')
                        print(result)
                print("Returning to main menu...")
                return True  # Return to main menu
            else:
                # Use session's command handler
                result = session.handle_command(gm_input)
                if result:
                    print(result)
        else:
            # Narrate to characters (responses are printed by gm_narrate)
            session.gm_narrate(gm_input)

    return False  # Exit game


def main():
    """Main entry point."""
    clear_screen()
    print(LOGO)

    settings = load_settings()

    while True:
        choice = show_main_menu()

        if choice == '1':
            # New Campaign
            session = create_new_campaign(settings)
            if session:
                if not run_game_session(session):
                    break  # Exit entirely
            clear_screen()
            print(LOGO)

        elif choice == '2':
            # Load Campaign
            session = load_campaign_menu(settings)
            if session:
                if not run_game_session(session):
                    break  # Exit entirely
            clear_screen()
            print(LOGO)

        elif choice == '3':
            # Settings
            settings = settings_menu(settings)
            clear_screen()
            print(LOGO)

        elif choice == '4':
            # Exit
            print("\n  Goodbye, Wastelander. Stay safe out there.\n")
            break


if __name__ == "__main__":
    main()