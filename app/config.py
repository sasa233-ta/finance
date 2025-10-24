import os


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    # If DATABASE_URL env var is provided use it (with postgres:// normalization),
    # otherwise fall back to a local SQLite file under data/app.db (absolute path).
    database_url = (os.environ.get('DATABASE_URL') or '').strip()
    if database_url:
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
    else:
        # app/ is this file's directory; project root is parent -> data is under project root
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        sqlite_path = os.path.join(project_root, 'data', 'app.db')
        database_url = f'sqlite:///{sqlite_path}'

    SQLALCHEMY_DATABASE_URI = database_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
