<#
.SYNOPSIS
  Build the API + agent image with Cloud Build and deploy it to Cloud Run, then smoke-test it.

.EXAMPLE
  ./scripts/deploy_api.ps1 -ProjectId smartspend-ai-123456
#>
param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$Region = "us-central1",
    [string]$GeminiModel = "gemini-3.8-flash",
    [string]$GeminiLocation = "global",
    [switch]$SkipSmokeTest
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

function Invoke-Step([scriptblock]$Cmd) {
    & $Cmd
    if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code ${LASTEXITCODE}: $Cmd" }
}

$Image = "$Region-docker.pkg.dev/$ProjectId/smartspend/api:$(Get-Date -Format 'yyyyMMdd-HHmmss')"
$BuildSa = "projects/$ProjectId/serviceAccounts/smartspend-build@$ProjectId.iam.gserviceaccount.com"
$ApiSa = "smartspend-api@$ProjectId.iam.gserviceaccount.com"

Push-Location $Root
try {
    Write-Host "==> Building $Image with Cloud Build"
    Invoke-Step {
        gcloud builds submit . --project $ProjectId --region $Region `
            --config api/cloudbuild.yaml --substitutions "_IMAGE=$Image" `
            --service-account $BuildSa --default-buckets-behavior regional-user-owned-bucket
    }

    Write-Host "==> Deploying smartspend-api to Cloud Run"
    $envVars = @(
        "GCP_PROJECT=$ProjectId", "BQ_DATASET=smartspend", "GEMINI_MODEL=$GeminiModel",
        "GEMINI_LOCATION=$GeminiLocation", "RECEIPTS_BUCKET=$ProjectId-smartspend-receipts"
    ) -join ","
    Invoke-Step {
        gcloud run deploy smartspend-api --project $ProjectId --region $Region --image $Image `
            --service-account $ApiSa --no-allow-unauthenticated `
            --set-env-vars $envVars `
            --cpu 1 --memory 1Gi --concurrency 20 --timeout 120 `
            --min-instances 0 --max-instances 2
    }
} finally {
    Pop-Location
}

$Url = (gcloud run services describe smartspend-api --project $ProjectId --region $Region --format "value(status.url)")
Write-Host "`nDeployed: $Url"
if ($SkipSmokeTest) { return }

Write-Host "==> Smoke test (authenticated with your gcloud identity)"
$Headers = @{ Authorization = "Bearer $(gcloud auth print-identity-token)" }
Invoke-RestMethod "$Url/healthz" -Headers $Headers | ConvertTo-Json
Write-Host "--> Categorizing pending transactions with Gemini"
Invoke-RestMethod "$Url/categorize?limit=200" -Method Post -Headers $Headers | ConvertTo-Json -Depth 4
Write-Host "--> Categorizer accuracy vs. ground truth"
Invoke-RestMethod "$Url/categorize/accuracy" -Headers $Headers | ConvertTo-Json -Depth 4
Write-Host "--> Asking the advisor"
$body = @{ message = "Am I over budget anywhere this month, and where should I cut back?" } | ConvertTo-Json
(Invoke-RestMethod "$Url/chat" -Method Post -Headers $Headers -ContentType "application/json" -Body $body).answer
Write-Host "`nTry it in the browser:  gcloud run services proxy smartspend-api --project $ProjectId --region $Region --port 8080"
Write-Host "then open http://localhost:8080/docs"
