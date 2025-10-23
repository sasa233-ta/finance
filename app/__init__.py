
from flask import Flask

def create_app():

	app = Flask(__name__)
	# Configuration
	app.config.from_object('app.config.DevelopmentConfig')

	# Initialize extensions that require app
	from .auth.models import db
	db.init_app(app)

	# Register Blueprints
	from .auth import auth as auth_blueprint
	app.register_blueprint(auth_blueprint, url_prefix='/auth')

	from .stocks import stocks as stocks_blueprint
	app.register_blueprint(stocks_blueprint, url_prefix='/stocks')

	from .user import user as user_blueprint
	app.register_blueprint(user_blueprint, url_prefix='/user')

	from .admin import admin as admin_blueprint
	app.register_blueprint(admin_blueprint, url_prefix='/admin')

	from .analysis import analysis as analysis_blueprint
	app.register_blueprint(analysis_blueprint, url_prefix='/analysis')

	from .jquants import jquants as jquants_blueprint
	app.register_blueprint(jquants_blueprint, url_prefix='/jquants')
	
	from .prediction import prediction as prediction_blueprint
	app.register_blueprint(prediction_blueprint, url_prefix='/prediction')

	# 全画面でログイン必須（authのlogin, register, static, logout以外）
	from flask import session, redirect, url_for, request

	@app.before_request
	def require_login():
		# skip login check for CLI or when session not available
		if not request:
			return None
		allowed = [
			'/auth/login', '/auth/register', '/auth/logout', '/static/', '/favicon.ico'
		]
		if request.path.startswith('/static/') or request.path == '/favicon.ico':
			return None
		if request.path in allowed:
			return None
		if 'user_id' not in session:
			return redirect(url_for('auth.login_page'))

	return app
