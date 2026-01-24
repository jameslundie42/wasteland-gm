from dotenv import load_dotenv
load_dotenv()

from session import Session
from character import Character
from agent import Agent

def main():
  # Load agent and character data
  agent = Agent.from_json('agents/default.json')
  doc = Character.from_json('characters/doc.json')
  doc.player = agent

  # Initialize session
  session = Session()
  session.add_character(doc)

  print(f"\nLoaded character: {doc.name}")
  print(f"Level: {doc.level}, HP: {doc.health['current']}/{doc.health['max']}")
  print(f"Carry Weight: {doc.inventory.total_weight:.1f}/{doc.inventory.max_capacity} lbs\n")
  print(f"Type /help for available commands or /info {doc.name} for detailed information.\n")
  print(f"Starting game session...\n")

  # Start game loop
  while True:
    gm_input = input("GM: ")

    # Skip empty input
    if not gm_input.strip():
      continue

    if gm_input.startswith("/"):
      # Handle GM commands
      if gm_input.lower() == "/quit":
        print("Exiting game session...")
        break
      else:
        # Use session's command handler
        result = session.handle_command(gm_input)
        if result:
          print(result)
    else:
      # Narrate to all characters, get their responses, and narrate back
      responses = session.gm_narrate(gm_input)
      for char_name, response in responses.items():
        print(f"{char_name}: {response}")

if __name__ == "__main__":
  main()