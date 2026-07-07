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

# 定刻ダイジェスト（毎日 朝5時）: 保存済みの最新空き状況をまとめて1通通知する。
# 空き確認（availabilityの各タスク/GitHub Actions）が裏でシートを更新している前提。
# 読み取り＋送信だけなので一瞬で終わり、5:00にほぼ正確に届く。時刻を変えるなら下の -At を編集する。
$actionDigest = New-ScheduledTaskAction -Execute "F:\dev\netaichi\.venv\Scripts\python.exe" `
    -Argument "-m netaichi digest" -WorkingDirectory "F:\dev\netaichi"

$triggerDigest = New-ScheduledTaskTrigger -Daily -At 5:00AM

$settingsDigest = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -StartWhenAvailable

Register-ScheduledTask -TaskName "netaichi-digest" -Action $actionDigest -Trigger $triggerDigest `
    -Settings $settingsDigest -Description "毎朝5時: 保存済みの最新空き状況をまとめてDiscordに定刻通知" -Force

Get-ScheduledTask -TaskName "netaichi-digest" | Select-Object TaskName, State
Write-Host "定刻ダイジェストの登録完了。毎朝5:00ちょうどに現在の空き一覧を通知します。"
