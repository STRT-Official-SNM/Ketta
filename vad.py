import webrtcvad
import collections
import sys
import pyaudio
import wave
import time
import speech_recognition as sr
import numpy as np
import socket

# Import the command sender to control the UI
from control import send_ui_command

# --- Configuration ---
# UDP socket for sending LOUDNESS data to the UI
LOUDNESS_HOST = "127.0.0.1"
LOUDNESS_UDP_PORT = 45455
SENSITIVITY = 500.0

# UDP socket for sending TRANSCRIBED TEXT to the main_loop script
TEXT_HOST = "127.0.0.1"
TEXT_UDP_PORT = 45457 # A new, dedicated port for text

def main():
    """Listens for speech, transcribes, and sends text to the logic loop."""
    # Audio format settings
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    CHUNK_DURATION_MS = 30
    PADDING_DURATION_MS = 1000 # 1 second of pre-speech audio buffer
    CHUNK_SIZE = int(RATE * CHUNK_DURATION_MS / 1000)
    NUM_PADDING_CHUNKS = int(PADDING_DURATION_MS / CHUNK_DURATION_MS)
    
    vad = webrtcvad.Vad(3) # VAD aggressiveness (0-3)
    pa_instance = pyaudio.PyAudio()
    
    # Sockets for communication
    loudness_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    text_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # This outer loop allows the script to listen for a new conversation after one ends.
    while True: 
        stream = pa_instance.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                                  input=True, frames_per_buffer=CHUNK_SIZE)
        
        ring_buffer = collections.deque(maxlen=NUM_PADDING_CHUNKS)
        triggered = False
        voiced_frames = []
        
        send_ui_command("listening")
        print("\nListening for speech...")
        
        # --- Listen for the first word ---
        while not triggered:
            chunk = stream.read(CHUNK_SIZE)
            
            # Calculate and send loudness to the UI
            try:
                np_data = np.frombuffer(chunk, dtype=np.int16)
                rms = np.sqrt(np.mean(np_data.astype(np.float32)**2))
                loudness = min(1.0, (rms / SENSITIVITY))
                loudness_sock.sendto(str(loudness).encode('utf-8'), (LOUDNESS_HOST, LOUDNESS_UDP_PORT))
            except Exception as e:
                print(f"Loudness calc/send error: {e}")

            is_speech = vad.is_speech(chunk, RATE)
            if is_speech:
                sys.stdout.write('+')
                triggered = True
                voiced_frames.extend(list(ring_buffer))
                voiced_frames.append(chunk)
            else:
                sys.stdout.write('-')
                ring_buffer.append(chunk)
            sys.stdout.flush()

        # --- Voice detected, start recording until silence ---
        print("\nSpeech detected, recording...")
        silence_start_time = None
        while triggered:
            chunk = stream.read(CHUNK_SIZE)
            voiced_frames.append(chunk)

            # Keep sending loudness
            np_data = np.frombuffer(chunk, dtype=np.int16)
            rms = np.sqrt(np.mean(np_data.astype(np.float32)**2))
            loudness = min(1.0, (rms / SENSITIVITY))
            loudness_sock.sendto(str(loudness).encode('utf-8'), (LOUDNESS_HOST, LOUDNESS_UDP_PORT))

            is_speech = vad.is_speech(chunk, RATE)
            if not is_speech:
                if silence_start_time is None:
                    silence_start_time = time.time()
                elif time.time() - silence_start_time > 1.2: # 1.2s of silence ends recording
                    triggered = False
            else:
                silence_start_time = None
        
        print("Recording finished.")
        stream.stop_stream()
        stream.close()

        # --- Process, Transcribe, and Send ---
        send_ui_command("thinking")
        loudness_sock.sendto(b'0.0', (LOUDNESS_HOST, LOUDNESS_UDP_PORT)) # Reset loudness meter
        
        wav_data = b''.join(voiced_frames)
        
        try:
            recognizer = sr.Recognizer()
            audio_data = sr.AudioData(wav_data, RATE, pa_instance.get_sample_size(FORMAT))
            
            # Use Google's free web API for speech recognition
            text = recognizer.recognize_google(audio_data, language="en-US")
            print("Recognized Text:", text)
            
            # SEND THE RECOGNIZED TEXT TO THE MAIN_LOOP SCRIPT
            text_sock.sendto(text.encode('utf-8'), (TEXT_HOST, TEXT_UDP_PORT))
            
        except sr.UnknownValueError:
            print("Speech was not understood.")
            # Send a specific error message so the main loop can handle it
            text_sock.sendto(b'__speech_not_understood__', (TEXT_HOST, TEXT_UDP_PORT))
        except sr.RequestError as e:
            print(f"Google Speech Recognition request failed: {e}")
            text_sock.sendto(b'__recognition_error__', (TEXT_HOST, TEXT_UDP_PORT))
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
        break

if __name__ == "__main__":
    try:
        main_speech_loop()
    except KeyboardInterrupt:
        print("\nSpeech listener interrupted by user.")
        send_ui_command("reset")
