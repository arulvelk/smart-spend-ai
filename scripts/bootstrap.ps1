<#
.SYNOPSIS
  One-time GCP setup for SmartSpend AI: Terraform infra, synthetic data, BigQuery load.

.EXAMPLE
  ./scripts/bootstrap.ps1 -ProjectId smartspend-ai-123456 -BillingAccount XXXXXX-XXXXXX-XXXXXX
#>
param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$BillingAccount = "",
    [string]$Region = "us-central1",
    [int]$BudgetUsd = 50
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

foreach ($tool in "gcloud", "terraform", "uv") {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "$tool is not installed. See README > Prerequisites."
    }
}

Write-Host "==> Pointing gcloud and Application Default Credentials at $ProjectId"
gcloud config set project $ProjectId
gcloud auth application-default set-quota-project $ProjectId

Write-Host "==> Terraform: APIs, BigQuery, bucket, Artifact Registry, service accounts, budget"
terraform -chdir="$Root/infra/terraform" init -input=false
terraform -chdir="$Root/infra/terraform" apply -auto-approve `
    -var "project_id=$ProjectId" `
    -var "region=$Region" `
    -var "billing_account_id=$BillingAccount" `
    -var "budget_amount_usd=$BudgetUsd"

Write-Host "==> Generating synthetic data"
Push-Location "$Root/data"
try {
    uv sync
    uv run python generate.py
    Write-Host "==> Loading BigQuery and uploading sample receipts"
    uv run python load_bigquery.py --project $ProjectId
} finally {
    Pop-Location
}

Write-Host "`nDone. Open BigQuery: https://console.cloud.google.com/bigquery?project=$ProjectId"
