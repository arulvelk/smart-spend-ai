<#
.SYNOPSIS
  One-time GCP setup for SmartSpend AI: Terraform infra, synthetic data, BigQuery load.

.EXAMPLE
  ./scripts/bootstrap.ps1 -ProjectId smartspend-ai-123456 -BillingAccount XXXXXX-XXXXXX-XXXXXX

.EXAMPLE
  # Apply infrastructure changes only; keep the data already in BigQuery.
  ./scripts/bootstrap.ps1 -ProjectId smartspend-ai-123456 -BillingAccount XXXXXX-XXXXXX-XXXXXX -SkipData
#>
param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$BillingAccount = "",
    [string]$Region = "us-central1",
    [int]$BudgetUsd = 50,
    [switch]$SkipData
)
$ErrorActionPreference = "Stop"

# Native commands (gcloud, terraform, uv) don't throw on failure; stop on non-zero exit codes.
function Invoke-Step([scriptblock]$Cmd) {
    & $Cmd
    if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code ${LASTEXITCODE}: $Cmd" }
}
$Root = Split-Path -Parent $PSScriptRoot

foreach ($tool in "gcloud", "terraform", "uv") {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "$tool is not installed. See README > Prerequisites."
    }
}

Write-Host "==> Pointing gcloud and Application Default Credentials at $ProjectId"
Invoke-Step { gcloud config set project $ProjectId }

Write-Host "==> Enabling the APIs Terraform itself needs (new projects start with these off)"
Invoke-Step { gcloud services enable cloudresourcemanager.googleapis.com serviceusage.googleapis.com billingbudgets.googleapis.com --project $ProjectId }
Invoke-Step { gcloud auth application-default set-quota-project $ProjectId }

Write-Host "==> Terraform: APIs, BigQuery, bucket, Artifact Registry, service accounts, budget"
# Saved (gitignored) so later `terraform apply` runs and deploy scripts reuse the same values.
@"
project_id         = "$ProjectId"
region             = "$Region"
billing_account_id = "$BillingAccount"
budget_amount_usd  = $BudgetUsd
"@ | Set-Content -Encoding ascii "$Root/infra/terraform/terraform.tfvars"
Invoke-Step { terraform -chdir="$Root/infra/terraform" init -input=false }
Invoke-Step { terraform -chdir="$Root/infra/terraform" apply -auto-approve -input=false }

if ($SkipData) {
    Write-Host "`nInfrastructure updated; data left as is (-SkipData)."
    return
}

Write-Host "==> Generating synthetic data"
Push-Location "$Root/data"
try {
    Invoke-Step { uv sync }
    Invoke-Step { uv run python generate.py }
    Write-Host "==> Loading BigQuery and uploading sample receipts"
    Invoke-Step { uv run python load_bigquery.py --project $ProjectId }
} finally {
    Pop-Location
}

Write-Host "`nDone. Open BigQuery: https://console.cloud.google.com/bigquery?project=$ProjectId"
