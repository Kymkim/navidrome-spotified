from flask import Flask, request, render_template
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import ARRAY
from cryptography.fernet import Fernet

import os
key = os.environ["PW_KEY"]

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    sonic_album_id = db.Column(db.String(200), nullable=False)

with app.app_context():
    db.create_all()

#API call to login the user. Store the login credetials to the database
#Must use the Navidrome API to check if the login credentials are valid
#Passwords need to be hashed
@app.route("/login", methods=["GET", "POST"])
def login():
    
    #Handle login by hashing
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username or not password:
            flash("Missing username or password")
            return render_template("login.html")

        #TODO: Try logging in first to navidrome to make sure user account is valid

        #Update database with the credentials
        user = User.query.filter_by(username=username).first()
        cipher = Fernet(key)
        encoded_password = cipher.encrypt(password.encode())

        #If user does not exist...
        if not user:
            user = User(username=username, password=encoded_password, sonic_album_id="NONE")
            db.session.add(user)
        else: #Otherwise, update the password hash
            user.password = encoded_password

        db.session.commit()

    return render_template("login.html")


if __name__ == "__main__":
    app.run(debug=True)