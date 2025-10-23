import pytest
import pandas as pd
from app.analysis.services import StockAnalyzer

class DummyAPI:
    def get_stock_data_today(self, code):
        return pd.DataFrame([
            {'Date': '2025-10-20', 'Close': 1000, 'Volume': 50000},
            {'Date': '2025-10-21', 'Close': 1100, 'Volume': 60000},
        ])
    def get_financial_data(self, code):
        return pd.DataFrame([
            {'DisclosedDate': '2022-10-01', 'NetSales': 100000, 'Profit': 5000, 'Equity': 20000, 'EquityToAssetRatio': 0.5, 'NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStock': 10000},
            {'DisclosedDate': '2023-10-01', 'NetSales': 120000, 'Profit': 6000, 'Equity': 22000, 'EquityToAssetRatio': 0.55, 'NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStock': 10000},
            {'DisclosedDate': '2024-10-01', 'NetSales': 140000, 'Profit': 7000, 'Equity': 25000, 'EquityToAssetRatio': 0.6, 'NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStock': 10000},
            {'DisclosedDate': '2025-10-01', 'NetSales': 160000, 'Profit': 8000, 'Equity': 28000, 'EquityToAssetRatio': 0.65, 'NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStock': 10000},
        ])
    def get_listed_issue_master(self, code):
        return pd.DataFrame([
            {'Code': code, 'Name': 'テスト株式会社'}
        ])

def test_calc_scores(monkeypatch):
    # StockAnalyzerのapiをダミーに差し替え
    monkeypatch.setattr('app.analysis.services.JQuantsAPI', lambda: DummyAPI())
    analyzer = StockAnalyzer('1234')
    scores = analyzer.calc_scores()
    assert isinstance(scores, dict)
    assert all(k in scores for k in ['valuation', 'stability', 'growth', 'profitability', 'liquidity'])
    assert scores['valuation'] is not None
    assert scores['stability'] is not None
    assert scores['growth'] is not None
    assert scores['profitability'] is not None
    assert scores['liquidity'] is not None
