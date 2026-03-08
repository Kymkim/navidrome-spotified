import os
import requests
from flask import Flask, request, render_template, flash
from flask_sqlalchemy import SQLAlchemy
from cryptography.fernet import Fernet
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.ext.mutable import MutableDict

# --- Environment & app setup ---
CIPHER_KEY = os.environ.get("CIPHER_KEY")
if not CIPHER_KEY:
    raise RuntimeError("CIPHER_KEY environment variable is not set!")
AUDIOMUSE_URL = os.environ["AUDIOMUSE_URL"]
NAVIDROME_URL = os.environ["NAVIDROME_URL"]

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "supersecret")  # for flash messages

db = SQLAlchemy(app)
cipher = Fernet(CIPHER_KEY)

# --- Database model ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    generated_albums = db.Column(MutableDict.as_mutable(db.JSON), default=dict)

with app.app_context():
    db.create_all()


# --- Routes ---
@app.route("/login", methods=["GET", "POST"])
def login():
    """
    User login route.
    Stores encrypted credentials in the database.
    TODO: Validate credentials against Navidrome API.
    """
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username or not password:
            flash("Missing username or password")
            return render_template("login.html")

        encoded_password = cipher.encrypt(password.encode())
        user = User.query.filter_by(username=username).first()

        if not user:
            user = User(username=username, password=encoded_password)
            db.session.add(user)
        else:
            user.password = encoded_password

        db.session.commit()
        flash("Credentials saved successfully!")

    return render_template("login.html")


# --- Scheduler setup ---
def daily_task():
    with app.app_context():
        dailyMix()

# --- Helper Functions ---
import requests
def makePlaylist(user, songs, name=None, playlist_id=None):
    """
    Create or update a playlist for a user.

    Args:
        user (User): The user who owns the playlist.
        songs (list): List of song IDs to add.
        name (str, optional): Name for a new playlist.
        playlist_id (str, optional): ID of an existing playlist to update.

    Returns:
        dict | None: API response JSON if successful, otherwise None.
    """

    playlist_params = {
        "u": user.username,
        "p": cipher.decrypt(user.password).decode("utf-8"),
        "v": "1.16.1",
        "c": "spotified",
        "f": "json",
        "songId": songs
    }

    # determine create vs update
    if playlist_id:
        playlist_params["playlistId"] = playlist_id
        action = "updating"
    elif name:
        playlist_params["name"] = name
        action = "creating"
    else:
        raise ValueError("Either 'name' or 'playlist_id' must be provided.")

    response = requests.get(
        f"{NAVIDROME_URL}/createPlaylist.view",
        params=playlist_params
    )

    json_res=response.json()
    if json_res["subsonic-response"]["status"] == "failed":
        print(f"Error {action} playlist for {user.username}")
        return None

    print("Playlist made/updated!")
    return json_res


# --- Playlist Generations ---
def dailyMix():
    users = User.query.all()

    for user in users:
        print(f"----- MAKING DAILY MIX PLAYLIST FOR USER {user.username} ------")
        password = cipher.decrypt(user.password).decode("utf-8")

        # Request playlist based on user sonic fingerprint
        params = {
            "n": 30,
            "navidrome_user": user.username,
            "navidrome_password": password
        }

        try:
            response = requests.get(f"{AUDIOMUSE_URL}/sonic_fingerprint/generate", params=params)
        except(requests.RequestException, KeyError, ValueError) as e:
            print(f"Error ({e}) generating playlist for {user.username}")
            continue
            
        tracks = response.json()
        song_ids = [track["item_id"] for track in tracks]

        #Check if user has an existing Sonic Playlist already.
        #Make a new playlist if does not exist.
        #Update if it already exists
        albums = user.generated_albums or {}
        dailyMixID = albums.get("dailyMix")
        if dailyMixID is None:
            print("No existing playlist... making a new Your Daily Mix!")
            makeRes = makePlaylist(user, song_ids, name="Your Daily Mix!")
            if makeRes is None:
                print(f"Failed making playlist for {user}")
            else:
                user.generated_albums["dailyMix"] = makeRes["subsonic-response"]["playlist"]["id"]
                db.session.commit()
                print(f"Playlist info updated for {user.username}")
        else:
            print("Existing playlist found! Attempting to update...")
            makeRes = makePlaylist(user, song_ids, playlist_id=dailyMixID)
            #Update failed. Try making a new playlist            
            if makeRes is None:
                print("Update failed! Making a new one!")
                retry = makePlaylist(user, song_ids, name="Your Daily Mix!")
                if retry is None:
                    print(f"Failed retrying making a new playlist... CHECK THE DATABASE")
                else:
                    user.generated_albums["dailyMix"] = retry["subsonic-response"]["playlist"]["id"]
                    db.session.commit()
                    print(f"Playlist info updated for {user.username}")

# --- App entry point ---
if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.add_job(daily_task, 'cron', hour="0")  # Runs every day
    scheduler.start()
    app.run(host="0.0.0.0", port=5000)