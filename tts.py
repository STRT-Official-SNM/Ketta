import subprocess
import os
import concurrent.futures
from pydub import AudioSegment # Still needed for potential future use or if you add playback
import shutil # For creating directories
import re # For manual sentence splitting
import threading # Import the threading module
import time # For the sleep function in the new thread
from playsound import playsound
import queue # Import queue for thread-safe communication
import control

# --- Configuration ---
# IMPORTANT: Update these paths to match your setup!
# Path to the Piper executable (e.g., 'piper' on Linux/macOS, 'piper.exe' on Windows)
PIPER_EXECUTABLE_PATH = 'piper' # Example: adjust this to your actual path

# Path to your downloaded ONNX model file (e.g., 'en_US-lessac-medium.onnx')
# Assuming model files are in the same directory as the script
MODEL_PATH = './tts/en_US-hfc_female-medium.onnx'

# Path to your downloaded model's config file (e.g., 'en_US-lessac-medium.onnx.json')
# Assuming model files are in the same directory as the script
CONFIG_PATH = './tts/en_US-hfc_female-medium.onnx.json'

# Directory to store individual audio files for each sentence
OUTPUT_INDIVIDUAL_AUDIO_DIR = 'audio'

# Maximum number of concurrent TTS processes. Adjust based on your CPU cores and system resources.
MAX_WORKERS = 4 # A good starting point is usually the number of CPU cores.

# --- Global Queue for Playback ---
# This queue will hold the paths of audio files ready for playback.
audio_playback_queue = queue.Queue()
# An event to signal the playback thread to stop when all files are generated and played.
playback_finished_event = threading.Event() # This event will now be used to signal the *end of the program*

# --- Helper Functions ---

def split_text_into_sentences(text):
    """
    Splits the given text into a list of sentences using a manual, rule-based approach.
    This method looks for common sentence-ending punctuation followed by whitespace.
    """
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]

def generate_audio_for_sentence(sentence_id, sentence, piper_exec, model, config, output_dir):
    """
    Generates audio for a single sentence using Piper TTS.
    Returns the path to the generated audio file.
    """
    os.makedirs(output_dir, exist_ok=True)
    output_filepath = os.path.join(output_dir, f"s_{sentence_id}.wav")
    print(f"Generating audio for sentence {sentence_id}: '{sentence[:50]}...'")

    try:
        command = [
            piper_exec,
            '-m', model,
            '-c', config,
            '-f', output_filepath
        ]
        result = subprocess.run(
            command,
            input=sentence,
            capture_output=True,
            text=True,
            check=True
        )
        if result.stderr:
            print(f"Piper TTS stderr for sentence {sentence_id}: {result.stderr}")
        print(f"Finished generating audio for sentence {sentence_id} to {output_filepath}")
        return output_filepath
    except FileNotFoundError:
        print(f"Error: Piper executable not found at '{piper_exec}'. Please check the path.")
        return None
    except subprocess.CalledProcessError as e:
        print(f"Error generating audio for sentence {sentence_id}: {e}")
        print(f"Command: {' '.join(e.cmd)}")
        print(f"Return Code: {e.returncode}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred for sentence {sentence_id}: {e}")
        return None

# --- Modified Thread Function ---
def playing_now_thread():
    """
    This thread continuously checks the queue for audio files to play.
    It sends 'speaking' command before playing and 'reset' command after.
    It stops when the playback_finished_event is set and the queue is empty.
    """
    while not playback_finished_event.is_set() or not audio_playback_queue.empty():
        try:
            audio_file_path = audio_playback_queue.get(timeout=0.5) # Shorter timeout
            print(f"Playing: {audio_file_path}")
            # Send 'speaking' command before playing
            control.send_command('speaking')
            playsound(audio_file_path)
            # Send 'reset' command after playing
            control.send_command('reset')
            print(f"Finished playing: {audio_file_path}")
            audio_playback_queue.task_done()
        except queue.Empty:
            # If the queue is empty, and the main loop isn't finished yet,
            # just wait a bit and check again.
            if not playback_finished_event.is_set():
                time.sleep(0.1)
            else:
                # If playback_finished_event is set and queue is empty,
                # then we can exit the loop.
                pass
        except Exception as e:
            print(f"Error playing audio file: {e}")
            if 'audio_file_path' in locals():
                audio_playback_queue.task_done()
    print("Playback thread: Exiting.")


# --- Main Execution ---

def main():
    input_file_name = 'output.txt'
    
    playing_thread = threading.Thread(target=playing_now_thread)
    playing_thread.daemon = True
    playing_thread.start()
    print("Started 'playing now' thread.")

    while True:
        print(f"\nMonitoring '{input_file_name}' for new content...")
        
        input_text = ""
        while True:
            if os.path.exists(input_file_name):
                with open(input_file_name, 'r') as f:
                    current_text = f.read().strip()
                if current_text:
                    input_text = current_text
                    print(f"New content found in '{input_file_name}'.")
                    break
            time.sleep(1) # Check every 1 second

        # Process the new content
        if input_text:
            # 1. Create the output directory for individual audio files
            # Clear it before processing new input to avoid clutter from previous runs
            if os.path.exists(OUTPUT_INDIVIDUAL_AUDIO_DIR):
                shutil.rmtree(OUTPUT_INDIVIDUAL_AUDIO_DIR)
            os.makedirs(OUTPUT_INDIVIDUAL_AUDIO_DIR, exist_ok=True)
            print(f"Created output directory for individual audios: {OUTPUT_INDIVIDUAL_AUDIO_DIR}")

            # 2. Split input text into sentences
            sentences = split_text_into_sentences(input_text)
            if not sentences:
                print("No sentences found or error in splitting text for the current input. Skipping.")
                # Clear the file even if no sentences were found to prevent re-processing
                with open(input_file_name, 'w') as f:
                    f.write('')
                continue # Go back to the top of the while True loop

            print(f"\nSplit text into {len(sentences)} sentences.")

            # 3. Generate audio for each sentence in parallel
            futures = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                for i, sentence in enumerate(sentences):
                    future = executor.submit(
                        generate_audio_for_sentence,
                        i, sentence,
                        PIPER_EXECUTABLE_PATH, MODEL_PATH, CONFIG_PATH, OUTPUT_INDIVIDUAL_AUDIO_DIR
                    )
                    futures[i] = future

                # Add generated audio paths to the playback queue in order
                for i in range(len(sentences)):
                    if i in futures:
                        try:
                            audio_path = futures[i].result()
                            if audio_path:
                                audio_playback_queue.put(audio_path)
                            else:
                                print(f"Skipping playback for sentence {i} due to generation error.")
                        except Exception as exc:
                            print(f'Sentence {i} generation raised an exception: {exc}')
                            print(f"Skipping playback for sentence {i} due to exception.")
                    else:
                        print(f"Warning: Future for sentence {i} not found. This should not happen.")
            
            print("\nAll audio generation tasks for the current input completed and results added to playback queue.")

            # 4. Clear the input file after processing
            with open(input_file_name, 'w') as f:
                f.write('')
            print(f"Cleared '{input_file_name}' for next input.")
        else:
            print(f"'{input_file_name}' is empty. Waiting for content...")
        
        # Add a small delay before checking for new input again
        time.sleep(2) # Adjust as needed

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nProgram interrupted by user. Shutting down...")
        playback_finished_event.set() # Signal playback thread to stop
        # The daemon thread will exit with the main program.
        # If it were not a daemon thread, you'd need playing_thread.join() here.
