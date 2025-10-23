from flask import Blueprint, request, jsonify, render_template
from .services import JQuantsAPI

jquants_bp = Blueprint('jquants', __name__, url_prefix='/jquants')

@jquants_bp.route('/stock/<code>')
def stock(code):
    api = JQuantsAPI()
    try:
        df = api.get_stock_data(code)
        data = df.to_dict(orient='records')
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@jquants_bp.route('/stock_today/<code>')
def stock_today(code):
    api = JQuantsAPI()
    try:
        df = api.get_stock_data_today(code)
        data = df.to_dict(orient='records')
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@jquants_bp.route('/listed_master')
def listed_master():
    code = request.args.get('code')
    date = request.args.get('date')
    api = JQuantsAPI()
    df = api.get_listed_issue_master(code, date)
    data = df.to_dict(orient='records')
    return jsonify(data)

@jquants_bp.route('/financial/<code>')
def financial(code):
    api = JQuantsAPI()
    df = api.get_financial_data(code)
    data = df.to_dict(orient='records')
    return jsonify(data)

@jquants_bp.route('/earnings_calendar')
def earnings_calendar():
    api = JQuantsAPI()
    df = api.get_earnings_calendar()
    data = df.to_dict(orient='records')
    return jsonify(data)

@jquants_bp.route('/cash_dividend/<code>')
def cash_dividend(code):
    date = request.args.get('date')
    api = JQuantsAPI()
    data = api.get_cash_dividend(code, date)
    return jsonify(data)
