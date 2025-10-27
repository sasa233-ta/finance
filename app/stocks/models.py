
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


class RiseProbabilitySummary(db.Model):
    """Single-row per stock storing latest rise probabilities from multiple models.

    Managed by stock_code (unique) rather than numeric stock_id.
    Columns:
      - stock_code: Stock.code (unique)
      - prob_model1 .. prob_model4: floats in [0,1]
      - updated_at: last update timestamp
    """
    __tablename__ = 'rise_probability_summary'

    # use stock_code as the primary key (no separate numeric id)
    stock_code = db.Column(db.String(8), primary_key=True, nullable=False)
    prob_model1 = db.Column(db.Float)
    prob_model2 = db.Column(db.Float)
    prob_model3 = db.Column(db.Float)
    prob_model4 = db.Column(db.Float)
    # AUC scores for each model (optional, may be null)
    auc_model1 = db.Column(db.Float)
    auc_model2 = db.Column(db.Float)
    auc_model3 = db.Column(db.Float)
    auc_model4 = db.Column(db.Float)
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now(), nullable=False)

    def __repr__(self):
        return f'<RiseProbabilitySummary {self.stock_code} m1={self.prob_model1} m2={self.prob_model2}>'
