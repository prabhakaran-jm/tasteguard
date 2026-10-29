variable "project_id" {
  type        = string
  description = "GCP project ID"
  default     = "tasteguard-qloo-2026"
}

variable "region" {
  type        = string
  description = "Cloud Run / Artifact Registry region"
  default     = "us-central1"
}

variable "service_name" {
  type        = string
  default     = "tasteguard"
}

variable "image" {
  type        = string
  description = "Full container image URL in Artifact Registry. Empty skips Cloud Run until after Cloud Build."
  default     = ""
}

variable "qloo_api_key" {
  type        = string
  sensitive   = true
  description = "Qloo hackathon API key"
}

variable "gemini_api_key" {
  type        = string
  sensitive   = true
  description = "Gemini API key"
}

variable "min_instances" {
  type        = number
  default     = 1
  description = "Keep warm through the hackathon window"
}

variable "max_instances" {
  type        = number
  # Single instance: eval_cache is process-local; multi-instance can 404 on /repair.
  default     = 1
}

variable "gemini_model" {
  type        = string
  description = "Gemini model id for propose/repair"
  default     = "gemini-3.8-flash"
}
