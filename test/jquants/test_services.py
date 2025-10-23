import pytest
import pandas as pd
from app.jquants.services import JQuantsAPI

class DummyJQuantsAPI:
    def __init__(self):
        pass
    def get_stock_data(self, code, start_date=None, end_date=None):
        return pd.DataFrame([
            {'Date': '2025-10-20', 'Close': 1000, 'Volume': 50000},
            {'Date': '2025-10-21', 'Close': 1100, 'Volume': 60000},
        ])
    def get_stock_data_today(self, code, date=None):
        return pd.DataFrame([
            {'Date': '2025-10-21', 'Close': 1100, 'Volume': 60000},
        ])
    def get_listed_issue_master(self, code=None, date=None):
        return pd.DataFrame([
            {'Code': code or '1234', 'Name': 'テスト株式会社'}
        ])
    def get_financial_data(self, code=None):
        return pd.DataFrame([
            {'DisclosedDate': '2025-10-01', 'NetSales': 160000, 'Profit': 8000, 'Equity': 28000, 'EquityToAssetRatio': 0.65, 'NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStock': 10000},
        ])
    def get_earnings_calendar(self):
        return pd.DataFrame([
            {'Date': '2025-10-25', 'Code': '1234', 'Earnings': '発表'}
        ])
    def get_cash_dividend(self, code=None, date=None):
        return [
            {'Code': code or '1234', 'Dividend': 30, 'Date': '2025-10-21'}
        ]

def test_get_stock_data(monkeypatch):
    monkeypatch.setattr('app.jquants.services.JQuantsAPI', lambda: DummyJQuantsAPI())
    api = JQuantsAPI()
    df = api.get_stock_data('1234')
    assert not df.empty
    assert 'Close' in df.columns

def test_get_stock_data_today(monkeypatch):
    monkeypatch.setattr('app.jquants.services.JQuantsAPI', lambda: DummyJQuantsAPI())
    api = JQuantsAPI()
    df = api.get_stock_data_today('1234')
    assert not df.empty
    assert 'Close' in df.columns

def test_get_listed_issue_master(monkeypatch):
    monkeypatch.setattr('app.jquants.services.JQuantsAPI', lambda: DummyJQuantsAPI())
    api = JQuantsAPI()
    df = api.get_listed_issue_master('1234')
    assert not df.empty
    assert 'Code' in df.columns

def test_get_financial_data(monkeypatch):
    monkeypatch.setattr('app.jquants.services.JQuantsAPI', lambda: DummyJQuantsAPI())
    api = JQuantsAPI()
    df = api.get_financial_data('1234')
    assert not df.empty
    assert 'Profit' in df.columns

def test_get_earnings_calendar(monkeypatch):
    monkeypatch.setattr('app.jquants.services.JQuantsAPI', lambda: DummyJQuantsAPI())
    api = JQuantsAPI()
    df = api.get_earnings_calendar()
    assert not df.empty
    assert 'Earnings' in df.columns

def test_get_cash_dividend(monkeypatch):
    monkeypatch.setattr('app.jquants.services.JQuantsAPI', lambda: DummyJQuantsAPI())
    api = JQuantsAPI()
    data = api.get_cash_dividend('1234')
    assert isinstance(data, list)
    assert data[0]['Dividend'] == 30
