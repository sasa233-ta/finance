
from app.auth.models import db

class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(8), unique=True, nullable=False)
    name = db.Column(db.String(128), nullable=False)
    name_normalized = db.Column(db.String(128))
    date = db.Column(db.String(16))
    market = db.Column(db.String(64))
    sector33_code = db.Column(db.String(8))
    sector33 = db.Column(db.String(64))
    sector17_code = db.Column(db.String(8))
    sector17 = db.Column(db.String(64))
    scale_code = db.Column(db.String(8))
    scale = db.Column(db.String(32))
    is_listed = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<Stock {self.code} {self.name}>'
