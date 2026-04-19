# BtoB-AI-Workers

BtoB AI Workers事業の業務自動化モノレポ。

## 構成

```
BtoB-AI-Workers/
├── line-slack-agent/     # LINE↔Slack連携Bot経由の案件投稿・候補者返信自動化
├── knowledge/            # Google Drive同期先（業務ナレッジのミラー、readonly）
└── .gitignore
```

## 各自動化

### line-slack-agent（Phase 0 骨組み実装中）

LINE公式アカウント↔Slack連携Bot（Zapier）経由で、案件投稿と候補者返信を完全自動化するエージェント。詳細は [`line-slack-agent/README.md`](line-slack-agent/README.md) 参照。

- 設計: `C:\Users\hi200\.claude\plans\mutable-conjuring-pike.md`
- codex-review ゲート通過済み（`ok: true`、3反復）

## knowledge/ の運用（パターンA: Drive→GitHub片方向同期）

- **source of truth**: Google Drive `BtoB-AI-Workers-Knowledge/`（業務担当編集）
- このrepoの `knowledge/` は Drive 同期先の **readonly ミラー**
- 同期Bot: `line-slack-agent/scripts/sync_drive_to_github.py`

GitHub側のknowledge/を直接編集しないこと。Driveを正本として編集→同期Botが反映。

## セットアップ

各自動化のREADMEを参照。Python環境は自動化ごとに独立（`pyproject.toml`）。

## 運用規則

- 機密情報（`.env`、`service_account.json`、DB本体）は絶対にコミットしない（`.gitignore` で除外済み）
- ガードレール系YAML（`config/*.yaml`）の変更はPRレビュー必須
- 本番送信ゲート（`AGENT_MODE=production`）はテスト・評価fixtureの合格後のみ解放
