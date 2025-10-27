"""Utilities to fetch market data using yfinance and save per-industry pickles/CSVs.

Functions:
 - fetch_and_save_by_industry: entry point to fetch tickers grouped by industry
 - download_with_backoff: wrapper around yfinance.download with exponential backoff
 - chunked: helper to split lists into chunks
 - _atomic_save: helper to write file atomically

Default behavior: 5 years of daily data, chunked downloads and pauses between chunks
to avoid triggering remote rate limits. Saved files placed under <out_base>/<industry>/
as per-ticker pickle (and optional CSV).
"""

from __future__ import annotations

import os
import time
import random
from datetime import date, timedelta, datetime
from app.utils import market_today
from tempfile import NamedTemporaryFile
from typing import Dict, Iterable, List, Optional

import pandas as pd
import yfinance as yf


def chunked(iterable: Iterable[str], size: int):
	it = iter(iterable)
	chunk = []
	for item in it:
		chunk.append(item)
		if len(chunk) >= size:
			yield chunk
			chunk = []
	if chunk:
		yield chunk


def _atomic_save(data_bytes: bytes, out_path: str):
	os.makedirs(os.path.dirname(out_path), exist_ok=True)
	dirpath = os.path.dirname(out_path)
	with NamedTemporaryFile('wb', delete=False, dir=dirpath, suffix='.tmp') as tmp:
		tmp.write(data_bytes)
		tmp_name = tmp.name
	os.replace(tmp_name, out_path)


def download_with_backoff(tickers: List[str], start: str, end: str,
						  max_retries: int = 5, base_backoff: float = 1.0) -> pd.DataFrame:
	"""Download data for tickers using yfinance with simple exponential backoff.

	Returns a pandas DataFrame (may be MultiIndex columns when multiple tickers).
	"""
	for attempt in range(max_retries):
		try:
			# threads=False to avoid many parallel connections to Yahoo
			df = yf.download(tickers=tickers, start=start, end=end, group_by='ticker',
							 threads=False, progress=False)
			return df
		except Exception as e:
			wait = min(base_backoff * (2 ** attempt) + random.random(), 60)
			print(f"yfinance download failed (attempt={attempt+1}/{max_retries}): {e}. retrying in {wait:.1f}s")
			time.sleep(wait)
	raise RuntimeError("yfinance download failed after retries")


def _save_dataframe_per_ticker(df: pd.DataFrame, tickers: List[str], out_dir: str,
							   save_pkl: bool = True, save_csv: bool = False) -> List[str]:
	"""Given a dataframe returned by yf.download and the tickers list, save each
	ticker's subframe to out_dir/<ticker>.(pkl|csv). Returns list of saved paths.
	"""
	saved = []
	# If multiple tickers, df.columns is MultiIndex (ticker, field)
	if isinstance(df.columns, pd.MultiIndex):
		for ticker in tickers:
			if ticker not in df.columns.get_level_values(0):
				# ticker not present in response
				print(f"ticker {ticker} not in downloaded frame")
				continue
			sub = df[ticker].copy()
			# ensure index is a column (Date)
			sub = sub.reset_index()
			fname_base = os.path.join(out_dir, f"{ticker}")
			if save_pkl:
				pkl_bytes = pd.to_pickle(sub, None) if False else None
				# pandas.to_pickle writes to a file path; to use atomic write we serialize
				# via to_pickle to a buffer using BytesIO. Simpler: write to temp file then replace.
				tmp_path = fname_base + '.pkl.tmp'
				sub.to_pickle(tmp_path)
				final_pkl = fname_base + '.pkl'
				os.replace(tmp_path, final_pkl)
				saved.append(final_pkl)
			if save_csv:
				csv_tmp = fname_base + '.csv.tmp'
				sub.to_csv(csv_tmp, index=False)
				final_csv = fname_base + '.csv'
				os.replace(csv_tmp, final_csv)
				saved.append(final_csv)
	else:
		# single ticker or single-frame returned
		fname_base = os.path.join(out_dir, 'data')
		os.makedirs(out_dir, exist_ok=True)
		if save_pkl:
			tmp = os.path.join(out_dir, 'data.pkl.tmp')
			df.to_pickle(tmp)
			final = os.path.join(out_dir, 'data.pkl')
			os.replace(tmp, final)
			saved.append(final)
		if save_csv:
			tmp = os.path.join(out_dir, 'data.csv.tmp')
			df.to_csv(tmp)
			final = os.path.join(out_dir, 'data.csv')
			os.replace(tmp, final)
			saved.append(final)

	return saved


def fetch_and_save_by_industry(industry_map: Dict[str, List[str]],
							   out_base: str = 'data',
							   years: int = 5,
							   chunk_size: int = 50,
							   pause: float = 1.5,
							   save_pkl: bool = True,
							   save_csv: bool = False) -> Dict[str, List[str]]:
	"""Fetch time series data for tickers grouped by industry and save per-ticker pickles.

	Args:
	  industry_map: mapping of industry_code -> list of tickers (yfinance symbols, e.g. '2678.T')
	  out_base: base output directory (will create <out_base>/<industry_code>/)
	  years: number of years before today to download (default 5)
	  chunk_size: number of tickers to request in one yf.download call
	  pause: seconds to sleep between chunks to reduce throttling risk
	  save_pkl/save_csv: which formats to save

	Returns:
	  dict mapping industry_code -> list of saved file paths
	"""
	results: Dict[str, List[str]] = {}
	# Use market-aware 'today' (if current time is before 15:30, use previous trading day)
	end_dt = market_today()
	try:
		start_dt = end_dt.replace(year=end_dt.year - years)
	except Exception:
		# fallback for leap-day issues
		start_dt = end_dt - timedelta(days=365 * years)

	start = start_dt.isoformat()
	end = end_dt.isoformat()

	for industry, tickers in industry_map.items():
		print(f"Processing industry {industry}: {len(tickers)} tickers")
		industry_out = os.path.join(out_base, industry)
		os.makedirs(industry_out, exist_ok=True)
		saved_files: List[str] = []

		for i, chunk in enumerate(chunked(tickers, chunk_size), start=1):
			print(f"  fetching chunk {i} ({len(chunk)} tickers) for {industry}")
			df = download_with_backoff(chunk, start=start, end=end)
			saved = _save_dataframe_per_ticker(df, chunk, industry_out, save_pkl, save_csv)
			saved_files.extend(saved)
			# pause between chunks
			time.sleep(pause + random.random() * 0.5)

		results[industry] = saved_files

	return results


