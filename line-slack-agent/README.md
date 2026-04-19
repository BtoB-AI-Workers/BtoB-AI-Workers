# line-slack-agent

LINE↔Slack連携Bot（Zapier）経由で、BtoB AI Workers事業の案件投稿・候補者返信を自動化するエージェント。

## 現状: 骨組み実装中（Phase 0）

- プラン: `C:\Users\hi200\.claude\plans\mutable-conjuring-pike.md`
- codex-reviewゲート通過済み（`ok: true`、3反復）
- ディレクトリ構成・config雛形・主要モジュール骨が投入済み

## アーキテクチャ（要点）

```
[Slack @claude メンション / Zapier投稿]
  → 署名検証/timestamp/allowlist
  → SQLite TXN: dedupe_ledger claim + inbox insert
  → COMMIT → ack() (<100ms)
  → Worker lease
  → killswitch照会
  → claude -p headless (読み取り専用、sandbox cwd、JSON出力)
  → Python決定論ラッパー: L1 NG / L2 intent / L3 scope / L6 schema / killswitch / L5 allowlist
  → Slack WebClient送信 (Zapier経由でLINEへ転送)
  → Sheets 業務DB + audit_log
```

## ディレクトリ構成

- `config/` — ガードレール・allowlist・閾値（Git管理、エンジニア編集）
- `knowledge/` — Drive→GitHub同期先のミラー（業務担当がDriveで編集、readonly）
- `src/webhook/` — Slack Bolt受信、署名検証、dedupe_ledger、3秒ACK
- `src/worker/` — SQLiteキューlease、`claude -p` 起動、決定論送信
- `src/guardrails/` — L1-L6 ガードレール
- `src/intent/` — 意図分類（Phase 1はjob_classifierのみ、Phase 2でフルclassifier）
- `src/db/` — SQLite/Sheets クライアント
- `prompts/` — Claude Code headless用プロンプト
- `scripts/` — 初期化・同期Bot・評価スクリプト
- `tests/` — unit test / fixtures
- `sandbox/` — Claude Code cwd（knowledgeコピーのみ配置）

## Phase 0（Phase 1開始ゲート）

ユーザー側作業:
- [ ] GitHub private repo 新設、`line-slack-agent/` をpush
- [ ] Slack で `#agent-audit` 新設、BotをInviteできる状態に
- [ ] Slack App 作成（Events API、chat:write、channels:history、reactions:read）
- [ ] Zapier の Slack→LINE フィルタを「bot投稿のみ転送」に変更
- [ ] Google Sheets 新規スプレッドシート作成、service_account に編集権限付与
- [ ] `tests/fixtures/slack_events/` に実イベントJSONを10件以上収集

Claude側作業（完了済み）:
- [x] ディレクトリ構成、`pyproject.toml`、`.env.example`、config/*.yaml 雛形
- [x] `src/webhook/verify.py` + tests
- [x] `src/webhook/dedupe_ledger.py` + tests
- [x] `src/worker/queue_sqlite.py`
- [x] `src/guardrails/l1_ngword.py` + tests
- [x] `src/guardrails/l4_killswitch.py` + tests
- [x] `src/guardrails/l5_send_allowlist.py`
- [x] `src/worker/output_schema.py`（Claude出力JSON厳格検証、Layer6）
- [x] `src/intent/job_classifier.py`（Phase 1案件投稿専用L2）
- [x] `prompts/system_guardrails.md`、`prompts/job_posting.md`
- [x] `scripts/init_sqlite.py`
- [x] `scripts/sync_drive_to_github.py`（Drive→GitHub片方向同期）

Claude側作業（Phase 1 Week 1残り）:
- [ ] `src/webhook/app.py`（Slack Bolt、署名検証→SQLite TXN→ack）
- [ ] `src/worker/runner.py`（claude -p subprocess、sandbox cwd）
- [ ] `src/worker/deterministic_sender.py`（Python側送信、全ガードレール再検証）
- [ ] `src/db/sheets_client.py`（既存 `scripts/append_to_sheet.py` 設計流用）
- [ ] `src/db/jobs_repo.py`、`src/db/audit_log_repo.py`

## セットアップ（Phase 0完了後）

```bash
cd line-slack-agent
pip install -e ".[dev]"
cp .env.example .env
# .env を編集してトークン・ID類を設定
python scripts/init_sqlite.py
python scripts/init_sheets.py  # Phase 1 Week 2で実装予定
pytest
```

## 運用モード

- `AGENT_MODE=dry_run`（既定）: 本番送信を全停止、DMドラフトのみ
- `AGENT_MODE=production`: dry-runゲート通過＋L2評価パス後に解放
