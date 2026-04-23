# =============================================================================
# rds.tf — RDS PostgreSQL 15 (managed relational database)
# =============================================================================
#
# IMPORTANT NOTES
# ---------------
# 1. RDS is placed in PRIVATE subnets with no public access.
#    The only way to connect is from within the VPC (ECS task or a bastion host).
#
# 2. Alembic migrations run automatically at container startup via the
#    docker-entrypoint.sh script (alembic upgrade head). This is safe because
#    ECS rolling deploys stop old tasks before starting new ones by default.
#
# 3. Automated backups are enabled (7-day retention). For additional safety,
#    see scripts/backup_db.py which pg_dumps to S3.
#
# 4. The database password is stored in SSM Parameter Store (ssm.tf) and
#    injected into the container as an environment variable — it never appears
#    in the task definition JSON or CloudWatch logs.
#
# CONNECT MANUALLY (for schema inspection or emergency ops)
# ---------------------------------------------------------
#   Option A — AWS Systems Manager Session Manager (no bastion host needed):
#     1. Add a small EC2 instance in a private subnet with SSM agent.
#     2. aws ssm start-session --target i-XXXXX
#     3. psql postgresql://postgres:PASSWORD@RDS_ENDPOINT:5432/ekorepetycje
#
#   Option B — ECS Exec (if EnableExecuteCommand=true on the ECS service):
#     aws ecs execute-command \
#       --cluster ekorepetycje-prod \
#       --task TASK_ARN \
#       --container app \
#       --interactive --command "/bin/bash"
# =============================================================================

# ---------------------------------------------------------------------------
# DB Subnet Group — tells RDS which subnets it can use for its ENI
# ---------------------------------------------------------------------------

resource "aws_db_subnet_group" "main" {
  name       = "${local.name_prefix}-db-subnet"
  subnet_ids = [aws_subnet.private_a.id, aws_subnet.private_b.id]
  description = "Private subnets for RDS PostgreSQL"

  tags = { Name = "${local.name_prefix}-db-subnet" }
}

# ---------------------------------------------------------------------------
# DB Parameter Group — PostgreSQL 15 settings
# ---------------------------------------------------------------------------
# Using a custom parameter group (even with defaults) gives us the ability to
# tune settings (e.g. shared_buffers, max_connections) without recreating RDS.

resource "aws_db_parameter_group" "main" {
  name        = "${local.name_prefix}-pg15"
  family      = "postgres15"
  description = "PostgreSQL 15 parameter group for ${local.name_prefix}"

  # Force SSL connections — clients that don't use SSL will be rejected.
  # asyncpg (used by the app) connects with SSL by default when the endpoint
  # is a hostname (RDS enforces it via the pg_hba.conf hostssl rule).
  parameter {
    name  = "rds.force_ssl"
    value = "1"
    apply_method = "immediate"
  }

  tags = { Name = "${local.name_prefix}-pg15" }
}

# ---------------------------------------------------------------------------
# RDS Instance
# ---------------------------------------------------------------------------

resource "aws_db_instance" "main" {
  identifier        = "${local.name_prefix}-db"
  engine            = "postgres"
  engine_version    = "15"
  instance_class    = var.db_instance_class
  allocated_storage = var.db_allocated_storage

  # Storage autoscaling: if the DB exceeds allocated_storage, AWS automatically
  # expands it up to max_allocated_storage without downtime.
  max_allocated_storage = 100

  db_name  = var.db_name
  username = var.db_username
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  parameter_group_name   = aws_db_parameter_group.main.name

  # No public access — connects only from within the VPC
  publicly_accessible = false

  # Multi-AZ: disabled for MVP, enable for production SLA
  multi_az = var.db_multi_az

  # Automated backups — 7-day retention window
  backup_retention_period = 7
  backup_window           = "02:00-03:00"   # 2-3 AM UTC (low-traffic window)
  maintenance_window      = "sun:03:00-sun:04:00"

  # Encrypt at rest using the default AWS-managed KMS key.
  # This covers the data volume, backups, and snapshots.
  storage_encrypted = true

  # Prevent accidental deletion via 'terraform destroy'.
  # To actually delete, set to false, apply, then destroy.
  deletion_protection = true

  # Keep a final snapshot for disaster recovery when deleting.
  skip_final_snapshot       = false
  final_snapshot_identifier = "${local.name_prefix}-final-snapshot"

  # Performance Insights: helps diagnose slow queries in the AWS console.
  # Free for db.t3 instances (up to 7 days retention).
  performance_insights_enabled = true

  tags = { Name = "${local.name_prefix}-db" }
}
