

from app import create_app
from app.auth.models import db, User
from app.stocks.models import Stock
from app.auth.utils import hash_password
from flask_migrate import Migrate
import os


app = create_app()

# Initialize extensions
db.init_app(app)
migrate = Migrate(app, db)


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
        db.create_all()
        create_sample_users()
    app.run(debug=True)
