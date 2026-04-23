# =============================================================================
# alb.tf — Application Load Balancer + ACM TLS certificate + Route 53 DNS
# =============================================================================
#
# TRAFFIC FLOW
#
#   Browser
#     │ HTTP :80
#     ▼
#   ALB Listener :80  ──────► 301 Redirect to https://domain_name{path}
#
#   Browser
#     │ HTTPS :443  (TLS terminated at ALB — ECS receives plain HTTP :8000)
#     ▼
#   ALB Listener :443
#     │  forward
#     ▼
#   Target Group (IP type)
#     │  health-checked via GET /health → 200 {"status":"ok"}
#     ▼
#   ECS Fargate Task :8000
#
# TLS CERTIFICATE
#   ACM issues a free TLS certificate for domain_name and *.domain_name.
#   Certificate validation is done via DNS CNAME records.
#   If create_route53_zone = true, Terraform creates the CNAME automatically.
#   If false, check 'terraform output acm_validation_cnames' and add them in
#   your DNS provider. ACM will validate and issue the cert within ~30 minutes.
# =============================================================================

# ---------------------------------------------------------------------------
# ACM Certificate
# ---------------------------------------------------------------------------

resource "aws_acm_certificate" "main" {
  domain_name               = var.domain_name
  subject_alternative_names = ["*.${var.domain_name}"]  # covers www. subdomain
  validation_method         = "DNS"

  # When reissuing (e.g. key rotation), create the new cert before destroying
  # the old one so the ALB listener is never without a valid cert.
  lifecycle {
    create_before_destroy = true
  }

  tags = { Name = "${local.name_prefix}-cert" }
}

# ---------------------------------------------------------------------------
# Route 53 Hosted Zone (optional — controlled by create_route53_zone variable)
# ---------------------------------------------------------------------------
# If you already have a hosted zone for this domain, import it:
#   terraform import aws_route53_zone.main ZONE_ID

resource "aws_route53_zone" "main" {
  count = var.create_route53_zone ? 1 : 0
  name  = var.domain_name

  tags = { Name = "${local.name_prefix}-zone" }
}

# ---------------------------------------------------------------------------
# ACM DNS Validation Records
# ---------------------------------------------------------------------------
# ACM gives us a set of CNAME records to add; once it detects them, it
# issues the certificate. This is idempotent — re-runs don't re-validate.

resource "aws_route53_record" "acm_validation" {
  for_each = var.create_route53_zone ? {
    for dvo in aws_acm_certificate.main.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  } : {}

  zone_id = aws_route53_zone.main[0].zone_id
  name    = each.value.name
  type    = each.value.type
  records = [each.value.record]
  ttl     = 60

  allow_overwrite = true
}

# Wait until ACM confirms the certificate is issued before attaching it to the ALB.
# Terraform will poll for up to 75 minutes (ACM SLA is typically <30 min).
resource "aws_acm_certificate_validation" "main" {
  certificate_arn = aws_acm_certificate.main.arn

  validation_record_fqdns = var.create_route53_zone ? [
    for record in aws_route53_record.acm_validation : record.fqdn
  ] : []

  timeouts {
    create = "75m"
  }
}

# ---------------------------------------------------------------------------
# Application Load Balancer
# ---------------------------------------------------------------------------

resource "aws_lb" "main" {
  name               = "${local.name_prefix}-alb"
  internal           = false       # public-facing
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = [aws_subnet.public_a.id, aws_subnet.public_b.id]

  # Access logs: enable in production for auditing and debugging.
  # Requires an S3 bucket with the correct bucket policy (see AWS docs).
  # access_logs {
  #   bucket  = "your-alb-logs-bucket"
  #   prefix  = local.name_prefix
  #   enabled = true
  # }

  # Deletion protection prevents accidentally destroying the load balancer.
  enable_deletion_protection = true

  tags = { Name = "${local.name_prefix}-alb" }
}

# ---------------------------------------------------------------------------
# Target Group — where the ALB sends traffic
# ---------------------------------------------------------------------------

resource "aws_lb_target_group" "app" {
  name        = "${local.name_prefix}-tg"
  port        = 8000          # FastAPI port
  protocol    = "HTTP"        # TLS is terminated at the ALB
  vpc_id      = aws_vpc.main.id
  target_type = "ip"          # required for Fargate (no EC2 instance IDs)

  health_check {
    path                = "/health"          # FastAPI GET /health → {"status":"ok"}
    protocol            = "HTTP"
    healthy_threshold   = 2                  # 2 consecutive successes = healthy
    unhealthy_threshold = 3                  # 3 consecutive failures = unhealthy
    timeout             = 5                  # seconds per check
    interval            = 30                 # seconds between checks
    matcher             = "200"              # expected HTTP status code
  }

  # Graceful connection draining: give in-flight requests 30s to complete
  # before removing a deregistered target. Prevents 502 errors on deploys.
  deregistration_delay = 30

  tags = { Name = "${local.name_prefix}-tg" }
}

# ---------------------------------------------------------------------------
# ALB Listeners
# ---------------------------------------------------------------------------

# HTTP listener — always redirects to HTTPS. Never routes traffic to ECS.
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"   # permanent redirect — browsers will cache it
    }
  }
}

# HTTPS listener — forwards to the ECS target group
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"  # TLS 1.2 + 1.3 only
  certificate_arn   = aws_acm_certificate_validation.main.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

# ---------------------------------------------------------------------------
# Route 53 DNS record — points domain to the ALB
# ---------------------------------------------------------------------------

resource "aws_route53_record" "app" {
  count   = var.create_route53_zone ? 1 : 0
  zone_id = aws_route53_zone.main[0].zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}

# www subdomain → same ALB
resource "aws_route53_record" "www" {
  count   = var.create_route53_zone ? 1 : 0
  zone_id = aws_route53_zone.main[0].zone_id
  name    = "www.${var.domain_name}"
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}
