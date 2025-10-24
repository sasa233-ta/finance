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
    # additional technical features
    df['ret_3'] = df['Close'].pct_change(3)
    df['ret_10'] = df['Close'].pct_change(10)
    df['ma_5'] = df['Close'].rolling(5).mean()
    df['ma_25'] = df['Close'].rolling(25).mean()
    df['ma_gap'] = (df['Close'] - df['ma_25']) / df['ma_25']
    df['vol_5'] = df['Volume'].rolling(5).mean()
    df['vol_std_5'] = df['Volume'].rolling(5).std()
    df['vol_std_10'] = df['Volume'].rolling(10).std()
    # ma ratio
    df['ma_ratio_5_25'] = df['ma_5'] / df['ma_25']
    # momentum
    df['mom_5'] = df['Close'] / df['Close'].shift(5) - 1
    # RSI (simple implementation)
    delta = df['Close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    roll_up = up.rolling(14).mean()
    roll_down = down.rolling(14).mean()
    rs = roll_up / roll_down
    df['rsi_14'] = 100 - (100 / (1 + rs))
    start_date = df['Date'].min()
    end_date = df['Date'].max()
    pickle_path = os.path.join('data', 'tokyo_weather.pkl')
    weather_df = fetch_tokyo_weather(start_date, end_date, pickle_path)
    df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
    weather_df['date'] = pd.to_datetime(weather_df['date']).dt.strftime('%Y-%m-%d')
    df_merged = pd.merge(df, weather_df, left_on='Date', right_on='date', how='left')
    # drop rows missing essential features
    essential = ['ret_1', 'ret_5', 'ma_5', 'ma_25', 'ma_gap', 'vol_5', 'target']
    existing_essentials = [c for c in essential if c in df_merged.columns]
    df_merged = df_merged.dropna(subset=existing_essentials)
    return df_merged

# --- model_service.py ---
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
import lightgbm as lgb
from sklearn.preprocessing import StandardScaler

class StockModels:
    def __init__(self):
        # 学習コストを抑えるためデフォルトの反復回数を下げ、MLPは早期停止を有効にする
        self.lr = LogisticRegression(max_iter=500)
        self.mlp = MLPClassifier(hidden_layer_sizes=(32, 16), max_iter=200, early_stopping=True, n_iter_no_change=10, random_state=42)
        self.lgbm = None
        self.scaler = StandardScaler()
        # 学習制御パラメータ
        self.max_samples = 1500  # これ以上の行は末尾を採用してトレーニングデータを制限する
        self.lgb_rounds = 50
        self.lgb_early_stopping = 10

    def fit(self, X_train, y_train):
        # データ量が大きい場合は末尾 N サンプルに制限する（直近のデータを利用するため）
        if X_train.shape[0] > self.max_samples:
            start_idx = X_train.shape[0] - self.max_samples
            X_train = X_train[start_idx:]
            y_train = y_train[start_idx:]

        # ロジスティック回帰
        self.lr.fit(X_train, y_train)

        # 標準化と MLP 学習（早期停止有効）
        self.scaler.fit(X_train)
        X_train_std = self.scaler.transform(X_train)
        try:
            self.mlp.fit(X_train_std, y_train)
        except Exception as e:
            # 学習失敗しても続行できるようログ出力のみ
            print('MLP fit failed:', e)

        # LightGBM は検証データを作って早期停止をかける
        # 小さい割合を validation に割り当てる
        if X_train.shape[0] >= 50:
            val_size = max( int(0.1 * X_train.shape[0]), 10 )
            X_tr, X_val = X_train[:-val_size], X_train[-val_size:]
            y_tr, y_val = y_train[:-val_size], y_train[-val_size:]
        else:
            X_tr, X_val, y_tr, y_val = X_train, X_train, y_train, y_train

        lgb_train = lgb.Dataset(X_tr, y_tr)
        lgb_val = lgb.Dataset(X_val, y_val, reference=lgb_train)
        params = {
            'objective': 'binary',
            'metric': 'auc',
            'verbosity': -1,
            'boosting_type': 'gbdt',
            'seed': 42
        }

        # Try multiple training call styles to maximize compatibility across LightGBM versions.
        # 1) callbacks API (newer versions)
        # 2) early_stopping_rounds kwarg (some versions)
        # 3) no early stopping
        self.lgbm = None
        if hasattr(lgb, 'early_stopping') and self.lgb_early_stopping and self.lgb_early_stopping > 0:
            try:
                self.lgbm = lgb.train(params, lgb_train, num_boost_round=self.lgb_rounds, valid_sets=[lgb_val], callbacks=[lgb.early_stopping(self.lgb_early_stopping)])
            except Exception as e_cb:
                print('LightGBM training with callbacks failed:', e_cb)

        # If callbacks attempt failed or wasn't used, try early_stopping_rounds kwarg
        if self.lgbm is None and self.lgb_early_stopping and self.lgb_early_stopping > 0:
            try:
                self.lgbm = lgb.train(params, lgb_train, num_boost_round=self.lgb_rounds, valid_sets=[lgb_val], early_stopping_rounds=self.lgb_early_stopping)
            except Exception as e_es:
                print('LightGBM training with early_stopping_rounds failed:', e_es)

        # Finally, try without early stopping
        if self.lgbm is None:
            try:
                self.lgbm = lgb.train(params, lgb_train, num_boost_round=self.lgb_rounds, valid_sets=[lgb_val])
            except Exception as e_final:
                print('LightGBM training failed (no early stopping):', e_final)
                self.lgbm = None

        return self

    def save(self, path):
        # モデルをpickleで保存（scaler, lr, mlp, lgbm をまとめて保存）
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            pickle.dump({
                'lr': self.lr,
                'mlp': self.mlp,
                'lgbm': self.lgbm,
                'scaler': self.scaler
            }, f)

    @classmethod
    def load(cls, path):
        with open(path, 'rb') as f:
            data = pickle.load(f)
        inst = cls()
        inst.lr = data.get('lr', inst.lr)
        inst.mlp = data.get('mlp', inst.mlp)
        inst.lgbm = data.get('lgbm', inst.lgbm)
        inst.scaler = data.get('scaler', inst.scaler)
        return inst

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
            # Check feature dimension matches scaler (if scaler was fitted)
            try:
                expected_dim = self.scaler.mean_.shape[0]
                if X_test.shape[1] != expected_dim:
                    print(f"Warning: X_test feature dim ({X_test.shape[1]}) != expected ({expected_dim}).")
            except Exception:
                # scaler may not be fitted in some failure modes; ignore
                pass

            if self.lgbm is None:
                # 学習に失敗している場合は中立的な確率を返す（0.5）
                lgb_pred = np.full(X_test.shape[0], 0.5)
            else:
                # LightGBM の predict ではベストイテレーションが存在すれば使う。
                # バージョン差で属性名が異なる場合に備えフォールバックを行う。
                num_iter = None
                for attr in ('best_iteration', 'best_iteration_'):
                    num_iter = getattr(self.lgbm, attr, None)
                    if num_iter:
                        break
                # num_iter が 0 や None の場合は渡さない
                if num_iter and int(num_iter) > 0:
                    lgb_pred = self.lgbm.predict(X_test, num_iteration=int(num_iter))
                else:
                    lgb_pred = self.lgbm.predict(X_test)
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
