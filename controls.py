# controls.py
"""
Spotify playback & volume control wrappers.

Usage:
    from controls import SpotifyControls
    spc = SpotifyControls(spotipy_client, device_id)
    spc.volume_delta(+10)
    spc.next_track()
    spc.restart_or_previous()   # handles single vs double-press semantics if you want to
    spc.toggle_play_pause()
"""

import time
import logging

logger = logging.getLogger("controls")
logging.basicConfig(level=logging.INFO)

class SpotifyControls:
    def __init__(self, sp, device_id=None, double_press_window=0.4):
        """
        sp: a spotipy.Spotify instance already authenticated with
            the 'user-modify-playback-state' scope.
        device_id: optional Spotify Connect device id to target. If None,
                   requests will omit device_id (Spotify will choose).
        double_press_window: seconds allowed between presses to count as double-press.
        """
        self.sp = sp
        self.device_id = device_id
        self.double_press_window = double_press_window
        self._last_prev_press = 0.0
        # cached playing state (True=playing, False=paused, None=unknown)
        self._is_playing = None
        # cached volume (0-100) - initialize lazily
        self._volume = None

    def _device_kw(self):
        return {"device_id": self.device_id} if self.device_id else {}

    def _safe_call(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            logger.exception("Spotify API call failed: %s", e)
            return None

    def refresh_state(self):
        """Fetch current playback state and volume from Spotify (best-effort)."""
        try:
            state = self.sp.current_playback()
            if state:
                self._is_playing = state.get("is_playing", None)
                # may be None if no device
                device = state.get("device", {})
                self._volume = device.get("volume_percent", None)
                logger.debug("Refreshed playback state: playing=%s volume=%s", self._is_playing, self._volume)
            else:
                self._is_playing = None
                self._volume = None
            return state
        except Exception as e:
            logger.exception("Failed to refresh playback state: %s", e)
            self._is_playing = None
            self._volume = None
            return None

    def set_volume(self, percent):
        """Set volume to a specific percent (0-100)."""
        percent = max(0, min(100, int(percent)))
#        logger.info("Setting volume to %s%% (device=%s)", percent, self.device_id)

        self._safe_call(self.sp.volume, percent, **self._device_kw())
        self._volume = percent

    def volume_delta(self, delta_percent):
        """Change volume by delta_percent (positive or negative)."""
        # try to use cached value if present
        if self._volume is None:
            self.refresh_state()
        if self._volume is None:
            # fallback: just set to delta relative to 50
            new_v = max(0, min(100, 50 + int(delta_percent)))
        else:
            new_v = max(0, min(100, int(self._volume) + int(delta_percent)))
        logger.info("Changing volume by %s -> %s%%", delta_percent, new_v)
        self.set_volume(new_v)

    def pause(self):
        logger.info("Pausing playback ")
        self._safe_call(self.sp.pause_playback, **self._device_kw())
        self._is_playing = False

    def resume(self):
        logger.info("Resuming playback ")
        # start_playback may need additional args; this will resume where available
        self._safe_call(self.sp.start_playback, **self._device_kw())
        self._is_playing = True

    def toggle_play_pause(self):
        # If we don't know state, try to fetch it
        if self._is_playing is None:
            self.refresh_state()
        if self._is_playing:
            self.pause()
        else:
            self.resume()

    def next_track(self):
#        logger.info("Skipping to next track (device=%s)", self.device_id)
        self._safe_call(self.sp.next_track, **self._device_kw())
        # We assume playback is still playing after a skip
        self._is_playing = True

    def previous_track(self):
#        logger.info("Skipping to previous track (device=%s)", self.device_id)
        self._safe_call(self.sp.previous_track, **self._device_kw())
        self._is_playing = True

    def seek_start(self):
#        logger.info("Seeking to start of track (device=%s)", self.device_id)
        # seek to 0ms
        self._safe_call(self.sp.seek_track, 0, **self._device_kw())
        self._is_playing = True

 #   def restart_or_previous(self):
    def restart_track(self):
        """
        If called once: restart track (seek to 0).
        If called twice within double_press_window -> previous_track.
        Return 'restart' or 'previous' depending on what happened.
        """
        now = time.time()
        dt = now - self._last_prev_press
        logger.debug("restart_or_previous called, dt=%s", dt)
        if dt <= self.double_press_window:
            # treat as double-press -> previous track
#            logger.info("Detected double-press -> previous track")
            self.previous_track()
            self._last_prev_press = 0.0
            return "previous"
        else:
            # single-press -> restart
#            logger.info("Single press -> restart current track")
            self.seek_start()
            self._last_prev_press = now
            return "restart"
