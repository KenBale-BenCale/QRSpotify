import signal

# Global flag for main loop
running = True

# Signal handler
def handle_exit(signum, frame):
    global running
    print(f"\nSignal {signum} received. Exiting gracefully...")
    running = False

# Register signals
signal.signal(signal.SIGINT, handle_exit)   # Ctrl+C
signal.signal(signal.SIGTERM, handle_exit)  # kill command / system stop

# Main loop
try:
    while running:
        # Your main loop code (QR scanning, Spotify, LED updates, etc.)
        frame = picam2.capture_array()
        qr_data = decode_frame(frame)
        if qr_data:
            # handle QR code...
            pass

        time.sleep(0.2)

finally:
    print("Stopping input handler & cleaning up...")
    try:
        input_handler.stop()
    except Exception as e:
        print("Error stopping input handler:", e)
    try:
        picam2.stop()
    except Exception as e:
        print("Error stopping camera:", e)
    try:
        led.stop()
    except Exception as e:
        print("Error stopping LEDs:", e)
    print("Cleanup complete. Exiting.")
    sys.exit(0)
