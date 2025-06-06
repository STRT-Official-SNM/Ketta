import numpy as np
import sounddevice as sd
# import soundfile as sf # Not used in this version for live input
import tensorflow as tf # Or tflite_runtime.interpreter as tf
import time
import vad # Assuming vad.py contains a main() function
import threading
import queue
import control

# --- Configuration ---
MODEL_PATH = 'model.tflite'  # Replace with the path to your TFLite model
LABELS_PATH = 'labels.txt'     # Replace with the path to your labels.txt file
SAMPLE_RATE = 44032         # Teachable Machine audio models typically use 16kHz (or your trained model's rate)
DURATION = 1                # Duration of each audio chunk in seconds
CHUNK_SIZE = int(SAMPLE_RATE * DURATION) # Number of samples per chunk
CONFIDENCE_THRESHOLD = 0.7 # Adjust as needed for your wake word detection

# --- Global Variables for Threading ---
audio_queue = queue.Queue()
stop_event = threading.Event() # To signal the recording thread to stop

# --- Load Model ---
try:
    interpreter = tf.lite.Interpreter(model_path=MODEL_PATH)
    interpreter.allocate_tensors()
except Exception as e:
    print(f"Error loading TFLite model: {e}")
    print("Make sure your model path is correct.")
    exit()

# Get input and output tensor details
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

input_shape = input_details[0]['shape']
input_dtype = input_details[0]['dtype']

print(f"Model Input Shape: {input_shape}")
print(f"Model Input Dtype: {input_dtype}")

# --- Load Labels ---
try:
    with open(LABELS_PATH, 'r') as f:
        labels = [line.strip() for line in f.readlines()]
    print(f"Loaded Labels: {labels}")
except FileNotFoundError:
    print(f"Error: labels.txt not found at {LABELS_PATH}. Please provide the correct path.")
    exit()
except Exception as e:
    print(f"Error loading labels: {e}")
    exit()

# Ensure the input shape matches expectations
# Note: Teachable Machine audio models often expect a specific number of samples,
# which might not directly be CHUNK_SIZE if they do internal spectrogram conversion.
# For raw audio input like this script, CHUNK_SIZE should match model's expected raw audio length.
if len(input_shape) > 1 and input_shape[1] != CHUNK_SIZE:
    print(f"Warning: Model expects input length {input_shape[1]}, but CHUNK_SIZE is {CHUNK_SIZE}.")
    print("This might indicate an issue with your model or expected input preprocessing.")
    print("Ensure your Teachable Machine model was trained with 1-second raw audio samples if CHUNK_SIZE reflects that.")
    # Consider adjusting CHUNK_SIZE or your model's input layer.

# --- Audio Recording Thread Function ---
def audio_recorder():
    """Captures audio and puts it into the queue."""
    print("Audio recording thread started.")
    try:
        def callback(indata, frames, time_info, status):
            if status:
                print(status, flush=True)
            if not stop_event.is_set():
                audio_queue.put(indata.copy()) # Put a copy into the queue

        with sd.InputStream(samplerate=SAMPLE_RATE,
                             channels=1,
                             callback=callback,
                             blocksize=CHUNK_SIZE, # Process audio in chunks of CHUNK_SIZE
                             dtype='float32'):     # TFLite model expects float32
            while not stop_event.is_set():
                sd.sleep(100) # Keep the stream alive and responsive to stop_event
    except Exception as e:
        print(f"Error in audio recording thread: {e}")
    finally:
        print("Audio recording thread stopped.")

# --- Inference Function ---
def process_audio_chunk(audio_data_raw):
    """Processes a single audio chunk for inference."""
    audio_data = audio_data_raw[:, 0] # Assuming mono, take the first channel

    # Normalize (optional, but often good practice if model was trained with normalized audio)
    # This normalization is a simple peak normalization per chunk.
    # If your model expects a different kind of normalization (e.g., global mean/std), adjust this.
    max_val = np.max(np.abs(audio_data))
    if max_val > 0:
        audio_data = audio_data / max_val
    else:
        audio_data = np.zeros_like(audio_data) # Handle silence

    # Ensure the audio data is the correct length (CHUNK_SIZE)
    # This step might be redundant if blocksize in InputStream is CHUNK_SIZE
    # and no partial blocks are generated.
    if len(audio_data) < CHUNK_SIZE:
        processed_audio_data = np.pad(audio_data, (0, CHUNK_SIZE - len(audio_data)), 'constant')
    elif len(audio_data) > CHUNK_SIZE:
        processed_audio_data = audio_data[:CHUNK_SIZE]
    else:
        processed_audio_data = audio_data

    # Reshape for the model (e.g., [1, CHUNK_SIZE])
    input_tensor = np.expand_dims(processed_audio_data, axis=0).astype(input_dtype)

    # Check if input_tensor shape matches model's expected input_shape
    if input_tensor.shape != tuple(input_shape):
        print(f"Mismatched shapes! Input tensor: {input_tensor.shape}, Model expects: {input_shape}")
        # Attempt to reshape if it's a simple mismatch like [1, N] vs [1, N, 1]
        if len(input_shape) == 3 and input_shape[2] == 1 and len(input_tensor.shape) == 2:
            input_tensor = np.expand_dims(input_tensor, axis=2)
            print(f"Reshaped input tensor to: {input_tensor.shape}")
        elif len(input_shape) == 2 and len(input_tensor.shape) == 3 and input_tensor.shape[2] == 1:
            input_tensor = np.squeeze(input_tensor, axis=2)
            print(f"Reshaped input tensor to: {input_tensor.shape}")
        else:
            print("Cannot automatically reshape. Please check model input requirements.")
            return # Skip inference if shape is wrong

    try:
        interpreter.set_tensor(input_details[0]['index'], input_tensor)
        interpreter.invoke()
        output_tensor = interpreter.get_tensor(output_details[0]['index'])
        probabilities = np.array(output_tensor[0])

        predicted_index = np.argmax(probabilities)
        predicted_class = labels[predicted_index]
        confidence = probabilities[predicted_index]

        if confidence >= CONFIDENCE_THRESHOLD:
            # print(f"Detected: {predicted_class} (Confidence: {confidence:.2f})")
            if predicted_class == '1 ketta': # Make sure '1 ketta' is exactly what's in your labels.txt
                print(f"WAKEWORD DETECTED! ({predicted_class} - Confidence: {confidence:.2f})")
                vad.main() # Call your VAD function
                #control.send_command('speaking')
                # Be cautious: if vad.main() is blocking or long-running,
                # it might still make the main loop less responsive.
                # Consider if vad.main() also needs to be non-blocking or run in a thread.
    except Exception as e:
        print(f"Error during inference: {e}")


# --- Main Loop ---
if __name__ == "__main__":
    print("Starting wakeword recognition. Say 'ketta'...")
    print(f"Audio chunks will be {DURATION} second(s) long ({CHUNK_SIZE} samples at {SAMPLE_RATE} Hz).")
    print(f"Model expects input of type {input_dtype} and shape {input_shape}.")


    # Start the audio recording thread
    recording_thread = threading.Thread(target=audio_recorder, daemon=True) # daemon=True allows main to exit
    recording_thread.start()

    print("\nListening for wakeword... Press Ctrl+C to stop.")
    try:
        while True:
            try:
                # Get audio data from the queue, with a timeout to allow Ctrl+C
                audio_chunk = audio_queue.get(timeout=0.1) # Timeout in seconds
                process_audio_chunk(audio_chunk)
                audio_queue.task_done() # Signal that the item has been processed
            except queue.Empty:
                # No audio data in the queue, continue looping
                time.sleep(0.01) # Small sleep to prevent busy-waiting
                continue
            except Exception as e:
                print(f"Error in main loop: {e}")
                break # Or handle more gracefully

    except KeyboardInterrupt:
        print("\nStopping recognition...")
    finally:
        print("Signalling recording thread to stop...")
        stop_event.set()
        if recording_thread.is_alive():
            recording_thread.join(timeout=2) # Wait for the thread to finish
        print("All threads stopped.")
        # Clean up Sounddevice stream explicitly if needed, though context manager should handle it.
        # sd.stop() # May not be necessary if InputStream context manager cleans up properly.
