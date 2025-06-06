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

def main():
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    CHUNK_DURATION_MS = 30
    PADDING_DURATION_MS = 5000
    CHUNK_SIZE = int(RATE * CHUNK_DURATION_MS / 1000)
    CHUNK_BYTES = CHUNK_SIZE * 2
    NUM_PADDING_CHUNKS = int(PADDING_DURATION_MS / CHUNK_DURATION_MS)
    NUM_WINDOW_CHUNKS = int(240 / CHUNK_DURATION_MS)
    NUM_WINDOW_CHUNKS_END = NUM_WINDOW_CHUNKS * 2

    vad = webrtcvad.Vad(1)

    pygame.mixer.pre_init(RATE, -16, CHANNELS, 2048)
    pygame.mixer.init()
    pygame.init()

    pa = pyaudio.PyAudio()
    stream = pa.open(format=FORMAT,
                     channels=CHANNELS,
                     rate=RATE,
                     input=True,
                     start=False,
                     frames_per_buffer=CHUNK_SIZE)

    def normalize(snd_data):
        MAXIMUM = 32767
        times = float(MAXIMUM) / max(abs(i) for i in snd_data)
        r = array('h', (int(i * times) for i in snd_data))
        return r

    try:
        ring_buffer = collections.deque(maxlen=NUM_PADDING_CHUNKS)
        triggered = False
        ring_buffer_flags = [0] * NUM_WINDOW_CHUNKS
        ring_buffer_index = 0
        ring_buffer_flags_end = [0] * NUM_WINDOW_CHUNKS_END
        ring_buffer_index_end = 0
        raw_data = array('h')
        index = 0
        start_point = 0
        StartTime = time.time()
        got_a_sentence = False

        print("* recording: ")
        stream.start_stream()

        while not got_a_sentence:
            chunk = stream.read(CHUNK_SIZE)
            raw_data.extend(array('h', chunk))
            index += CHUNK_SIZE
            TimeUse = time.time() - StartTime

            active = vad.is_speech(chunk, RATE)

            sys.stdout.write('1' if active else '_')
            sys.stdout.flush()

            ring_buffer_flags[ring_buffer_index] = 1 if active else 0
            ring_buffer_index = (ring_buffer_index + 1) % NUM_WINDOW_CHUNKS

            ring_buffer_flags_end[ring_buffer_index_end] = 1 if active else 0
            ring_buffer_index_end = (ring_buffer_index_end + 1) % NUM_WINDOW_CHUNKS_END

            if not triggered:
                ring_buffer.append(chunk)
                if sum(ring_buffer_flags) > 0.8 * NUM_WINDOW_CHUNKS:
                    sys.stdout.write(' Open ')
                    triggered = True
                    start_point = index - CHUNK_SIZE * 20
                    ring_buffer.clear()
            else:
                ring_buffer.append(chunk)
                if sum(ring_buffer_flags_end) < 0.1 * NUM_WINDOW_CHUNKS_END or TimeUse > 10:
                    sys.stdout.write(' Close ')
                    triggered = False
                    got_a_sentence = True

        sys.stdout.write('\n')
        stream.stop_stream()
        print("* done recording")

        # Trim beginning silence
        raw_data.reverse()
        for _ in range(start_point):
            raw_data.pop()
        raw_data.reverse()

        raw_data = normalize(raw_data)

        # Save to WAV
        wf = wave.open("r.wav", 'w')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframesraw(raw_data)
        wf.close()

        # Transcribe and send to Rasa
        try:
            recognizer = sr.Recognizer()
            with sr.AudioFile("r.wav") as source:
                audio = recognizer.record(source)
                text = recognizer.recognize_google(audio, language="en-IN")
                print("Recognized:", text)
                text = text.lower()

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
        except Exception as e:
            print("Error during recognition or Rasa communication:", e)

        while pygame.mixer.get_busy():
            pass

    except KeyboardInterrupt:
        print("Interrupted by user.")

    stream.close()
    pa.terminate()


if __name__ == "__main__":
    main()

