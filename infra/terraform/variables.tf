variable "project_id" {
  description = "Existing GCP project id (create it with gcloud first, see README)."
  type        = string
}

variable "region" {
  description = "Region for Cloud Run, Functions, Scheduler, Artifact Registry and Vertex AI."
  type        = string
  default     = "us-central1"
}

variable "bq_location" {
  description = "BigQuery dataset location."
  type        = string
  default     = "US"
}

variable "dataset_id" {
  description = "BigQuery dataset that holds all SmartSpend tables."
  type        = string
  default     = "smartspend"
}

variable "billing_account_id" {
  description = "Billing account id (XXXXXX-XXXXXX-XXXXXX). Leave empty to skip creating the budget alert."
  type        = string
  default     = ""
}

variable "budget_amount_usd" {
  description = "Monthly budget that triggers email alerts at 50%, 90% and 100%."
  type        = number
  default     = 50
}

variable "deletion_protection" {
  description = "Protect BigQuery tables from terraform destroy. Off by default for a portfolio project."
  type        = bool
  default     = false
}
