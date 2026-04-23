# =============================================================================
# ssm.tf — AWS Systems Manager Parameter Store (encrypted secrets)
# =============================================================================
#
# WHY SSM INSTEAD OF ENV VARS IN THE TASK DEFINITION?
# -----------------------------------------------------
# ECS task definitions are visible in the AWS console and AWS API in plain text.
# Storing secrets as environment variable values in the task definition JSON
# means anyone with DescribeTaskDefinition IAM access sees them.
#
# With SSM SecureString parameters:
#   1. Values are stored encrypted (KMS) and never appear in task definition JSON.
#   2. The task definition references the SSM parameter ARN.
#   3. At task startup, the ECS agent fetches and decrypts the value using the
#      execution role, then injects it as an environment variable — so the
#      application code sees it exactly as if it were a plain env var.
#   4. Access is auditable via CloudTrail.
#
# PARAMETER NAMING CONVENTION
#   /{app_name}/{environment}/{variable_name}
#   e.g. /ekorepetycje/prod/secret_key
#
# NOTE: Terraform stores variable values in its state file.
# Use an encrypted S3 backend (see main.tf) to protect state at rest.
# =============================================================================

# ---------------------------------------------------------------------------
# DATABASE_URL — asyncpg connection string (includes credentials)
# ---------------------------------------------------------------------------
# Built from RDS outputs so it stays consistent with the actual instance.
# If you change db_username or db_password, re-applying Terraform updates
# this parameter automatically.

resource "aws_ssm_parameter" "database_url" {
  name        = "${local.ssm_prefix}/database_url"
  type        = "SecureString"
  description = "PostgreSQL connection string for the FastAPI app"

  value = "postgresql+asyncpg://${var.db_username}:${var.db_password}@${aws_db_instance.main.address}:${aws_db_instance.main.port}/${var.db_name}"

  tags = { Name = "${local.name_prefix}-ssm-database-url" }
}

# ---------------------------------------------------------------------------
# SECRET_KEY — itsdangerous session/CSRF signing key
# ---------------------------------------------------------------------------

resource "aws_ssm_parameter" "secret_key" {
  name        = "${local.ssm_prefix}/secret_key"
  type        = "SecureString"
  description = "Application SECRET_KEY for signing session cookies and CSRF tokens"
  value       = var.secret_key

  tags = { Name = "${local.name_prefix}-ssm-secret-key" }
}

# ---------------------------------------------------------------------------
# REDIS_URL — ElastiCache connection string
# ---------------------------------------------------------------------------
# Not a secret (no auth on default Redis), but stored in SSM for consistency
# so all configuration comes from one place.

resource "aws_ssm_parameter" "redis_url" {
  name        = "${local.ssm_prefix}/redis_url"
  type        = "String"   # Not sensitive — no password in URL
  description = "Redis connection URL for event cache"

  value = "redis://${aws_elasticache_cluster.main.cache_nodes[0].address}:${aws_elasticache_cluster.main.cache_nodes[0].port}/0"

  tags = { Name = "${local.name_prefix}-ssm-redis-url" }
}

# ---------------------------------------------------------------------------
# RESEND_API_KEY — transactional email
# ---------------------------------------------------------------------------

resource "aws_ssm_parameter" "resend_api_key" {
  name        = "${local.ssm_prefix}/resend_api_key"
  type        = "SecureString"
  description = "Resend.com API key for sending emails"
  value       = var.resend_api_key != "" ? var.resend_api_key : "disabled"

  tags = { Name = "${local.name_prefix}-ssm-resend" }
}

# ---------------------------------------------------------------------------
# TURNSTILE_SECRET_KEY — Cloudflare bot protection
# ---------------------------------------------------------------------------

resource "aws_ssm_parameter" "turnstile_secret_key" {
  name        = "${local.ssm_prefix}/turnstile_secret_key"
  type        = "SecureString"
  description = "Cloudflare Turnstile secret key for CAPTCHA verification"
  value       = var.turnstile_secret_key

  tags = { Name = "${local.name_prefix}-ssm-turnstile" }
}
