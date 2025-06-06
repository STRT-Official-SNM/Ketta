# control.py

import socket
import sys

# The UDP port must match the one in app.py
UDP_PORT = 45454
HOST = "127.0.0.1"  # localhost

def send_command(command: str):
    """Sends a command to the running orb application via UDP."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        # Encode the command string into bytes
        message = command.encode('utf-8')
        # Send the message
        sock.sendto(message, (HOST, UDP_PORT))
        print(f"Sent command: '{command}'")

if __name__ == "__main__":
    # A list of valid commands to send
    valid_commands = ["listening", "thinking", "speaking", "reset"]
    
    if len(sys.argv) < 2:
        print("Usage: python control.py [command]")
        print(f"Available commands: {', '.join(valid_commands)}")
        sys.exit(1)

    command_to_send = sys.argv[1].lower()

    if command_to_send in valid_commands:
        send_command(command_to_send)
    else:
        print(f"Error: '{command_to_send}' is not a valid command.")
        print(f"Available commands: {', '.join(valid_commands)}")
        sys.exit(1)
