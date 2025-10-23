import os
import pandas as pd
import datetime
from .utils import get_jquants_api, make_features, StockModels
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score

# 分析用サービス

def predict_stock(code):
    """
    指定した銘柄・期間の株価データで各モデルの上昇確率を返す
    """
    api = get_jquants_api()
    df = api.get_stock_data(code)
    # --- JQUANTSデータ取得確認 ---
    df_feat = make_features(df)
    # --- 特徴量候補: すべてのカラムからtarget, Date, code, weatherのkey以外を自動抽出 ---
    all_columns = list(df_feat.columns)
    # 除外したいカラム
    exclude_cols = ['target', 'Date', 'date', 'code', 'Close_shift3']
    features = [c for c in all_columns if c not in exclude_cols]
    # ↓特徴量を絞りたい場合は下記のようにコメントアウトで選択
    # features = ['ret_1', 'ret_5', 'ma_gap', 'vol_5']
    # features = ['ret_1', 'ret_5', 'ma_5', 'ma_25', 'ma_gap', 'vol_5', 'temperature_2m_max']
    X = df_feat[features].values
    y = df_feat['target'].values
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    models = StockModels()
    models.fit(X_train, y_train)
    preds = models.predict_proba(X_test)
    aucs = {
        'logistic': roc_auc_score(y_test, preds['logistic']),
        'lightgbm': roc_auc_score(y_test, preds['lightgbm']),
        'nn': roc_auc_score(y_test, preds['nn']),
        'ensemble': roc_auc_score(y_test, preds['ensemble'])
    }
    result = {
        'date': df_feat.iloc[-1]['Date'],
        'code': code,
        'logistic': float(preds['logistic'][-1]),
        'lightgbm': float(preds['lightgbm'][-1]),
        'nn': float(preds['nn'][-1]),
        'ensemble': float(preds['ensemble'][-1]),
        'auc': aucs
    }
    return result
