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

# 集客0レッスンのコート取消（毎日 朝9時）
$actionCancel = New-ScheduledTaskAction -Execute "F:\dev\netaichi\.venv\Scripts\python.exe" `
    -Argument "-m netaichi cancel --headless" -WorkingDirectory "F:\dev\netaichi"

$triggerCancel = New-ScheduledTaskTrigger -Daily -At 9:00AM

$settingsCancel = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -StartWhenAvailable

Register-ScheduledTask -TaskName "netaichi-cancel" -Action $actionCancel -Trigger $triggerCancel `
    -Settings $settingsCancel -Description "翌日の集客0レッスンのコート取消＋テニスベア募集削除→Discord通知" -Force

Get-ScheduledTask -TaskName "netaichi-cancel" | Select-Object TaskName, State
Write-Host "コート取消登録完了。毎日朝9時に翌日の集客0レッスンを取消します。"
