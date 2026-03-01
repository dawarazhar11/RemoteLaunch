# Create scheduled task for RemoteLaunch Agent auto-start
Unregister-ScheduledTask -TaskName "RemoteLaunch Agent" -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute "python" -Argument "E:\RemoteLaunch\windows_agent.py"
$trigger = New-ScheduledTaskTrigger -AtLogon
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask -TaskName "RemoteLaunch Agent" -Action $action -Trigger $trigger -RunLevel Highest -Settings $settings -Description "RemoteLaunch Windows Agent - serves app list and handles file uploads on port 7891"

Write-Host "Scheduled task created successfully" -ForegroundColor Green
