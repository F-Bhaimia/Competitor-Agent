# Remove existing task if it exists
Unregister-ScheduledTask -TaskName "Competitor Agent Weekly Scan" -Confirm:$false -ErrorAction SilentlyContinue

# Create new scheduled task for Monday 10 AM
$action = New-ScheduledTaskAction -Execute "C:\Users\fbhaimia\OneDrive - MemberSolutions\Desktop\AI Mandy\Competitor-Agent-FRESH\scheduled_scan.bat" -WorkingDirectory "C:\Users\fbhaimia\OneDrive - MemberSolutions\Desktop\AI Mandy\Competitor-Agent-FRESH"
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 10:00AM
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName "Competitor Agent Weekly Scan" -Action $action -Trigger $trigger -Settings $settings -Description "Weekly scan of competitor websites for updates"

Write-Host "Scheduled task created: Monday 10:00 AM"
