from flask import jsonify, session, render_template
from . import user
from app.auth.decorators import login_required

@user.route('/')
@login_required
def mypage():
    user_id = session.get('user_id')
    role = session.get('role')
    return render_template('user/mypage.html', user_id=user_id, role=role)
