def normalize_for_search(text):
    if not text:
        return ''
    import unicodedata
    text_nfkc = unicodedata.normalize("NFKC", text)
    def z2h_alpha(c):
        if 'Ａ' <= c <= 'Ｚ':
            return chr(ord(c) - 0xFEE0)
        if 'ａ' <= c <= 'ｚ':
            return chr(ord(c) - 0xFEE0)
        return c
    return ''.join([z2h_alpha(c) for c in text_nfkc])
import os
import unicodedata
import pandas as pd
import requests
from datetime import datetime
from app.auth.models import db
from app.stocks.models import Stock, RiseProbabilitySummary

JPX_XLS_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../data'))
XLS_PATH = os.path.join(DATA_DIR, 'jpx_listed_companies.xls')
TIMESTAMP_PATH = XLS_PATH + '.timestamp'


def fetch_and_update_stocks():
    today = datetime.now().strftime('%Y-%m-%d')
    os.makedirs(DATA_DIR, exist_ok=True)
    # 1日1回のみダウンロード
    if os.path.exists(XLS_PATH) and os.path.exists(TIMESTAMP_PATH) and open(TIMESTAMP_PATH, encoding='utf-8').read().strip() == today:
        pass
    else:
        r = requests.get(JPX_XLS_URL)
        r.raise_for_status()
        with open(XLS_PATH, 'wb') as f:
            f.write(r.content)
        with open(TIMESTAMP_PATH, 'w', encoding='utf-8') as f:
            f.write(today)
    # Excel→DB投入
    df = pd.read_excel(XLS_PATH, dtype=str)
    colmap = {
        "date": "日付",
        "code": "コード",
        "name": "銘柄名",
        "market": "市場・商品区分",
        "sector33_code": "33業種コード",
        "sector33": "33業種区分",
        "sector17_code": "17業種コード",
        "sector17": "17業種区分",
        "scale_code": "規模コード",
        "scale": "規模区分"
    }
    stocks = []
    for _, row in df.iterrows():
        code = row.get(colmap["code"])
        if code and code.isdigit() and len(code) == 4:
            code = code + ".T"
        name = row.get(colmap["name"])
        # NFKC正規化＋全角英字を半角英字に
        if name:
            name_nfkc = unicodedata.normalize("NFKC", name)
            # 全角英字→半角英字
            def z2h_alpha(c):
                if 'Ａ' <= c <= 'Ｚ':
                    return chr(ord(c) - 0xFEE0)
                if 'ａ' <= c <= 'ｚ':
                    return chr(ord(c) - 0xFEE0)
                return c
            name_normalized = ''.join([z2h_alpha(c) for c in name_nfkc])
        else:
            name_normalized = None
        stocks.append(Stock(
            code=code,
            name=name,
            name_normalized=name_normalized,
            date=row.get(colmap["date"]),
            market=row.get(colmap["market"]),
            sector33_code=row.get(colmap["sector33_code"]),
            sector33=row.get(colmap["sector33"]),
            sector17_code=row.get(colmap["sector17_code"]),
            sector17=row.get(colmap["sector17"]),
            scale_code=row.get(colmap["scale_code"]),
            scale=row.get(colmap["scale"]),
            is_listed=True
        ))
    db.session.query(Stock).delete()
    db.session.bulk_save_objects(stocks)
    db.session.commit()
    return len(stocks)


def update_or_create_rise_probs(stock_code: str, probs: dict):
    """Upsert rise probability summary for `stock_code`.

    `probs` expected keys: 'model1','model2','model3','model4' (values convertible to float).
    Returns (True, obj) on success, (False, message) on error.
    """
    stock = Stock.query.filter_by(code=stock_code).first()
    if not stock:
        return False, f'stock not found: {stock_code}'

    try:
        # manage by stock_code instead of numeric stock_id
        row = RiseProbabilitySummary.query.filter_by(stock_code=stock.code).first()
        if not row:
            row = RiseProbabilitySummary(stock_code=stock.code)
            db.session.add(row)

        # set provided probabilities (ignore missing keys)
        for key in ('model1', 'model2', 'model3', 'model4'):
            val = probs.get(key)
            if val is not None:
                setattr(row, f'prob_{key}', float(val))

        # set provided AUC scores if present
        for key in ('model1', 'model2', 'model3', 'model4'):
            auc_key = f'auc_{key}'
            auc_val = probs.get(auc_key)
            if auc_val is not None:
                try:
                    setattr(row, f'auc_{key}', float(auc_val))
                except Exception:
                    # ignore invalid auc values
                    pass

        db.session.commit()
        return True, row
    except Exception as e:
        db.session.rollback()
        return False, f'db error: {e}'
