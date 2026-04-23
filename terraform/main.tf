# =============================================================================
# main.tf — Terraform root module: provider configuration and backend
# =============================================================================
#
# OVERVIEW
# --------
# This Terraform project provisions a production-ready AWS deployment for
# Ekorepetycje — a FastAPI + PostgreSQL + Redis tutoring platform.
#
# RESOURCES CREATED (in order of dependency)
#   VPC           → vpc.tf            (networking foundation)
#   Security Groups → security_groups.tf (traffic rules between layers)
#   ECR           → ecr.tf            (Docker image registry)
#   RDS           → rds.tf            (PostgreSQL 15 database)
#   ElastiCache   → elasticache.tf    (Redis 7 cache)
#   IAM           → iam.tf            (task execution and task roles)
#   SSM           → ssm.tf            (encrypted secret storage)
#   ALB           → alb.tf            (HTTPS load balancer + ACM cert)
#   ECS           → ecs.tf            (Fargate container service)
#
# MONTHLY COST ESTIMATE (eu-central-1, on-demand, as of 2025)
#   ECS Fargate   0.25 vCPU / 512 MB       ~$7
#   RDS           db.t3.micro (20 GB)       ~$15   (free tier: first 12 months)
#   ElastiCache   cache.t3.micro            ~$12
#   ALB           (fixed + ~1 LCU)          ~$16
#   NAT Gateway   (1x, data transfer)       ~$35
#   ECR           (<1 GB storage)           ~$0.10
#   CloudWatch    (log ingestion)           ~$2
#   TOTAL                                   ~$87 / month
#
# To reduce NAT Gateway cost add VPC endpoints for ECR/S3/SSM (saves ~$15-20).
#
# FIRST-TIME SETUP ORDER
#   1.  aws configure           # or set AWS_PROFILE env var
#   2.  terraform init
#   3.  terraform plan -var-file=prod.tfvars
#   4.  terraform apply -var-file=prod.tfvars
#   5.  Push Docker image to ECR (see outputs.tf for push commands)
#   6.  Force new ECS deployment to pull the image
# =============================================================================

terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # ---------------------------------------------------------------------------
  # REMOTE STATE — uncomment and configure before team/CI use.
  # Create the S3 bucket and DynamoDB table manually first:
  #
  #   aws s3 mb s3://ekorepetycje-tfstate --region eu-central-1
  #   aws s3api put-bucket-versioning \
  #       --bucket ekorepetycje-tfstate \
  #       --versioning-configuration Status=Enabled
  #   aws dynamodb create-table \
  #       --table-name ekorepetycje-tflock \
  #       --attribute-definitions AttributeName=LockID,AttributeType=S \
  #       --key-schema AttributeName=LockID,KeyType=HASH \
  #       --billing-mode PAY_PER_REQUEST \
  #       --region eu-central-1
  # ---------------------------------------------------------------------------
  # backend "s3" {
  #   bucket         = "ekorepetycje-tfstate"
  #   key            = "prod/terraform.tfstate"
  #   region         = "eu-central-1"
  #   dynamodb_table = "ekorepetycje-tflock"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region

  # All resources created by this module will carry these tags.
  # Enables cost-allocation filtering by project/environment in AWS Cost Explorer.
  default_tags {
    tags = {
      Project     = var.app_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# ---------------------------------------------------------------------------
# Locals — computed values reused across modules to keep naming consistent.
# ---------------------------------------------------------------------------
locals {
  # Short prefix used in resource names: e.g. "ekorepetycje-prod"
  name_prefix = "${var.app_name}-${var.environment}"

  # Friendly name for SSM paths: e.g. "/ekorepetycje/prod/secret_key"
  ssm_prefix = "/${var.app_name}/${var.environment}"
}
