#!/usr/bin/env python3
"""
QRSpotify 5.0 - Headless Pi Zero version
- Uses Picamera2 + pyzbar for QR scanning
- Uses refresh token flow for Spotify (no interactive OAuth)
- Uses LEDController and InputHandler (GPIO + keyboard)
"""

import os
from dotenv import load_dotenv
# Load environment variables
load_dotenv(dotenv_path="/home/pi/QRSpotify/.env")

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")
REFRESH_TOKEN = os.getenv("SPOTIFY_REFRESH_TOKEN")
ACCESS_TOKEN = os.getenv("SPOTIFY_ACCESS_TOKEN")
if not all([CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN]):
    raise RuntimeError("Spotify credentials not set in environment.")

#import os
from datetime import datetime
import time
import threading
import sys
import requests
import subprocess
import base64
#from dotenv import load_dotenv
#load_dotenv()
# Make sure runtime dir exists if your system requires it (optional)
os.environ.setdefault("XDG_RUNTIME_DIR", "/tmp/runtime-root")

# Camera + QR
from picamera2 import Picamera2
from pyzbar import pyzbar

# Input / controls / LED (your modules)
from controls import SpotifyControls
from input_handler import InputHandler
from led_controller import LEDController

# keyboard for headless quit
import keyboard

if not CLIENT_ID or not CLIENT_SECRET or not REFRESH_TOKEN:
    print("ERROR: Spotify credentials not set in environment.")
    print("Please set SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET and SPOTIFY_REFRESH_TOKEN.")
    sys.exit(1)

#sp_oauth = SpotifyOAuth(
#    client_id=CLIENT_ID,
#    client_secret=CLIENT_SECRET,
#    redirect_uri=REDIRECT_URI,
#    scope=SCOPE
#)
RED_PIN = 22
GREEN_PIN = 18

led = LEDController(red_pin=RED_PIN, green_pin=GREEN_PIN, active_high=True)

# small helper to refresh Spotify access tokens
class SpotifyTokenManager:
    def __init__(self, client_id, client_secret, refresh_token):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.access_token = None
        self.expires_at = 0

    def refresh_access_token(self):
        auth_header = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        r = requests.post(
            "https://accounts.spotify.com/api/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token
            },
            headers={"Authorization": f"Basic {auth_header}"}
        )
        r.raise_for_status()
        token_info = r.json()
        self.access_token = token_info["access_token"]
        self.expires_at = time.time() + token_info.get("expires_in", 3600) - 30
        print(f"{datetime.now():%Y-%m-%d %H:%M:%S} Access token refreshed. Expires at {time.ctime(self.expires_at)}")

    def get_access_token(self):
        if not self.access_token or time.time() >= self.expires_at:
            self.refresh_access_token()
        return self.access_token

token_manager = SpotifyTokenManager(CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN)

def get_spotify_client():
    import spotipy
    token = token_manager.get_access_token()
    return spotipy.Spotify(auth=token)

# Utility functions (normalise and device lookup)
def normalise_spotify_url(url: str) -> str:
    url = url.strip()
    if "?" in url:
        url = url.split("?", 1)[0]
    if url.startswith("spotify:"):
        return url
    if "open.spotify.com" in url:
        parts = url.replace("https://open.spotify.com/", "").split("/")
        if len(parts) >= 2:
            content_type = parts[0]
            content_id = parts[1]
            return f"spotify:{content_type}:{content_id}"
    return url
def get_device_id_by_name(sp, target_name: str):
    devices = sp.devices().get('devices', [])
    for d in devices:
        if d.get('name', '').lower() == target_name.lower():
            return d.get('id')
    return None

def get_current_track(sp):
    playback = sp.current_playback()
    if not playback or not playback.get("item"):
        return None
    item = playback["item"]
    track_name = item["name"]
    artists = ", ".join([artist["name"] for artist in item["artists"]])
    album = item["album"]["name"]
    url = item["external_urls"]["spotify"]
    track_number = item.get("track_number", None)
    return {
        "track_name": track_name,
        "artists": artists,
        "album": album,
        "url": url,
        "track_number": track_number
    }

# Retry playback thread
retry_thread_running = False
def retry_playback(sp, track_uri, device_name="Web Player (Chrome)"):
    global phone_device_id, retry_thread_running
    retry_thread_running = True
    led.set_state("RED_BLINK")
    while True:
        phone_device_id = get_device_id_by_name(sp, device_name)
        if not phone_device_id:
            print(f"{datetime.now():%Y-%m-%d %H:%M:%S}, Device '{device_name}' not found. Retrying…")
            time.sleep(5)
            continue
        try:
            sp.start_playback(device_id=phone_device_id, uris=[track_uri])
            led.set_state("GREEN_SOLID")
            print(f"{datetime.now():%Y-%m-%d %H:%M:%S}, Playback started on {device_name}")
            break
        except Exception as e:
            print(f"{datetime.now():%Y-%m-%d %H:%M:%S}, Playback retry error: {e}. Retrying…")
            time.sleep(5)
    retry_thread_running = False

# QR decode (via pyzbar on numpy frame)
def decode_frame(frame):
    decoded = pyzbar.decode(frame)
    if decoded:
        return decoded[0].data.decode("utf-8")
    return None
print("LEDS set")
led.set_state("GREEN_SOLID")
time.sleep(0.5)
led.set_state("RED_SOLID")
time.sleep(0.5)
led.set_state("OFF")
print("LEDS standby")

# Create Spotify client once (we will refresh tokens inside loop)
sp = get_spotify_client()

PHONE_DEVICE_NAME = "Web Player (Chrome)"
phone_device_id = get_device_id_by_name(sp, PHONE_DEVICE_NAME)
print(f"{datetime.now():%Y-%m-%d %H:%M:%S},Target device: {PHONE_DEVICE_NAME}")
print(f"{datetime.now():%Y-%m-%d %H:%M:%S},Device ID: {phone_device_id}")

if phone_device_id is None:
    led.set_state("RED_BLINK")
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S},No active Spotify device found! Playback may fail.")
    phone_device_id = None

# Start controls + input handler
spc = SpotifyControls(sp, device_id=phone_device_id)
input_handler = InputHandler(spc)
input_handler.start()
print(f"{datetime.now():%Y-%m-%d %H:%M:%S},InputHandler started (GPIO + keyboard)")

# Camera start
picam2 = Picamera2()
picam2.start()
print(f"{datetime.now():%Y-%m-%d %H:%M:%S},Camera Starting. Ready")

last_track_id = None

try:
    while True:
        sp = get_spotify_client()  # ensure token is fresh for each loop

        if phone_device_id is None:
            phone_device_id = get_device_id_by_name(sp, PHONE_DEVICE_NAME)
            if phone_device_id:
                led.set_state("RED_SOLID")
            else:
                print("Rechecking in 5 seconds")
                time.sleep(5)
                continue
        info = get_current_track(sp)
        if info:
            current_id = info['url']
            if current_id != last_track_id:
                print(f"\nNow playing: {info['track_number']}. {info['track_name']} - {info['artists']}")
                last_track_id = current_id
            led.set_state("GREEN_SOLID")
        else:
            led.set_state("RED_SOLID")

        # Capture and decode
        frame = picam2.capture_array()
        qr_data = decode_frame(frame)
        if qr_data:
            url = qr_data
            print(f"{datetime.now():%Y-%m-%d %H:%M:%S} QR code detected: {url}")

            try:
                r = requests.head(url, allow_redirects=True)
                final_url = r.url
            except Exception as e:
                print("Error resolving URL:", e)
                continue

            uri = normalise_spotify_url(final_url)
            if phone_device_id is None:
                print("ERROR: Spotify device not found!")
                continue

            try:
                if uri.startswith("spotify:track:") or uri.startswith("spotify:episode:"):
                    print("Starting track/episode playback…")
                    sp.start_playback(device_id=phone_device_id, uris=[uri])
                else:
                    print("Starting context playback…")
                    sp.start_playback(device_id=phone_device_id, context_uri=uri)
                print("Playing!")
            except Exception as e:
                print(f"{datetime.now():%Y-%m-%d %H:%M:%S},Spotify error:", e)
                led.set_state("RED_BLINK")
                # start retry thread if not running
                if not retry_thread_running:
                    threading.Thread(target=retry_playback, args=(sp, uri), daemon=True).start()

        # Quit key (headless)
        if keyboard.is_pressed('q'):
            print("Quit key detected. Exiting...")
            break

        time.sleep(0.2)
finally:
    print("Stopping input handler & cleaning up...")
        # Stop input handling first
    try:
        input_handler.stop()
    except Exception as e:
        print("Error stopping input handler:", e)
    # Stop camera next
    try:
        picam2.stop()
    except Exception as e:
        print("Error stopping camera:", e)
    # Stop LEDs last to ensure GPIO is still valid
    try:
        led.stop()
    except Exception as e:
        print("Error stopping LEDs:", e)
    print("Cleanup complete. Exiting.")
    sys.exit(0)



