import os
import gc
import logging
from datetime import datetime
import portalocker

from app import create_app
from app.admin import utils as admin_utils


LOG_DIR = 'instance'
LOCK_PATH = os.path.join(LOG_DIR, 'update_rise_probability.lock')
LAST_LOG = os.path.join(LOG_DIR, 'rise_prob_last_run.log')
FAILED_LOG = os.path.join(LOG_DIR, 'failed_rise_prob_files.log')


def ensure_dirs():
    os.makedirs(LOG_DIR, exist_ok=True)


def write_last_run(processed, failed):
    try:
        with open(LAST_LOG, 'a', encoding='utf-8') as f:
            f.write(f"{datetime.utcnow().isoformat()}Z processed={processed} failed={failed}\n")
    except Exception:
        pass


def append_failed(details):
    try:
        if not details:
            return
        with open(FAILED_LOG, 'a', encoding='utf-8') as f:
            for code, ok, msg in details:
                if not ok:
                    f.write(f"{datetime.utcnow().isoformat()}Z {code}: {msg}\n")
    except Exception:
        pass


def run(data_dir: str = 'data', max_items: int = None, lock_timeout: int = 10, per_file_timeout: int = 300, per_file_retries: int = 10):
    """Run the update process:
    - acquire a file lock to prevent concurrent runs
    - call admin_utils.update_rankings_from_pickles
    - log results
    Returns (processed, failed, details)
    """
    ensure_dirs()

    # acquire lock
    fh = open(LOCK_PATH, 'w')
    try:
        portalocker.lock(fh, portalocker.LOCK_EX)
    except Exception as e:
        fh.close()
        raise RuntimeError(f'Could not acquire lock: {e}')

    try:
        app = create_app()
        with app.app_context():
            processed, failed, details = admin_utils.update_rankings_from_pickles(out_base=data_dir, max_items=max_items, per_file_timeout=per_file_timeout, per_file_retries=per_file_retries)
            write_last_run(processed, failed)
            append_failed(details)
            # free memory of any other temporaries
            gc.collect()
            return processed, failed, details
    finally:
        try:
            fh.close()
            # remove lock file if exists
            try:
                os.remove(LOCK_PATH)
            except Exception:
                pass
        except Exception:
            pass


if __name__ == '__main__':
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument('--data-dir', default='data')
    p.add_argument('--max-items', type=int, default=None)
    p.add_argument('--per-file-timeout', type=int, default=60, help='timeout seconds per file processing')
    p.add_argument('--per-file-retries', type=int, default=2, help='retries per file on timeout/error')
    args = p.parse_args()
    try:
        processed, failed, details = run(data_dir=args.data_dir, max_items=args.max_items, per_file_timeout=args.per_file_timeout, per_file_retries=args.per_file_retries)
        print(f'processed={processed} failed={failed}')
    except Exception as e:
        logging.exception('update_rise_probability failed')
        print('error:', e)
