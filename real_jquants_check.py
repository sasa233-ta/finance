from app.jquants.services import JQuantsAPI

if __name__ == '__main__':
    api = JQuantsAPI()
    code = '7203'  # 例: トヨタ自動車
    print('--- 株価データ（直近） ---')
    try:
        df = api.get_stock_data_today(code)
        print(df.head())
    except Exception as e:
        print('株価データ取得失敗:', e)

    print('--- 財務データ ---')
    try:
        df = api.get_financial_data(code)
        print(df.head())
    except Exception as e:
        print('財務データ取得失敗:', e)

    print('--- 銘柄マスタ ---')
    try:
        df = api.get_listed_issue_master(code)
        print(df.head())
    except Exception as e:
        print('銘柄マスタ取得失敗:', e)
