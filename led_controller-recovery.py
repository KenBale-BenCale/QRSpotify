import RPi.GPIO as GPIO
import threading
import time

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

class LEDController:
    def __init__(self, red_pin, green_pin, active_high=True):
        self.red_pin = red_pin
        self.green_pin = green_pin
        self.active_high = active_high

        self.state = "OFF"
        self._blink = False
        self._stop_event = threading.Event()

        GPIO.setup(self.red_pin, GPIO.OUT)
        GPIO.setup(self.green_pin, GPIO.OUT)
        self._apply_state(False)

        self._blink_thread = threading.Thread(target=self._blink_loop, daemon=True)
        self._blink_thread.start()

    def _led_on(self, pin):
        try:
            GPIO.output(pin, GPIO.HIGH if self.active_high else GPIO.LOW)
        except RuntimeError:
            pass

    def _led_off(self, pin):
        try:
            GPIO.output(pin, GPIO.LOW if self.active_high else GPIO.HIGH)
        except RuntimeError:
            pass

    def _apply_state(self, on_state=True):
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
        while not self._stop_event.is_set():
            if self._blink:
                self._apply_state(True)
                if self._stop_event.wait(0.4):
                    break
                self._apply_state(False)
                if self._stop_event.wait(0.4):
                    break
            else:
                self._apply_state(True)
                if self._stop_event.wait(0.1):
                    break

    def set_state(self, new_state):
        self.state = new_state
        self._blink = "BLINK" in new_state

    def stop(self):
        self._stop_event.set()
        self._blink_thread.join()
        self._led_off(self.red_pin)
        self._led_off(self.green_pin)
        GPIO.cleanup()
