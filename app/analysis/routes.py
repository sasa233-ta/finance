from flask import request, jsonify
from . import analysis
from .services import StockAnalyzer

@analysis.route('/score/<code>')
def score(code):
    try:
        analyzer = StockAnalyzer(code)
        scores = analyzer.calc_scores()
        return jsonify(scores)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
