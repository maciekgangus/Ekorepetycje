# =============================================================================
# ecs.tf — ECS Fargate cluster, task definition, and service
# =============================================================================
#
# HOW ECS FARGATE WORKS
# ----------------------
# - CLUSTER: a logical grouping of tasks/services (no EC2 instances to manage).
# - TASK DEFINITION: a blueprint — Docker image, CPU, memory, env vars, ports.
# - SERVICE: keeps N copies of the task running, replaces failed tasks, and
#   integrates with the ALB target group for traffic routing.
#
# DEPLOYMENT STRATEGY (rolling update)
# - When you push a new image and force-update the service, ECS starts new
#   tasks first (downloading the new image, running migrations), waits for
#   them to pass the ALB health check, then stops the old task.
# - minimum_healthy_percent = 0 allows the old task to stop before the new
#   one is healthy (important at desired_count = 1 to avoid running 2 tasks).
# - maximum_percent = 200 allows 2x tasks during the transition window.
# - Circuit breaker + rollback: if the new task fails to become healthy within
#   the deployment timeout, ECS automatically rolls back to the previous task.
#
# SECRETS INJECTION
# - Sensitive env vars (DATABASE_URL, SECRET_KEY, etc.) are referenced by
#   SSM Parameter ARN in the "secrets" block — they are never stored in the
#   task definition JSON. The ECS agent fetches and decrypts them at startup.
#
# MIGRATIONS
# - docker-entrypoint.sh runs `alembic upgrade head` before starting uvicorn.
# - With desired_count = 1, only one task runs migrations at a time (safe).
# - With desired_count > 1, move migrations to a one-off "migration task".
# =============================================================================

# ---------------------------------------------------------------------------
# CloudWatch Log Group — stores stdout/stderr from the container
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${local.name_prefix}"
  retention_in_days = 30   # keep 30 days of logs; reduce to 7 for cost savings

  tags = { Name = "${local.name_prefix}-logs" }
}

# ---------------------------------------------------------------------------
# ECS Cluster
# ---------------------------------------------------------------------------

resource "aws_ecs_cluster" "main" {
  name = local.name_prefix  # "ekorepetycje-prod"

  # Container Insights: sends CPU/memory/network metrics to CloudWatch.
  # Costs ~$0.01 per task-hour extra — worth it for production visibility.
  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = { Name = "${local.name_prefix}-cluster" }
}

# ---------------------------------------------------------------------------
# ECS Task Definition
# ---------------------------------------------------------------------------

resource "aws_ecs_task_definition" "app" {
  family = local.name_prefix

  # Fargate mode — no EC2 instances, AWS manages the underlying host
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"   # required for Fargate; gives each task its own ENI

  cpu    = var.ecs_cpu      # 256 = 0.25 vCPU
  memory = var.ecs_memory   # 512 MB

  execution_role_arn = aws_iam_role.ecs_execution.arn  # ECS agent permissions
  task_role_arn      = aws_iam_role.ecs_task.arn        # App-level AWS permissions

  container_definitions = jsonencode([
    {
      name  = "app"
      image = "${aws_ecr_repository.app.repository_url}:latest"

      portMappings = [
        {
          containerPort = 8000
          protocol      = "tcp"
        }
      ]

      # Non-sensitive environment variables — these are visible in the
      # task definition JSON, so avoid putting secrets here.
      environment = [
        { name = "DEBUG",            value = "False" },
        { name = "LLM_PROVIDER",     value = var.llm_provider },
        { name = "BEDROCK_MODEL_ID", value = var.bedrock_model_id },
        { name = "RESEND_FROM_EMAIL", value = var.resend_from_email },
        { name = "RESEND_TO_EMAIL",   value = var.resend_to_email },
        { name = "TURNSTILE_SITE_KEY", value = var.turnstile_site_key },
        # Backup config — no sensitive data
        { name = "BACKUP_S3_BUCKET",  value = var.backup_s3_bucket },
        { name = "AWS_DEFAULT_REGION", value = var.aws_region },
        { name = "BACKUP_RETAIN_DAYS", value = "30" },
      ]

      # Sensitive variables — fetched from SSM Parameter Store at task startup.
      # The "valueFrom" ARN format:
      #   arn:aws:ssm:REGION:ACCOUNT_ID:parameter/PATH
      # Using the resource ARN from ssm.tf ensures the task always references
      # the current version of the parameter.
      secrets = [
        {
          name      = "DATABASE_URL"
          valueFrom = aws_ssm_parameter.database_url.arn
        },
        {
          name      = "SECRET_KEY"
          valueFrom = aws_ssm_parameter.secret_key.arn
        },
        {
          name      = "REDIS_URL"
          valueFrom = aws_ssm_parameter.redis_url.arn
        },
        {
          name      = "RESEND_API_KEY"
          valueFrom = aws_ssm_parameter.resend_api_key.arn
        },
        {
          name      = "TURNSTILE_SECRET_KEY"
          valueFrom = aws_ssm_parameter.turnstile_secret_key.arn
        },
      ]

      # Container health check — separate from the ALB health check.
      # The ALB health check controls traffic routing; this one controls
      # whether ECS marks the container as healthy and restarts it if not.
      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60   # give alembic migrations time to complete on cold start
      }

      # Send stdout/stderr to CloudWatch Logs
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.app.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      # Essential = true means if this container exits, the task is considered
      # failed and ECS will restart the entire task.
      essential = true
    }
  ])

  tags = { Name = "${local.name_prefix}-task" }
}

# ---------------------------------------------------------------------------
# ECS Service
# ---------------------------------------------------------------------------

resource "aws_ecs_service" "app" {
  name            = "${local.name_prefix}-svc"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = var.ecs_desired_count
  launch_type     = "FARGATE"

  # Place tasks in private subnets — outbound via NAT Gateway
  network_configuration {
    subnets         = [aws_subnet.private_a.id, aws_subnet.private_b.id]
    security_groups = [aws_security_group.ecs.id]
    assign_public_ip = false   # private subnet + NAT, no public IP needed
  }

  # Wire the service to the ALB target group.
  # ECS registers/deregisters task IPs automatically.
  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "app"
    container_port   = 8000
  }

  # Rolling update settings:
  deployment_minimum_healthy_percent = 0    # allows old task to stop before new one is healthy
  deployment_maximum_percent         = 200  # allows 2x tasks during transition

  # Circuit breaker: automatically roll back to the previous task definition
  # if the new deployment fails to reach a steady state (e.g. image pull error,
  # unhealthy health checks, OOM kill).
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  # Ignore task_definition changes in Terraform after the first deploy.
  # This allows CI/CD to update the service without Terraform conflicts.
  # To force a Terraform-driven redeploy, run: terraform apply -replace=aws_ecs_service.app
  lifecycle {
    ignore_changes = [task_definition]
  }

  # Ensure the ALB listener exists and the certificate is validated before
  # the service starts receiving traffic.
  depends_on = [
    aws_lb_listener.https,
    aws_iam_role_policy_attachment.ecs_execution_managed,
    aws_iam_role_policy_attachment.ecs_execution_ssm,
  ]

  tags = { Name = "${local.name_prefix}-svc" }
}
