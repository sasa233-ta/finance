from app.jquants.services import JQuantsAPI
import pandas as pd
from .utils import get_latest

class StockAnalyzer:
    def __init__(self, code):
        self.code = code
        self.api = JQuantsAPI()
        self.stock_df = None
        self.fin_df = None
        self.issue_df = None
        self._fetch_data()

    def _fetch_data(self):
        try:
            self.stock_df = self.api.get_stock_data_today(code=self.code)
        except Exception as e:
            raise RuntimeError(f"株価データ取得失敗: {e}")
        try:
            self.fin_df = self.api.get_financial_data(code=self.code)
        except Exception as e:
            raise RuntimeError(f"財務データ取得失敗: {e}")
        try:
            self.issue_df = self.api.get_listed_issue_master(code=self.code)
        except Exception as e:
            raise RuntimeError(f"銘柄マスタ取得失敗: {e}")

    def calc_scores(self):
        # 公式APIリファレンスに合わせてカラム名を修正
        missing_columns = []
        # 最新データ取得
        stock = self.stock_df.sort_values('Date').iloc[-1]
        fin = self.fin_df.sort_values('DisclosedDate').iloc[-1]
        issue = self.issue_df.iloc[-1]

        # 割安性: PER, PBR（計算式で求める）
        try:
            close = float(stock['Close']) if 'Close' in stock and stock['Close'] else None
            profit = float(fin['Profit']) if 'Profit' in fin and fin['Profit'] else None
            equity = float(fin['Equity']) if 'Equity' in fin and fin['Equity'] else None
            shares = float(fin['NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStock']) if 'NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStock' in fin and fin['NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStock'] else None
            eps = (profit / shares) if profit and shares else None
            bps = (equity / shares) if equity and shares else None
            per = (close / eps) if close and eps and eps != 0 else None
            pbr = (close / bps) if close and bps and bps != 0 else None
            score_valuation = None
            if per is not None and pbr is not None:
                score = 10 - (per / 10 + pbr)
                score_valuation = round(min(max(score, 0), 10), 1)
            elif per is not None:
                score = 10 - (per / 10)
                score_valuation = round(min(max(score, 0), 10), 1)
            elif pbr is not None:
                score = 10 - pbr
                score_valuation = round(min(max(score, 0), 10), 1)
        except Exception as e:
            score_valuation = None

        # 安定性: 自己資本比率（equity_to_asset_ratio）
        try:
            capital_ratio = float(fin['EquityToAssetRatio']) if 'EquityToAssetRatio' in fin and fin['EquityToAssetRatio'] else None
            score_stability = round(capital_ratio*10) if capital_ratio is not None else None
        except Exception as e:
            score_stability = None

        # 成長性: 売上成長率（NetSales）と利益成長率（Profit）３年で計算
        try:
            if self.fin_df.shape[0] >= 4 and 'NetSales' in self.fin_df.columns and 'DisclosedDate' in self.fin_df.columns:
                self.fin_df['DisclosedDate'] = pd.to_datetime(self.fin_df['DisclosedDate'], errors='coerce')
                sorted_fin = self.fin_df.sort_values('DisclosedDate', ascending=False)
                sales_start = float(sorted_fin.iloc[12]['NetSales'] or 0)
                sales_end = float(sorted_fin.iloc[0]['NetSales'] or 0)
                profit_start = float(sorted_fin.iloc[12]['Profit'] or 0) if 'Profit' in self.fin_df.columns else 0
                profit_end = float(sorted_fin.iloc[0]['Profit'] or 0) if 'Profit' in self.fin_df.columns else 0
                years = (sorted_fin.iloc[0]['DisclosedDate'] - sorted_fin.iloc[12]['DisclosedDate']).days / 365.0
                cagr_sales = ((sales_end / sales_start) ** (1 / years) - 1) * 100 if sales_start > 0 and years > 0 else 0
                cagr_profit = ((profit_end / profit_start) ** (1 / years) - 1) * 100 if profit_start > 0 and years > 0 else 0
                combined_growth = (cagr_sales + cagr_profit) / 2
                score_growth_100 = min(max(combined_growth / 10 * 5, 1), 10)
                score_growth = round(score_growth_100, 1)
            else:
                score_growth = None
        except Exception as e:
            score_growth = None

        # 収益性: ROE・ROA・営業利益率の平均
        try:
            profit = float(fin['Profit']) if 'Profit' in fin and fin['Profit'] else None
            equity = float(fin['Equity']) if 'Equity' in fin and fin['Equity'] else None
            total_assets = float(fin['TotalAssets']) if 'TotalAssets' in fin and fin['TotalAssets'] else None
            operating_profit = float(fin['OperatingProfit']) if 'OperatingProfit' in fin and fin['OperatingProfit'] else None
            net_sales = float(fin['NetSales']) if 'NetSales' in fin and fin['NetSales'] else None

            roe = (profit / equity * 100) if profit and equity else None
            roa = (profit / total_assets * 100) if profit and total_assets else None
            op_margin = (operating_profit / net_sales * 100) if operating_profit and net_sales else None

            # それぞれ0～20点換算し、平均を10点満点に正規化
            scores = []
            if roe is not None:
                scores.append(min(max(roe / 2, 0), 20))
            if roa is not None:
                scores.append(min(max(roa * 2, 0), 20))
            if op_margin is not None:
                scores.append(min(max(op_margin / 5, 0), 20))
            score_profitability = round(sum(scores) / len(scores) / 2, 1) if scores else None
        except Exception as e:
            score_profitability = None

        # 流動性: 出来高（Volume）
        try:
            volume = float(stock['Volume']) if 'Volume' in stock and stock['Volume'] else None
            score_liquidity_100 = min(max((volume or 0) / 10000, 0), 100) if volume is not None else None
            score_liquidity = round(score_liquidity_100 / 10, 1) if score_liquidity_100 is not None else None
        except Exception as e:
            score_liquidity = None

        return {
            'valuation': round(score_valuation, 1) if score_valuation is not None else None,
            'stability': round(score_stability, 1) if score_stability is not None else None,
            'growth': round(score_growth, 1) if score_growth is not None else None,
            'profitability': round(score_profitability, 1) if score_profitability is not None else None,
            'liquidity': round(score_liquidity, 1) if score_liquidity is not None else None,
        }
