from picamera2 import Picamera2
import numpy as np
import time

# Initialize camera
picam2 = Picamera2()
picam2.start()
print("Camera started. Press Ctrl+C to stop.")

try:
    frame_count = 0
    while True:
        frame = picam2.capture_array()
        frame_count += 1

        # Simple sanity check: is the frame mostly non-zero?
        if np.any(frame):  # if any pixel has a non-zero value
            status = "Frame OK"
        else:
            status = "Frame blank!"

        if frame_count % 10 == 0:  # Print every 10 frames
            print(f"Captured {frame_count} frames - {status}")

        time.sleep(0.1)

except KeyboardInterrupt:
    print("\nStopping camera test...")

finally:
    picam2.stop()
    print("Camera stopped.")
