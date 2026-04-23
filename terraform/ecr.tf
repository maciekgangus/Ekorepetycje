# =============================================================================
# ecr.tf — Elastic Container Registry: Docker image storage
# =============================================================================
#
# ECR stores the application Docker images. The ECS task definition references
# the image by its ECR URI + tag (or digest for immutable deployments).
#
# PUSH WORKFLOW (run locally after 'terraform apply'):
#
#   # 1. Authenticate Docker to ECR
#   aws ecr get-login-password --region eu-central-1 | \
#     docker login --username AWS --password-stdin \
#     $(terraform output -raw ecr_repository_url | cut -d/ -f1)
#
#   # 2. Build the production image (uses .dockerignore automatically)
#   docker build -t ekorepetycje:latest .
#
#   # 3. Tag and push
#   ECR_URI=$(terraform output -raw ecr_repository_url)
#   docker tag ekorepetycje:latest ${ECR_URI}:latest
#   docker push ${ECR_URI}:latest
#
#   # 4. Force ECS to pull the new image
#   aws ecs update-service \
#     --cluster ekorepetycje-prod \
#     --service ekorepetycje-prod-svc \
#     --force-new-deployment \
#     --region eu-central-1
# =============================================================================

resource "aws_ecr_repository" "app" {
  name = local.name_prefix  # "ekorepetycje-prod"

  # MUTABLE allows re-pushing to the same tag (simpler CI).
  # Change to IMMUTABLE in mature setups where every deploy gets a unique tag
  # (git SHA) to prevent accidental overwrites and enable rollback by tag.
  image_tag_mutability = "MUTABLE"

  # Scan new images for OS-level CVEs automatically on push.
  # View results in ECR → Repositories → your-repo → Image scanning.
  image_scanning_configuration {
    scan_on_push = true
  }

  tags = { Name = "${local.name_prefix}-ecr" }
}

# ---------------------------------------------------------------------------
# Lifecycle policy — keep only the last 10 images to limit storage cost
# ---------------------------------------------------------------------------
# Old images accumulate quickly (1 push per deploy). This policy expires
# all "untagged" images immediately and keeps the 10 most recent tagged ones.
# Adjust count if you need longer rollback history.

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name

  policy = jsonencode({
    rules = [
      {
        # Rule 1: delete untagged images immediately.
        # These are intermediate layers from failed or replaced pushes.
        rulePriority = 1
        description  = "Expire untagged images immediately"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 1
        }
        action = { type = "expire" }
      },
      {
        # Rule 2: keep only the 10 most recent tagged images.
        # Oldest images beyond the count are expired and cannot be used for rollback.
        rulePriority = 2
        description  = "Keep last 10 tagged images"
        selection = {
          tagStatus   = "tagged"
          tagPrefixList = ["latest", "v", "sha-"]
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = { type = "expire" }
      }
    ]
  })
}
