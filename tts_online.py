# tts_stream_player.py (Seamless Audio Version)

import subprocess
import os
import threading
import time
import socket
import control
import requests
import stream2sentence as s2s

# --- Configuration ---
AUDIO_API_URL = "https://kettatts.vercel.app/api/generate-audio-stream"
TTS_COMMAND_UDP_PORT = 45456
INPUT_FILE_NAME = 'output.txt'

# --- Global State ---
current_playback_process = None
main_process_stop_event = threading.Event()

def stream_audio_from_api(text_chunk):
    """Calls the streaming audio API and yields audio chunks."""
    payload = {"text": text_chunk}
    try:
        with requests.post(AUDIO_API_URL, json=payload, stream=True, timeout=90) as response:
            if response.status_code == 200:
                print(f"Streaming audio for: '{text_chunk}'")
                for chunk in response.iter_content(chunk_size=4096):
                    yield chunk
            else:
                print(f"API Error for '{text_chunk}': Status {response.status_code}, {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"API Connection Error: {e}")

def command_listener_thread():
    """Listens for 'stop_audio' commands."""
    global current_playback_process
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(('localhost', TTS_COMMAND_UDP_PORT))
        print(f"TTS script listening for commands on UDP port {TTS_COMMAND_UDP_PORT}")
        while True:
            data, _ = sock.recvfrom(1024)
            command = data.decode('utf-8').strip()
            if command == 'stop_audio':
                print("Received 'stop_audio' command. Halting playback.")
                main_process_stop_event.set()
                if current_playback_process and current_playback_process.poll() is None:
                    current_playback_process.terminate()
                control.send_ui_command('reset')

def main_process():
    """Waits for the input file, processes it, and streams audio continuously."""
    global current_playback_process
    while not main_process_stop_event.is_set():
        try:
            print(f"\n--- Waiting for '{INPUT_FILE_NAME}' to appear and have content... ---")
            
            while not (os.path.exists(INPUT_FILE_NAME) and os.path.getsize(INPUT_FILE_NAME) > 0):
                if main_process_stop_event.is_set(): return
                time.sleep(0.1)
            
            print("--- File detected. Starting continuous audio pipeline. ---")
            control.send_ui_command('speaking')

            with open(INPUT_FILE_NAME, 'r', encoding='utf-8') as f:
                sentence_generator = s2s.generate_sentences(f, minimum_sentence_length=8)

                # --- THIS IS THE KEY ARCHITECTURAL CHANGE ---
                # 1. Launch ffplay ONCE outside the loop.
                ffplay_cmd = ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'error', '-i', '-']
                current_playback_process = subprocess.Popen(ffplay_cmd, stdin=subprocess.PIPE)
                
                # 2. Iterate through sentences and pipe all audio to the SINGLE ffplay process.
                for sentence in sentence_generator:
                    if main_process_stop_event.is_set(): break
                    
                    audio_chunk_generator = stream_audio_from_api(sentence)
                    
                    for audio_chunk in audio_chunk_generator:
                        try:
                            if current_playback_process.stdin:
                                current_playback_process.stdin.write(audio_chunk)
                            else:
                                break
                        except (BrokenPipeError, OSError):
                            print("ffplay process closed prematurely.")
                            main_process_stop_event.set() # Set stop event to exit cleanly
                            break
                
                # 3. After the loop, close the pipe and wait for ffplay to finish naturally.
                if current_playback_process.stdin:
                    current_playback_process.stdin.close()
                current_playback_process.wait()
                # --- END OF CHANGE ---

            if not main_process_stop_event.is_set():
                print("\n--- Playback finished successfully. ---")
                control.send_ui_command('reset')
                time.sleep(1)
                control.send_ui_command('hide')
            else:
                print("\n--- Playback was interrupted. ---")
        
        except Exception as e:
            print(f"An error occurred in the main loop: {e}")
        
        finally:
            if os.path.exists(INPUT_FILE_NAME):
                os.remove(INPUT_FILE_NAME)
            main_process_stop_event.clear()
            current_playback_process = None

if __name__ == "__main__":
    cmd_thread = threading.Thread(target=command_listener_thread, daemon=True)
    cmd_thread.start()
    try:
        main_process()
    except KeyboardInterrupt:
        print("\nProgram interrupted by user. Shutting down...")
        main_process_stop_event.set()
