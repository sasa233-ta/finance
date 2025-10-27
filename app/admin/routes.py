
from flask import render_template, request, redirect, url_for, flash
from . import admin
from app.auth.decorators import login_required, role_required
from app.stocks.services import fetch_and_update_stocks
from .services import search_users, change_user_role
from .services import fetch_prime_industry_pickles
from .services import update_rankings_from_pickles
from .services import list_tables, query_table, get_table_columns
from .services import get_alembic_revision, get_alembic_heads, run_db_upgrade, get_available_revisions, run_db_downgrade, get_db_history
@admin.route('/users', methods=['GET'])
@login_required
@role_required('admin')
def admin_users():
    q = request.args.get('q', '')
    users = search_users(q)
    return render_template('admin/admin_users.html', users=users)

@admin.route('/users/<int:user_id>/role', methods=['POST'])
@login_required
@role_required('admin')
def change_role(user_id):
    new_role = request.form.get('role')
    success, msg = change_user_role(user_id, new_role)
    flash(msg, 'success' if success else 'danger')
    return redirect(url_for('admin.admin_users'))

@admin.route('/')
@login_required
@role_required('admin')
def admin_page():
    return render_template('admin/admin.html')


@admin.route('/tables', methods=['GET'])
@login_required
@role_required('admin')
def admin_tables():
    tables = list_tables()
    return render_template('admin/tables.html', tables=tables)


@admin.route('/tables/<table_name>', methods=['GET'])
@login_required
@role_required('admin')
def table_detail(table_name):
    # paging
    page = request.args.get('page', 1, type=int)
    per_page = 20
    # search params
    search_col = request.args.get('col')
    q = request.args.get('q', '')
    rows, total, columns = query_table(table_name, page=page, per_page=per_page, search_column=search_col, search_term=q if q else None)
    total_pages = max(1, (total + per_page - 1) // per_page)
    return render_template('admin/table_detail.html', table_name=table_name, rows=rows, columns=columns, page=page, total=total, total_pages=total_pages, q=q, search_col=search_col)

@admin.route('/update_stocks', methods=['POST'])
@login_required
@role_required('admin')
def update_stocks():
    count = fetch_and_update_stocks()
    flash(f'株データを{count}件更新しました', 'success')
    return redirect(url_for('admin.admin_page'))


@admin.route('/fetch_prime_pickles', methods=['POST'])
@login_required
@role_required('admin')
def fetch_prime_pickles():
    # Parameters could be extended to accept chunk_size/pause via form if desired
    res = fetch_prime_industry_pickles(out_base='data', years=5, chunk_size=50, pause=1.5)
    if res is None:
        flash('本日すでに取得済みです（1日1回のみ）', 'info')
    else:
        total = sum(len(v) for v in res.values())
        flash(f'プライム内国株式のデータを取得・保存しました（ファイル数: {total}）', 'success')
    return redirect(url_for('admin.admin_page'))


@admin.route('/update_rankings', methods=['POST'])
@login_required
@role_required('admin')
def update_rankings():
    # Run batch: load local pickles and update rise probability summaries
    # optional test mode: limit number of processed files
    try:
        max_items = request.form.get('max_items', type=int)
    except Exception:
        max_items = None
    processed, failed, details = update_rankings_from_pickles(out_base='data', max_items=max_items)
    if processed == 0 and failed == 0:
        flash('ピックルファイルが見つかりませんでした。まずはデータ取得を実行してください。', 'info')
    else:
        note = ''
        if max_items:
            note = f' (テスト件数上限: {max_items})'
        flash(f'ランキング更新: 成功 {processed} 件, 失敗 {failed} 件{note}', 'success' if failed == 0 else 'warning')
        # If there are failures, include a short summary of error messages for debugging
        if failed:
            err_messages = []
            for code, ok, msg in details:
                if not ok:
                    # keep messages short
                    s = f"{code}: {str(msg)[:200]}"
                    err_messages.append(s)
            if err_messages:
                # show up to 10 failing items
                flash('失敗詳細: ' + '; '.join(err_messages[:10]), 'danger')
    return redirect(url_for('admin.admin_page'))


@admin.route('/migrations', methods=['GET'])
@login_required
@role_required('admin')
def admin_migrations():
    """Show basic migration status (current revision and heads)."""
    current = get_alembic_revision()
    heads = get_alembic_heads()
    revisions = get_available_revisions()
    history = get_db_history()
    return render_template('admin/migrations.html', current=current, heads=heads, revisions=revisions, history=history)


@admin.route('/migrations/upgrade', methods=['POST'])
@login_required
@role_required('admin')
def migrations_upgrade():
    # Run migrations and show output
    success, output = run_db_upgrade()
    # shorten output shown in flash to avoid huge messages
    short = (output[:1500] + '...') if output and len(output) > 1500 else (output or '')
    if success:
        flash('マイグレーションが正常に適用されました。現在のリビジョン: ' + (get_alembic_revision() or '不明'), 'success')
        if short:
            flash('出力: ' + short, 'info')
    else:
        flash('マイグレーションに失敗しました。管理者コンソールで出力を確認してください。', 'danger')
        if short:
            flash('出力: ' + short, 'danger')
    return redirect(url_for('admin.admin_migrations'))


@admin.route('/migrations/downgrade', methods=['POST'])
@login_required
@role_required('admin')
def migrations_downgrade():
    target = request.form.get('target_revision')
    if not target:
        flash('ターゲットのリビジョンを選択してください。', 'danger')
        return redirect(url_for('admin.admin_migrations'))
    success, output = run_db_downgrade(target)
    short = (output[:1500] + '...') if output and len(output) > 1500 else (output or '')
    if success:
        flash(f'ダウングレードに成功しました。現在のリビジョン: {get_alembic_revision() or "不明"}', 'success')
        if short:
            flash('出力: ' + short, 'info')
    else:
        flash('ダウングレードに失敗しました。出力を確認してください。', 'danger')
        if short:
            flash('出力: ' + short, 'danger')
    return redirect(url_for('admin.admin_migrations'))
