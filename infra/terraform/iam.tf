# One least-privilege service account per runtime.
resource "google_service_account" "api" {
  account_id   = "smartspend-api"
  display_name = "SmartSpend API + agent (Cloud Run)"
  depends_on   = [google_project_service.enabled]
}

resource "google_service_account" "ui" {
  account_id   = "smartspend-ui"
  display_name = "SmartSpend UI (Cloud Run)"
  depends_on   = [google_project_service.enabled]
}

resource "google_service_account" "jobs" {
  account_id   = "smartspend-jobs"
  display_name = "SmartSpend scheduled jobs (Cloud Functions)"
  depends_on   = [google_project_service.enabled]
}

resource "google_service_account" "scheduler" {
  account_id   = "smartspend-scheduler"
  display_name = "Cloud Scheduler invoker"
  depends_on   = [google_project_service.enabled]
}

locals {
  data_writers = {
    api  = google_service_account.api.member
    jobs = google_service_account.jobs.member
  }
}

# Run BigQuery jobs and call Gemini on Vertex AI.
resource "google_project_iam_member" "bq_job_user" {
  for_each = local.data_writers
  project  = var.project_id
  role     = "roles/bigquery.jobUser"
  member   = each.value
}

resource "google_project_iam_member" "vertex_user" {
  for_each = local.data_writers
  project  = var.project_id
  role     = "roles/aiplatform.user"
  member   = each.value
}

# Read/write only the SmartSpend dataset.
resource "google_bigquery_dataset_iam_member" "data_editor" {
  for_each   = local.data_writers
  dataset_id = google_bigquery_dataset.smartspend.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = each.value
}

resource "google_storage_bucket_iam_member" "receipts_rw" {
  bucket = google_storage_bucket.receipts.name
  role   = "roles/storage.objectAdmin"
  member = google_service_account.api.member
}

resource "google_pubsub_topic_iam_member" "jobs_publish_alerts" {
  topic  = google_pubsub_topic.alerts.name
  role   = "roles/pubsub.publisher"
  member = google_service_account.jobs.member
}

# Cloud Build runs as its own service account (new projects no longer get a
# privileged default build identity). Used by scripts/deploy_*.ps1.
resource "google_service_account" "build" {
  account_id   = "smartspend-build"
  display_name = "SmartSpend Cloud Build"
  depends_on   = [google_project_service.enabled]
}

resource "google_project_iam_member" "build_roles" {
  for_each = toset([
    "roles/artifactregistry.writer", # push images
    "roles/logging.logWriter",       # build logs
    "roles/storage.objectViewer",    # read uploaded source from the build bucket
  ])
  project = var.project_id
  role    = each.value
  member  = google_service_account.build.member
}
