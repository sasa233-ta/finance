#!/usr/bin/env python
import argparse
import logging
from app import create_app
from app.admin import utils as admin_utils


def main(out_base: str = 'data', years: int = 5, chunk_size: int = 50, pause: float = 1.5, save_pkl: bool = True, save_csv: bool = False):
    app = create_app()
    with app.app_context():
        try:
            res = admin_utils.fetch_prime_industry_pickles(out_base=out_base, years=years, chunk_size=chunk_size, pause=pause, save_pkl=save_pkl, save_csv=save_csv)
            print('fetch_prime_industry_pickles result:', res)
        except Exception:
            logging.exception('fetch_prime_industry_pickles failed')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--data-dir', default='data')
    p.add_argument('--years', type=int, default=5)
    p.add_argument('--chunk-size', type=int, default=50)
    p.add_argument('--pause', type=float, default=1.5)
    p.add_argument('--no-pkl', dest='save_pkl', action='store_false')
    p.add_argument('--no-csv', dest='save_csv', action='store_false')
    p.add_argument('--max-items', type=int, default=None, help='limit number of tickers to fetch (resume-aware)')
    args = p.parse_args()
    main(out_base=args.data_dir, years=args.years, chunk_size=args.chunk_size, pause=args.pause, save_pkl=args.save_pkl, save_csv=args.save_csv, max_items=args.max_items)
