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
 - `web` サービスはエントリポイントの `entrypoint.sh` を経由して起動します。`entrypoint.sh` は環境変数 `RUN_MIGRATIONS` が `true` の場合に自動で `flask db upgrade` を実行してから `gunicorn` を起動するようになりました。自動実行を無効化したい場合は `RUN_MIGRATIONS=false` を設定してください。

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

## DB運用と環境（運用ガイド）

このプロジェクトのデータベース運用について、開発／本番で注意すべき点と推奨ワークフローをまとめます。

1) 主要な環境変数
- `DATABASE_URL` - 接続先データベース。開発は `postgres://user:pass@db:5432/appdb`、本番はプラットフォームが提供する値を用います。
- `RUN_MIGRATIONS` - コンテナ起動時にマイグレーション (`flask db upgrade`) を自動実行するか（`true`/`false`）。
- `RUN_INIT` - entrypoint で `init_db.py` を実行するか（テーブル作成 + シード）。開発専用に `true` を使う場合がありますが、本番では推奨しません。

2) Docker 起動時のふるまい
- `docker-compose.yml` では `web` サービスが `entrypoint.sh` を呼び、`RUN_INIT` が `true` の場合に `init_db.py` を実行します。既存の `init_db.py` は `User` と `Stock` のテーブルのみを作成します。
 - 現在 `entrypoint.sh` は `RUN_MIGRATIONS` を参照し、`true` のときに `flask db upgrade` を実行します。必要に応じて `.env` やデプロイ環境で `RUN_MIGRATIONS=true` を設定してください。ただし複数インスタンスが同時に起動する環境ではマイグレーション競合のリスクがあるため、CI/CD 側で一度だけ実行する運用を推奨します（下記参照）。

3) ローカルでのマイグレーション開発ワークフロー
- 初回（migrations ディレクトリが無い場合）:

```powershell
$env:FLASK_APP="run.py"
$env:FLASK_ENV="development"
flask db init
flask db migrate -m "initial"
flask db upgrade
```

- 既存の DB に対してマイグレーションを導入する場合は、現在のスキーマを Alembic の最新版として記録する `stamp head` を使うと安全です:

```powershell
flask db init        # migrations が無い場合のみ
flask db stamp head  # 既存 DB を "最新" としてマーク（alembic_version を作成）
```

以後、モデルを変更したら `flask db migrate` → `flask db upgrade` を実行します。

4) Docker 上でマイグレーションを安全に実行する
- 起動時に `flask db upgrade` を自動実行する場合、複数インスタンスが同時に upgrade を行うと競合する可能性があります。競合を避けるための方法:
  - デプロイ時の CI で一度だけ `flask db upgrade` を実行する（推奨）。
  - 起動時にリーダー（1インスタンス）だけが `flask db upgrade` を実行する運用にする。

Docker コンテナ内で手動でマイグレーションを適用する例:
```powershell
docker-compose run --rm web flask db migrate -m "add rise_probability_summary"
docker-compose run --rm web flask db upgrade
```

または、既に起動中の web コンテナで直接適用:
```powershell
docker-compose exec web flask db upgrade
```

5) 既存データのバックアップとリストア
- 本番データを扱う前には必ずバックアップを取得してください（`pg_dump` 推奨）。例:

```powershell
# データベースダンプ
pg_dump "postgres://user:pass@host:5432/appdb" -Fc -f backup_$(Get-Date -Format yyyyMMdd).dump
# リストア
pg_restore -d "postgres://user:pass@host:5432/appdb" backup.dump
```

6) 注意点とベストプラクティス
- `migrations/` ディレクトリは Git にコミットして管理する（スキーマ変更をコードレビューできるように）。
- 破壊的なスキーマ変更（カラム削除や NOT NULL 制約の追加など）は事前にバックアップとロールバック手順を用意する。
- 開発では `RUN_INIT=true` を使って簡易的にテーブルを作ることができますが、本番ではマイグレーションで管理することを推奨します。
- Postgres を本番で使用することを推奨します（SQLite はコンテナ寿命に依存するため本番での利用は避ける）。

必要であれば、`Flask-Migrate` の導入（`requirements.txt` への追記、`app/__init__.py` への設定追加、`entrypoint.sh` の更新）や `migrations/` の初回生成を代行できます。

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