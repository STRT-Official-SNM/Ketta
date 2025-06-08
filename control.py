# control.py

import socket
import sys

# --- Configuration ---
# Define the unique ports for each application
HOST = "127.0.0.1"  # Use localhost for both
UI_COMMAND_UDP_PORT = 45454   # Port for the main UI application (app.py)
TTS_COMMAND_UDP_PORT = 45456  # Port for the TTS audio player script

def send_ui_command(command: str):
    """Sends a command to the UI application (app.py)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(command.encode('utf-8'), (HOST, UI_COMMAND_UDP_PORT))
        print(f"Sent UI command: '{command}'")
    except Exception as e:
        print(f"Error sending command to UI: {e}")

def send_tts_command(command: str):
    """Sends a command to the TTS audio player script."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(command.encode('utf-8'), (HOST, TTS_COMMAND_UDP_PORT))
        print(f"Sent TTS command: '{command}'")
    except Exception as e:
        print(f"Error sending command to TTS: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("\nUsage: python control.py <target> <command>")
        print("\nTargets:")
        print("  ui       - Controls the visual orb (app.py)")
        print("  tts      - Controls the audio player")
        print("\nExamples:")
        print("  python control.py ui show")
        print("  python control.py ui listening")
        print("  python control.py tts stop_audio")
        sys.exit(1)

    target = sys.argv[1].lower()
    command_to_send = sys.argv[2].lower()

    if target == 'ui':
        send_ui_command(command_to_send)
    elif target == 'tts':
        send_tts_command(command_to_send)
    else:
        print(f"Error: Invalid target '{target}'. Use 'ui' or 'tts'.")
        sys.exit(1)
