# netaichi

ネットあいち（愛知県施設予約システム）のテニスコート自動抽選・予約管理ボット。

## セットアップ

```powershell
poetry install
```

1. `.env` を作成（`.env.example` 参照）
2. Google スプレッドシート用の認証情報を `config/json/` に配置
3. DB初期化: `poetry run python main.py init`

## コマンド

| コマンド | 内容 |
|---------|------|
| `poetry run python main.py init` | DBを初期化しスプレッドシートからアカウントを取り込む |
| `poetry run python main.py o` | oguriグループの抽選申込を実行 |
| `poetry run python main.py k` | komadaグループの抽選申込を実行 |
| `poetry run python main.py r` | 予約情報を収集しスプレッドシートに反映 |

※ CLIはリファクタリングで `python -m netaichi <command>` 形式に移行予定。
