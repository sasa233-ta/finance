from flask import Blueprint

jquants = Blueprint('jquants', __name__)

from . import routes
