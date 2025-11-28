from picamera2 import Picamera2
import cv2
from pyzbar import pyzbar
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import time
import numpy as np

# -------------------------------
# Spotify setup
# -------------------------------
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id="YOUR_CLIENT_ID",
    client_secret="YOUR_CLIENT_SECRET",
    redirect_uri="http://localhost:8888/callback",
    scope="user-modify-playback-state,user-read-playback-state"
))

# Keep track of already opened URLs
opened_urls = set()

# -------------------------------
# Camera setup
# -------------------------------
picam2 = Picamera2()
config = picam2.create_video_configuration(
    main={"size": (1280, 720), "format": "BGR888"}
)
picam2.configure(config)
picam2.start()

# -------------------------------
# Image correction functions
# -------------------------------
def fix_orientation(frame):
    return cv2.rotate(frame, cv2.ROTATE_180)

def fix_colour(frame):
    frame = frame.copy()
    frame[:, :, 2] = frame[:, :, 2] * 0.6  # reduce red
    frame = frame[:, :, ::-1]  # BGR->RGB
    return frame

def to_grayscale(frame):
    frame_corrected = fix_colour(frame)
    gray = cv2.cvtColor(frame_corrected, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    return gray

# -------------------------------
# Helper to convert Spotify URL to URI
# -------------------------------
def spotify_uri_from_url(url):
    # Expect format: https://open.spotify.com/album/ALBUM_ID
    parts = url.split("/")
    if len(parts) >= 5 and parts[3] == "album":
        album_id = parts[4].split("?")[0]  # remove query string
        return f"spotify:album:{album_id}"
    return None

# -------------------------------
# Main loop
# -------------------------------
while True:
    frame = picam2.capture_array()
    frame = fix_orientation(frame)

    gray = to_grayscale(frame)
    decoded = pyzbar.decode(gray)

    for obj in decoded:
        url = obj.data.decode()
        if url not in opened_urls:
            print("QR:", url)
            opened_urls.add(url)

            album_uri = spotify_uri_from_url(url)
            if album_uri:
                try:
                    sp.start_playback(context_uri=album_uri)
                    print("Playing album on Spotify!")
                except spotipy.SpotifyException as e:
                    print("Spotify playback failed:", e)

    cv2.imshow("Camera Preview", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cv2.destroyAllWindows()
