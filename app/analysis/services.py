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
        # 注意: 財務数値の単位（例: 金額が千円・百万円単位で入っている場合）や
        # EPS/BPS の符号により結果が大きく変わるため、可能な限り安全に計算します。
        try:
            def safe_float(d, key):
                if d is None:
                    return None
                # d may be a Series or dict-like
                try:
                    v = d.get(key) if hasattr(d, 'get') else d[key]
                except Exception:
                    return None
                if v in (None, '', 'None'):
                    return None
                try:
                    return float(v)
                except Exception:
                    return None

            close = safe_float(stock, 'Close')
            profit = safe_float(fin, 'Profit')
            equity = safe_float(fin, 'Equity')
            shares = safe_float(fin, 'NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStock')

            # EPS/BPS: まずは profit/share, equity/share を試算
            eps = (profit / shares) if (profit is not None and shares is not None and shares != 0) else None
            bps = (equity / shares) if (equity is not None and shares is not None and shares != 0) else None

            # PER = price / EPS (EPS が正のときのみ意味を持つ)
            per = None
            if close is not None and eps is not None and eps != 0:
                # ignore negative or extremely small EPS (may indicate loss or unit mismatch)
                if eps > 1e-9:
                    per = close / eps

            # PBR: 理論的には market_cap / equity が正しい。market_cap = close * shares
            pbr = None
            if equity is not None and equity != 0:
                if close is not None and shares is not None:
                    market_cap = close * shares
                    # if market_cap and equity are on same scale, this is reliable
                    pbr = market_cap / equity
                elif bps is not None and bps != 0:
                    # fallback to price / bps
                    pbr = close / bps if close is not None else None

            # マッピング: PER は小さいほど良い、PBR も小さいほど良い。
            # 実務的な閾値を用いて 0-10 に逆比例マッピングする（閾値は調整可能）。
            PER_THRESHOLD = 20.0
            PBR_THRESHOLD = 2.0

            def score_from_inverse(val, thr):
                # val が小さいほど高スコア。val <= 0 は None（または 0 点）に扱う。
                if val is None or val <= 0:
                    return None
                try:
                    score = (thr / val) * 10.0
                    return round(min(max(score, 0.0), 10.0), 1)
                except Exception:
                    return None

            per_score = score_from_inverse(per, PER_THRESHOLD)
            pbr_score = score_from_inverse(pbr, PBR_THRESHOLD)

            score_candidates = [s for s in (per_score, pbr_score) if s is not None]
            score_valuation = round(sum(score_candidates) / len(score_candidates), 1) if score_candidates else None
        except Exception:
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

        # 収益性: ROE・ROA・営業利益率を閾値ベースで 0-10 に正規化して平均をとる
        try:
            # 値の取得: '0' や 0 を有効な値として扱う
            def to_float_safe(d, key):
                v = d.get(key, None)
                if v is None:
                    return None
                try:
                    return float(v)
                except Exception:
                    return None

            profit = to_float_safe(fin, 'Profit')
            equity = to_float_safe(fin, 'Equity')
            total_assets = to_float_safe(fin, 'TotalAssets')
            operating_profit = to_float_safe(fin, 'OperatingProfit')
            net_sales = to_float_safe(fin, 'NetSales')

            roe_pct = (profit / equity * 100.0) if (profit is not None and equity not in (None, 0)) else None
            roa_pct = (profit / total_assets * 100.0) if (profit is not None and total_assets not in (None, 0)) else None
            op_margin_pct = (operating_profit / net_sales * 100.0) if (operating_profit is not None and net_sales not in (None, 0)) else None

            # 閾値（業界や方針に応じて調整可能）
            ROE_THRESHOLD = 15.0      # 15% を満点
            ROA_THRESHOLD = 7.5      # 7.5% を満点
            OP_MARGIN_THRESHOLD = 10.0  # 10% を満点

            def map_to_0_10(val, thr):
                if val is None:
                    return None
                try:
                    score = (val / thr) * 10.0
                    return min(max(score, 0.0), 10.0)
                except Exception:
                    return None

            scores = []
            roe_score = map_to_0_10(roe_pct, ROE_THRESHOLD)
            roa_score = map_to_0_10(roa_pct, ROA_THRESHOLD)
            op_margin_score = map_to_0_10(op_margin_pct, OP_MARGIN_THRESHOLD)
            for s in (roe_score, roa_score, op_margin_score):
                if s is not None:
                    scores.append(s)

            score_profitability = round(sum(scores) / len(scores), 1) if scores else None
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
