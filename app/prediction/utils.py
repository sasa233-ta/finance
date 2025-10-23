import importlib
import os
import pandas as pd
import pickle
import requests
from datetime import datetime, timedelta

def get_jquants_api():
    mod = importlib.import_module('app.jquants.services')
    return mod.JQuantsAPI()


def fetch_tokyo_weather(start_date, end_date, pickle_path):
    if os.path.exists(pickle_path):
        with open(pickle_path, 'rb') as f:
            weather_df = pickle.load(f)
        if not isinstance(weather_df, pd.DataFrame):
            weather_df = pd.DataFrame(weather_df)
    else:
        weather_df = pd.DataFrame()
    existing_dates = set(weather_df['date']) if not weather_df.empty else set()
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    all_dates = [(start_dt + timedelta(days=i)).strftime('%Y-%m-%d') for i in range((end_dt-start_dt).days+1)]
    fetch_dates = [d for d in all_dates if d not in existing_dates]
    if not fetch_dates:
        return weather_df
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        'latitude': 35.68,
        'longitude': 139.76,
        'start_date': fetch_dates[0],
        'end_date': fetch_dates[-1],
        'daily': ['temperature_2m_max','temperature_2m_min','precipitation_sum','weathercode'],
        'timezone': 'Asia/Tokyo'
    }
    r = requests.get(url, params=params)
    r.raise_for_status()
    data = r.json()['daily']
    df_new = pd.DataFrame(data)
    df_new['date'] = pd.to_datetime(df_new['time']).dt.strftime('%Y-%m-%d')
    df_new = df_new.drop('time', axis=1)
    if not weather_df.empty:
        weather_df = pd.concat([weather_df, df_new], ignore_index=True)
        weather_df = weather_df.drop_duplicates('date').sort_values('date').reset_index(drop=True)
    else:
        weather_df = df_new
    with open(pickle_path, 'wb') as f:
        pickle.dump(weather_df, f)
    return weather_df

def make_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values('Date').copy()
    df['Close'] = df['Close'].astype(float)
    df['Volume'] = df['Volume'].astype(float)
    df['Close_shift3'] = df['Close'].shift(-3)
    df['target'] = ((df['Close_shift3'] - df['Close']) / df['Close'] >= 0.015).astype(int)
    df['ret_1'] = df['Close'].pct_change(1)
    df['ret_5'] = df['Close'].pct_change(5)
    df['ma_5'] = df['Close'].rolling(5).mean()
    df['ma_25'] = df['Close'].rolling(25).mean()
    df['ma_gap'] = (df['Close'] - df['ma_25']) / df['ma_25']
    df['vol_5'] = df['Volume'].rolling(5).mean()
    start_date = df['Date'].min()
    end_date = df['Date'].max()
    pickle_path = os.path.join('data', 'tokyo_weather.pkl')
    weather_df = fetch_tokyo_weather(start_date, end_date, pickle_path)
    df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
    weather_df['date'] = pd.to_datetime(weather_df['date']).dt.strftime('%Y-%m-%d')
    df_merged = pd.merge(df, weather_df, left_on='Date', right_on='date', how='left')
    df_merged = df_merged.dropna(subset=['ret_1', 'ret_5', 'ma_5', 'ma_25', 'ma_gap', 'vol_5', 'target'])
    return df_merged

# --- model_service.py ---
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
import lightgbm as lgb
from sklearn.preprocessing import StandardScaler

class StockModels:
    def __init__(self):
        self.lr = LogisticRegression(max_iter=1000)
        self.mlp = MLPClassifier(hidden_layer_sizes=(32, 16), max_iter=1000, random_state=42)
        self.lgbm = None
        self.scaler = StandardScaler()

    def fit(self, X_train, y_train):
        self.lr.fit(X_train, y_train)
        self.scaler.fit(X_train)
        X_train_std = self.scaler.transform(X_train)
        self.mlp.fit(X_train_std, y_train)
        lgb_train = lgb.Dataset(X_train, y_train)
        params = {
            'objective': 'binary',
            'metric': 'auc',
            'verbosity': -1,
            'boosting_type': 'gbdt',
            'seed': 42
        }
        self.lgbm = lgb.train(params, lgb_train, num_boost_round=100)

    def predict_proba(self, X_test):
        # --- デバッグ: 入力・モデル状態確認 ---
        print('predict_proba: X_test shape:', X_test.shape)
        try:
            lr_pred = self.lr.predict_proba(X_test)[:, 1]
        except Exception as e:
            print('LogisticRegression予測エラー:', e)
            raise
        try:
            X_test_std = self.scaler.transform(X_test)
            mlp_pred = self.mlp.predict_proba(X_test_std)[:, 1]
        except Exception as e:
            print('MLPClassifier予測エラー:', e)
            raise
        try:
            lgb_pred = self.lgbm.predict(X_test, num_iteration=self.lgbm.best_iteration)
        except Exception as e:
            print('LightGBM予測エラー:', e)
            raise
        ensemble_pred = (lr_pred + lgb_pred + mlp_pred) / 3
        return {
            'logistic': lr_pred,
            'lightgbm': lgb_pred,
            'nn': mlp_pred,
            'ensemble': ensemble_pred
        }
