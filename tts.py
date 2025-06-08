# tts_audio_player.py

import subprocess
import os, sys
import concurrent.futures
import shutil
import re
import threading
import time
import queue
import socket
import control

# --- Configuration ---
PIPER_EXECUTABLE_PATH = 'piper'
MODEL_PATH = './tts/en_US-hfc_female-medium.onnx'
CONFIG_PATH = './tts/en_US-hfc_female-medium.onnx.json'
OUTPUT_INDIVIDUAL_AUDIO_DIR = 'audio'
MAX_WORKERS = 4
# This is the dedicated port this script will LISTEN on.
TTS_COMMAND_UDP_PORT = 45456

# --- Global State ---
audio_playback_queue = queue.Queue()
# --- REMOVED: playback_finished_event was causing the thread to die. ---
current_playback_process = None # Holds the current ffplay process
# This new event will signal the generation process to stop.
generation_stop_event = threading.Event()


# --- Helper Functions (Unchanged) ---
def split_text_into_sentences(text):
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]

def generate_audio_for_sentence(sentence_id, sentence, piper_exec, model, config, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    output_filepath = os.path.join(output_dir, f"s_{sentence_id}.wav")
    try:
        command = [piper_exec, '-m', model, '-c', config, '-f', output_filepath]
        result = subprocess.run(command, input=sentence, capture_output=True, text=True, check=True, timeout=60)
        return output_filepath
    except Exception as e:
        print(f"An error occurred generating audio for sentence {sentence_id}: {e}")
        return None

# --- Threading Functions ---
def command_listener_thread():
    """Listens for UDP commands and controls both playback and generation."""
    global current_playback_process
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(('localhost', TTS_COMMAND_UDP_PORT))
        print(f"TTS script listening for commands on UDP port {TTS_COMMAND_UDP_PORT}")
        while True:
            data, _ = sock.recvfrom(1024)
            command = data.decode('utf-8').strip()
            if command == 'stop_audio':
                print("Received 'stop_audio' command. Halting generation and playback.")
                # 1. Signal all processes to stop
                generation_stop_event.set()

                # 2. Clear the input file to prevent re-processing
                with open('output.txt', 'w') as f: f.write('')

                # 3. Terminate any current audio playback
                if current_playback_process and current_playback_process.poll() is None:
                    print("Terminating current audio process...")
                    current_playback_process.terminate()
                    current_playback_process = None
                
                # --- CHANGE START: Robustly clear the queue ---
                # This ensures that queue.join() in the main thread will not block.
                print("Clearing audio playback queue...")
                while not audio_playback_queue.empty():
                    try:
                        audio_playback_queue.get_nowait()
                        audio_playback_queue.task_done() # CRITICAL: Signal that the task is done
                    except queue.Empty:
                        break
                # --- CHANGE END ---
                
                # 4. Tell the UI to go back to its idle state
                control.send_ui_command('reset')


def playing_now_thread():
    """A persistent worker thread that plays audio from the queue."""
    global current_playback_process
    # --- CHANGE: This thread should run forever, waiting for work.
    while True:
        try:
            # This will block until an item is available.
            audio_file_path = audio_playback_queue.get()
            
            # If a stop was triggered, just throw away the item and continue.
            if generation_stop_event.is_set():
                audio_playback_queue.task_done()
                continue

            control.send_ui_command('speaking')
            try:
                current_playback_process = subprocess.Popen(
                    ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet', audio_file_path],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                current_playback_process.wait()
            except FileNotFoundError:
                print("\n\nERROR: 'ffplay' command not found. Please install FFmpeg.\n\n")
                # Can't recover from this, so we exit the thread.
                return
            finally:
                current_playback_process = None

            audio_playback_queue.task_done() # Signal that this item is processed.
            
            # --- CHANGE: This logic now belongs in the main loop.
            # if audio_playback_queue.empty():
            #     control.send_ui_command('reset')
        except Exception as e:
            # This thread should be robust.
            print(f"Error in playback thread: {e}")

# --- Main Execution ---
def main():
    input_file_name = 'output.txt'

    # Start helper threads
    cmd_listener = threading.Thread(target=command_listener_thread, daemon=True)
    cmd_listener.start()
    playing_thread = threading.Thread(target=playing_now_thread, daemon=True)
    playing_thread.start()
    print("Started 'playing now' and 'command listener' threads.")

    while True:
        # Reset event for the new loop
        generation_stop_event.clear()

        print(f"\nMonitoring '{input_file_name}' for new content...")
        input_text = ""
        while True:
            # Also check for stop event while waiting for the file
            if generation_stop_event.is_set(): break
            if os.path.exists(input_file_name):
                with open(input_file_name, 'r', encoding='utf-8') as f:
                    current_text = f.read().strip()
                if current_text:
                    input_text = current_text
                    break
            time.sleep(1)

        if generation_stop_event.is_set():
            print("Skipping processing due to stop signal.")
            continue

        if input_text:
            if os.path.exists(OUTPUT_INDIVIDUAL_AUDIO_DIR):
                shutil.rmtree(OUTPUT_INDIVIDUAL_AUDIO_DIR)
            os.makedirs(OUTPUT_INDIVIDUAL_AUDIO_DIR, exist_ok=True)
            sentences = split_text_into_sentences(input_text)
            if not sentences:
                with open(input_file_name, 'w') as f: f.write('')
                continue

            generated_paths = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                future_to_id = {
                    executor.submit(generate_audio_for_sentence, i, sentence,
                        PIPER_EXECUTABLE_PATH, MODEL_PATH, CONFIG_PATH, OUTPUT_INDIVIDUAL_AUDIO_DIR): i
                    for i, sentence in enumerate(sentences)
                }

                for future in concurrent.futures.as_completed(future_to_id):
                    if generation_stop_event.is_set():
                        print("Stop signal received. Cancelling remaining generation tasks.")
                        for f in future_to_id: f.cancel()
                        break 

                    sentence_id = future_to_id[future]
                    try:
                        audio_path = future.result()
                        if audio_path:
                            generated_paths[sentence_id] = audio_path
                    except Exception as exc:
                        print(f'Sentence {sentence_id} generated an exception: {exc}')

            # Only queue audio if generation was NOT interrupted
            if not generation_stop_event.is_set():
                print("Generation complete. Queueing files for playback.")
                for i in range(len(sentences)):
                    if i in generated_paths:
                        audio_playback_queue.put(generated_paths[i])
                
                # This now correctly waits for the persistent playback thread to finish all items.
                audio_playback_queue.join() 
                
                # Check again in case a stop command came during playback.
                if not generation_stop_event.is_set():
                     print("\n--- All audio finished playing. ---")
                     control.send_ui_command('reset') # Send reset here
                     time.sleep(1) # Give a moment before hiding
                     control.send_ui_command('hide')
                else:
                     print("\n--- Playback was interrupted. ---")
            else:
                print("\n--- Generation was interrupted. Playback aborted. ---")
            
            with open(input_file_name, 'w') as f: f.write('')


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nProgram interrupted by user. Shutting down...")
        generation_stop_event.set()
