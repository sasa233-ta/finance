import os
import requests
import pandas as pd
import datetime
from dotenv import load_dotenv
from .utils import normalize_code

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data/")

class JQuantsAPI:
    def __init__(self):
        self.api_url = 'https://api.jquants.com'
        self.refresh_token = self._load_refresh_token()
        self.id_token = self._get_id_token()

    def _load_refresh_token(self, path="refresh_token.txt"):
        try:
            with open(DATA_DIR + path, "r", encoding="utf-8") as f:
                token = f.read().strip()
                return token
        except FileNotFoundError:
            raise FileNotFoundError(f"{DATA_DIR + path} が見つかりません。リフレッシュトークンを設定してください。")

    def _get_id_token(self):
        url = f"{self.api_url}/v1/token/auth_refresh?refreshtoken={self.refresh_token}"
        res = requests.post(url)
        if res.status_code == 200:
            return res.json()['idToken']
        else:
            print("[J-Quants認証失敗] リフレッシュトークンが無効。新規取得を試みます。")
            self.refresh_token = self.get_new_refresh_token()
            url = f"{self.api_url}/v1/token/auth_refresh?refreshtoken={self.refresh_token}"
            res = requests.post(url)
            if res.status_code == 200:
                return res.json()['idToken']
            else:
                print(f"[J-Quants認証失敗] status_code={res.status_code}, url={url}, text={res.text}")
                raise RuntimeError('J-Quants認証失敗')

    def get_new_refresh_token(self):
        mail = os.getenv('JQUANTS_MAIL_ADDRESS')
        password = os.getenv('JQUANTS_PASSWORD')
        url = f"{self.api_url}/v1/token/auth_user"
        payload = {"mailaddress": mail, "password": password}
        res = requests.post(url, json=payload)
        if res.status_code == 200:
            refresh_token = res.json()['refreshToken']
            with open(DATA_DIR + "refresh_token.txt", "w", encoding="utf-8") as f:
                f.write(refresh_token)
            print("新しいリフレッシュトークンを取得しました")
            return refresh_token
        else:
            print(f"[J-Quantsリフレッシュトークン取得失敗] status_code={res.status_code}, url={url}, text={res.text}")
            raise RuntimeError('J-Quantsリフレッシュトークン取得失敗')

    def get_stock_data(self, code, start_date=None, end_date=None):
        code = normalize_code(code)
        today = datetime.date.today()
        now = datetime.datetime.now()
        if now.hour < 9:
            today = today - datetime.timedelta(days=1)
        if today.weekday() == 5:
            today = today - datetime.timedelta(days=1)
        elif today.weekday() == 6:
            today = today - datetime.timedelta(days=2)
        if today.weekday() == 5:
            today = today - datetime.timedelta(days=1)
        elif today.weekday() == 6:
            today = today - datetime.timedelta(days=2)
        end = end_date or today.strftime('%Y-%m-%d')
        start = start_date or (datetime.datetime.strptime(end, '%Y-%m-%d').date() - datetime.timedelta(days=364*2)).strftime('%Y-%m-%d')
        headers = {'Authorization': f'Bearer {self.id_token}'}
        params = {'code': code, 'from': start, 'to': end}
        url = f"{self.api_url}/v1/prices/daily_quotes"
        print(f"[J-Quants APIリクエスト] code={code}")
        resp = requests.get(url, headers=headers, params=params)
        if resp.status_code != 200:
            print(f"[J-Quants APIエラー] status_code={resp.status_code}, url={url}, text={resp.text}")
        data = resp.json().get('daily_quotes', [])
        df = pd.DataFrame(data)
        if df.empty:
            raise ValueError('データ取得失敗')
        return df

    def get_stock_data_today(self, code, date=None):
        code = normalize_code(code)
        if date is None:
            today = datetime.date.today()
            now = datetime.datetime.now()
            if now.hour < 9:
                today = today - datetime.timedelta(days=1)
            if today.weekday() == 5:
                today = today - datetime.timedelta(days=1)
            elif today.weekday() == 6:
                today = today - datetime.timedelta(days=2)
            date = today.strftime('%Y-%m-%d')
        headers = {'Authorization': f'Bearer {self.id_token}'}
        params = {'code': code, 'date': date }
        url = f"{self.api_url}/v1/prices/daily_quotes"
        print(f"[J-Quants APIリクエスト(当日)] code={code}, date={date}")
        resp = requests.get(url, headers=headers, params=params)
        if resp.status_code != 200:
            print(f"[J-Quants APIエラー] status_code={resp.status_code}, url={url}, text={resp.text}")
        data = resp.json().get('daily_quotes', [])
        print(data)
        df = pd.DataFrame(data)
        if df.empty:
            raise ValueError('データ取得失敗')
        return df

    def get_listed_issue_master(self, code=None, date=None):
        headers = {'Authorization': f'Bearer {self.id_token}'}
        params = {}
        if code:
            code = normalize_code(code)
            params['code'] = code
        if date:
            params['date'] = date
        resp = requests.get(f"{self.api_url}/v1/listed/info", headers=headers, params=params)
        data = resp.json().get('info', [])
        df = pd.DataFrame(data)
        return df

    def get_financial_data(self, code=None):
        headers = {'Authorization': f'Bearer {self.id_token}'}
        params = {}
        if code:
            code = normalize_code(code)
            params['code'] = code
        resp = requests.get(f"{self.api_url}/v1/fins/statements", headers=headers, params=params)
        data = resp.json().get('statements', [])
        df = pd.DataFrame(data)
        return df

    def get_earnings_calendar(self):
        headers = {'Authorization': f'Bearer {self.id_token}'}
        resp = requests.get(f"{self.api_url}/v1/fins/announcement", headers=headers)
        data = resp.json().get('announcement', [])
        df = pd.DataFrame(data)
        return df

    def get_cash_dividend(self, code=None, date=None):
        url = f"{self.api_url}/v1/dividends/cash_dividends"
        params = {}
        if code:
            code = normalize_code(code)
            params['code'] = code
        if date:
            params['date'] = date
        headers = {'Authorization': f'Bearer {self.id_token}'}
        resp = requests.get(url, headers=headers, params=params)
        if resp.status_code != 200:
            print(f"status_code={resp.status_code}, url={url}, text={resp.text}")
            raise RuntimeError('J-Quants配当金情報取得失敗')
        data = resp.json().get('cash_dividends', [])
        return data
