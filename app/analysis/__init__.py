from flask import Blueprint

analysis = Blueprint('analysis', __name__)

from . import routes
