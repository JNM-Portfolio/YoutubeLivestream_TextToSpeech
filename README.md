# YoutubeLivestream_TextToSpeech
 
Reads YouTube live chat messages based on an activation phrase and uses Text-to-Speech (TTS) with an animated character overlay for streaming.

![Screenshot Placeholder](screenshot.png)  <!-- TODO: Add a screenshot or GIF! -->

## Features

*   Connects to YouTube Live Chat using Pytchat (via Video ID).
*   Filters messages based on a configurable activation phrase.
*   Reads filtered messages aloud using:
    *   ElevenLabs (High Quality, requires API Key & ffmpeg)
    *   (Optional) pyttsx3 (Offline, system-dependent)
*   Displays messages temporarily on screen.
*   Shows a character (from the game Limbus Company) that "talks" during TTS playback.
*   Configurable via environment variables (`.env`) and Python script constants.
*   Simple web overlay easily added to OBS (or similar) as a Browser Source.

## Prerequisites

*   **Python:** Version 3.9 or higher recommended.
*   **pip:** Python package installer (usually comes with Python).
*   **Git:** For cloning the repository.
*   **ffmpeg:** **Required** for audio playback with the `elevenlabs` library's `play()` function.
    *   **Windows:** Download from [ffmpeg.org](https://ffmpeg.org/download.html) (e.g., builds from gyan.dev), unzip, and add the `bin` folder to your system's PATH environment variable.
    *   **macOS:** `brew install ffmpeg`
    *   **Linux (Debian/Ubuntu):** `sudo apt update && sudo apt install ffmpeg`
*   **(Optional - for pyttsx3):** Depending on your OS, you might need additional system libraries like `espeak` (Linux) or specific frameworks (macOS).

## Setup

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/YOUR_USERNAME/YOUR_REPOSITORY_NAME.git
    cd YOUR_REPOSITORY_NAME
    ```

2.  **Create Virtual Environment (Recommended):**
    ```bash
    python -m venv venv
    # Activate (Linux/macOS):
    source venv/bin/activate
    # Activate (Windows CMD):
    .\venv\Scripts\activate
    # Activate (Windows PowerShell):
    .\venv\Scripts\Activate.ps1
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **API Keys & Configuration (`.env`):**
    *   You need an **ElevenLabs API Key**. Get one from [elevenlabs.io](https://elevenlabs.io/).
    *   Copy the example environment file:
        ```bash
        # If you don't have an example.env, just create .env
        # cp example.env .env
        ```
    *   Create or edit the `.env` file in the project root and add your keys/IDs:
        ```dotenv
        ELEVENLABS_API_KEY="sk_YOUR_ELEVENLABS_API_KEY_HERE" # I would advice you to create it an environment variable
        ELEVENLABS_VOICE_ID="21m00Tcm4TlvDq8ikWAM" # Optional: Set default voice ID (e.g., Rachel)
        YOUTUBE_VIDEO_ID="YOUR_YOUTUBE_VIDEO_ID_HERE" # Important! Set this before running
        ```
    *   Replace the placeholder values with your actual credentials and the Video ID of the stream you want to monitor.

5.  **Character Images:**
    *   Ensure the character images (`FaustTop.png`, `FaustBottom.png`, or your custom ones) are present in a `static` subfolder within the project directory.
    *   Adjust the dimensions and percentages in `templates/index.html` CSS if using different images.

## Configuration (Optional)

You can further configure the application by editing `chat_overlay.py`:

*   `TTS_PROVIDER`: Change between `"elevenlabs"` and `"pyttsx3"`.
*   `TTS_CONFIG`: Modify settings like voice ID (if not using `.env`), model, rate, etc.
*   `ACTIVATION_PHRASE`: Change the phrase required to trigger TTS (e.g., `"!say "`). Remember the space at the end if needed.

And `templates/index.html`:

*   `FLAP_START_DELAY_MS`: Adjust the delay (in milliseconds) before the flapping animation starts to better sync with TTS audio beginning.
*   `FLAP_SPEED`: Controls how fast the character flaps (milliseconds per toggle). Lower is faster.
*   CSS Variables: Adjust character size (`#faust-container` width/height), positioning, message bubble appearance, etc.

## Running the Application

1.  **Start Your YouTube Live Stream.**
2.  **Find Your Live Stream's Video ID:** This is the part of the URL after `watch?v=`, like `dQw4w9WgXcQ`.
3.  **Update `.env`:** Make sure `YOUTUBE_VIDEO_ID` in your `.env` file is set to the correct Video ID for your *current* live stream.
4.  **Run the Python Script:**
    ```bash
    python chat_overlay.py
    ```
    You should see log messages indicating the TTS service initialization, Pytchat listener starting, and the Flask server running.
5.  **Add to OBS:**
    *   In OBS Studio (or similar streaming software), add a new "Browser" source.
    *   Set the URL to `http://127.0.0.1:5000`.
    *   Set the Width and Height (e.g., 1920x1080 or just the size needed for the overlay elements).
    *   Ensure the background is transparent (the CSS `body { background-color: rgba(0, 0, 0, 0); }` should handle this).
    *   Check "Shutdown source when not visible" and "Refresh browser when scene becomes active" for better resource management.

## Usage

*   While the script is running and connected to your stream, viewers can type messages in chat.
*   If a message starts exactly with the `ACTIVATION_PHRASE` (e.g., `faust says hello there!`), the text following the phrase will be:
    *   Displayed in the message bubble on the overlay.
    *   Sent to the configured TTS service to be spoken aloud.
    *   The character overlay will animate while the TTS is speaking.

## Troubleshooting

*   **`ValueError: signal only works in main thread`:** Ensure you are running the latest version of the code where `pytchat.create()` is called in the main thread before starting the listener thread.
*   **No Audio / ElevenLabs Errors:**
    *   Verify your `ELEVENLABS_API_KEY` in `.env` is correct.
    *   Make sure `ffmpeg` is installed correctly and accessible in your system's PATH.
    *   Check ElevenLabs API status and your account usage/credits.
*   **Pytchat Errors (`InvalidVideoIdException`, `RetryExceededError`):**
    *   Double-check that `YOUTUBE_VIDEO_ID` in `.env` is correct for the *currently live* stream. Pytchat won't work on VODs or non-live videos.
    *   Ensure your internet connection is stable.
*   **Animation Sync Issues:** Adjust `FLAP_START_DELAY_MS` in `templates/index.html`.

## Contributing

Pull requests are welcome...
