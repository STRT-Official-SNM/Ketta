import webrtcvad
import collections
import sys
import pyaudio
from array import array
import wave
import time
import speech_recognition as sr
import requests
import json
import uuid
import pygame
import numpy as np
import socket
from gpytranslate import SyncTranslator

# Import the command sender to control the UI
from control import send_ui_command

# Configuration for sending loudness data
LOUDNESS_HOST = "127.0.0.1"
LOUDNESS_UDP_PORT = 45455 # Must match the port in app.py
SENSITIVITY = 500.0       # Microphone sensitivity for loudness calculation

def main():
    # Audio format settings
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    CHUNK_DURATION_MS = 30
    PADDING_DURATION_MS = 1500 # Reduced padding
    CHUNK_SIZE = int(RATE * CHUNK_DURATION_MS / 1000)
    NUM_PADDING_CHUNKS = int(PADDING_DURATION_MS / CHUNK_DURATION_MS)
    
    # VAD aggressiveness (0-3)
    vad = webrtcvad.Vad(3)

    # PyAudio setup
    pa = pyaudio.PyAudio()
    stream = pa.open(format=FORMAT,
                     channels=CHANNELS,
                     rate=RATE,
                     input=True,
                     frames_per_buffer=CHUNK_SIZE)

    # UDP socket for sending loudness
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Ring buffer for VAD
    ring_buffer = collections.deque(maxlen=NUM_PADDING_CHUNKS)
    triggered = False
    voiced_frames = []
    
    # --- Tell the UI to start its listening animation ---
    print("Sending 'listening' command to UI...")
    send_ui_command("listening")
    
    print("Listening for speech...")
    while not triggered:
        chunk = stream.read(CHUNK_SIZE)
        
        # --- Calculate and send loudness regardless of speech ---
        try:
            np_data = np.frombuffer(chunk, dtype=np.int16)
            rms = np.sqrt(np.mean(np_data.astype(np.float32)**2))
            loudness = min(1.0, (rms / SENSITIVITY))
            sock.sendto(str(loudness/1000000).encode('utf-8'), (LOUDNESS_HOST, LOUDNESS_UDP_PORT))
        except Exception as e:
            print(f"Loudness calc/send error: {e}")

        is_speech = vad.is_speech(chunk, RATE)

        sys.stdout.write('+' if is_speech else '-')
        sys.stdout.flush()

        if is_speech:
            triggered = True
            print("\nSpeech detected, recording...")
            voiced_frames.extend(list(ring_buffer)) # Add pre-speech buffer
            ring_buffer.clear()
            voiced_frames.append(chunk)
            break
        else:
            ring_buffer.append(chunk)

    # Once triggered, record until silence
    silence_start_time = None
    while triggered:
        chunk = stream.read(CHUNK_SIZE)
        voiced_frames.append(chunk)

        # --- Keep sending loudness during recording ---
        np_data = np.frombuffer(chunk, dtype=np.int16)
        rms = np.sqrt(np.mean(np_data.astype(np.float32)**2))
        loudness = min(1.0, (rms / SENSITIVITY))
        sock.sendto(str(loudness).encode('utf-8'), (LOUDNESS_HOST, LOUDNESS_UDP_PORT))

        is_speech = vad.is_speech(chunk, RATE)
        if not is_speech:
            if silence_start_time is None:
                silence_start_time = time.time()
            elif time.time() - silence_start_time > 1.0: # 1 second of silence
                triggered = False
        else:
            silence_start_time = None # Reset silence timer
            
    print("\nRecording finished.")
    stream.stop_stream()
    stream.close()
    pa.terminate()

    # --- Tell the UI to switch to the 'thinking' animation ---
    print("Sending 'thinking' command to UI...")
    send_ui_command("thinking")
    
    # Send one last "zero" loudness value
    sock.sendto(b'0.0', (LOUDNESS_HOST, LOUDNESS_UDP_PORT))
    sock.close()

    # Process the recorded audio
    wav_data = b''.join(voiced_frames)

    # Save to WAV (optional, but good for debugging)
    with wave.open("last_recording.wav", 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(pa.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(wav_data)

    # Transcribe and send to Rasa
    try:
        recognizer = sr.Recognizer()
        audio_data = sr.AudioData(wav_data, RATE, pa.get_sample_size(FORMAT))
        
        text = recognizer.recognize_google(audio_data, language="en-US")
        print("Recognized:", text)
        #t = SyncTranslator()
        #trans = t.translate(text, targetlang="en")
        #text=trans.text
        text = text.lower()
        print('Translation: ',text)

        sender_id = str(uuid.uuid4())  # unique session id
        rasa_url = "http://127.0.0.1:5005/webhooks/rest/webhook"
        payload = {
            "sender": sender_id,
            "message": text
        }

        response = requests.post(rasa_url, json=payload)

        if response.status_code == 200:
            messages = response.json()
            for msg in messages:
                if "text" in msg:
                    print("Rasa:", msg["text"])
                    with open('output.txt', 'w') as f:
                        f.write(msg['text'])
                if "image" in msg:
                    print("Rasa Image:", msg["image"])
        else:
            print("Rasa connection failed:", response.status_code, response.text)
        
    except sr.UnknownValueError:
        print("Speech was not understood.")
        with open('output.txt', 'w') as f:
            f.write("Sorry! I couldn't understand what you just said")
    except Exception as e:
        print(f"Error during recognition or Rasa communication: {e}")
    #finally:
        #print("Sending 'reset' command to UI.")

if __name__ == "__main__":
    # This can be called from another script
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        send_ui_command("reset") # Ensure UI resets on exit
