from app.stocks.models import Stock
from app.stocks.utils import fetch_and_save_by_industry
from app.prediction.utils import make_features, StockModels
from sklearn.metrics import roc_auc_score
from app.stocks.services import update_or_create_rise_probs
import os
from datetime import date as _date
import pandas as pd
import re
import subprocess
import json
import uuid
import time
import traceback


def fetch_prime_industry_pickles(out_base: str = 'data', years: int = 5,
                                 chunk_size: int = 50, pause: float = 1.5,
                                 save_pkl: bool = True, save_csv: bool = False):
    """Fetch Prime-listed domestic stocks, group by 17-industry code and
    save per-ticker pickles under out_base/<sector17_code>/.

    This was refactored out of services.py to keep the service layer thin.
    Returns the results dict from `fetch_and_save_by_industry`, or None if
    the daily timestamp indicates previous run.
    """
    # Check daily timestamp to run at most once per day
    os.makedirs(out_base, exist_ok=True)
    ts_path = os.path.join(out_base, 'prime_fetch.timestamp')
    today = _date.today().isoformat()
    if os.path.exists(ts_path):
        try:
            with open(ts_path, 'r', encoding='utf-8') as f:
                if f.read().strip() == today:
                    # already fetched today
                    return None
        except Exception:
            # ignore read errors and continue
            pass

    # Filter stocks that are on the Prime market and domestic (内国株式)
    q = Stock.query
    q = q.filter(
        (Stock.market.ilike('%プライム%') & Stock.market.ilike('%内国%'))
        | (Stock.scale.ilike('%内国%'))
    )
    stocks = q.all()

    # Build mapping: sector17_code -> list of tickers
    industry_map = {}
    for s in stocks:
        key = s.sector17_code or s.sector17 or 'unknown'
        code = s.code
        if not code:
            continue
        industry_map.setdefault(key, []).append(code)

    # Call utils to fetch and save
    results = fetch_and_save_by_industry(industry_map,
                                         out_base=out_base,
                                         years=years,
                                         chunk_size=chunk_size,
                                         pause=pause,
                                         save_pkl=save_pkl,
                                         save_csv=save_csv)

    # write timestamp on success
    try:
        with open(ts_path, 'w', encoding='utf-8') as f:
            f.write(today)
    except Exception:
        # ignore write errors
        pass

    return results


def update_rankings_from_pickles(out_base: str = 'data', max_items: int = None,
                                 per_file_timeout: int = None, per_file_retries: int = None):
    """Load per-ticker pickles under `out_base/*/*.pkl`, run prediction models using
    local data (no JQuants), and upsert the probabilities into RiseProbabilitySummary.

    Returns a tuple (processed_count, failed_count, details_list)
    where details_list contains (code, ok, message) entries.
    """
    processed = 0
    failed = 0
    details = []
    attempts = 0

    if not os.path.exists(out_base):
        return processed, failed, details

    # Only search one level under out_base: directories whose name contains digits
    for sub in os.listdir(out_base):
        subpath = os.path.join(out_base, sub)
        if not os.path.isdir(subpath):
            continue
        # require the subfolder name to be an industry index 1..17
        # accept pure-digit names and ensure they fall in range 1..17
        if not sub.isdigit():
            continue
        try:
            idx = int(sub)
        except Exception:
            continue
        if idx < 1 or idx > 17:
            continue
        # walk inside this subdirectory only
        for root, dirs, files in os.walk(subpath):
            for fname in files:
                # accept .pkl and .pickle extensions
                if not (fname.endswith('.pkl') or fname.endswith('.pickle')):
                    continue
                p = os.path.join(root, fname)
                code = os.path.splitext(fname)[0]
                # count this file as an attempt (one loop iteration)
                attempts += 1
                try:
                    df = pd.read_pickle(p)
                    # Normalize date column: make_features expects Date/date as str
                    if 'Date' in df.columns:
                        try:
                            # convert Timestamp/datetime to ISO string to satisfy strptime-based parsers
                            if not pd.api.types.is_string_dtype(df['Date']):
                                df = df.copy()
                                df['Date'] = df['Date'].astype(str)
                        except Exception:
                            # let make_features handle or raise a clearer error below
                            pass
                    elif 'date' in df.columns:
                        try:
                            if not pd.api.types.is_string_dtype(df['date']):
                                df = df.copy()
                                df['date'] = df['date'].astype(str)
                        except Exception:
                            pass
                    else:
                        # missing required date column -> try to infer from index or other columns
                        inferred = False
                        try:
                            # if index is datetime-like, use it
                            if hasattr(df, 'index') and pd.api.types.is_datetime64_any_dtype(df.index):
                                df = df.copy()
                                df['Date'] = df.index.astype(str)
                                inferred = True
                        except Exception:
                            pass

                        if not inferred:
                            # look for any column with a date-like name (e.g. 'date', '日付', '年月日')
                            candidates = [c for c in df.columns if any(k in c.lower() for k in ('date', '日付', '年月日', 'dt'))]
                            if candidates:
                                col = candidates[0]
                                try:
                                    if not pd.api.types.is_string_dtype(df[col]):
                                        df = df.copy()
                                        df['Date'] = df[col].astype(str)
                                    else:
                                        df = df.copy()
                                        df['Date'] = df[col]
                                    inferred = True
                                except Exception:
                                    inferred = False

                        if not inferred:
                            raise RuntimeError("missing 'Date' or 'date' column and no date-like index/column found")

                    # Note: per_file_timeout / per_file_retries are accepted for
                    # API compatibility with scripts/update_rise_probability.py.
                    # Current implementation processes files synchronously in this loop.
                    df_feat = make_features(df)
                    # prepare features similar to predict_stock
                    all_columns = list(df_feat.columns)
                    exclude_cols = ['target', 'Date', 'date', 'code', 'Close_shift3']
                    features = [c for c in all_columns if c not in exclude_cols]
                    if not features:
                        raise RuntimeError('no features available')
                    X = df_feat[features].values
                    y = df_feat['target'].values
                    n = X.shape[0]
                    if n < 2:
                        raise RuntimeError('not enough samples')
                    n_train = max(1, int(n * 0.7))
                    n_test = max(1, int(n * 0.7))
                    X_train, X_test = X[:n_train], X[-n_test:]
                    y_train, y_test = y[:n_train], y[-n_test:]

                    models = StockModels()
                    models.fit(X_train, y_train)
                    preds = models.predict_proba(X_test)
                    # take last prediction for each model
                    probs = {
                        'model1': float(preds['logistic'][-1]),
                        'model2': float(preds['lightgbm'][-1]),
                        'model3': float(preds['nn'][-1]),
                        'model4': float(preds['ensemble'][-1]),
                    }

                    # compute AUC on the test set when possible
                    aucs = {}
                    try:
                        # ensure y_test has variation
                        if len(set(y_test)) > 1:
                            mapping = {
                                'model1': 'logistic',
                                'model2': 'lightgbm',
                                'model3': 'nn',
                                'model4': 'ensemble',
                            }
                            for mkey, pred_key in mapping.items():
                                try:
                                    arr = preds[pred_key]
                                    # if arr is 2D probabilities for classes, take positive class
                                    import numpy as _np
                                    arr = _np.asarray(arr)
                                    if arr.ndim == 2 and arr.shape[1] > 1:
                                        prob_pos = arr[:, 1]
                                    else:
                                        prob_pos = arr
                                    aucs[mkey] = float(roc_auc_score(y_test, prob_pos))
                                except Exception:
                                    aucs[mkey] = None
                        else:
                            # not enough class variation to compute AUC
                            for k in ('model1','model2','model3','model4'):
                                aucs[k] = None
                    except Exception:
                        for k in ('model1','model2','model3','model4'):
                            aucs[k] = None

                    # attach AUCs to probs dict with keys 'auc_model1'..
                    for k, v in aucs.items():
                        probs[f'auc_{k}'] = v

                    ok, res = update_or_create_rise_probs(code, probs)
                    if ok:
                        processed += 1
                        details.append((code, True, 'ok'))
                    else:
                        failed += 1
                        details.append((code, False, res))
                except Exception as e:
                    failed += 1
                    details.append((code, False, str(e)))

                # If a max_items limit is provided, stop after attempting that many files
                if max_items is not None and attempts >= int(max_items):
                    return processed, failed, details

    return processed, failed, details
