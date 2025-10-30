
from app import create_app
from app.auth.models import db, User
from app.stocks.models import Stock
from app.auth.utils import hash_password
import os

app = create_app()

# create_app() initializes extensions (db.init_app) so don't call it again here

def create_sample_users():
    users = [
        {"username": "paiduser", "email": "paid@example.com", "password": "paidpass", "role": "paid"},
        {"username": "adminuser", "email": "admin@example.com", "password": "adminpass", "role": "admin"}
    ]
    for u in users:
        if not User.query.filter_by(username=u["username"]).first():
            user = User(
                username=u["username"],
                email=u["email"],
                password_hash=hash_password(u["password"]),
                role=u["role"]
            )
            db.session.add(user)
    db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        # Ensure only the User and Stock tables are created when running run.py
        print('Creating user and stock tables (if not exist)...')
        # Use metadata.create_all to create specific tables
        db.metadata.create_all(bind=db.engine, tables=[User.__table__, Stock.__table__])
        print('Tables ensured. Seeding sample users...')
        create_sample_users()
    app.run(debug=True)
