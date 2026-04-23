# =============================================================================
# outputs.tf — Values printed after 'terraform apply'
# =============================================================================
#
# Run 'terraform output' at any time to re-print these values.
# Run 'terraform output -raw <name>' to get a single value for scripting.
# =============================================================================

# ---------------------------------------------------------------------------
# App URL
# ---------------------------------------------------------------------------

output "app_url" {
  description = "HTTPS URL of the deployed application"
  value       = "https://${var.domain_name}"
}

output "alb_dns_name" {
  description = <<-EOT
    Raw ALB DNS name. Use this as a CNAME target if you manage DNS outside Route 53
    (e.g. Cloudflare). Point your apex/root domain using an ALIAS/ANAME record.
  EOT
  value = aws_lb.main.dns_name
}

# ---------------------------------------------------------------------------
# Docker / ECR
# ---------------------------------------------------------------------------

output "ecr_repository_url" {
  description = "ECR image URI. Tag and push your Docker image here."
  value       = aws_ecr_repository.app.repository_url
}

output "docker_push_commands" {
  description = "Copy-paste commands to authenticate and push the Docker image to ECR."
  value       = <<-EOT
    # 1. Authenticate
    aws ecr get-login-password --region ${var.aws_region} | \
      docker login --username AWS --password-stdin ${split("/", aws_ecr_repository.app.repository_url)[0]}

    # 2. Build
    docker build -t ${var.app_name}:latest .

    # 3. Tag & Push
    docker tag ${var.app_name}:latest ${aws_ecr_repository.app.repository_url}:latest
    docker push ${aws_ecr_repository.app.repository_url}:latest

    # 4. Force new ECS deployment
    aws ecs update-service \
      --cluster ${aws_ecs_cluster.main.name} \
      --service ${aws_ecs_service.app.name} \
      --force-new-deployment \
      --region ${var.aws_region}
  EOT
}

# ---------------------------------------------------------------------------
# Route 53 — only shown when create_route53_zone = true
# ---------------------------------------------------------------------------

output "route53_nameservers" {
  description = <<-EOT
    Route 53 nameservers for your hosted zone.
    Update your domain registrar to use these nameservers so that AWS manages
    your DNS. This is required for the ACM certificate to validate automatically.
  EOT
  value = var.create_route53_zone ? aws_route53_zone.main[0].name_servers : []
}

# ---------------------------------------------------------------------------
# ACM — shown when create_route53_zone = false (manual DNS validation)
# ---------------------------------------------------------------------------

output "acm_validation_cnames" {
  description = <<-EOT
    CNAME records to add to your DNS provider for ACM certificate validation.
    Only needed when create_route53_zone = false.
    After adding the CNAMEs, ACM validates and issues the certificate (~30 min).
  EOT
  value = {
    for dvo in aws_acm_certificate.main.domain_validation_options :
    dvo.domain_name => {
      name  = dvo.resource_record_name
      type  = dvo.resource_record_type
      value = dvo.resource_record_value
    }
  }
}

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

output "rds_endpoint" {
  description = "RDS PostgreSQL hostname (not publicly accessible — VPC only)"
  value       = aws_db_instance.main.address
}

output "rds_port" {
  description = "RDS PostgreSQL port"
  value       = aws_db_instance.main.port
}

# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------

output "redis_endpoint" {
  description = "ElastiCache Redis hostname (VPC only)"
  value       = aws_elasticache_cluster.main.cache_nodes[0].address
}

# ---------------------------------------------------------------------------
# ECS
# ---------------------------------------------------------------------------

output "ecs_cluster_name" {
  description = "ECS cluster name — used with aws ecs commands"
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  description = "ECS service name — used with aws ecs update-service"
  value       = aws_ecs_service.app.name
}

output "cloudwatch_log_group" {
  description = "CloudWatch log group for application logs. Stream with: aws logs tail <group> --follow"
  value       = aws_cloudwatch_log_group.app.name
}

# ---------------------------------------------------------------------------
# ECS Exec — interactive shell into a running task (debugging)
# ---------------------------------------------------------------------------

output "ecs_exec_command" {
  description = <<-EOT
    Template command to open a shell inside a running ECS task (requires
    EnableExecuteCommand=true on the ECS service and SSM agent in the image).
    Replace TASK_ARN with the actual task ARN from 'aws ecs list-tasks'.
  EOT
  value = <<-EOT
    # List running tasks
    aws ecs list-tasks --cluster ${aws_ecs_cluster.main.name} --region ${var.aws_region}

    # Open interactive shell (replace TASK_ARN)
    aws ecs execute-command \
      --cluster ${aws_ecs_cluster.main.name} \
      --task TASK_ARN \
      --container app \
      --interactive \
      --command "/bin/bash" \
      --region ${var.aws_region}
  EOT
}
