# Flask App - ローカル起動とRailwayデプロイ手順

このドキュメントはローカル開発（Docker Compose）と Railway へのデプロイ手順をまとめたものです。

注意: 本リポジトリはアプリ本体が `flask_app` ディレクトリ下にあります。ローカルでは `docker-compose.yml` を `flask_app` 配下で使えます。

## 前提
- Docker と docker-compose がインストール済み
- Git リポジトリに変更を commit & push できる
- Railway アカウント（デプロイ先）がある

## 環境変数（重要）
- `SECRET_KEY` — 本番では長くランダムな文字列を設定
- `DATABASE_URL` — Railway の Postgres を使う場合に設定（例: `postgres://user:pass@host:5432/dbname`）
  - アプリは `postgres://` を `postgresql://` に正規化して接続します。
- `RUN_MIGRATIONS` — entrypoint でマイグレーションを自動実行するか（`true`/`false`）

### ローカル（Docker Compose）での起動
`flask_app` ディレクトリで実行します。

PowerShell:
```powershell
cd c:\Users\Owner\myapp\pythonWeb\flask_app
docker-compose up --build
```

- この compose は `db`（Postgres）と `web`（Flask）を立ち上げます。
- `web` サービスは起動時に `flask db upgrade` を実行してから `gunicorn` を起動します（環境変数 `RUN_MIGRATIONS` を `false` にすれば自動実行を無効化できます）。

### ローカルで直接（仮想環境）起動する場合
開発用に直接 Flask を使って起動したい場合:
```powershell
# 仮想環境作成・有効化
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 開発サーバ起動
python run.py
```

※ ただし、開発中でも Postgres を使う場合は `DATABASE_URL` を `postgres://...` に設定しておくか、`docker-compose` を使うことを推奨します。

### マイグレーション（Flask-Migrate）
初回のみ migrations フォルダを生成します（開発環境で実行）。

PowerShell:
```powershell
$env:FLASK_APP="run.py"
$env:FLASK_ENV="development"
flask db init       # まだ migrations/ が無い場合のみ
flask db migrate -m "initial"
flask db upgrade
```

作成された `migrations/` フォルダは Git にコミットしておくと、CI/本番で使いやすくなります。

## Railway へデプロイ（Dockerfile を使う想定）
1. 変更を Git に commit & push
2. Railway にログインして新規プロジェクトを作成し、GitHub リポジトリを接続
3. Railway のプロジェクトで Postgres プラグインを追加（または既存の有料 DB を使う）
4. Railway の Environment variables（Settings）に以下を設定:
   - `FLASK_ENV=production`
   - `SECRET_KEY` を設定
   - `DATABASE_URL`（Railway が提供）
   - 必要なら `RUN_MIGRATIONS=true`（自動で `flask db upgrade` を実行）
5. デプロイを開始。ログで `flask db upgrade` と `gunicorn` の起動が確認できれば完了。

### マイグレーションの実行（本番）
- 自動で実行すると便利ですが、複数インスタンスでの競合を避けたい場合は手動で一度だけ実行する方法を推奨します。
- Railway の UI から「Run a one-off command」で次を一度実行:
```
flask db upgrade
```

## 注意事項
- SQLite はコンテナのファイルシステムに保存されるため、本番（Railway）では推奨しません。本番運用では必ず `DATABASE_URL` で Postgres の利用を推奨します。
- `.env` を誤ってコミットしないように注意してください。`.env.sample` を作成して値の例だけ管理すると良いです。
- マイグレーション実行は慎重に：スキーマ変更が破壊的な場合は事前にバックアップを取る（`pg_dump` 等）。

## トラブルシューティング（よくある問題）
- `ModuleNotFoundError: flask_migrate` が出る: `pip install -r requirements.txt` を実行して依存を入れてください。
- `psycopg2` 関連の問題: ビルドエラーが出る場合は `psycopg2-binary` が `requirements.txt` に入っているか確認（本 repo では `psycopg2-binary` を使っています）。
- ポートが競合する: ローカルで 5000 ポートが使われている場合は `docker-compose.yml` のポートマッピングを変更してください。

---

何を次に進めますか？
- `migrations/` を私が生成してコミットする（ローカルで実行して差分を作成します）。
- Railway でのデプロイを一緒に進める（環境変数のセット方法やログ確認をサポート）。
- README を更に詳しく（CIや監視の手順）拡張する。