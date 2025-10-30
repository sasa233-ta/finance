import os
import gc
import logging
from datetime import datetime
import uuid
import portalocker

from app import create_app
from app.admin import utils as admin_utils


LOG_DIR = 'instance'
LOCK_PATH = os.path.join(LOG_DIR, 'update_rise_probability.lock')
LAST_LOG = os.path.join(LOG_DIR, 'rise_prob_last_run.log')
FAILED_LOG = os.path.join(LOG_DIR, 'failed_rise_prob_files.log')


def ensure_dirs():
    os.makedirs(LOG_DIR, exist_ok=True)


def setup_logging_for_run(run_id: str = None):
    """Configure logging to write to instance/update_rankings.<run_id>.log and to stdout.
    Called at the start of each run to ensure a per-run file is available.
    """
    ensure_dirs()
    if run_id is None:
        run_id = uuid.uuid4().hex
    log_path = os.path.join(LOG_DIR, f'update_rankings.{run_id}.log')

    # Acquire the root logger and clear existing handlers to avoid duplication
    root_logger = logging.getLogger()
    # If handlers already configured, remove them so repeated runs (in same process) don't duplicate
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)

    root_logger.setLevel(logging.DEBUG)

    # File handler (detailed)
    fh = logging.FileHandler(log_path, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh_formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')
    fh.setFormatter(fh_formatter)
    root_logger.addHandler(fh)

    # Stream handler (console, less verbose)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch_formatter = logging.Formatter('%(levelname)s: %(message)s')
    ch.setFormatter(ch_formatter)
    root_logger.addHandler(ch)

    logging.getLogger(__name__).info('Logging initialized. log_file=%s', log_path)

    # (No stdout/stderr redirection - keep logging handlers only)

    return log_path


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


def run(data_dir: str = 'data', max_items: int = None, lock_timeout: int = 10, per_file_timeout: int = 300, per_file_retries: int = 10, model: str = None):
    """Run the update process:
    - acquire a file lock to prevent concurrent runs
    - call admin_utils.update_rankings_from_pickles
    - log results
    Returns (processed, failed, details)
    """
    ensure_dirs()
    # setup per-run logging to file + console
    try:
        log_path = setup_logging_for_run()
    except Exception:
        # If logging setup fails, continue but ensure at least root logger exists
        logging.getLogger(__name__).exception('Failed to initialize per-run logging')
        log_path = None

    logging.getLogger(__name__).info('Starting update_rise_probability run; data_dir=%s max_items=%s model=%s', data_dir, max_items, model)

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
            processed, failed, details = admin_utils.update_rankings_from_pickles(out_base=data_dir, max_items=max_items, per_file_timeout=per_file_timeout, per_file_retries=per_file_retries, model=model)
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
    p.add_argument('--model', type=str, default=None, help='model to use for prediction (lightgbm|logistic|nn|ensemble|all)')
    args = p.parse_args()
    try:
        processed, failed, details = run(data_dir=args.data_dir, max_items=args.max_items, per_file_timeout=args.per_file_timeout, per_file_retries=args.per_file_retries, model=args.model)
        print(f'processed={processed} failed={failed}')
    except Exception as e:
        logging.exception('update_rise_probability failed')
        print('error:', e)
