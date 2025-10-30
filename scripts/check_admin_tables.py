import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import create_app
from app.auth.models import db
import sqlalchemy

app = create_app()
with app.app_context():
    print('SQLALCHEMY_DATABASE_URI =', app.config.get('SQLALCHEMY_DATABASE_URI'))
    try:
        print('db.engine.url =', db.engine.url)
    except Exception as e:
        print('db.engine.url error', e)
    insp = sqlalchemy.inspect(db.engine)
    try:
        tables = insp.get_table_names()
        print('inspector.get_table_names() ->', tables)
    except Exception as e:
        print('inspector error:', e)
    try:
        from app.admin.services import list_tables
        print('list_tables() ->', list_tables())
    except Exception as e:
        print('list_tables() error:', e)

# test client for /admin/tables
with app.test_client() as c:
    with c.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'admin'
    res = c.get('/admin/tables')
    print('GET /admin/tables status:', res.status_code)
    html = res.get_data(as_text=True)
    print('HTML length:', len(html))
    print('--- html preview ---')
    print(html[:1200])
    try:
        for t in tables:
            print(f"contains '{t}'? ->", (t in html))
    except Exception:
        pass
