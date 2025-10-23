from flask import request, jsonify
from . import prediction
from .services import predict_stock


@prediction.route('/predict/<code>')
def predict(code):
    try:
            result = predict_stock(code)
            # デバッグ: 予測値の有無をprint
            print('API result:', result)
            logistic = float(result["logistic"]) if "logistic" in result else None
            lightgbm = float(result["lightgbm"]) if "lightgbm" in result else None
            nn = float(result["nn"]) if "nn" in result else None
            ensemble = float(result["ensemble"]) if "ensemble" in result else None
            if all(x is None for x in [logistic, lightgbm, nn, ensemble]):
                return jsonify({
                    'error': '予測データがありません（API result: %s）' % result
                }), 200
            return jsonify({
                "logistic": logistic,
                "lightgbm": lightgbm,
                "nn": nn,
                "ensemble": ensemble
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
