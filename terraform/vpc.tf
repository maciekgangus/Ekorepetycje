# =============================================================================
# vpc.tf — Virtual Private Cloud: network topology
# =============================================================================
#
# TOPOLOGY
#
#   Internet
#      │
#      ▼
#   Internet Gateway (igw)
#      │
#   ┌──┴──────────────────────────────────────────────────────────────┐
#   │                       VPC  10.0.0.0/16                          │
#   │                                                                  │
#   │  ┌─────────────────────────┐  ┌─────────────────────────┐       │
#   │  │  Public subnet AZ-a     │  │  Public subnet AZ-b     │       │
#   │  │  10.0.0.0/24            │  │  10.0.1.0/24            │       │
#   │  │  ALB nodes              │  │  ALB nodes              │       │
#   │  │  NAT Gateway ←─── EIP  │  │                         │       │
#   │  └───────────┬─────────────┘  └─────────────────────────┘       │
#   │              │ NAT                                               │
#   │  ┌───────────▼─────────────┐  ┌─────────────────────────┐       │
#   │  │  Private subnet AZ-a    │  │  Private subnet AZ-b    │       │
#   │  │  10.0.10.0/24           │  │  10.0.11.0/24           │       │
#   │  │  ECS tasks              │  │  ECS tasks (HA)         │       │
#   │  │  RDS primary            │  │  RDS standby (Multi-AZ) │       │
#   │  │  ElastiCache node       │  │  ElastiCache (if HA)    │       │
#   │  └─────────────────────────┘  └─────────────────────────┘       │
#   └──────────────────────────────────────────────────────────────────┘
#
# WHY TWO AZs?
#   AWS requires ALB and RDS subnet groups to span ≥ 2 AZs.
#   It also enables zero-downtime Multi-AZ failover later with no re-architecturing.
# =============================================================================

# ---------------------------------------------------------------------------
# VPC
# ---------------------------------------------------------------------------

resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"

  # Enable DNS hostname resolution so RDS/ElastiCache endpoints resolve correctly
  # inside the VPC without extra DNS configuration.
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = { Name = "${local.name_prefix}-vpc" }
}

# ---------------------------------------------------------------------------
# Public subnets — host the ALB and NAT Gateway
# ---------------------------------------------------------------------------

resource "aws_subnet" "public_a" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.0.0/24"
  availability_zone = "${var.aws_region}a"

  # Instances launched here get a public IP automatically.
  # Needed so the NAT Gateway has reachability to the Internet Gateway.
  map_public_ip_on_launch = true

  tags = { Name = "${local.name_prefix}-public-a" }
}

resource "aws_subnet" "public_b" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "${var.aws_region}b"

  map_public_ip_on_launch = true

  tags = { Name = "${local.name_prefix}-public-b" }
}

# ---------------------------------------------------------------------------
# Private subnets — host ECS tasks, RDS, and ElastiCache
# ---------------------------------------------------------------------------

resource "aws_subnet" "private_a" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.10.0/24"
  availability_zone = "${var.aws_region}a"

  tags = { Name = "${local.name_prefix}-private-a" }
}

resource "aws_subnet" "private_b" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.11.0/24"
  availability_zone = "${var.aws_region}b"

  tags = { Name = "${local.name_prefix}-private-b" }
}

# ---------------------------------------------------------------------------
# Internet Gateway — gives the public subnets a path to the internet
# ---------------------------------------------------------------------------

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = { Name = "${local.name_prefix}-igw" }
}

# ---------------------------------------------------------------------------
# NAT Gateway — gives private subnets outbound internet access
#
# Single NAT Gateway keeps costs low for MVP (~$35/month).
# For high availability, create one per AZ and use separate route tables.
# ---------------------------------------------------------------------------

# Elastic IP address attached to the NAT Gateway.
# The EIP address is static so external services (e.g. Resend email API)
# can allowlist this IP if needed.
resource "aws_eip" "nat" {
  domain = "vpc"

  # EIP must be released only after the NAT Gateway it powers is destroyed.
  depends_on = [aws_internet_gateway.main]

  tags = { Name = "${local.name_prefix}-nat-eip" }
}

resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public_a.id  # NAT lives in a PUBLIC subnet

  tags = { Name = "${local.name_prefix}-nat" }
}

# ---------------------------------------------------------------------------
# Route tables
# ---------------------------------------------------------------------------

# Public route table: default route → Internet Gateway
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = { Name = "${local.name_prefix}-rt-public" }
}

# Private route table: default route → NAT Gateway
# (so ECS can reach ECR, SSM, Resend API, etc.)
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }

  tags = { Name = "${local.name_prefix}-rt-private" }
}

# Associate public subnets with the public route table
resource "aws_route_table_association" "public_a" {
  subnet_id      = aws_subnet.public_a.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "public_b" {
  subnet_id      = aws_subnet.public_b.id
  route_table_id = aws_route_table.public.id
}

# Associate private subnets with the private route table
resource "aws_route_table_association" "private_a" {
  subnet_id      = aws_subnet.private_a.id
  route_table_id = aws_route_table.private.id
}

resource "aws_route_table_association" "private_b" {
  subnet_id      = aws_subnet.private_b.id
  route_table_id = aws_route_table.private.id
}
