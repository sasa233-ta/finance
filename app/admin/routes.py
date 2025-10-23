
from flask import render_template, request, redirect, url_for, flash
from . import admin
from app.auth.decorators import login_required, role_required
from app.stocks.services import fetch_and_update_stocks
from .services import search_users, change_user_role
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

@admin.route('/update_stocks', methods=['POST'])
@login_required
@role_required('admin')
def update_stocks():
    count = fetch_and_update_stocks()
    flash(f'株データを{count}件更新しました', 'success')
    return redirect(url_for('admin.admin_page'))
