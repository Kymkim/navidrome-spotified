#Weekly Tasks (i.e. custom playlist and stuff)
from app import app, db, User
from cryptography.fernet import Fernet
import requests

import os
key = os.environ["PW_KEY"]
AUDIOMUSE_URL = os.environ["AUDIOMUSE_URL"]
NAVIDROME_URL = os.environ["NAVIDROME_URL"]

from ENVARS import key

def sonicPlaylist():
    users = User.query.all()
    for user in users:
        cipher = Fernet(key)

        # Request to the API with 12 sonically similar songs
        params = {
            "n": 30,
            "navidrome_user": user.username,
            "navidrome_password": cipher.decrypt(user.password).decode("utf-8")
        }
        response = requests.get(AUDIOMUSE_URL+"/sonic_fingerprint/generate", params=params)

        match response.status_code:

            #Create Playlist
            case 200:
                #Store Suggested Tracks
                tracks = response.json()

                song_ids = []
                for track in tracks:
                    song_ids.append(track["item_id"])
                print(song_ids)

                #Change existing playlist if it already exists
                if user.sonic_album_id == "NONE":
                    params = {
                        "u": user.username,
                        "p": cipher.decrypt(user.password).decode("utf-8"),
                        "v": "1.16.1",
                        "c": "spotified",
                        "name": "Weekly: Sonic Fingerprint",
                        "songId": song_ids,
                        "f": "json"
                    }
                else:
                    params = {
                        "u": user.username,
                        "p": cipher.decrypt(user.password).decode("utf-8"),
                        "v": "1.16.1",
                        "c": "spotified",
                        "playlistId": user.sonic_album_id,
                        "songId": song_ids,
                        "f": "json"
                    }

                response = requests.get(NAVIDROME_URL+"/createPlaylist.view", params=params)
                data = response.json()
                print(data["subsonic-response"])
                user.sonic_album_id = data["subsonic-response"]["playlist"]["id"]
                db.session.commit()
                
            case 400:
                print("Bad request")
            case 500:
                print("Server Error")
        

def artistPlaylist():
    pass

def songPlaylist():
    pass

if __name__ == "__main__":
    with app.app_context():
        sonicPlaylist()
        artistPlaylist()
        songPlaylist()