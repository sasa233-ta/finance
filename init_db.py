from app import create_app
from app.auth.models import db, User
from app.stocks.models import Stock
from app.auth.utils import hash_password


def init_db():
    app = create_app()
    with app.app_context():
        # create only user and stock tables
        db.metadata.create_all(bind=db.engine, tables=[User.__table__, Stock.__table__])
        # seed sample users
        if not User.query.filter_by(username='adminuser').first():
            admin = User(username='adminuser', email='admin@example.com', password_hash=hash_password('adminpass'), role='admin')
            db.session.add(admin)
        if not User.query.filter_by(username='paiduser').first():
            paid = User(username='paiduser', email='paid@example.com', password_hash=hash_password('paidpass'), role='paid')
            db.session.add(paid)
        db.session.commit()
        print('DB initialized: ensured user and stock tables, seeded sample users')


if __name__ == '__main__':
    init_db()
