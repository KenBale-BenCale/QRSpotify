import RPi.GPIO as GPIO
import threading
import time
import keyboard
import logging
import RPi.GPIO as GPIO

# Force BCM mode immediately
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

keyboardactive = False    #Toggle to activate/deactivate keyboard controls

logging.basicConfig(level=logging.INFO)

class InputHandler:
    """
    Handles 5 physical GPIO buttons + keyboard keys for SpotifyControls.
    Buttons:
      - VOL_UP / VOL_DOWN
      - NEXT / PREV
      - PLAY/PAUSE toggle
    Keyboard: W / S / D / A / SPACE
    """

    DEBOUNCE_SECONDS = 0.2  # ignore repeated presses within 200ms

    def __init__(self, spotify_controls):
        self.spc = spotify_controls
        self.running = False

        # GPIO pins (BCM)
        self.PIN_VOL_UP = 27
        self.PIN_VOL_DOWN = 5
        self.PIN_NEXT = 23
        self.PIN_PREV = 24
        self.PIN_PLAY_PAUSE = 17

        # Track last press times for debounce
        self._last_press = {pin: 0 for pin in [
            self.PIN_VOL_UP, self.PIN_VOL_DOWN,
            self.PIN_NEXT, self.PIN_PREV, self.PIN_PLAY_PAUSE
        ]}

    def start(self):
        logging.info("Starting InputHandler (Polling mode)...")
#        GPIO.setmode(GPIO.BCM)

        # Setup all pins as input with pull-ups
        pins = [self.PIN_VOL_UP, self.PIN_VOL_DOWN,
                self.PIN_NEXT, self.PIN_PREV, self.PIN_PLAY_PAUSE]
        for p in pins:
            GPIO.setup(p, GPIO.IN, pull_up_down=GPIO.PUD_UP)

#GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
#GPIO.add_event_detect(pin, GPIO.FALLING, callback=handler, bouncetime=250)


        self.running = True
        self.thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.thread.start()

    def stop(self):
        logging.info("Stopping InputHandler...")
        self.running = False
        self.thread.join()
        GPIO.cleanup()

    def _poll_loop(self):
        prev_prev_pressed = False  # for PREV double-press logic
        prev_pressed_time = 0

        while self.running:
            now = time.time()

            # VOL_UP
            if GPIO.input(self.PIN_VOL_UP) == GPIO.LOW and now - self._last_press[self.PIN_VOL_UP] > self.DEBOUNCE_SECONDS:
                self.spc.volume_delta(10)
                self._last_press[self.PIN_VOL_UP] = now

            # VOL_DOWN
            if GPIO.input(self.PIN_VOL_DOWN) == GPIO.LOW and now - self._last_press[self.PIN_VOL_DOWN] > self.DEBOUNCE_SECONDS:
                self.spc.volume_delta(-10)
                self._last_press[self.PIN_VOL_DOWN] = now

            # NEXT
            if GPIO.input(self.PIN_NEXT) == GPIO.LOW and now - self._last_press[self.PIN_NEXT] > self.DEBOUNCE_SECONDS:
                self.spc.next_track()
                self._last_press[self.PIN_NEXT] = now

            # PREV (single/double press)
            if GPIO.input(self.PIN_PREV) == GPIO.LOW and now - self._last_press[self.PIN_PREV] > self.DEBOUNCE_SECONDS:
#                 self.spc.previous_track()
#                 prev_prev_pressed = False

                if prev_prev_pressed and now - prev_pressed_time < 0.5:
                    # Double press -> skip to previous track
                    self.spc.previous_track()
                    prev_prev_pressed = False
                else:
                    # Single press -> restart current track
                    self.spc.restart_track()
                    prev_prev_pressed = True
#                    prev_pressed_time = now
#                self._last_press[self.PIN_PREV] = now

            # PLAY/PAUSE toggle
            if GPIO.input(self.PIN_PLAY_PAUSE) == GPIO.LOW and now - self._last_press[self.PIN_PLAY_PAUSE] > self.DEBOUNCE_SECONDS:
                self.spc.toggle_play_pause()
                self._last_press[self.PIN_PLAY_PAUSE] = now

            # --- Keyboard input ---
            # Volume
            if keyboardactive == True:
                if keyboard.is_pressed('w'):
                    self.spc.volume_delta(10)
                if keyboard.is_pressed('s'):
                    self.spc.volume_delta(-10)
            # Skip tracks
                if keyboard.is_pressed('d'):
                    self.spc.next_track()
                if keyboard.is_pressed('a'):
                    self.spc.previous_track()  # same logic as GPIO double-press optional
            # Play/Pause
                if keyboard.is_pressed('space'):
                    self.spc.toggle_play_pause()

                time.sleep(0.05)  # 50ms polling
