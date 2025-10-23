from .models import User, db
from .utils import hash_password, verify_password

def register_user(username, email, password, role='free'):
    hashed_pw = hash_password(password)
    user = User(username=username, email=email, password_hash=hashed_pw, role=role)
    db.session.add(user)
    db.session.commit()
    return user

def authenticate_user(username, password):
    user = User.query.filter_by(username=username).first()
    if user and verify_password(user.password_hash, password):
        return user
    return None
