import RPi.GPIO as GPIO
import threading
import time

class LEDController:
    """
    Dual-LED controller for Raspberry Pi.
    Handles:
        OFF - both LEDs off (standby)
        RED_SOLID - red on (nothing playing)
        RED_BLINK - red blinking (error)
        GREEN_SOLID - green on (playing)
        GREEN_BLINK - green blinking (button pressed)
    """

    def __init__(self, red_pin, green_pin, active_high=True):
        self.red_pin = red_pin
        self.green_pin = green_pin
        self.active_high = active_high

        self.state = "OFF"
        self._blink = False
        self._blink_thread = None
        self._running = True

        # Setup GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.red_pin, GPIO.OUT)
        GPIO.setup(self.green_pin, GPIO.OUT)
        self._apply_state(False)  # ensure both off

        # Start blinking thread
        self._blink_thread = threading.Thread(target=self._blink_loop, daemon=True)
        self._blink_thread.start()

    def _led_on(self, pin):
        GPIO.output(pin, GPIO.HIGH if self.active_high else GPIO.LOW)

    def _led_off(self, pin):
        GPIO.output(pin, GPIO.LOW if self.active_high else GPIO.HIGH)

    def _apply_state(self, on_state=True):
        """
        Update LEDs according to self.state.
        on_state is True during blink "on" phase, False during "off" phase.
        """
        # Turn both off by default
        self._led_off(self.red_pin)
        self._led_off(self.green_pin)

        if self.state == "OFF":
            return
        elif self.state == "RED_SOLID":
            self._led_on(self.red_pin)
        elif self.state == "GREEN_SOLID":
            self._led_on(self.green_pin)
        elif self.state == "RED_BLINK" and on_state:
            self._led_on(self.red_pin)
        elif self.state == "GREEN_BLINK" and on_state:
            self._led_on(self.green_pin)

    def _blink_loop(self):
        while self._running:
            if self._blink:
                self._apply_state(True)
                time.sleep(0.4)
                self._apply_state(False)
                time.sleep(0.4)
            else:
                self._apply_state(True)
                time.sleep(0.1)

    def set_state(self, new_state):
        """
        Set new LED state. Handles blinking automatically.
        """
        self.state = new_state
        self._blink = "BLINK" in new_state

    def cleanup(self):
        """
        Call this when shutting down to clean GPIO
        """
        self._running = False
        time.sleep(0.2)
        self._led_off(self.red_pin)
        self._led_off(self.green_pin)
        GPIO.cleanup()
