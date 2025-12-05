# spotify_controls.py
import spotipy
import requests
import base64
from datetime import datetime

class SpotifyControls:
    """
    Manages Spotify playback for up to two accounts on a static device.
    - Checks if an account is active elsewhere
    - Plays QR-scanned tracks if account is free
    - Fetches track metadata if account is busy
    """

    def __init__(self, accounts, device_id):
        """
        accounts: list of dicts [{client_id, client_secret, refresh_token, name}, ...]
        device_id: device ID of Pi to force playback to
        """
        self.accounts = accounts
        self.device_id = device_id
        self.sp_clients = [self._make_sp_client(acc) for acc in accounts]

    def _make_sp_client(self, acc):
        token = self._refresh_token(acc)
        return spotipy.Spotify(auth=token)

    def _refresh_token(self, acc):
        """Use refresh token flow to get new access token"""
        auth_header = base64.b64encode(f"{acc['client_id']}:{acc['client_secret']}".encode()).decode()
        r = requests.post(
            "https://accounts.spotify.com/api/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": acc["refresh_token"]
            },
            headers={"Authorization": f"Basic {auth_header}"}
        )
        r.raise_for_status()
        token_info = r.json()
        return token_info["access_token"]

    def is_active_elsewhere(self, sp):
        """Returns True if this account is playing on a device that is not our Pi"""
        playback = sp.current_playback()
        if not playback:
            return False
        device = playback.get("device", {})
        # If playing somewhere else, return True
        return device.get("id") != self.device_id and playback.get("is_playing", False)

    def play_qr(self, url):
        """
        Tries each account in order:
            - If account free, plays URL on Pi device
            - If all accounts busy, returns metadata
        Returns (played, metadata)
            played: True if playback started
            metadata: dict with track info if not played
        """
        normalized = self._normalize_spotify_url(url)
        for sp, acc in zip(self.sp_clients, self.accounts):
            try:
                if not self.is_active_elsewhere(sp):
                    if normalized.startswith("spotify:track:") or normalized.startswith("spotify:episode:"):
                        sp.start_playback(device_id=self.device_id, uris=[normalized])
                    else:
                        sp.start_playback(device_id=self.device_id, context_uri=normalized)
                    return True, None
            except Exception as e:
                print(f"{datetime.now()},Error with account {acc['name']}: {e}")
                continue

        # All accounts busy, fetch metadata for VLC
        return False, self.get_track_metadata(normalized)

    def get_track_metadata(self, normalized_url):
        """Fetch basic metadata from a Spotify URL"""
        for sp in self.sp_clients:
            try:
                if normalized_url.startswith("spotify:track:"):
                    track = sp.track(normalized_url)
                    return {
                        "name": track["name"],
                        "artists": ", ".join([a["name"] for a in track["artists"]]),
                        "album": track["album"]["name"]
                    }
                elif normalized_url.startswith("spotify:playlist:"):
                    playlist = sp.playlist(normalized_url)
                    return {
                        "name": playlist["name"],
                        "owner": playlist["owner"]["display_name"],
                        "num_tracks": playlist["tracks"]["total"]
                    }
            except:
                continue
        return {"name": "Unknown", "artists": "", "album": ""}

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
