from app.auth.models import User, db
from app.admin import utils as admin_utils
from sqlalchemy import inspect, Table, MetaData, select, func, String
from sqlalchemy.exc import NoSuchTableError
import subprocess
import shlex
import os
import re

def search_users(query):
    q = query.strip()
    user_query = User.query
    if q:
        user_query = user_query.filter((User.username.contains(q)) | (User.email.contains(q)))
    return user_query.order_by(User.id).all()

def change_user_role(user_id, new_role):
    user = User.query.get_or_404(user_id)
    if new_role not in ['free', 'paid', 'admin']:
        return False, '不正な権限です'
    user.role = new_role
    db.session.commit()
    return True, f'ユーザー {user.username} の権限を {new_role} に変更しました'


def fetch_prime_industry_pickles(out_base: str = 'data', years: int = 5,
                                 chunk_size: int = 50, pause: float = 1.5,
                                 save_pkl: bool = True, save_csv: bool = False,
                                 max_items: int = None):
    """Fetch Prime (domestic) listed stocks, group by 17-industry code and
    save per-ticker pickles under out_base/<sector17_code>/. Returns results dict.
    """
    try:
        # Launch the fetch job as a detached subprocess so the web worker isn't blocked.
        import subprocess
        import sys
        import logging

        script_path = os.path.join('scripts', 'fetch_prime_industry_pickles.py')
        args = [sys.executable, script_path, '--data-dir', out_base, '--years', str(years), '--chunk-size', str(chunk_size), '--pause', str(pause)]
        if not save_pkl:
            args.append('--no-pkl')
        if not save_csv:
            args.append('--no-csv')
        if max_items is not None:
            args += ['--max-items', str(max_items)]

        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        return {'queued': True, 'message': 'background fetch job started'}
    except Exception:
        # fallback to synchronous call if subprocess cannot be started
        try:
            return admin_utils.fetch_prime_industry_pickles(
                out_base=out_base,
                years=years,
                chunk_size=chunk_size,
                pause=pause,
                save_pkl=save_pkl,
                save_csv=save_csv,
                max_items=max_items,
            )
        except Exception:
            raise


def update_rankings_from_pickles(out_base: str = 'data', max_items: int = None):
    """Load per-ticker pickles under `out_base/*/*.pkl`, run prediction models using
    local data (no JQuants), and upsert the probabilities into RiseProbabilitySummary.

    Returns a tuple (processed_count, failed_count, details_list)
    where details_list contains (code, ok, message) entries.
    """
    # Short-term: run asynchronously in a background thread to avoid blocking the web request.
    # The actual heavy work is implemented in admin_utils.update_rankings_from_pickles.
    try:
        # Spawn a separate process to run the batch job so the web worker
        # process is not impacted by heavy CPU / long-running work.
        import subprocess
        import sys
        import logging

        script_path = os.path.join('scripts', 'update_rise_probability.py')
        args = [sys.executable, script_path]
        if out_base:
            args += ['--data-dir', out_base]
        if max_items:
            args += ['--max-items', str(max_items)]

        # Detach: don't wait for completion and discard output (container logs will still catch prints if needed)
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        return {'queued': True, 'message': 'background job started'}
    except Exception as e:
        # fallback to synchronous execution on unexpected error
        try:
            return admin_utils.update_rankings_from_pickles(out_base=out_base, max_items=max_items)
        except Exception:
            raise e


def list_tables():
    """Return a list of table names in the current database, excluding alembic_version."""
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    return [t for t in tables if t != 'alembic_version']


def get_table_columns(table_name: str):
    """Return list of column info dicts for given table name.

    Each dict contains: name, type (string), nullable.
    """
    inspector = inspect(db.engine)
    try:
        cols = inspector.get_columns(table_name)
    except Exception:
        return []
    result = []
    for c in cols:
        result.append({
            'name': c.get('name'),
            'type': str(c.get('type')),
            'nullable': c.get('nullable', True)
        })
    return result


def query_table(table_name: str, page: int = 1, per_page: int = 20, search_column: str = None, search_term: str = None):
    """Query a table with optional column partial-match search and simple pagination.

    Returns (rows:list[dict], total:int, columns:list[str])
    """
    metadata = MetaData()
    try:
        table = Table(table_name, metadata, autoload_with=db.engine)
    except NoSuchTableError:
        return [], 0, []
    except Exception:
        return [], 0, []

    # build base select
    stmt = select(table)

    # apply search if provided and column exists
    if search_column and search_term:
        if search_column in table.c:
            col = table.c[search_column]
            stmt = stmt.where(col.cast(String).like(f"%{search_term}%"))

    # total count
    try:
        if search_column and search_term and (search_column in table.c):
            col = table.c[search_column]
            count_stmt = select([func.count()]).select_from(table).where(col.cast(String).like(f"%{search_term}%"))
        else:
            count_stmt = select([func.count()]).select_from(table)
        total = db.session.execute(count_stmt).scalar() or 0
    except Exception:
        total = 0

    # pagination
    page = max(1, int(page or 1))
    per_page = max(1, int(per_page or 20))
    offset = (page - 1) * per_page
    stmt = stmt.limit(per_page).offset(offset)

    try:
        res = db.session.execute(stmt)
        rows = [dict(r._mapping) for r in res.fetchall()]
    except Exception:
        rows = []

    cols = [c.name for c in table.columns]
    return rows, int(total), cols


def get_alembic_revision():
    """Return current alembic revision from alembic_version table (or None)."""
    try:
        res = db.session.execute("SELECT version_num FROM alembic_version")
        row = res.fetchone()
        if row:
            return row[0]
    except Exception:
        return None


def get_alembic_heads():
    """Return alembic heads via `flask db heads` command output (string)."""
    try:
        # use subprocess to call flask CLI; FLASK_APP env should be set in environment
        proc = subprocess.run(shlex.split('python -m flask db heads'), capture_output=True, text=True, check=False)
        out = proc.stdout + proc.stderr
        return out.strip()
    except Exception as e:
        return f'Error: {e}'


def run_db_upgrade():
    """Run `python -m flask db upgrade` and return (success:bool, output:str).

    Runs as a subprocess and captures stdout/stderr. Caller should enforce admin-only access.
    """
    try:
        proc = subprocess.run(shlex.split('python -m flask db upgrade'), capture_output=True, text=True, check=False)
        out = proc.stdout + '\n' + proc.stderr
        success = proc.returncode == 0
        return success, out.strip()
    except Exception as e:
        return False, str(e)


def get_available_revisions():
    """List migration files under migrations/versions and return list of (rev, name).

    Files are expected like: <rev>_description.py
    """
    versions_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', 'migrations', 'versions')
    # normalize path in case
    versions_dir = os.path.abspath(versions_dir)
    result = []
    try:
        for fname in sorted(os.listdir(versions_dir)):
            if not fname.endswith('.py'):
                continue
            m = re.match(r'([0-9a-f]+)_(.+)\.py', fname)
            if m:
                rev = m.group(1)
                name = m.group(2).replace('_', ' ')
            else:
                rev = fname.replace('.py', '')
                name = fname
            result.append((rev, name, fname))
    except Exception:
        # if directory missing or unreadable, return empty
        return []
    return result


def run_db_downgrade(target_revision: str):
    """Run `python -m flask db downgrade <target_revision>` and return (success, output).

    Warning: downgrades can be destructive; caller should enforce admin-only access and confirmation.
    """
    if not target_revision:
        return False, 'No target revision provided'
    try:
        cmd = f'python -m flask db downgrade {shlex.quote(target_revision)}'
        proc = subprocess.run(shlex.split(cmd), capture_output=True, text=True, check=False)
        out = proc.stdout + '\n' + proc.stderr
        success = proc.returncode == 0
        return success, out.strip()
    except Exception as e:
        return False, str(e)


def get_db_history():
    """Return verbose alembic history output as string."""
    try:
        proc = subprocess.run(shlex.split('python -m flask db history --verbose'), capture_output=True, text=True, check=False)
        out = proc.stdout + proc.stderr
        return out.strip()
    except Exception as e:
        return f'Error: {e}'
