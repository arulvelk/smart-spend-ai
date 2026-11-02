output "dataset" {
  value = "${var.project_id}.${google_bigquery_dataset.smartspend.dataset_id}"
}

output "receipts_bucket" {
  value = google_storage_bucket.receipts.name
}

output "artifact_registry" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.containers.repository_id}"
}

output "service_accounts" {
  value = {
    api       = google_service_account.api.email
    ui        = google_service_account.ui.email
    jobs      = google_service_account.jobs.email
    scheduler = google_service_account.scheduler.email
    build     = google_service_account.build.email
  }
}

output "alerts_topic" {
  value = google_pubsub_topic.alerts.id
}
