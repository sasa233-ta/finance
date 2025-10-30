

from flask import render_template, request
from . import stocks
from app.auth.decorators import login_required
from app.stocks.models import Stock
from app.stocks.services import normalize_for_search
from app.stocks.models import RiseProbabilitySummary
from app.stocks.services import get_rankings
from sqlalchemy import func

@stocks.route('/')
@login_required
def stock_list():
    page = request.args.get('page', 1, type=int)
    per_page = 50
    market = request.args.get('market', '')
    sector = request.args.get('sector', '')
    q = request.args.get('q', '').strip()
    query = Stock.query
    if market:
        query = query.filter(Stock.market == market)
    if sector:
        query = query.filter(Stock.sector33 == sector)
    if q:
        q_norm = normalize_for_search(q)
        query = query.filter(
            (Stock.code.contains(q)) |
            (Stock.name.contains(q)) |
            (Stock.name_normalized.contains(q_norm))
        )
    pagination = query.order_by(Stock.code).paginate(page=page, per_page=per_page, error_out=False)
    stocks = pagination.items
    # 絞込用の選択肢リスト
    markets = [row[0] for row in Stock.query.with_entities(Stock.market).distinct().order_by(Stock.market)]
    sectors = [row[0] for row in Stock.query.with_entities(Stock.sector33).distinct().order_by(Stock.sector33)]
    return render_template('stocks/stocks_list.html', stocks=stocks, pagination=pagination, markets=markets, sectors=sectors, market=market, sector=sector, q=q)

@stocks.route('/<code>')
@login_required
def stock_detail(code):
    stock = Stock.query.filter_by(code=code).first()
    if stock:
        return render_template('stocks/stock_detail.html', stock=stock)
    return render_template('stocks/stock_detail.html', stock=None)



@stocks.route('/rankings')
@login_required
def rankings():
    """sector17 ごとのランキング一覧。クエリパラメータ:
    - model: 'avg'（デフォルト）または 'prob_model1'..'prob_model4' のいずれかでソート
    """
    # no pagination; default sort by model1 and limit to top 20
    sort_model = request.args.get('model', 'prob_model1')
    limit = 20

    # allow sector passed as query param (form submit)
    sector = request.args.get('sector')

    # sectors list for selector
    sectors = [row[0] for row in Stock.query.with_entities(Stock.sector17).distinct().order_by(Stock.sector17)]

    items = get_rankings(sector=sector, model=sort_model, limit=limit)

    return render_template('stocks/rankings.html', items=items, sectors=sectors, selected_sector=sector, sort_model=sort_model)
