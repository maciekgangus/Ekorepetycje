# =============================================================================
# variables.tf — All configurable inputs for the deployment
# =============================================================================
#
# HOW TO USE
# ----------
# Create a file named "prod.tfvars" (it is gitignored by default) and set
# the required values. Example:
#
#   aws_region        = "eu-central-1"
#   app_name          = "ekorepetycje"
#   environment       = "prod"
#   domain_name       = "ekorepetycje.pl"
#   db_password       = "a-very-long-random-password-here"
#   secret_key        = "run: python -c \"import secrets; print(secrets.token_hex(32))\""
#   resend_api_key    = "re_xxxxxxxxxxxx"
#   resend_to_email   = "kontakt@ekorepetycje.pl"
#   turnstile_site_key    = "0x..."
#   turnstile_secret_key  = "0x..."
#
# Sensitive variables are marked sensitive=true — Terraform will redact them
# from plan/apply output and will NOT store them in plain text in state.
# However, state files must still be stored securely (encrypted S3 + KMS).
# =============================================================================

# ---------------------------------------------------------------------------
# AWS / meta
# ---------------------------------------------------------------------------

variable "aws_region" {
  type        = string
  default     = "eu-central-1"
  description = "AWS region to deploy all resources into. eu-central-1 (Frankfurt) is closest to Poland."
}

variable "app_name" {
  type        = string
  default     = "ekorepetycje"
  description = "Application name used as a prefix in resource names and SSM paths."
}

variable "environment" {
  type        = string
  default     = "prod"
  description = "Deployment environment (prod | staging). Affects resource names and SSM paths."
}

# ---------------------------------------------------------------------------
# Networking / DNS
# ---------------------------------------------------------------------------

variable "domain_name" {
  type        = string
  description = <<-EOT
    The primary domain for the application, e.g. "ekorepetycje.pl".
    Used to:
      1. Create an ACM TLS certificate (HTTPS required for Secure cookie flag).
      2. Configure the ALB HTTPS listener.
      3. Create a Route 53 public hosted zone (if create_route53_zone = true).
    If you manage DNS elsewhere, set create_route53_zone = false and manually
    add the CNAME records printed in 'terraform output acm_validation_cnames'.
  EOT
}

variable "create_route53_zone" {
  type        = bool
  default     = true
  description = <<-EOT
    When true, Terraform creates a Route 53 public hosted zone for domain_name
    and adds the ACM certificate validation CNAME records automatically.
    Set to false if your DNS is managed outside AWS (Cloudflare, OVH, etc.);
    in that case add the CNAME records manually after 'terraform apply'.
  EOT
}

# ---------------------------------------------------------------------------
# Database — RDS PostgreSQL 15
# ---------------------------------------------------------------------------

variable "db_username" {
  type        = string
  default     = "postgres"
  description = "PostgreSQL master username. Avoid 'admin' — it is reserved by AWS RDS."
}

variable "db_password" {
  type        = string
  sensitive   = true
  description = "PostgreSQL master password. Minimum 16 chars recommended. Never commit this value."
}

variable "db_name" {
  type        = string
  default     = "ekorepetycje"
  description = "Name of the application database created on first boot."
}

variable "db_instance_class" {
  type        = string
  default     = "db.t3.micro"
  description = <<-EOT
    RDS instance type. db.t3.micro is free-tier eligible for the first 12 months.
    For production with >50 concurrent users, upgrade to db.t3.small or db.t3.medium.
  EOT
}

variable "db_allocated_storage" {
  type        = number
  default     = 20
  description = "Initial allocated storage in GiB. RDS auto-scales up to 100 GiB by default."
}

variable "db_multi_az" {
  type        = bool
  default     = false
  description = <<-EOT
    Enable Multi-AZ standby for automatic failover (~doubles cost).
    Recommended for production once the platform has paying users.
    Set to false for MVP to keep costs down (~$15/month vs ~$30/month).
  EOT
}

# ---------------------------------------------------------------------------
# Cache — ElastiCache Redis 7
# ---------------------------------------------------------------------------

variable "redis_node_type" {
  type        = string
  default     = "cache.t3.micro"
  description = <<-EOT
    ElastiCache node type. cache.t3.micro provides 0.5 GB RAM — sufficient for
    the 5-minute event window cache with a typical tutoring school volume.
  EOT
}

# ---------------------------------------------------------------------------
# Compute — ECS Fargate
# ---------------------------------------------------------------------------

variable "ecs_cpu" {
  type        = number
  default     = 256
  description = <<-EOT
    Fargate task CPU units. 256 = 0.25 vCPU.
    FastAPI with async I/O is CPU-light; 0.25 vCPU handles ~200 req/s.
    Valid combinations: 256/512, 512/1024-2048, 1024/2048-8192.
  EOT
}

variable "ecs_memory" {
  type        = number
  default     = 512
  description = "Fargate task memory in MiB. 512 MB is sufficient for the Python app."
}

variable "ecs_desired_count" {
  type        = number
  default     = 1
  description = <<-EOT
    Number of running ECS tasks. Keep at 1 for MVP — APScheduler runs in-process
    and would fire duplicate reminder emails if count > 1.
    To scale horizontally, move APScheduler to a dedicated worker task.
  EOT
}

# ---------------------------------------------------------------------------
# Application secrets
# ---------------------------------------------------------------------------

variable "secret_key" {
  type        = string
  sensitive   = true
  description = <<-EOT
    FastAPI SECRET_KEY — used to sign session cookies and CSRF tokens.
    Generate with: python -c "import secrets; print(secrets.token_hex(32))"
    Minimum 64 hex characters (32 bytes entropy). Never reuse across environments.
  EOT
}

variable "resend_api_key" {
  type        = string
  sensitive   = true
  default     = ""
  description = "Resend.com API key for transactional email. Leave empty to disable email (logs only)."
}

variable "resend_from_email" {
  type        = string
  default     = "Ekorepetycje <onboarding@resend.dev>"
  description = "Verified sender email shown in outbound mail. Use your verified domain in production."
}

variable "resend_to_email" {
  type        = string
  default     = "kontakt@ekorepetycje.pl"
  description = "Destination address for contact-form submissions."
}

variable "turnstile_site_key" {
  type        = string
  default     = "1x00000000000000000000AA"
  description = "Cloudflare Turnstile site key (public). Replace test key before go-live."
}

variable "turnstile_secret_key" {
  type        = string
  sensitive   = true
  default     = "1x0000000000000000000000000000000AA"
  description = "Cloudflare Turnstile secret key. Replace test key before go-live."
}

variable "llm_provider" {
  type        = string
  default     = "disabled"
  description = <<-EOT
    AI chat backend. Options:
      "disabled" — chat widget visible but shows unavailable (no extra cost).
      "bedrock"  — Amazon Bedrock Claude (the task IAM role already has permission;
                   set BEDROCK_MODEL_ID below and enable in this variable).
  EOT
}

variable "bedrock_model_id" {
  type        = string
  default     = "anthropic.claude-3-haiku-20240307-v1:0"
  description = "Bedrock model ID. Only used when llm_provider = 'bedrock'."
}

# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------

variable "backup_s3_bucket" {
  type        = string
  default     = ""
  description = <<-EOT
    S3 bucket name for pg_dump backups (scripts/backup_db.py).
    Leave empty to disable backups. The bucket must exist before deploying —
    create it manually or add an aws_s3_bucket resource to this module.
  EOT
}
