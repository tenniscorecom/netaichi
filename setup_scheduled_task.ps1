# ネットあいち空き状況チェックの定期実行をタスクスケジューラに登録する
# 実行方法: このファイルを右クリック→「PowerShellで実行」
#           またはPowerShellで .\setup_scheduled_task.ps1

$action = New-ScheduledTaskAction -Execute "F:\dev\netaichi\.venv\Scripts\python.exe" `
    -Argument "-m netaichi availability --headless" -WorkingDirectory "F:\dev\netaichi"

# 毎時0分から1時間おきに実行（10年間 ≒ 実質無期限）
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date `
    -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650)

# ReCAPTCHA等で止まった場合に備えて30分でタイムアウト
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -StartWhenAvailable

Register-ScheduledTask -TaskName "netaichi-availability" -Action $action -Trigger $trigger `
    -Settings $settings -Description "ネットあいち空き状況チェック（毎時）→Discord通知" -Force

Get-ScheduledTask -TaskName "netaichi-availability" | Select-Object TaskName, State
Write-Host "空きチェック登録完了。毎時0分に実行され、新しい空きがあればDiscordに通知されます。"

# 旧タスク（cancel単体）が残っていれば削除する
try { Unregister-ScheduledTask -TaskName "netaichi-cancel" -Confirm:$false -ErrorAction Stop } catch {}

# 毎日の処理（毎日 朝9時）: prune（練習埋まりでレッスン削除）→ cancel（0人でコート取消）
$actionDaily = New-ScheduledTaskAction -Execute "F:\dev\netaichi\.venv\Scripts\python.exe" `
    -Argument "-m netaichi daily --headless" -WorkingDirectory "F:\dev\netaichi"

$triggerDaily = New-ScheduledTaskTrigger -Daily -At 9:00AM

$settingsDaily = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -StartWhenAvailable

Register-ScheduledTask -TaskName "netaichi-daily" -Action $actionDaily -Trigger $triggerDaily `
    -Settings $settingsDaily -Description "毎日朝9時: 練習埋まりでレッスン削除→翌日0人でコート取消＋募集削除→Discord通知" -Force

Get-ScheduledTask -TaskName "netaichi-daily" | Select-Object TaskName, State
Write-Host "毎日処理の登録完了。毎日朝9時に prune→cancel を実行します。"

# 定刻ダイジェストの自動通知は行わない方針（直近の通知は availability-soon が担当）。
# 2ヶ月先までの一覧が見たいときは能動的に `python -m netaichi digest` を実行する。
# 以前登録した定刻タスクが残っていれば削除する。
try { Unregister-ScheduledTask -TaskName "netaichi-digest" -Confirm:$false -ErrorAction Stop } catch {}
