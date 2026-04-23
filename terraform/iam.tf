# =============================================================================
# iam.tf — IAM roles for ECS
# =============================================================================
#
# ECS USES TWO SEPARATE IAM ROLES:
#
# 1. EXECUTION ROLE (ecs_execution_role)
#    Used by the ECS AGENT (the AWS infrastructure layer) to:
#    - Pull the Docker image from ECR
#    - Write container stdout/stderr to CloudWatch Logs
#    - Fetch secrets from SSM Parameter Store at task startup
#
#    This role is NOT visible to code running inside the container.
#
# 2. TASK ROLE (ecs_task_role)
#    Used by the APPLICATION CODE running inside the container.
#    Gives boto3 / AWS SDK calls within the app access to:
#    - Amazon Bedrock (AI chat feature, when llm_provider=bedrock)
#    - S3 (backup script: scripts/backup_db.py)
#
#    This role IS visible to the app (via the ECS metadata credential provider).
#    Never add AdministratorAccess or broad * permissions here.
# =============================================================================

# ---------------------------------------------------------------------------
# 1. Execution Role
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "ecs_assume_role" {
  # Allow the ECS Tasks service to assume this role
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_execution" {
  name               = "${local.name_prefix}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
  description        = "ECS agent role: pull images, write logs, read SSM secrets"
}

# AWS managed policy granting ECR pull + CloudWatch log creation.
# This policy is maintained by AWS and gets updated when new ECS features ship.
resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Additional policy: read SSM SecureString parameters used as container secrets
data "aws_iam_policy_document" "ssm_read" {
  statement {
    sid    = "ReadAppSecrets"
    effect = "Allow"

    actions = [
      "ssm:GetParameters",
      "ssm:GetParameter",
    ]

    # Scope to only this application's parameters — not the entire account.
    resources = [
      "arn:aws:ssm:${var.aws_region}:*:parameter/${var.app_name}/${var.environment}/*"
    ]
  }

  # SSM SecureString parameters are encrypted with KMS.
  # The execution role needs decrypt permission to read them.
  statement {
    sid    = "DecryptSSMKMS"
    effect = "Allow"

    actions = ["kms:Decrypt"]

    # "alias/aws/ssm" is the default SSM key — no extra KMS setup required.
    resources = ["arn:aws:kms:${var.aws_region}:*:key/alias/aws/ssm"]
  }
}

resource "aws_iam_policy" "ssm_read" {
  name        = "${local.name_prefix}-ssm-read"
  description = "Read SSM parameters for ${local.name_prefix}"
  policy      = data.aws_iam_policy_document.ssm_read.json
}

resource "aws_iam_role_policy_attachment" "ecs_execution_ssm" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = aws_iam_policy.ssm_read.arn
}

# ---------------------------------------------------------------------------
# 2. Task Role (permissions for application code)
# ---------------------------------------------------------------------------

resource "aws_iam_role" "ecs_task" {
  name               = "${local.name_prefix}-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
  description        = "Application role: Bedrock AI chat + S3 backups"
}

data "aws_iam_policy_document" "task_permissions" {
  # --- Amazon Bedrock: AI chat (llm_provider = "bedrock") -------------------
  # InvokeModelWithResponseStream is the streaming API used by app/services/chat.py.
  # Restricted to the single model ID configured in variables.tf.
  statement {
    sid    = "BedrockChat"
    effect = "Allow"

    actions = ["bedrock:InvokeModelWithResponseStream"]

    resources = [
      "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.bedrock_model_id}"
    ]
  }

  # --- S3: database backups (scripts/backup_db.py) --------------------------
  # Grants only the specific operations the backup script needs.
  # If backup_s3_bucket is empty the policy still exists but will never match
  # any real resource, so it is effectively a no-op.
  dynamic "statement" {
    for_each = var.backup_s3_bucket != "" ? [1] : []
    content {
      sid    = "S3Backup"
      effect = "Allow"

      actions = [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket",
        "s3:DeleteObject",
      ]

      resources = [
        "arn:aws:s3:::${var.backup_s3_bucket}",
        "arn:aws:s3:::${var.backup_s3_bucket}/*",
      ]
    }
  }
}

resource "aws_iam_policy" "task_permissions" {
  name        = "${local.name_prefix}-task-permissions"
  description = "App-level permissions: Bedrock + S3 backups"
  policy      = data.aws_iam_policy_document.task_permissions.json
}

resource "aws_iam_role_policy_attachment" "ecs_task_permissions" {
  role       = aws_iam_role.ecs_task.name
  policy_arn = aws_iam_policy.task_permissions.arn
}
