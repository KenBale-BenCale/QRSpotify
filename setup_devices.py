#!/usr/bin/env python3
import json
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os

os.environ["SPOTIPY_CLIENT_ID"] = "c129514435024e23bf9ed5e843b5a6c0"
os.environ["SPOTIPY_CLIENT_SECRET"] ="a8cab539d11d4fb794e96130ad21f642"
os.environ["SPOTIPY_REDIRECT_URI"] = "http://127.0.0.1:8888/callback"

PRIORITY_FILE = "device_priority.json"

def get_devices(sp):
    """Return a list of available Connect devices."""
    devices = sp.devices().get("devices", [])
    return devices


def choose_priority(devices):
    """Ask user to select device priority order."""
    print("\nAvailable Spotify Devices:\n")
    for i, dev in enumerate(devices):
        print(f"{i+1}. {dev['name']}  ({dev['type']})")

    print("\nEnter device numbers in the priority order you want.")
    print("Example: 2 1 3")

    while True:
        user_input = input("\nPriority order: ").strip()
        try:
            indices = list(map(int, user_input.split()))
            if any(i < 1 or i > len(devices) for i in indices):
                raise ValueError
            break
        except ValueError:
            print("Invalid input. Enter numbers like: 2 1 3")

    # Create ordered list of device *names* (not IDs)
    ordered_devices = [devices[i-1]["name"] for i in indices]
    return ordered_devices


def save_priority(priority_list):
    """Save priority list to a JSON file."""
    with open(PRIORITY_FILE, "w") as f:
        json.dump({"priority": priority_list}, f, indent=4)
    print(f"\nSaved priority list to {PRIORITY_FILE}")


def main():
    print("=== Spotify Device Priority Setup ===")

    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope="user-read-playback-state"))

    devices = get_devices(sp)
    if not devices:
        print("No Spotify Connect devices found.")
        return

    priority = choose_priority(devices)
    save_priority(priority)

    print("\nSetup complete. Device priority saved.\n")


if __name__ == "__main__":
    main()
