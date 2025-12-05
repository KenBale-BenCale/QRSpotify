#!/usr/bin/env python3
"""
QRSpot_master.py
- Two Spotify accounts (BEN then N)
- Picamera2 + pyzbar QR scanning
- Uses existing InputHandler and LEDController
- Plays on Pi device if account free; otherwise provides metadata for VLC
"""

import os
import sys
import time
import signal
import logging
import requests
import base64
from datetime import datetime

from dotenv import load_dotenv
load_dotenv(dotenv_path="/home/pi/QRSpotify/.env")

# Camera + QR
from picamera2 import Picamera2
from pyzbar import pyzbar

# Existing local modules (must be present in same folder)
from input_handler import InputHandler
from led_controller import LEDController

# Logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("QRSpot")

# Global running flag (signal handler sets False)
running = True
def handle_signal(sig, frame):
    global running
    log.info(f"Signal {sig} received — shutting down gracefully.")
    running = False

signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)

# --- LED setup (your pins may differ) ---
RED_PIN = int(os.getenv("LED_RED_PIN", 22))
GREEN_PIN = int(os.getenv("LED_GREEN_PIN", 18))
led = LEDController(red_pin=RED_PIN, green_pin=GREEN_PIN, active_high=True)
led.set_state("OFF")

# --- Simple Token Manager per account ---
class TokenManager:
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
        log.info(f"{datetime.now():%Y-%m-%d %H:%M:%S} Token refreshed for client {self.client_id[:6]}..., expires at {time.ctime(self.expires_at)}")

    def get_access_token(self):
        if not self.access_token or time.time() >= self.expires_at:
            self.refresh_access_token()
        return self.access_token

# --- SpotifyControls class to match InputHandler expectations ---
class SpotifyControls:
    def __init__(self, accounts, device_id=None):
        """
        accounts: list of dicts {name, client_id, client_secret, refresh_token}
        device_id: device id string for the Pi (optional)
        """
        self.accounts = []
        for a in accounts:
            tm = TokenManager(a["client_id"], a["client_secret"], a["refresh_token"])
            self.accounts.append({
                "name": a["name"],
                "tm": tm
            })
        self.device_id = device_id or os.getenv("PI_DEVICE_ID", None)
        # spotipy is imported lazily where needed to avoid needing spotipy on systems that don't have it installed
        try:
            import spotipy
            self._spotipy = spotipy
        except Exception:
            self._spotipy = None

    def _client_for(self, account):
        token = account["tm"].get_access_token()
        return self._spotipy.Spotify(auth=token)

    def _normalize_spotify_url(self, url):
        url = url.strip()
        if "?" in url:
            url = url.split("?", 1)[0]
        if url.startswith("spotify:"):
            return url
        if "open.spotify.com" in url:
            parts = url.replace("https://open.spotify.com/", "").split("/")
            if len(parts) >= 2:
                return f"spotify:{parts[0]}:{parts[1]}"
        return url

    # --- availability check ---
    def is_account_active_elsewhere(self, account):
        """
        Returns True if account is playing on a device that is NOT the Pi device_id.
        """
        try:
            sp = self._client_for(account)
            playback = sp.current_playback()
            if not playback:
                return False
            device = playback.get("device", {}) or {}
            is_playing = playback.get("is_playing", False)
            dev_id = device.get("id")
            # If playing and device id is not our device => active elsewhere
            if is_playing and (self.device_id is None or dev_id != self.device_id):
                return True
            return False
        except Exception as e:
            log.warning(f"Could not check playback for {account['name']}: {e}")
            return False

    # --- play a normalized URI on Pi device for the given account ---
    def play_on_account(self, account, normalized_uri):
        try:
            sp = self._client_for(account)
            if self.device_id:
                if normalized_uri.startswith("spotify:track:") or normalized_uri.startswith("spotify:episode:"):
                    sp.start_playback(device_id=self.device_id, uris=[normalized_uri])
                else:
                    sp.start_playback(device_id=self.device_id, context_uri=normalized_uri)
            else:
                # no explicit device: start playback (Spotify will pick)
                if normalized_uri.startswith("spotify:track:") or normalized_uri.startswith("spotify:episode:"):
                    sp.start_playback(uris=[normalized_uri])
                else:
                    sp.start_playback(context_uri=normalized_uri)
            return True
        except Exception as e:
            log.error(f"Playback error for {account['name']}: {e}")
            return False

    # --- metadata fetch ---
    def fetch_metadata(self, normalized_uri):
        for account in self.accounts:
            try:
                sp = self._client_for(account)
                if normalized_uri.startswith("spotify:track:"):
                    t = sp.track(normalized_uri)
                    return {"type":"track","name":t["name"], "artists": ", ".join([a["name"] for a in t["artists"]]), "album": t["album"]["name"]}
                if normalized_uri.startswith("spotify:playlist:"):
                    p = sp.playlist(normalized_uri)
                    return {"type":"playlist","name":p["name"], "owner": p["owner"]["display_name"], "num_tracks": p["tracks"]["total"]}
                if normalized_uri.startswith("spotify:album:"):
                    a = sp.album(normalized_uri)
                    return {"type":"album","name":a["name"], "artist": ", ".join([ar["name"] for ar in a["artists"]])}
            except Exception:
                continue
        return {"type":"unknown","name":normalized_uri}

    # --- methods InputHandler expects ---
    def volume_delta(self, delta):
        # Adjust volume on whichever account is currently controlling the Pi (best-effort)
        for account in self.accounts:
            try:
                sp = self._client_for(account)
                sp.volume(delta, device_id=self.device_id)  # delta is absolute in some APIs; if fails you can read current and set
                return
            except Exception:
                continue

    def next_track(self):
        for account in self.accounts:
            try:
                sp = self._client_for(account)
                sp.next_track(device_id=self.device_id)
                return
            except Exception:
                continue

    def previous_track(self):
        for account in self.accounts:
            try:
                sp = self._client_for(account)
                sp.previous_track(device_id=self.device_id)
                return
            except Exception:
                continue

    def restart_track(self):
        # Seek to 0 on play
        for account in self.accounts:
            try:
                sp = self._client_for(account)
                sp.seek_track(0, device_id=self.device_id)
                return
            except Exception:
                continue

    def toggle_play_pause(self):
        for account in self.accounts:
            try:
                sp = self._client_for(account)
                playback = sp.current_playback()
                if playback and playback.get("is_playing", False):
                    sp.pause_playback(device_id=self.device_id)
                else:
                    sp.start_playback(device_id=self.device_id)
                return
            except Exception:
                continue

    # --- convenience: iterate accounts in preferred order (BEN then N) ---
    def get_accounts_in_order(self):
        return self.accounts  # already constructed in order caller provides

# --- Build account list from environment ---
def make_accounts_from_env():
    pairs = []
    for label in ("BEN", "N"):
        cid = os.getenv(f"SPOTIFY_CLIENT_ID_{label}")
        csec = os.getenv(f"SPOTIFY_CLIENT_SECRET_{label}")
        rtk = os.getenv(f"SPOTIFY_REFRESH_TOKEN_{label}")
        name = label.lower()
        if not (cid and csec and rtk):
            raise RuntimeError(f"Missing credentials for {label} in .env")
        pairs.append({"name": name, "client_id": cid, "client_secret": csec, "refresh_token": rtk})
    return pairs

accounts = make_accounts_from_env()
PI_DEVICE_ID = os.getenv("PI_DEVICE_ID", None)

# Create controls and hook to InputHandler
sp_controls = SpotifyControls(accounts, device_id=PI_DEVICE_ID)
input_handler = InputHandler(sp_controls)
input_handler.start()
log.info("InputHandler started")

# Camera init
picam2 = Picamera2()
picam2.start()
log.info("Camera started")

# Helper: normalize url and decide account
def normalise_spotify_url(url: str) -> str:
    url = url.strip()
    if "?" in url:
        url = url.split("?", 1)[0]
    if url.startswith("spotify:"):
        return url
    if "open.spotify.com" in url:
        parts = url.replace("https://open.spotify.com/", "").split("/")
        if len(parts) >= 2:
            return f"spotify:{parts[0]}:{parts[1]}"
    return url

def find_first_free_account():
    """
    Returns (account_dict, manager) for first free account (in configured order).
    If none free, returns (None, None).
    """
    for account in sp_controls.get_accounts_in_order():
        try:
            if not sp_controls.is_account_active_elsewhere(account):
                return account, account["tm"]
        except Exception as e:
            log.warning(f"Availability check error for {account['name']}: {e}")
    return None, None

# Main loop
log.info("Ready — scanning for QR codes. Press Ctrl+C to stop.")
frame_count = 0
try:
    while running:
        frame = picam2.capture_array()
        frame_count += 1

        # Basic sanity: ensure frame non-empty occasionally
        if frame_count % 50 == 0:
            import numpy as np
            if not np.any(frame):
                log.warning("Captured blank frame!")

        decoded = pyzbar.decode(frame)
        if decoded:
            url = decoded[0].data.decode("utf-8")
            log.info(f"QR detected: {url}")
            led.set_state("RED_SOLID")  # indicate processing

            # Resolve redirects
            final = url
            try:
                r = requests.head(url, allow_redirects=True, timeout=5)
                final = r.url
            except Exception as e:
                log.warning(f"Could not resolve URL: {e}")

            normalized = normalise_spotify_url(final)
            # find free account
            account, manager = find_first_free_account()
            if account:
                log.info(f"Playing via account: {account['name']}")
                led.set_state("GREEN_SOLID")
                # attempt play
                success = sp_controls.play_on_account(account, normalized)
                if not success:
                    log.error("Playback failed, setting RED_BLINK")
                    led.set_state("RED_BLINK")
            else:
                # both busy -> fetch metadata and hand to VLC placeholder
                meta = sp_controls.fetch_metadata(normalized)
                log.info(f"Both accounts busy — metadata: {meta}")
                led.set_state("RED_SOLID")
                # TODO: send this metadata to your VLC script (e.g. via socket or file)
        # Sleep to avoid pegging CPU
        time.sleep(0.2)

except Exception as e:
    log.exception(f"Unhandled exception in main loop: {e}")

finally:
    log.info("Shutting down — cleaning up subsystems")
    try:
        input_handler.stop()
    except Exception as e:
        log.warning(f"Error stopping input handler: {e}")
    try:
        picam2.stop()
    except Exception as e:
        log.warning(f"Error stopping camera: {e}")
    try:
        # your led_controller.py provides cleanup() in earlier versions; call whichever you have
        if hasattr(led, "stop"):
            led.stop()
        elif hasattr(led, "cleanup"):
            led.cleanup()
        else:
            # best-effort
            try:
                led.set_state("OFF")
            except Exception:
                pass
    except Exception as e:
        log.warning(f"Error stopping LEDs: {e}")
    log.info("Cleanup complete. Exiting.")
    sys.exit(0)
