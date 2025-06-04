# Ketta - Modular Voice Assistant

<p align="center">
  <img src="https://raw.githubusercontent.com/STRT-Official-SNM/Ketta/refs/heads/main/logo.png" alt="Ketta">
</p>

Ketta is a modular voice assistant designed to run on Linux. It utilizes a combination of local and cloud-based services for wakeword detection, voice activity detection (VAD), speech-to-text (STT), natural language understanding (NLU via Rasa), and text-to-speech (TTS). It also includes skills for launching applications and performing web searches.

## Features

*   **Wakeword Detection:** Listens for "Ketta" using a Teachable Machine model.
*   **Voice Activity Detection:** Detects speech segments after the wakeword.
*   **Speech-to-Text:** Converts spoken commands to text (uses Google Speech Recognition via `speech_recognition` library).
*   **Natural Language Understanding:** Sends transcribed text to a Rasa server for intent recognition and entity extraction.
*   **Text-to-Speech:** Synthesizes Rasa's responses into audible speech using Piper TTS.
    *   Includes both a simpler file-based TTS (`tts.py`) and a more advanced threaded, streaming TTS (`threaded_tts.py`).
*   **Application Launcher:** Can open installed desktop applications by name.
*   **Search & Information:**
    *   Performs web searches using DuckDuckGo.
    *   Fetches information from Wikipedia.
    *   Solves basic math expressions.
    *   Provides current time and date.

## Core Components & Files

*   `tm_model.py`: Handles wakeword detection using a TensorFlow Lite model trained with Teachable Machine. Triggers `vad.py` upon detecting the wakeword.
*   `labels.txt`: Contains the class labels for the Teachable Machine model used by `tm_model.py`.
*   `vad.py`:
    *   Performs Voice Activity Detection (VAD) using `webrtcvad`.
    *   Records audio after VAD triggers.
    *   Performs Speech-to-Text (STT) on the recorded audio using Google Cloud STT (via `speech_recognition`).
    *   Sends the transcribed text to a running Rasa instance.
    *   Writes Rasa's text response to `output.txt`.
*   `tts.py`:
    *   A file-based Text-to-Speech module.
    *   Monitors `output.txt` for new text from Rasa.
    *   Uses Piper TTS to generate audio for each sentence.
    *   Plays back generated audio sentences sequentially using `playsound`.
*   `threaded_tts.py`:
    *   An advanced, threaded, and streaming Text-to-Speech module (recommended over `tts.py`).
    *   Processes text into sentences, generates audio using Piper TTS in worker threads, and plays audio sequentially using `sounddevice`.
    *   More responsive and handles longer texts better.
*   `open_app.py`: Contains logic to find and launch installed Linux desktop applications.
*   `search.py`: Provides functionalities to answer queries using DuckDuckGo, Wikipedia, perform math calculations, and get time/date information.
*   `output.txt`: A temporary file used as a message queue between `vad.py` (writing Rasa's response) and the TTS scripts (reading the response to speak).

**Note:** Rasa itself (NLU server, domain, stories, actions) is not included in these files but is a required external component for this assistant to function fully. The `search.py` and `open_app.py` scripts would typically be called by custom actions within your Rasa setup.

## How It Works (Conceptual Flow)

1.  **Wakeword:** `tm_model.py` continuously listens to the microphone.
2.  If "Ketta" (or your trained wakeword) is detected with sufficient confidence:
    *   `tm_model.py` calls `vad.main()`.
3.  **VAD & STT:** `vad.py`:
    *   Starts recording using VAD to capture the user's command.
    *   Once speech ends, the audio is saved and sent to Google STT.
    *   The transcribed text is obtained.
4.  **NLU (Rasa):** `vad.py`:
    *   Sends the transcribed text to your running Rasa server's webhook.
    *   Rasa processes the text, identifies intent, and extracts entities.
    *   Rasa determines a response (this might involve Rasa custom actions that could potentially use `search.py` or `open_app.py`).
    *   Rasa sends its text response back to `vad.py`.
5.  **Response Handling:** `vad.py`:
    *   Writes Rasa's text response into `output.txt`.
6.  **TTS:** `tts.py` or `threaded_tts.py` (running in parallel):
    *   Continuously monitors `output.txt`.
    *   When new text appears, it splits the text into sentences.
    *   Generates `.wav` audio for each sentence using Piper TTS.
    *   Plays the audio sentences sequentially.
    *   Clears `output.txt` after processing.

## Prerequisites

*   **Python 3.7+**
*   **Linux Operating System** (due to `open_app.py`'s desktop file handling and some audio dependencies)
*   **pip** (Python package installer)
*   **External Tools:**
    *   **Piper TTS:** The Piper TTS binary must be installed and accessible in your PATH or specified in the TTS scripts. Download voice models for Piper.
    *   **Rasa:** A running Rasa server (version 2.x or 3.x) configured with your assistant's logic.
*   **Hardware:**
    *   Microphone

## Setup

1.  **Clone the Repository:**
    ```bash
    git clone <your-repository-url>
    cd <repository-name>
    ```

2.  **Create a Python Virtual Environment (Recommended):**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install Python Dependencies:**
    Create a `requirements.txt` file with the following content:
    ```txt
    # For tm_model.py
    numpy
    sounddevice
    # tensorflow or tflite_runtime (choose one based on your needs)
    # tensorflow  # For full TensorFlow
    tflite-runtime # For TensorFlow Lite runtime only (smaller)
    # vad.py (this is a custom module, ensure it's in the same directory or Python path)

    # For vad.py
    webrtcvad-wheels # or build from source if needed
    pyaudio
    SpeechRecognition
    requests
    pygame

    # For tts.py
    pydub
    playsound

    # For threaded_tts.py (sounddevice and numpy already listed)
    # wave (standard library)

    # For open_app.py
    # configparser (standard library)
    # difflib (standard library)

    # For search.py
    # requests (already listed)
    wikipedia-api
    ```
    Then install them:
    ```bash
    pip install -r requirements.txt
    ```
    *Note on `webrtcvad-wheels`: If it doesn't install directly, you might need to install system dependencies like `python3-dev` and build tools, or find a pre-built wheel for your system.*
    *Note on `pyaudio`: You might need to install `portaudio` development libraries: `sudo apt-get install portaudio19-dev python3-pyaudio` on Debian/Ubuntu.*

4.  **Set up Piper TTS:**
    *   Download the Piper TTS executable for your system from the [Piper releases page](https://github.com/rhasspy/piper/releases).
    *   Place it in a directory included in your system's PATH, or update `PIPER_EXECUTABLE_PATH` in `tts.py` and the `piper` command in `threaded_tts.py`.
    *   Download a Piper voice model (e.g., `en_US-hfc_female-medium.onnx` and its `.json` config file).
    *   Update `MODEL_PATH` and `CONFIG_PATH` in `tts.py`.
    *   Update `--model` and `--voice-dir` paths in `threaded_tts.py` (or place models in its default search path `~/.local/share/piper/voices/`).

5.  **Set up Teachable Machine Model:**
    *   Place your trained `model.tflite` file (for wakeword detection) in the project directory or update `MODEL_PATH` in `tm_model.py`.
    *   Ensure `labels.txt` is present and correctly lists your classes (e.g., "0 Background Noise", "1 ketta").

6.  **Set up Rasa:**
    *   Install Rasa and set up your Rasa project. This is a separate, more involved process. Refer to the [Rasa Documentation](https://rasa.com/docs/rasa/).
    *   Ensure your Rasa server is running and accessible at `http://127.0.0.1:5005/webhooks/rest/webhook` (or update the URL in `vad.py`).
    *   Your Rasa custom actions can utilize `open_app.py` and `search.py` by importing and calling their functions.

7.  **Configure Paths in Scripts (If not using defaults):**
    *   `tm_model.py`: `MODEL_PATH`, `LABELS_PATH`.
    *   `tts.py`: `PIPER_EXECUTABLE_PATH`, `MODEL_PATH`, `CONFIG_PATH`.
    *   `threaded_tts.py`: The `--model` and `--voice-dir` arguments or ensure models are in default locations.
    *   `vad.py`: `rasa_url`.

## Usage

1.  **Start your Rasa Server:**
    Open a terminal, navigate to your Rasa project directory, and start the Rasa server (e.g., `rasa run -m models --enable-api --cors "*"`).

2.  **Start the TTS Script:**
    Choose either `threaded_tts.py` (recommended) or `tts.py`.
    *   For `threaded_tts.py`:
        ```bash
        # Ensure voice model and config are in ~/.local/share/piper/voices/en_US-hfc_female-medium/
        # or specify paths:
        # python threaded_tts.py --model en_US-hfc_female-medium --voice-dir /path/to/your/piper/voices
        # It will wait for text from stdin by default or process a file/text if arguments are given.
        # For this project, it effectively waits because output.txt is handled by the main loop of tts.py
        # For Ketta, the tts.py script's main loop which monitors output.txt is more suitable.
        # Let's assume we adapt tts.py's monitoring logic or use tts.py directly.

        # If using tts.py:
        python tts.py
        ```
        *Self-correction: `threaded_tts.py` as provided is designed to take text via stdin/file arg. `tts.py` has the file monitoring loop for `output.txt`. For direct integration with the current setup, `tts.py` is easier to run as is. To use `threaded_tts.py`, you'd need to adapt its `main()` function to monitor `output.txt` like `tts.py` does, or modify `vad.py` to pipe output directly to `threaded_tts.py`'s stdin.*

    **Recommendation:** Stick with `tts.py` for now due to its `output.txt` monitoring loop, or modify `threaded_tts.py` to include a similar file monitoring loop.

3.  **Start the Wakeword Listener:**
    Open another terminal (with the virtual environment activated) and run:
    ```bash
    python tm_model.py
    ```
    You should see "Listening for wakeword...".

4.  **Speak to Ketta:**
    *   Say your wakeword (e.g., "Ketta").
    *   `tm_model.py` should print "WAKEWORD DETECTED!".
    *   `vad.py` will start recording (you might see `1`s and `_`s indicating speech/silence).
    *   Speak your command (e.g., "What time is it?", "Open Firefox").
    *   `vad.py` will transcribe it, send it to Rasa, and get a response.
    *   The response will be written to `output.txt`.
    *   `tts.py` (or the modified `threaded_tts.py`) will pick up the text from `output.txt` and speak it.

## Potential Improvements & Future Work

*   **Direct Rasa Action Integration:** Instead of writing Rasa's response to `output.txt` for generic TTS, have Rasa custom actions directly call functions in `search.py` or `open_app.py` and then formulate a more specific text response for TTS. The TTS part via `output.txt` would still be used for the final spoken response.
*   **Replace `output.txt`:** Use a more robust inter-process communication (IPC) mechanism like ZeroMQ, gRPC, or Python's `multiprocessing.Queue` if `vad.py` and the TTS script are part of a larger orchestrated application.
*   **Configuration File:** Centralize all configurable paths and settings into a single `config.ini` or `config.yaml` file.
*   **Error Handling:** Implement more robust error handling and logging across all modules.
*   **Alternative STT/TTS:** Explore options for fully local STT (e.g., Vosk, Coqui STT) and TTS if cloud dependency is a concern.
*   **GUI:** Develop a graphical user interface.
*   **Skill Expansion:** Add more skills and capabilities.
*   **Packaging:** Package the assistant for easier distribution.
*   **Asynchronous Operations:** Make more operations asynchronous (e.g., network requests in `vad.py` and `search.py`) to prevent blocking.
*   **Streamlined TTS Integration:** Modify `threaded_tts.py` to have a main loop that monitors `output.txt` like `tts.py`, to leverage its more advanced TTS capabilities within the current architecture.

## Troubleshooting

*   **"Piper executable not found"**: Ensure Piper is installed and its path is correctly set in the TTS script or your system PATH.
*   **"Model file not found"**: Double-check paths to `.tflite`, `.onnx` and `.json` model files.
*   **No sound / PyAudio errors**: Check microphone setup and install `portaudio` development libraries (`sudo apt-get install portaudio19-dev`). Ensure the correct audio input/output devices are being used.
*   **Rasa Connection Failed**: Make sure your Rasa server is running and accessible at the specified URL. Check for firewall issues.
*   **Low Wakeword Accuracy**: You may need to retrain your Teachable Machine model with more varied samples or adjust `CONFIDENCE_THRESHOLD` in `tm_model.py`.

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues.

## License

(Specify your chosen license here, e.g., MIT, Apache 2.0. If unsure, MIT is a common choice for open-source projects.)
Example:
This project is licensed under the GNU GPLv3 License - see the [LICENSE.md](LICENSE.md) file for details.
