# Windows Task Scheduler setup for automatic git pull
# Run this script once (as Administrator) to register the scheduled task.
# The task will run git pull daily at 07:00 in the dashboard repo directory.

$repoPath = Split-Path -Parent $MyInvocation.MyCommand.Definition
$taskName = "GasDashboard_GitPull"
$action   = New-ScheduledTaskAction `
    -Execute "git" `
    -Argument "pull" `
    -WorkingDirectory $repoPath

# Change -At and -RepetitionInterval to suit your update frequency.
$trigger  = New-ScheduledTaskTrigger -Daily -At "07:00"

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName  $taskName `
    -Action    $action `
    -Trigger   $trigger `
    -Settings  $settings `
    -RunLevel  Highest `
    -Force

Write-Host "Scheduled task '$taskName' registered. Runs daily at 07:00 in:"
Write-Host "  $repoPath"
Write-Host ""
Write-Host "To run immediately:  Start-ScheduledTask -TaskName '$taskName'"
Write-Host "To remove the task:  Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false"
