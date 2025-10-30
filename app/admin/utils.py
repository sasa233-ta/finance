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
import logging

logger = logging.getLogger(__name__)


def fetch_prime_industry_pickles(out_base: str = 'data', years: int = 5,
                                 chunk_size: int = 50, pause: float = 1.5,
                                 save_pkl: bool = True, save_csv: bool = False,
                                 max_items: int = None):
    """Fetch Prime-listed domestic stocks, group by 17-industry code and
    save per-ticker pickles under out_base/<sector17_code>/.

    This was refactored out of services.py to keep the service layer thin.
    Returns the results dict from `fetch_and_save_by_industry`, or None if
    the daily timestamp indicates previous run.
    """
    # Ensure output directory exists and prepare checkpoint file for resumable runs
    os.makedirs(out_base, exist_ok=True)
    ts_path = os.path.join(out_base, 'prime_fetch.timestamp')
    progress_path = os.path.join(out_base, 'prime_fetch.progress.json')
    today = _date.today().isoformat()

    # load progress if exists
    progress = {}
    try:
        if os.path.exists(progress_path):
            with open(progress_path, 'r', encoding='utf-8') as f:
                progress = json.load(f) or {}
    except Exception:
        progress = {}

    # If timestamp indicates a full run completed today and either no progress file
    # exists or progress indicates completion, skip. Otherwise allow resume.
    if os.path.exists(ts_path):
        try:
            with open(ts_path, 'r', encoding='utf-8') as f:
                if f.read().strip() == today:
                    # if progress file present and incomplete, allow resume
                    if not progress:
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

    # We'll process industry-by-industry so we can checkpoint progress per-sector
    results = {}
    # track how many tickers we've attempted/saved to support --max-items
    attempted = 0
    for sector, codes in industry_map.items():
        # determine which codes still need processing according to progress
        processed_codes = set(progress.get(sector, []))
        remaining = [c for c in codes if c not in processed_codes]
        # apply max_items limit across all sectors (resume-aware)
        if max_items is not None:
            remaining_allowed = int(max_items) - attempted
            if remaining_allowed <= 0:
                # already reached limit; stop processing further sectors
                continue
            # slice remaining to the allowed count
            remaining = remaining[:remaining_allowed]
        if not remaining:
            # nothing to do for this sector
            continue

        try:
            # call stock utils for this single sector only
            res = fetch_and_save_by_industry({sector: remaining},
                                             out_base=out_base,
                                             years=years,
                                             chunk_size=chunk_size,
                                             pause=pause,
                                             save_pkl=save_pkl,
                                             save_csv=save_csv)

            # res is mapping sector -> list of saved file paths
            saved_files = res.get(sector, [])
            # increment attempted by number of tickers requested in this sector
            attempted += len(remaining)
            # extract tickers from saved file names and update progress
            saved_tickers = set()
            for path in saved_files:
                try:
                    fname = os.path.basename(path)
                    name, _ext = os.path.splitext(fname)
                    saved_tickers.add(name)
                except Exception:
                    continue

            # merge into progress and persist
            prev = set(progress.get(sector, []))
            new = sorted(prev.union(saved_tickers))
            progress[sector] = new
            try:
                with open(progress_path, 'w', encoding='utf-8') as f:
                    json.dump(progress, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

            results[sector] = saved_files
        except Exception:
            # record failure for this sector and continue to next sector
            traceback.print_exc()
            # attempt to capture any files already saved for this sector so we can resume next time
            try:
                sector_dir = os.path.join(out_base, sector)
                saved_tickers = set()
                if os.path.isdir(sector_dir):
                    for fn in os.listdir(sector_dir):
                        if fn.endswith('.pkl') or fn.endswith('.pickle') or fn.endswith('.csv'):
                            name, _ = os.path.splitext(fn)
                            saved_tickers.add(name)
                prev = set(progress.get(sector, []))
                new = sorted(prev.union(saved_tickers))
                progress[sector] = new
                try:
                    with open(progress_path, 'w', encoding='utf-8') as f:
                        json.dump(progress, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
            except Exception:
                pass
            results[sector] = []

    # If all sectors are present in progress and cover their original tickers, mark timestamp
    try:
        complete = True
        for sector, codes in industry_map.items():
            if set(progress.get(sector, [])) >= set(codes):
                continue
            complete = False
            break
        if complete:
            try:
                with open(ts_path, 'w', encoding='utf-8') as f:
                    f.write(today)
            except Exception:
                pass
    except Exception:
        pass

    return results


def update_rankings_from_pickles(out_base: str = 'data', max_items: int = None,
                                 per_file_timeout: int = None, per_file_retries: int = None,
                                 model: str = None):
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

                    # model selection: if model is None or 'all', keep existing behaviour
                    sel = None if (model is None or str(model).lower() in ('all','mixed')) else str(model).lower()

                    models = StockModels()
                    # If caller requested a specific model, pass it explicitly to fit()
                    models.fit(X_train, y_train, train_only=sel)
                    preds = models.predict_proba(X_test)
                    # Debug: print detailed preds content to help trace None/empty results
                    # debug info about preds is logged via logger.debug elsewhere; avoid noisy prints

                    # helper to extract last element safely
                    def last_val(arr):
                        try:
                            return float(arr[-1])
                        except Exception:
                            return None

                    if sel is None:
                        # take last prediction for each model (backwards compatible)
                        probs = {
                            'model1': last_val(preds.get('logistic', [])),
                            'model2': last_val(preds.get('lightgbm', [])),
                            'model3': last_val(preds.get('nn', [])),
                            'model4': last_val(preds.get('ensemble', [])),
                        }
                    else:
                        # single-model mode: only include the requested model's probability
                        if sel in ('lightgbm', 'lgbm', 'lgb'):
                            # map to internal key 'model2'
                            # if model training was skipped/failed, avoid storing neutral 0.5 and use NULL instead
                            if hasattr(models, 'trained') and not models.trained.get('lgbm', False):
                                probs = {'model2': None}
                            else:
                                probs = {'model2': last_val(preds.get('lightgbm', []))}
                        elif sel in ('logistic', 'lr'):
                            # map to internal key 'model1'
                            if hasattr(models, 'trained') and not models.trained.get('lr', False):
                                probs = {'model1': None}
                            else:
                                probs = {'model1': last_val(preds.get('logistic', []))}
                        elif sel in ('nn', 'mlp', 'neural'):
                            # map to internal key 'model3'
                            if hasattr(models, 'trained') and not models.trained.get('mlp', False):
                                probs = {'model3': None}
                            else:
                                probs = {'model3': last_val(preds.get('nn', []))}
                        elif sel in ('ensemble',):
                            probs = {'model4': last_val(preds.get('ensemble', []))}
                        else:
                            # unknown model specified -> fallback to all
                            probs = {
                                'model1': last_val(preds.get('logistic', [])),
                                'model2': last_val(preds.get('lightgbm', [])),
                                'model3': last_val(preds.get('nn', [])),
                                'model4': last_val(preds.get('ensemble', [])),
                            }

                    # compute AUC on the test set when possible
                    aucs = {}
                    try:
                        # ensure y_test has variation
                        if len(set(y_test)) > 1:
                            # mapping for available preds
                            mapping = {
                                'model1': 'logistic',
                                'model2': 'lightgbm',
                                'model3': 'nn',
                                'model4': 'ensemble',
                            }

                            # if in single-model mode, only compute AUC for that model
                            if sel is None:
                                targets = mapping.items()
                            else:
                                # determine which single metric to compute
                                if sel in ('lightgbm','lgbm','lgb'):
                                    targets = (('model2', 'lightgbm'),)
                                elif sel in ('logistic','lr'):
                                    targets = (('model1', 'logistic'),)
                                elif sel in ('nn','mlp','neural'):
                                    targets = (('model3', 'nn'),)
                                elif sel == 'ensemble':
                                    targets = (('model4', 'ensemble'),)
                                else:
                                    targets = mapping.items()

                            import numpy as _np
                            for mkey, pred_key in targets:
                                try:
                                    arr = preds.get(pred_key, [])
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
                            if sel is None:
                                for k in ('model1','model2','model3','model4'):
                                    aucs[k] = None
                            else:
                                # single selected model -> set single auc key
                                if sel in ('lightgbm','lgbm','lgb'):
                                    aucs['model2'] = None
                                elif sel in ('logistic','lr'):
                                    aucs['model1'] = None
                                elif sel in ('nn','mlp','neural'):
                                    aucs['model3'] = None
                                elif sel == 'ensemble':
                                    aucs['model4'] = None
                    except Exception:
                        if sel is None:
                            for k in ('model1','model2','model3','model4'):
                                aucs[k] = None
                        else:
                            # best effort: put None for selected model
                            if sel in ('lightgbm','lgbm','lgb'):
                                aucs['model2'] = None
                            elif sel in ('logistic','lr'):
                                aucs['model1'] = None
                            elif sel in ('nn','mlp','neural'):
                                aucs['model3'] = None
                            elif sel == 'ensemble':
                                aucs['model4'] = None

                    # attach AUCs to probs dict with keys 'auc_model1'.. (only for keys present)
                    # If single-model mode and the model wasn't actually trained, ensure its AUC is None
                    if sel is not None and hasattr(models, 'trained'):
                        if sel in ('lightgbm','lgbm','lgb'):
                            aucs['model2'] = None if not models.trained.get('lgbm', False) else aucs.get('model2')
                        elif sel in ('logistic','lr'):
                            aucs['model1'] = None if not models.trained.get('lr', False) else aucs.get('model1')
                        elif sel in ('nn','mlp','neural'):
                            aucs['model3'] = None if not models.trained.get('mlp', False) else aucs.get('model3')
                        elif sel == 'ensemble':
                            # ensemble depends on components; if lgbm skipped, ensemble may be invalid
                            if not (models.trained.get('lr', False) and models.trained.get('mlp', False) and models.trained.get('lgbm', False)):
                                aucs['model4'] = None

                    for k, v in aucs.items():
                        probs[f'auc_{k}'] = v

                    # If a single model was selected (sel != None), clear other model columns to NULL
                    set_null = False if sel is None else True
                    # Debug: log the probs dict and set_null to ensure keys match DB expectations
                    try:
                        logger.debug('update_rankings_from_pickles: code=%s set_null=%s probs=%s', code, set_null, probs)
                    except Exception:
                        pass
                    ok, res = update_or_create_rise_probs(code, probs, set_null_for_missing=set_null)
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
