import os
import time
from elevenlabs.client import ElevenLabs
from elevenlabs import play, stream, Voice, VoiceSettings
import logging

# --- Base Class (Interface Definition) ---
class BaseTtsService:
    """Abstract base class for TTS services."""
    def __init__(self, config=None):
        """Initialize the service with optional configuration."""
        self.config = config or {}
        logging.info(f"Initializing {self.__class__.__name__}")

    def speak(self, text):
        """
        Generate audio for the text and play it (BLOCKING).
        This method should block until audio playback is complete.
        Raises NotImplementedError if not implemented by subclass.
        """
        raise NotImplementedError("Subclasses must implement the 'speak' method.")

    def cleanup(self):
        """Perform any cleanup needed when stopping."""
        logging.info(f"Cleaning up {self.__class__.__name__}")
        pass # Optional cleanup actions

# --- ElevenLabs Implementation ---
class ElevenLabsService(BaseTtsService):
    """TTS implementation using ElevenLabs API (online)."""
    def __init__(self, config=None):
        super().__init__(config)
        self.api_key = self.config.get("api_key")
        self.voice_id = self.config.get("voice_id", "21m00Tcm4TlvDq8ikWAM") # Default to Adam
        self.model = self.config.get("model", "eleven_turbo_v2")  # defaults to use the turbo model for low latency
        self.client = None

        if not self.api_key:
            logging.error("ElevenLabs API key not provided in config.")
            raise ValueError("Missing ElevenLabs API Key")

        try:
            # API key can be set via env var or passed explicitly
            # Passing explicitly is clearer for multi-service setup
            logging.info("Initializing ElevenLabs client...")
            self.client = ElevenLabs(api_key=self.api_key)
            # Verify connection (optional but recommended)
            self.client.voices.get_all()
            logging.info("ElevenLabs client initialized and API key verified.")
        except Exception as e:
            logging.error(f"Failed to initialize ElevenLabs client: {e}")
            self.client = None # Ensure client is None if init fails
            raise ConnectionError(f"ElevenLabs initialization failed: {e}")

    def speak(self, text):
        if not self.client:
            logging.error("Cannot speak: ElevenLabs client is not initialized.")
            # Simulate wait time
            time.sleep(1)
            return

        audio_stream = None
        try:
            logging.info(f"ElevenLabs generating audio for: '{text}' (Voice: {self.voice_id})")


            
            audio_stream = self.client.text_to_speech.convert(
                text=text,
                voice_id=self.voice_id,
                optimize_streaming_latency="0",
                output_format="mp3_22050_32",
                model_id="eleven_turbo_v2",  # use the turbo model for low latency, for other languages use the `eleven_multilingual_v2`
                voice_settings=VoiceSettings(
                    stability=0.0, # Adjust as needed
                    similarity_boost=1.0, # Adjust as needed
                    style=0.0,
                    use_speaker_boost=True,
                ),
            )
            logging.info("ElevenLabs audio stream generation initiated.")

            # Play the stream (blocking)
            # Requires ffmpeg installed and in PATH
            logging.info("ElevenLabs calling play/stream function... (BLOCKING)")
            if audio_stream:
                 play(audio_stream) # Use stream() for playback from the iterator
                 logging.info("ElevenLabs play/stream function COMPLETED.")
            else:
                 logging.warning("ElevenLabs audio stream was None, skipping playback.")

        except Exception as e:
            logging.error(f"Error during ElevenLabs speak: {e}")
            # Log specific API errors if needed
        finally:
             # Clean up stream resource if applicable (usually handled by stream/play)
             pass

    def cleanup(self):
        super().cleanup()
        # No specific client cleanup needed for elevenlabs usually
        logging.info("ElevenLabs service cleanup complete.")


# --- Factory Function ---
def get_tts_service(provider_name, config):
    """
    Factory function to create the appropriate TTS service instance.
    """
    provider_name = provider_name.lower()

    if provider_name == "elevenlabs":
        logging.info("Creating ElevenLabsService instance.")
        # Ensure API key is passed correctly
        el_config = config.get("elevenlabs", {})
        if "api_key" not in el_config:
             el_config["api_key"] = os.getenv("ELEVENLABS_API_KEY") # Fallback to env var
        return ElevenLabsService(el_config)
    # Add elif for other providers here (e.g., 'google_tts')
    else:
        logging.error(f"Unsupported TTS provider: {provider_name}")
        raise ValueError(f"Unsupported TTS provider: {provider_name}")