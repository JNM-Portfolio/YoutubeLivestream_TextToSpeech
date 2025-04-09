import os
import time
import threading
import queue
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import logging
from dotenv import load_dotenv
import random
from datetime import datetime, timezone
import pytchat

# --- Import TTS services ---
from tts_services import get_tts_service, BaseTtsService

# --- Load Environment Variables ---
load_dotenv()

# --- Configuration ---
TTS_PROVIDER = "elevenlabs"
TTS_CONFIG = {
    "elevenlabs": { # Example
        "voice_id": os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"), # Default to Rachel
        "model": "eleven_turbo_v2" # defaults to use the turbo model for low latency
    }
}

# --- YouTube Configuration ---
# !!!!! IMPORTANT: SET YOUR VIDEO ID HERE (via .env ideally) !!!!!
YOUTUBE_VIDEO_ID = os.getenv("YOUTUBE_VIDEO_ID", None)

# --- Activation Phrase ---
ACTIVATION_PHRASE = "faust says " # Case-insensitive check later
LOOK_FOR_YOUTUBE_ID = True # or false to disable YouTube chat polling

# --- Basic Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# Reduce log noise from libraries
logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)
logging.getLogger("googleapiclient.discovery").setLevel(logging.WARNING)
logging.getLogger("oauthlib").setLevel(logging.WARNING)
logging.getLogger("requests_oauthlib").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("websockets").setLevel(logging.WARNING)
logging.getLogger("engineio").setLevel(logging.WARNING)
logging.getLogger("socketio").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING) # Pytchat uses requests/urllib3

# --- Queues and Globals ---
tts_queue = queue.Queue()
socketio_global = None
active_tts_service: BaseTtsService = None
pytchat_instance = None # To hold the pytchat object for stopping
pytchat_listener_thread = None   # To hold the listener thread
tts_thread = None # To hold the TTS worker thread

# Flag to signal shutdown to threads
shutdown_event = threading.Event()

# --- TTS Worker ---
def tts_worker(tts_service: BaseTtsService): # Accepts the service instance
    """Worker thread that processes the TTS queue using the provided service."""
    logging.info(f"TTS Worker Thread Started (Using: {tts_service.__class__.__name__}).")
    while not shutdown_event.is_set():
        text_to_speak = None
        try:
            logging.info("TTS Worker: Waiting for item from queue...")
            text_to_speak = tts_queue.get() # Blocks here
            logging.info(f"TTS Worker: Got item: '{text_to_speak}'")

            if text_to_speak is None: # Signal to exit
                logging.info("TTS Worker: Received None, exiting.")
                break

            # --- Start Speaking Signal ---
            logging.info("TTS Worker: Attempting to emit tts_start...")
            if socketio_global:
                socketio_global.emit('tts_start', namespace='/')
                logging.info("TTS Worker: Emitted tts_start.")
            else:
                logging.warning("TTS Worker: socketio_global not set, cannot emit tts_start.")

            # --- Delegate to the TTS Service ---
            logging.info(f"TTS Worker: Calling {tts_service.__class__.__name__}.speak()...")
            tts_service.speak(text_to_speak)
            logging.info(f"TTS Worker: {tts_service.__class__.__name__}.speak() COMPLETED.")

        except queue.Empty:
            # Timeout occurred, just loop again and check shutdown_event
            continue
        except Exception as e:
            logging.error(f"!!!!!!!! ERROR in TTS worker processing '{text_to_speak}': {e} !!!!!!!!")
            # Avoid super-fast error loops
            time.sleep(1)

        finally:
            # --- Stop Speaking Signal (ALWAYS emit this, unless shutting down immediately) ---
            # Only emit stop if we actually started (i.e., text_to_speak was processed)
            # And only if we are not already shutting down
            if text_to_speak is not None and not shutdown_event.is_set():
                logging.info("TTS Worker: In finally block, attempting to emit tts_stop...")
                if socketio_global:
                    socketio_global.emit('tts_stop', namespace='/')
                    logging.info("TTS Worker: Emitted tts_stop.")
                else:
                    logging.warning("TTS Worker: socketio_global not set, cannot emit tts_stop.")

            # Mark the task as done in the queue
            if text_to_speak is not None:
                logging.info("TTS Worker: Marking task done.")
                # Use task_done() for queue management if using queue.join() later
                # If not using join(), this isn't strictly necessary but good practice
                try:
                     tts_queue.task_done()
                except ValueError:
                    # Can happen if task_done() is called after queue cleared or on None
                    logging.debug("TTS Worker: task_done() called when not needed or queue cleared.")
                except Exception as e_td:
                    logging.error(f"TTS Worker: Error calling task_done(): {e_td}")

    # --- End of Worker Loop ---
    logging.info("TTS Worker: Performing service cleanup...")
    if hasattr(tts_service, 'cleanup'): tts_service.cleanup()
    logging.info("TTS Worker Thread Finished.")

# --- Flask Web Server & SocketIO ---
app = Flask(__name__)
socketio = SocketIO(app, async_mode='threading', engineio_logger=False, logger=False)
socketio_global = socketio

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect', namespace='/')
def handle_connect():
    logging.info('Client connected')

@socketio.on('disconnect', namespace='/')
def handle_disconnect():
    logging.info('Client disconnected')

def handle_new_pytchat_message(item):
    """Processes messages received from the Pytchat listener."""
    try:
        message_text = getattr(item, 'message', '').strip()
        author = getattr(item.author, 'name', 'Someone')

        logging.debug(f"Received message from YouTube: '{message_text}' by {author}")

        # Check if the message starts with the activation phrase (case-insensitive)
        if message_text.lower().startswith(ACTIVATION_PHRASE):
            # Extract the actual message content aka remove the activation phrase
            content_to_speak = message_text[len(ACTIVATION_PHRASE):].strip()

            if not content_to_speak:
                logging.info("Activation phrase found but no message content.")
                return # Ignore empty messages

            logging.info(f"Activation phrase matched! Author: {author}, Content: '{content_to_speak}'")

            # Prepare for TTS
            tts_text = f"{content_to_speak}" # What the TTS will actually speak
            display_text = f"{author}: {content_to_speak}" # What appears in the bubble

            # Emit display message to overlay
            if socketio_global:
                socketio_global.emit('new_message', {'text': display_text}, namespace='/')
                logging.debug(f"Emitted display message: {display_text}")

            # Put job onto TTS queue
            tts_queue.put(tts_text)
            logging.info(f"Queued TTS job: {tts_text}")

    except Exception as e:
        logging.exception(f"Error handling Pytchat message: {getattr(item, 'json', str(item))}")

# --- Pytchat Listener Function ---
def pytchat_listener_loop(chat: pytchat.LiveChat, callback):
    """The loop that gets messages from an existing Pytchat instance."""
    global pytchat_instance # Reference the global instance for cleanup signal checks
    logging.info("Pytchat listener loop started.")
    try:
        while not shutdown_event.is_set() and chat.is_alive():
            try:
                items = chat.get().sync_items()
                for item in items:
                    # Check again before processing in case shutdown happened during get()
                    if shutdown_event.is_set():
                        break
                    callback(item) # Process message
                if shutdown_event.is_set():
                    break # Exit outer loop if shutdown signaled

            except pytchat.exceptions.RetryExceededError as e:
                 logging.error(f"Pytchat retry exceeded: {e}. Stopping listener loop.")
                 break # Exit loop on critical error
            except Exception as e:
                 # Log non-critical errors and continue loop
                 logging.exception("Error in Pytchat receive loop:")
                 time.sleep(5) # Avoid fast error loop

            # Check if termination was signaled externally (via pytchat_instance being None)
            if pytchat_instance is None:
                 logging.info("Pytchat instance was terminated externally. Stopping loop.")
                 break

            time.sleep(0.2) # Yield thread

    except Exception as e:
        # Catch errors happening outside the inner try (e.g., if chat object becomes invalid)
        logging.exception(f"Error in Pytchat listener outer loop:")
    finally:
        logging.info("Pytchat listener loop finished.")
        # Make sure the instance is terminated if the loop exits unexpectedly
        if pytchat_instance:
            try:
                logging.info("Pytchat listener ensuring instance is terminated in finally block.")
                pytchat_instance.terminate()
            except Exception as e_term:
                logging.error(f"Error terminating pytchat in listener finally: {e_term}")

# --- Manual Input Function (for testing) ---
def manual_message_input():
    """Provides manual input testing if YouTube is not configured."""
    logging.info("\n--- MANUAL TEST MODE ---")
    logging.info(f"Type a message starting with '{ACTIVATION_PHRASE}' to test TTS.")
    logging.info("Type 'quit' or 'exit' to stop.")
    while not shutdown_event.is_set():
        try:
            text = input("Enter test message: ")
            if shutdown_event.is_set(): break
            if text.lower() in ['quit', 'exit']: break
            # Simulate a basic object that looks like a Pytchat item
            # for the handler's needs
            class MockPytchatAuthor: name = "Tester"
            class MockPytchatItem: author = MockPytchatAuthor(); message = text
             # Call the handler with the mock item
            handle_new_pytchat_message(MockPytchatItem)
        except EOFError: break
        except Exception as e: logging.error(f"Error in manual input: {e}")
    logging.info("Manual input thread finished.")

# --- Main Execution ---
if __name__ == '__main__':
    logging.info("Starting application...")

    # --- Determine Run Mode ---
    run_youtube_mode = False
    if LOOK_FOR_YOUTUBE_ID and YOUTUBE_VIDEO_ID:
        logging.info("YouTube Video ID found. Attempting to run in YouTube Live mode.")
        run_youtube_mode = True
    else:
        logging.warning("YouTube Video ID not found. Running in Manual Input Test Mode.")

    # --- Initialize TTS Service ---
    try:
        logging.info(f"Initializing TTS provider: {TTS_PROVIDER}")
        active_tts_service = get_tts_service(TTS_PROVIDER, TTS_CONFIG)
    except Exception as e:
        logging.error(f"FATAL: Failed to initialize TTS service '{TTS_PROVIDER}'. Error: {e}")
        exit(1)

    # --- Create Pytchat Instance in MAIN THREAD (if applicable) ---
    if run_youtube_mode:
        try:
            logging.info(f"Creating Pytchat instance for Video ID: {YOUTUBE_VIDEO_ID}...")
            pytchat_instance = pytchat.create(video_id=YOUTUBE_VIDEO_ID)
            logging.info("Pytchat instance created successfully.")
        except pytchat.exceptions.InvalidVideoIdException:
            logging.error(f"FATAL: Invalid YouTube Video ID provided: '{YOUTUBE_VIDEO_ID}'")
            pytchat_instance = None # Ensure it's None if creation fails
            run_youtube_mode = False # Fallback to manual mode maybe? Or exit? For now, just log.
            exit(1) # Exit if video ID is invalid
        except Exception as e:
            logging.exception(f"FATAL: Failed to create Pytchat instance:")
            pytchat_instance = None
            exit(1) # Exit on other creation errors

    # --- Start Input Source Thread (Listener or Manual) ---
    input_thread = None # <<< ADD: Variable to hold the input thread
    if run_youtube_mode and pytchat_instance:
        logging.info("Starting Pytchat listener thread...")
        pytchat_listener_thread = threading.Thread( # <<< CHANGE: Use specific name <<<
            target=pytchat_listener_loop,
            args=(pytchat_instance, handle_new_pytchat_message),
            daemon=True # Keep daemon=True
        )
        input_thread = pytchat_listener_thread # Assign to generic input_thread
        pytchat_listener_thread.start()
    else:
        # Start manual input thread (either by choice or fallback)
        logging.info("Starting manual input thread for testing...")
        manual_input_thread = threading.Thread(target=manual_message_input, daemon=True)
        input_thread = manual_input_thread # Assign to generic input_thread
        manual_input_thread.start()


    # --- Start TTS Worker Thread ---
    logging.info("Starting TTS worker thread...")
    tts_thread = threading.Thread(target=tts_worker, args=(active_tts_service,), daemon=True)
    tts_thread.start()

    # --- Start Flask Server ---
    logging.info("Starting Flask-SocketIO server on http://127.0.0.1:5000")
    logging.info("Press Ctrl+C to stop the server.")
    try:
        socketio.run(app, host='127.0.0.1', port=5000, use_reloader=False, debug=False, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        logging.info("Flask server stopped by user (Ctrl+C).")
    except Exception as e:
         logging.error(f"Flask server failed: {e}")
    finally:
        # --- Cleanup ---
        logging.info("Shutting down application...")

        # 1. Signal all threads to stop
        logging.info("Setting shutdown event...")
        shutdown_event.set()

        # 2. Stop Pytchat instance (if it exists)
        # This should help unblock the listener thread's get() call
        if pytchat_instance:
            logging.info("Terminating Pytchat instance...")
            try:
                pytchat_instance.terminate()
                # Setting to None isn't strictly needed now with the event, but doesn't hurt
                # pytchat_instance = None
            except Exception as e_term:
                 logging.error(f"Error terminating Pytchat: {e_term}")

        # 3. Wait for the input thread (Pytchat listener or Manual) to exit
        if input_thread and input_thread.is_alive():
             logging.info(f"Waiting for {input_thread.name} thread to join...")
             input_thread.join(timeout=5) # Increased timeout slightly
             if input_thread.is_alive():
                  logging.warning(f"{input_thread.name} thread did not exit cleanly after timeout.")
             else:
                  logging.info(f"{input_thread.name} thread joined successfully.")

       # 4. Signal and wait for TTS worker
        #    - Send None to potentially unblock queue.get() faster than timeout
        #    - shutdown_event is already set, so it will exit its loop anyway
        logging.info("Signaling TTS worker queue with None...")
        tts_queue.put(None)
        if tts_thread and tts_thread.is_alive():
            logging.info("Waiting for TTS worker thread to finish...")
            tts_thread.join(timeout=10) # Allow time for final TTS playback if any + cleanup
            if tts_thread.is_alive():
                 logging.warning("TTS worker thread did not exit cleanly after timeout.")
            else:
                 logging.info("TTS worker thread joined successfully.")

        logging.info("Application finished.")