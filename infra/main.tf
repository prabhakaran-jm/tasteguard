locals {
  apis = [
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "secretmanager.googleapis.com",
    "iam.googleapis.com",
  ]
  deploy = var.image != ""
}

data "google_project" "project" {
  project_id = var.project_id
}

resource "google_project_service" "apis" {
  for_each = toset(local.apis)

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "tasteguard" {
  location      = var.region
  repository_id = "tasteguard"
  description   = "TasteGuard container images"
  format        = "DOCKER"

  depends_on = [google_project_service.apis]
}

# Cloud Build default SA must push to Artifact Registry.
resource "google_artifact_registry_repository_iam_member" "cloudbuild_writer" {
  project    = var.project_id
  location   = google_artifact_registry_repository.tasteguard.location
  repository = google_artifact_registry_repository.tasteguard.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${data.google_project.project.number}@cloudbuild.gserviceaccount.com"
}

resource "google_service_account" "runtime" {
  account_id   = "tasteguard-run"
  display_name = "TasteGuard Cloud Run"
}

resource "google_secret_manager_secret" "qloo" {
  secret_id = "qloo-api-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "qloo" {
  secret      = google_secret_manager_secret.qloo.id
  secret_data = var.qloo_api_key
}

resource "google_secret_manager_secret" "gemini" {
  secret_id = "gemini-api-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "gemini" {
  secret      = google_secret_manager_secret.gemini.id
  secret_data = var.gemini_api_key
}

resource "google_secret_manager_secret_iam_member" "qloo_accessor" {
  secret_id = google_secret_manager_secret.qloo.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_secret_manager_secret_iam_member" "gemini_accessor" {
  secret_id = google_secret_manager_secret.gemini.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_cloud_run_v2_service" "tasteguard" {
  count = local.deploy ? 1 : 0

  name     = var.service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.runtime.email

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      image = var.image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name = "QLOO_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.qloo.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "GEMINI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.gemini.secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "QLOO_BASE_URL"
        value = "https://hackathon.api.qloo.com"
      }

      env {
        name  = "GEMINI_MODEL"
        value = var.gemini_model
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_version.qloo,
    google_secret_manager_secret_version.gemini,
    google_secret_manager_secret_iam_member.qloo_accessor,
    google_secret_manager_secret_iam_member.gemini_accessor,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "public" {
  count = local.deploy ? 1 : 0

  project  = var.project_id
  location = google_cloud_run_v2_service.tasteguard[0].location
  name     = google_cloud_run_v2_service.tasteguard[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
