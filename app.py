import os
import requests
from flask import Flask, request, render_template, flash
from flask_sqlalchemy import SQLAlchemy
from cryptography.fernet import Fernet
from apscheduler.schedulers.background import BackgroundScheduler

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
    sonic_album_id = db.Column(db.String(200), nullable=False, default="NONE")


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
            user = User(username=username, password=encoded_password, sonic_album_id="NONE")
            db.session.add(user)
        else:
            user.password = encoded_password

        db.session.commit()
        flash("Credentials saved successfully!")

    return render_template("login.html")


# --- Scheduler setup ---
def weekly_task():
    with app.app_context():
        sonicPlaylist()

def sonicPlaylist():
    """Generate and update the weekly playlist for all users."""
    users = User.query.all()

    for user in users:
        print(f"----- MAKING PLAYLIST FOR USER {user.username} ------")
        try:
            password = cipher.decrypt(user.password).decode("utf-8")
        except Exception as e:
            print(f"Error decrypting password for {user.username}: {e}")
            continue

        # Request similar tracks from Audomuse API
        params = {
            "n": 30,
            "navidrome_user": user.username,
            "navidrome_password": password
        }

        try:
            response = requests.get(f"{AUDIOMUSE_URL}/sonic_fingerprint/generate", params=params)
        except requests.RequestException as e:
            print(f"Error requesting sonic fingerprint for {user.username}: {e}")
            continue

        if response.status_code != 200:
            print(f"Error ({response.status_code}) generating playlist for {user.username}")
            continue

        try:
            tracks = response.json()
        except ValueError:
            print(f"Invalid JSON response for {user.username}")
            continue

        song_ids = [track["item_id"] for track in tracks]

        # Prepare parameters for creating/updating playlist
        playlist_params = {
            "u": user.username,
            "p": password,
            "v": "1.16.1",
            "c": "spotified",
            "f": "json",
            "songId": song_ids
        }

        if user.sonic_album_id == "NONE":
            playlist_params["name"] = "Your Epic Daily Mix - TESTING"
        else:
            playlist_params["playlistId"] = user.sonic_album_id

        # Call Navidrome to create/update the playlist
        try:
            nav_response = requests.get(f"{NAVIDROME_URL}/createPlaylist.view", params=playlist_params)
            nav_data = nav_response.json()
            user.sonic_album_id = nav_data["subsonic-response"]["playlist"]["id"]
            db.session.commit()
            print(f"Playlist updated for {user.username}")
        except (requests.RequestException, KeyError, ValueError) as e:
            print(f"Error updating playlist for {user.username}: {e}")



# --- App entry point ---
if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.add_job(weekly_task, 'cron', hour="0", minute="0")  # Runs every day
    scheduler.start()
    app.run(host="0.0.0.0", port=5000)