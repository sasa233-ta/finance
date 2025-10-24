
from flask import render_template, request, jsonify, session, redirect, url_for
from . import auth
from .services import register_user, authenticate_user
from .models import db, User


@auth.route('/register', methods=['GET'])
def register_page():
    return render_template('auth/register.html')


@auth.route('/login', methods=['GET'])
def login_page():
    return render_template('auth/login.html')

@auth.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    role = data.get('role', 'free')
    if not username or not email or not password:
        return jsonify({'message': '全項目必須です'}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({'message': 'このユーザー名は既に使われています'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'message': 'このメールアドレスは既に使われています'}), 400
    user = register_user(username, email, password, role)
    return jsonify({'id': user.id, 'username': user.username, 'role': user.role}), 201

@auth.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    user = authenticate_user(username, password)
    if user:
        session['user_id'] = user.id
        session['role'] = user.role
        return jsonify({'message': 'Login successful', 'role': user.role})
    return jsonify({'message': 'Invalid credentials'}), 401

@auth.route('/logout')
def logout():
    session.clear()
    # ログアウトしたらログイン画面へリダイレクトする
    return redirect(url_for('auth.login_page'))
