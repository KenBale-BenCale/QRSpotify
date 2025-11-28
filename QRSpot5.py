#!/usr/bin/env python3

"""
QRSpotify 5.0
- Reads Spotify QR codes
- Selects playback device based on name
- Supports GPIO + keyboard controls via InputHandler
- Window allows quitting with 'q'
- changed cameras
- GPIO implimented
- Added LED lights
"""

import os
os.environ["XDG_RUNTIME_DIR"] = "/tmp/runtime-root"
from picamera2 import Picamera2
from pyzbar import pyzbar
import cv2
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import time
import requests
import webbrowser
import sys
from datetime import datetime
import threading

from controls import SpotifyControls
from input_handler import InputHandler
from led_controller import LEDController

RED_PIN = 22      #GPIO pins for LEDs
GREEN_PIN = 18

led = LEDController(red_pin=RED_PIN, green_pin=GREEN_PIN, active_high=True)

RETRY_INTERVAL = 5  # seconds to retest if error/exception is thrown


# ===================led test
print("LEDS set")
led.set_state("GREEN_SOLID")
time.sleep(0.5)
led.set_state("RED_SOLID")
time.sleep(1)
print("LEDS TEST")
time.sleep(1)
led.set_state("OFF")   # standby default
print("LEDS standby")


print("QRSpotify 4.0 loading")
print(" --------")
print(" | ___  |")
print(" | |  | |")
print(" | |  | |")
print("(_)  (_) \n\n")

print(" /\_/\ ")
print("(* . *)")
print("(_____)__")
print("")
print("")
print("")
print("\n\nA BCBC PRODUCTION\n\n")
# === Universal Spotify URL normaliser ===
def normalise_spotify_url(url: str) -> str:
    url = url.strip()
    if "?" in url:
        url = url.split("?")[0]
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
        if d['name'].lower() == target_name.lower():
            return d['id']
    return None


# === retrieve track info from Spotify ===


def get_current_track(sp: spotipy):
    playback = sp.current_playback()

    if not playback or not playback.get("item"):
        return None # Nothing is currently playing

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

#==============  If an error occurs, keep retrying periodically.
retry_thread_running = False

def retry_playback(sp, track_uri, device_name="Web Player (Chrome)"):
    """
    Retry playback until a valid device is found and playback succeeds.
    Stops for unsupported URI errors.
    """
    global phone_device_id
    led.set_state("RED_BLINK")

    while True:
        # Find the device
        phone_device_id = get_device_id_by_name(sp, device_name)
        if not phone_device_id:
            print(f"{datetime.now():%Y-%m-%d %H:%M:%S}, Device '{device_name}' not found. Retrying…")
            time.sleep(5)
            continue

        try:
            sp.start_playback(device_id=phone_device_id, uris=[track_uri])
            led.set_state("GREEN_SOLID")
            print(f"{datetime.now():%Y-%m-%d %H:%M:%S}, Playback started on {device_name}")
            break  # Success → exit loop

        except spotipy.exceptions.SpotifyException as e:
            if e.http_status == 404:
                # Device disappeared → retry
                print(f"{datetime.now():%Y-%m-%d %H:%M:%S}, Device not found, retrying…")
                time.sleep(5)
            elif e.http_status == 400:
                # Unsupported URI → stop retrying
                print(f"{datetime.now():%Y-%m-%d %H:%M:%S}, Unsupported URI: {track_uri}. Aborting retry.")
                led.set_state("RED_SOLID")
                break
            else:
                # Other errors → wait and retry
                print(f"{datetime.now():%Y-%m-%d %H:%M:%S}, Spotify error: {e}, retrying…")
                time.sleep(5)


# === Spotipy setup ===
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id="c129514435024e23bf9ed5e843b5a6c0",
    client_secret="a8cab539d11d4fb794e96130ad21f642",
    redirect_uri="http://127.0.0.1:8888/callback",
    scope="user-modify-playback-state,user-read-playback-state",
    cache_path="./.spotipy_cache"
))

PHONE_DEVICE_NAME = "Web Player (Chrome)"   # Change to your device
phone_device_id = get_device_id_by_name(sp, PHONE_DEVICE_NAME)
print(f"{datetime.now():%Y-%m-%d %H:%M:%S},Target device: {PHONE_DEVICE_NAME}")
print(f"{datetime.now():%Y-%m-%d %H:%M:%S},Device ID: {phone_device_id}")

if phone_device_id is None:
#    print(f"{datetime.now():%Y-%m-%d %H:%M:%S},WARNING: '{PHONE_DEVICE_NAME}' not found. Using first available device.")
#    devices = sp.devices()
#    if devices['devices']:
#        phone_device_id = devices['devices'][0]['id']
#    else:
#        print("{datetime.now():%Y-%m-%d %H:%M:%S},No active Spotify device found! Playback may fail.")
#        phone_device_id = None
     led.set_state("RED_BLINK")
     print("{datetime.now():%Y-%m-%d %H:%M:%S},No active Spotify device found! Playback may fail.")
     phone_device_id = None
     led.set_state("RED_BLINK")
     print("Rechecking in 5 seconds")
     time.sleep(5)




# === Spotify Controls + Input Handler ===
spc = SpotifyControls(sp, device_id=phone_device_id)
input_handler = InputHandler(spc)
input_handler.start()
print(f"{datetime.now():%Y-%m-%d %H:%M:%S},InputHandler started (GPIO + keyboard)")


# === Camera setup ===
picam2 = Picamera2()
picam2.start()
print(f"\n{datetime.now():%Y-%m-%d %H:%M:%S},\nCamera Starting.\nReady")

cv2.namedWindow("QRSpotify", cv2.WINDOW_NORMAL)
cv2.resizeWindow("QRSpotify", 1, 1)

last_track_id = None


try:
    while True:
        if phone_device_id is None:
            PHONE_DEVICE_NAME = "Web Player (Chrome)"   # Change to your device
            phone_device_id = get_device_id_by_name(sp, PHONE_DEVICE_NAME)
            print(f"{datetime.now():%Y-%m-%d %H:%M:%S},Target device: {PHONE_DEVICE_NAME}")
            print(f"{datetime.now():%Y-%m-%d %H:%M:%S},Device ID: {phone_device_id}")
            if phone_device_id != None:
                led.set_state("RED_SOLID")
            else:
                print("Rechecking in 5 seconds")
                time.sleep(5)

#        last_track_id = None
        info = get_current_track(sp)    # To find track info
        if info:
            current_id = info['url']  # or track_name+artist
            if current_id != last_track_id:
                print(f"\nNow playing: {info['track_number']}. {info['track_name']} - {info['artists']}")
                last_track_id = current_id


        if info:    # Control LEDS based on track info
            led.set_state("GREEN_SOLID")
#        else:
#            led.set_state("RED_SOLID")


#        time.sleep(1)


        # Quit key
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("Quit key detected. Exiting...")
            break

        frame = picam2.capture_array()
        decoded = pyzbar.decode(frame)

        for obj in decoded:
            url = obj.data.decode()
            print("QR code detected:", url)

            # Follow redirects
            try:
                r = requests.head(url, allow_redirects=True)
                final_url = r.url
            except Exception as e:
                print("Error resolving URL:", e)
                continue

#            print("Final URL:", final_url)    #debug

            # Convert to spotify:... URI
            uri = normalise_spotify_url(final_url)
#            print("Normalised Spotify URI:", uri)    #debug

            if phone_device_id is None:
                print(f"{datetime.now():%Y-%m-%d %H:%M:%S},ERROR: Spotify device '{PHONE_DEVICE_NAME}' not found!")
                continue
            else:
                print(f"{datetime.now():%Y-%m-%d %H:%M:%S},Using device: {PHONE_DEVICE_NAME} ({phone_device_id})")

            # Start playback
            try:
                if uri.startswith("spotify:track:") or uri.startswith("spotify:episode:"):
                    print("Starting track/episode playback…")
                    sp.start_playback(device_id=phone_device_id, uris=[uri])
#                    self.spc._is_playing = True
#                    self.spc.resume()
#                    info = get_current_track(sp)
#                    if info:
#                        print(info)
#        else:
#            print("Nothing is currently playing")

                else:
                    print("Starting context playback…")
                    sp.start_playback(device_id=phone_device_id, context_uri=uri)
#                    self.spc._is_playing = True
#                    self.spc.resume()
#                    info = get_current_track(sp)
#                    if info:
#                        print(info)


                print("Playing!")
#                info = get_current_track(sp)
#                if info:
#                    print(info)

            except spotipy.exceptions.SpotifyException as e:
                print(f"{datetime.now():%Y-%m-%d %H:%M:%S},Spotify error:", e)
                led.set_state("RED_BLINK")
                # Attempt playback; will keep retrying if Spotify throws an error
                track_uri = uri  # current QR code track
                if not retry_thread_running:
                    threading.Thread(target=retry_playback, args=(sp, track_uri), daemon=True).start()

        time.sleep(0.2)
#        print(f"{info['track_name']} - {info['artists']}")
#        info = get_current_track(sp)
#       if info:
#            print(info)
#        else:
#            print("Nothing is currently playing")


finally:
    print("Stopping input handler & cleaning up...")
    input_handler.stop()
    picam2.stop()
    cv2.destroyAllWindows()
    print("Camera stopped. Goodbye.")
    sys.exit(0)
