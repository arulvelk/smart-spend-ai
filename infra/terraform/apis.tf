locals {
  services = [
    "aiplatform.googleapis.com",       # Vertex AI / Gemini
    "run.googleapis.com",              # Cloud Run (API, agent, UI)
    "cloudfunctions.googleapis.com",   # Cloud Functions (gen2)
    "cloudscheduler.googleapis.com",   # Cloud Scheduler
    "cloudbuild.googleapis.com",       # builds for Run and Functions
    "artifactregistry.googleapis.com", # container images
    "bigquery.googleapis.com",         # data warehouse
    "storage.googleapis.com",          # receipt images
    "eventarc.googleapis.com",         # gen2 function triggers
    "pubsub.googleapis.com",           # alert fan-out
    "secretmanager.googleapis.com",    # app secrets
    "iam.googleapis.com",
    "logging.googleapis.com",
    "billingbudgets.googleapis.com",
  ]
}

resource "google_project_service" "enabled" {
  for_each           = toset(local.services)
  service            = each.value
  disable_on_destroy = false
}
