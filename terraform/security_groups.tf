# =============================================================================
# security_groups.tf — Traffic rules between each application layer
# =============================================================================
#
# SECURITY MODEL (principle of least privilege)
#
#   Internet
#      │  TCP 80, 443
#      ▼
#   [sg_alb]  — accepts only HTTP/HTTPS from the public internet
#      │  TCP 8000  (FastAPI port)
#      ▼
#   [sg_ecs]  — accepts traffic ONLY from the ALB security group
#      │  TCP 5432              │  TCP 6379
#      ▼                        ▼
#   [sg_rds]               [sg_redis]
#   only from sg_ecs        only from sg_ecs
#
# All egress (outbound) is allowed by default.
# ECS needs outbound to reach: ECR (image pull), SSM (secret fetch),
# CloudWatch (logs), Resend API (emails), and Cloudflare Turnstile.
# =============================================================================

# ---------------------------------------------------------------------------
# ALB Security Group — public-facing load balancer
# ---------------------------------------------------------------------------

resource "aws_security_group" "alb" {
  name        = "${local.name_prefix}-sg-alb"
  description = "Allow HTTP/HTTPS inbound to the Application Load Balancer"
  vpc_id      = aws_vpc.main.id

  # HTTP — redirected to HTTPS by the listener rule; keep open so
  # browsers that follow http:// links get a clean redirect response.
  ingress {
    description = "HTTP from internet"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # HTTPS — all real traffic arrives here
  ingress {
    description = "HTTPS from internet"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Allow ALB to forward health-check responses and replies back to clients
  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name_prefix}-sg-alb" }
}

# ---------------------------------------------------------------------------
# ECS Security Group — application container
# ---------------------------------------------------------------------------

resource "aws_security_group" "ecs" {
  name        = "${local.name_prefix}-sg-ecs"
  description = "Allow port 8000 inbound from ALB only; all outbound"
  vpc_id      = aws_vpc.main.id

  # Accept only traffic originating from the ALB.
  # Using a security-group source (instead of CIDR) means this rule
  # automatically stays correct if the ALB's internal IPs change.
  ingress {
    description     = "FastAPI from ALB"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  # Outbound is unrestricted — ECS needs to reach:
  #   - ECR endpoints (pull Docker image)
  #   - SSM Parameter Store (fetch secrets at startup)
  #   - CloudWatch Logs
  #   - Resend HTTPS API (send emails)
  #   - Cloudflare Turnstile API (CAPTCHA verification)
  #   - RDS and ElastiCache (within VPC, covered by their own SGs)
  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name_prefix}-sg-ecs" }
}

# ---------------------------------------------------------------------------
# RDS Security Group — PostgreSQL database
# ---------------------------------------------------------------------------

resource "aws_security_group" "rds" {
  name        = "${local.name_prefix}-sg-rds"
  description = "Allow PostgreSQL port 5432 from ECS only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "PostgreSQL from ECS"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  # Restrict egress to inside VPC only — RDS doesn't initiate outbound
  # connections to the internet. This is a defence-in-depth measure.
  egress {
    description = "VPC local egress"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [aws_vpc.main.cidr_block]
  }

  tags = { Name = "${local.name_prefix}-sg-rds" }
}

# ---------------------------------------------------------------------------
# ElastiCache Security Group — Redis cache
# ---------------------------------------------------------------------------

resource "aws_security_group" "redis" {
  name        = "${local.name_prefix}-sg-redis"
  description = "Allow Redis port 6379 from ECS only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Redis from ECS"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  egress {
    description = "VPC local egress"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [aws_vpc.main.cidr_block]
  }

  tags = { Name = "${local.name_prefix}-sg-redis" }
}
