resource "google_storage_bucket" "receipts" {
  name                        = "${var.project_id}-smartspend-receipts"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true

  lifecycle_rule {
    condition { age = 90 }
    action { type = "Delete" }
  }

  depends_on = [google_project_service.enabled]
}

resource "google_artifact_registry_repository" "containers" {
  repository_id = "smartspend"
  location      = var.region
  format        = "DOCKER"
  description   = "Images for the SmartSpend API, agent and UI."

  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions { keep_count = 5 }
  }

  depends_on = [google_project_service.enabled]
}

resource "google_pubsub_topic" "alerts" {
  name       = "smartspend-alerts"
  depends_on = [google_project_service.enabled]
}
