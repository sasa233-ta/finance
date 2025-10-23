from flask_sqlalchemy import SQLAlchemy

# single SQLAlchemy instance used by the app
db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    # use Text to allow long password hashes (scrypt/argon2 etc.)
    password_hash = db.Column(db.Text, nullable=False)
    role = db.Column(db.String(20), nullable=False, default='free')  # free, paid, admin

    def __repr__(self):
        return f'<User {self.username}>'
