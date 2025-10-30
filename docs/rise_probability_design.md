## rise_probability_summary 登録バッチ設計書

目的
- ./data/1 .. ./data/17 配下の各 `<stock_code>.pickle` を読み、各モデルの上昇確率および AUC を `rise_probability_summary` テーブルに格納する。

前提（ユーザ確認済）
- DB: SQLite
- テーブル: `rise_probability_summary`（既にマイグレーションファイルは存在）
- テーブルカラム（要件）:
	- stock_code TEXT PRIMARY KEY
	- prob_model1..prob_model4 REAL
	- auc_model1..auc_model4 REAL
	- updated_at DATETIME
- pickle 保存: `./data/<sector(1-17)>/<stock_code>.pickle`
- 同時実行禁止: `instance/update_rise_probability.lock` を作成して `portalocker` で排他ロック
- 実行トリガ: 管理画面のランキング更新ボタン -> 非同期でバッチ実行（詳細は下記）

高レベル設計
- 起動: バッチは管理画面経由で非同期に起動する（推奨: ワーカー or Redis-backed queue; 代替: フラスクからバックグラウンドスレッド/プロセス起動の短期的実装）。
- ロック: 起動直後に `instance` フォルダを作成し、`instance/update_rise_probability.lock` に対して `portalocker` による排他ロックを取得。取得できなければ終了。
- ファイル列挙: セクター 1..17 を順に処理。各ディレクトリ内で `*.pickle` をソートして列挙。
- 対象判定: 各 file について `stock_code` を取り、DB の `rise_probability_summary` を確認。
	- レコードが無い -> 処理対象（INSERT）
	- レコードがある & updated_at < now - 3 days -> 再処理対象
	- レコードがある & updated_at >= now - 3 days -> スキップ
- 処理: ファイルを open -> pickle.load -> 必要値を取り出す（下記参照）-> DB に upsert（1ファイルごとに commit）-> del 大きな変数 -> `gc.collect()`

 - タイムアウトとリトライ: 各ファイル処理は長時間ブロッキングする可能性があるため、親プロセスから子プロセス（またはサブプロセス）で実行し、`per_file_timeout` 秒でタイムアウトさせます。タイムアウト発生時は `per_file_retries` 回まで再試行します。再試行に失敗したファイルは `instance/failed_rise_prob_files.log` に記録します。デフォルト例: `per_file_timeout=60`, `per_file_retries=2`。

pickle 中身の取り扱い
- 実装参照: `app/prediction/services.py` の `predict_stock` が返す構造を踏襲。
	- 期待されるフォーマット（あるいは同等の出力を作ること）:
		- {'date': ..., 'code': 'XXXX', 'logistic': float, 'lightgbm': float, 'nn': float, 'ensemble': float, 'auc': {'logistic': float, 'lightgbm': float, 'nn': float, 'ensemble': float}}
- 実装方針:
	- pickle が上記フォーマット（またはモデル確率と真ラベル/予測確率を含む）であれば直接利用。
	- もし pickle が別形式で真ラベル/予測確率のみを持つ場合は、AUC を計算してカラムに格納する。
	- 形式が不明な場合は安全に例外を投げログ化し、他ファイル処理を継続する。

DB 書き込み（トランザクション）
- 1ファイル毎にトランザクションを開始 -> INSERT or UPDATE -> commit。
- SQLite + SQLAlchemy を想定。簡単な upsert は `INSERT OR REPLACE` でも可だが、`updated_at` を正しく扱うためは SELECT->UPDATE/INSERT の方が分かりやすい。

排他ロック実装（詳細）
- 依存: `portalocker` を requirements に追加。
- フロー:
	1. `os.makedirs('instance', exist_ok=True)`
	2. with open('instance/update_rise_probability.lock', 'w') as fh: portalocker.lock(fh, portalocker.LOCK_EX)
	3. 処理終了/例外時は finally で lock を解除しファイルを閉じる（必要なら削除）

非同期実行（管理画面からの起動） — 短期採用: Flask 内バックグラウンドスレッド

注: 将来的には Redis+RQ/Celery ベースのワーカー構成へ移行するのが望ましいですが、現時点では短期的に「管理画面からボタン押下で非同期に処理を開始する」ことを優先するため、Flask 内でバックグラウンドスレッドを使う方式を採用します。

理由と前提
- 即時導入・運用コスト低減が目的。開発/ステージング環境や小規模運用では手早く運用できるメリットがあります。
- 制約: PaaS（例: Railway）ではプロセス再起動やスケーリングでスレッドが中断されるリスクがあるため、長期安定運用には別途ワーカー構成の導入が必要です。

実装ポイント（Flask 内 Thread 型、採用内容）
- 管理画面のボタン押下ハンドラは即時に HTTP で成功応答（202 Accepted 等）を返し、実処理は別スレッドで実行する。
- 実処理関数は既存の `admin_utils.update_rankings_from_pickles`（または `scripts/update_rise_probability.py` のコア関数）を呼び出す形にし、ワーカー側で `portalocker` によるロックを取得して同時実行を防止する。
- 例的フロー:
	1. 管理画面エンドポイント呼び出し -> `threading.Thread(target=run_worker, args=(data_dir,), daemon=True).start()` を実行 -> 202 を返す
	2. `run_worker` 内で `os.makedirs('instance', exist_ok=True)` -> `with open('instance/update_rise_probability.lock','w') as fh: portalocker.lock(fh, portalocker.LOCK_EX)` を取得 -> ファイル処理を逐次実行 -> lock 解除

状態の可視化・ログ
- バックグラウンド処理の状態とログは `instance/` 下に保存する（例: `instance/rise_prob_last_run.log`, `instance/failed_rise_prob_files.log`）。
- 可能であれば簡易的なジョブステータステーブル（SQLite）を作って `job_id`, `status`, `started_at`, `finished_at`, `message` を書き出すと管理しやすい。

運用上の注意（必読）
- PaaS 環境ではプロセス再起動でスレッドが中断する恐れがある。重要なバッチは再起動耐性のあるワーカー構成へ移行すること。
- 同時に複数エンキューされるとスレッドが複数立ち上がる恐れがあるため、ワーカー側で `portalocker` による排他を必ず行ってください。

導入手順（短期方）
1. `app/admin/services.py` の `update_rankings_from_pickles` を修正して、スレッドで非同期起動する実装にする（即時 202 を返す）。
2. 実処理関数を `app/admin/utils.py` または `scripts/update_rise_probability.py` 側に分離して呼べるようにする（`run(data_dir)` など）。
3. ワーカー内で `portalocker` による排他ロックを取得して処理を行う。
4. 実行ログと失敗ファイル一覧を `instance/` 下に書き出す。
5. 将来的に Redis+RQ へ移行するため、ジョブ関数は外部から enqueue できる形（`run(data_dir)`）にしておく。

選択理由の記録
- 現時点では短期導入を優先するため thread-based を採用。後日ワーカー化する際は、この設計で作った `run(data_dir)` を RQ/Celery のタスクとして再利用できます。

メモリ対策
- 各 pickle を完全にロードしても、1ファイルずつ処理して即解放すれば総メモリ消費は各ファイル分に限定される。
- pickle 自体が単一ファイルで巨大配列を含みメモリ不足になる場合は、pickle 生成時に HDF5/npz/Parquet 等の chunkable な形式へ移行することを推奨。

途中再開
- 再起動時は DB の `updated_at` を見て再処理対象を決定するため途中再開が可能。

ログ・失敗管理
- 成功/失敗を `instance/` 下のログファイルに記録。
- 失敗ファイルは `instance/failed_rise_prob_files.log` に追記。

テスト計画
- 小さなモック pickle を用意し、1ファイル処理で期待される DB の値が格納される単体テストを作成。
- updated_at によるスキップ判定、壊れた pickle の挙動をテスト。

マイグレーションについて
- 既に `migrations/versions/3a7feb27002f_add_rise_probability_summary.py` が存在するので、まず現状のマイグレーション内容を確認（auc カラムがあるか）。
- もし auc カラムが無ければ、新規マイグレーションで `ALTER TABLE rise_probability_summary ADD COLUMN auc_model1 REAL, ...` を追加する。

TODO（実装時の作業リスト）
1. マイグレーションの確認・必要なら新規マイグレーション作成
2. `scripts/update_rise_probability.py` を作成（portalocker を用いた排他制御、1ファイルずつ upsert、メモリ解放）
3. `app/admin` の管理画面から非同期にジョブを起動する仕組みを実装（RQ/Celery or background thread with caveats）
4. ユニットテスト作成
5. requirements.txt に `portalocker`, `scikit-learn` を追加（未導入なら）

付録: pickle -> DB マッピング
- pickle 内に直接確率と auc がある場合:
	- prob_model1 = obj['logistic'] など
	- auc_model1 = obj['auc']['logistic'] など
- pickle 内に raw predictions と真ラベルがある場合:
	- auc = roc_auc_score(y_true, y_score)

---
作成日: 2025-10-29
作成者: 開発ドキュメント自動生成

