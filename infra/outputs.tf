output "service_url" {
  description = "Public TasteGuard URL (null until image is set and applied)"
  value       = try(google_cloud_run_v2_service.tasteguard[0].uri, null)
}

output "artifact_registry" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.tasteguard.repository_id}"
}

output "image_hint" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.tasteguard.repository_id}/tasteguard:latest"
}
