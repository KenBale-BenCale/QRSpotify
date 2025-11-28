import spotipy
from spotipy.oauth2 import SpotifyOAuth

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id="c129514435024e23bf9ed5e843b5a6c0",
    client_secret="a8cab539d11d4fb794e96130ad21f642",
    redirect_uri="http://127.0.0.1:8888/callback",
    scope="user-modify-playback-state,user-read-playback-state"
))

devices = sp.devices()
for d in devices['devices']:
    print(d['name'], d['id'], d['is_active'])
