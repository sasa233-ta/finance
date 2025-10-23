from app.auth.models import User, db

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
