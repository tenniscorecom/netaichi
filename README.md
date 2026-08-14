# netaichi

ネットあいち（愛知県施設予約システム）のテニスコート自動抽選・予約管理ボット。

## セットアップ

```powershell
poetry install --no-root
```

1. `.env` を作成（`.env.example` 参照）
2. Google スプレッドシート用の認証情報を `config/json/authorized_user.json` に配置
3. DB初期化: `poetry run python -m netaichi init`

## コマンド

| コマンド | 内容 |
|---------|------|
| `poetry run python -m netaichi init` | DBを初期化しスプレッドシートからアカウントを取り込む |
| `poetry run python -m netaichi lottery oguri` | oguriグループの抽選申込を実行 |
| `poetry run python -m netaichi lottery komada` | komadaグループの抽選申込を実行 |
| `poetry run python -m netaichi lottery oguri --dry-run` | 確認画面まで進むが確定しない（動作確認用） |
| `poetry run python -m netaichi reserve` | 予約情報を収集しスプレッドシートに反映 |
| `poetry run python -m netaichi availability` | 空き状況をチェックし新規の空きをDiscordに通知 |
| `poetry run python -m netaichi availability --no-notify` | 通知せず結果表示のみ（動作確認用） |
| `poetry run python -m netaichi swap` | 予約済みの枠をより良い番号のコートへ移動 |
| `poetry run python -m netaichi swap --dry-run` | 移動候補の表示のみ（移動しない） |
| `poetry run python -m netaichi shrink` | 参加人数に対して多すぎるコートを取消（2面→1面など） |
| `poetry run python -m netaichi shrink --dry-run` | 検出のみ（取り消さない） |
| `poetry run python -m netaichi bear` | 予約確定分の募集をテニスベアに作成 |
| `poetry run python -m netaichi bear --submit` | 確認モードを無視して確定まで実行 |

## テニスベア募集の自動作成

`rules/bear_rules.yaml` で設定。「過去のイベントをコピー」機能を使い、
コピー元と同じコートの過去イベントを選んで**日時（開始・終了・申込期限）だけ差し替える**。
タイトル・説明・料金・キャンセル規定はコピー元から引き継がれる。

- 4時間の予約は2時間×2枠のイベントに分割される
- 掲載済みの枠は `T_BearPost` テーブルで管理し二重掲載しない
- `submit: false`（確認モード）の間はフォーム入力まで行い確定ボタンを押さない

## コート乗り換え

抽選で当たったコートは番号を選べないため、予約済みの枠と同じ日時により良い番号が
空いていたら移動する。優先順位は `rules/swap_rules.yaml` で宣言する。

**必ず「移動先を予約 → 予約一覧で成功を確認 → 元を取消」の順で実行する。**
逆順にすると取り直しに失敗したとき枠そのものを失う。

- 空きが予約時間を**完全に覆うときだけ**移動する（部分的だと枠が分断されるため）
- 取消期限（前日15時）を過ぎると取消だけ失敗して2面持ちになるので、
  `min_days_ahead` より手前の日は対象にしない
- 元の取消に失敗した場合は自動で復旧せず、取り消すべき面を明記して Discord に通知する

## 多すぎるコートの取消（shrink）

2面取ってあっても参加人数が少なければ1面で足りる。余った面を `rules/shrink_rules.yaml`
の基準で取り消す。

- レッスンは何人来ても1面。練習会は**夏（7・8月）は4人／それ以外は3人**で1面
- 4時間の予約に2時間の募集が並ぶ場合、**時間帯ごとに数えて多い方**に合わせる
- 残す面は `swap_rules.yaml` の優先順位に従い、ブロックの端の面を残す
- 募集が出ていない枠は判断材料がないので触らない
- **1面しかない枠と、必要面数が0になる枠（集客0・自分のみ）は対象外**。
  全面取消は `cancel` が募集削除・部分予約の取り直しまで含めて処理するので、
  shrink が先に消すと二重取消になる。shrink は「最低1面は残す」場合だけ扱う

参加人数は募集をまたいで合計する。主催者が複数の募集で重複して数えられていても、
面が多めに残る側に倒れるので練習場所が足りなくなることはない。
実際の人数と必要面数はログに出るので、ずれていれば YAML の人数を調整する。

## 空き状況チェックの定期実行

チェック条件は `rules/availability_rules.yaml` で設定する。

Windowsタスクスケジューラへの登録例（毎時0分に実行）:

```powershell
$action = New-ScheduledTaskAction -Execute "F:\dev\netaichi\.venv\Scripts\python.exe" `
    -Argument "-m netaichi availability" -WorkingDirectory "F:\dev\netaichi"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName "netaichi-availability" -Action $action -Trigger $trigger
```

## 抽選申込ルール

どのコートをどの時間帯で申し込むかは `rules/lottery_rules.yaml` で宣言する。
コードを変更せずにルールを追加・変更できる。

```yaml
groups:
  oguri:
    players: 4
    rules:
      - name: 土日祝の昼
        days: weekend_holiday        # 土日祝
        times: [[9, 13], [13, 17]]
        amount: 1
        courts: ["130", "180"]       # 130=大高緑地 180=小幡緑地
```

## テスト

```powershell
poetry run python -m pytest tests/
```

ルール→申込データ生成のロジックはSelenium不要でテストできる。

## 構成

```
netaichi/
  __main__.py   # CLI
  config.py     # 設定（認証情報は.envから）
  browser/      # Selenium操作（chrome.py=汎用、netaichi.py=サイト固有、pages/=画面操作）
  db/           # SQLModelモデルとDB接続
  services/     # 業務ロジック（lottery=抽選申込、reserve=予約収集）
  helper/       # ログ・スプレッドシート等
rules/          # 申込ルール（YAML）
tests/          # ユニットテスト
```
