<#
.SYNOPSIS
  Build the Next.js UI with Cloud Build and deploy it to Cloud Run as a public site
  that calls the private API with its own service account.

.EXAMPLE
  ./scripts/deploy_ui.ps1 -ProjectId smartspend-ai-123456 -DemoPassword "pick-something"
#>
param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$Region = "us-central1",
    [string]$DemoPassword = ""
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

function Invoke-Step([scriptblock]$Cmd) {
    & $Cmd
    if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code ${LASTEXITCODE}: $Cmd" }
}

$Image = "$Region-docker.pkg.dev/$ProjectId/smartspend/ui:$(Get-Date -Format 'yyyyMMdd-HHmmss')"
$BuildSa = "projects/$ProjectId/serviceAccounts/smartspend-build@$ProjectId.iam.gserviceaccount.com"
$UiSa = "smartspend-ui@$ProjectId.iam.gserviceaccount.com"

$ApiUrl = (gcloud run services describe smartspend-api --project $ProjectId --region $Region --format "value(status.url)")
if (-not $ApiUrl) { throw "smartspend-api is not deployed yet. Run ./scripts/deploy_api.ps1 first." }

Write-Host "==> Allowing the UI's service account to call the private API"
Invoke-Step {
    gcloud run services add-iam-policy-binding smartspend-api --project $ProjectId --region $Region `
        --member "serviceAccount:$UiSa" --role roles/run.invoker --quiet | Out-Null
}

Push-Location $Root
try {
    Write-Host "==> Building $Image with Cloud Build"
    Invoke-Step {
        gcloud builds submit ui --project $ProjectId --region $Region `
            --config ui/cloudbuild.yaml --substitutions "_IMAGE=$Image" `
            --service-account $BuildSa --default-buckets-behavior regional-user-owned-bucket
    }
} finally {
    Pop-Location
}

Write-Host "==> Deploying smartspend-ui"
$envVars = "API_URL=$ApiUrl"
if ($DemoPassword) { $envVars += ",DEMO_PASSWORD=$DemoPassword" }
Invoke-Step {
    gcloud run deploy smartspend-ui --project $ProjectId --region $Region --image $Image `
        --service-account $UiSa --allow-unauthenticated `
        --set-env-vars $envVars `
        --cpu 1 --memory 512Mi --concurrency 40 --timeout 120 `
        --min-instances 0 --max-instances 2
}

$Url = (gcloud run services describe smartspend-ui --project $ProjectId --region $Region --format "value(status.url)")
Write-Host "`nSmartSpend UI: $Url"
if ($DemoPassword) { Write-Host "Sign in with any username and the demo password." }
