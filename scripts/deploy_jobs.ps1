<#
.SYNOPSIS
  Deploy the daily Cloud Function and its Cloud Scheduler trigger, wire up
  service-to-service auth, then run the job once (which also catches up any missed days).

.EXAMPLE
  ./scripts/deploy_jobs.ps1 -ProjectId smartspend-ai-123456
#>
param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$Region = "us-central1",
    [string]$Schedule = "0 6 * * *",
    [string]$TimeZone = "America/Los_Angeles",
    [switch]$SkipRun
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

function Invoke-Step([scriptblock]$Cmd) {
    & $Cmd
    if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code ${LASTEXITCODE}: $Cmd" }
}

$Fn = "smartspend-daily-job"
$JobsSa = "smartspend-jobs@$ProjectId.iam.gserviceaccount.com"
$SchedulerSa = "smartspend-scheduler@$ProjectId.iam.gserviceaccount.com"
$BuildSa = "projects/$ProjectId/serviceAccounts/smartspend-build@$ProjectId.iam.gserviceaccount.com"

$ApiUrl = (gcloud run services describe smartspend-api --project $ProjectId --region $Region --format "value(status.url)")
if (-not $ApiUrl) { throw "smartspend-api is not deployed yet. Run ./scripts/deploy_api.ps1 first." }

Write-Host "==> Allowing the job's service account to call the private API"
Invoke-Step {
    gcloud run services add-iam-policy-binding smartspend-api --project $ProjectId --region $Region `
        --member "serviceAccount:$JobsSa" --role roles/run.invoker --quiet | Out-Null
}

# The function needs the shared generator package next to its own code.
$Src = Join-Path ([System.IO.Path]::GetTempPath()) "smartspend-fn-$(Get-Random)"
New-Item -ItemType Directory $Src | Out-Null
Copy-Item "$Root/functions/daily_job/*" $Src -Recurse
Copy-Item "$Root/data/smartspend_data" "$Src/smartspend_data" -Recurse
Get-ChildItem $Src -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force

try {
    Write-Host "==> Deploying Cloud Function $Fn"
    Invoke-Step {
        gcloud functions deploy $Fn --gen2 --project $ProjectId --region $Region `
            --runtime python312 --source $Src --entry-point daily_job --trigger-http --no-allow-unauthenticated `
            --service-account $JobsSa --build-service-account $BuildSa `
            --set-env-vars "GCP_PROJECT=$ProjectId,BQ_DATASET=smartspend,API_URL=$ApiUrl,ALERTS_TOPIC=smartspend-alerts" `
            --memory 512Mi --timeout 300s --max-instances 1
    }
} finally {
    Remove-Item $Src -Recurse -Force
}

$FnUrl = (gcloud functions describe $Fn --gen2 --project $ProjectId --region $Region --format "value(serviceConfig.uri)")

Write-Host "==> Allowing Cloud Scheduler to invoke the function"
Invoke-Step {
    gcloud functions add-invoker-policy-binding $Fn --project $ProjectId --region $Region `
        --member "serviceAccount:$SchedulerSa" | Out-Null
}

Write-Host "==> Scheduling it: '$Schedule' ($TimeZone)"
$schedulerArgs = @("--project", $ProjectId, "--location", $Region, "--schedule", $Schedule, "--time-zone", $TimeZone,
    "--uri", $FnUrl, "--http-method", "POST", "--oidc-service-account-email", $SchedulerSa,
    "--oidc-token-audience", $FnUrl, "--attempt-deadline", "320s")
# `list` instead of `describe`: Windows PowerShell treats a native command's stderr as a
# terminating error under $ErrorActionPreference = "Stop", so a "not found" would abort the script.
$existing = gcloud scheduler jobs list --project $ProjectId --location $Region --format "value(name)" |
    Where-Object { $_ -like "*/jobs/$Fn" }
if ($existing) {
    Invoke-Step { gcloud scheduler jobs update http $Fn @schedulerArgs }
} else {
    Invoke-Step { gcloud scheduler jobs create http $Fn @schedulerArgs }
}

if ($SkipRun) { return }
Write-Host "==> Running the job now (catches up any days since the last load)"
$Headers = @{ Authorization = "Bearer $(gcloud auth print-identity-token)" }
Invoke-RestMethod $FnUrl -Method Post -Headers $Headers -TimeoutSec 320 | ConvertTo-Json -Depth 5
