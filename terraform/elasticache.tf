# =============================================================================
# elasticache.tf — ElastiCache Redis 7 (event-window cache)
# =============================================================================
#
# Redis is used as a 5-minute TTL cache for FullCalendar event queries.
# The app gracefully degrades (hits PostgreSQL directly) when Redis is
# unavailable — see app/core/cache.py.
#
# CLUSTER MODE: disabled (single node).
# For HA, enable cluster mode or add a replica; for MVP a single node is fine.
# =============================================================================

# ---------------------------------------------------------------------------
# Subnet Group — ElastiCache must know which subnets to place its nodes in
# ---------------------------------------------------------------------------

resource "aws_elasticache_subnet_group" "main" {
  name       = "${local.name_prefix}-redis-subnet"
  subnet_ids = [aws_subnet.private_a.id, aws_subnet.private_b.id]
  description = "Private subnets for ElastiCache Redis"

  tags = { Name = "${local.name_prefix}-redis-subnet" }
}

# ---------------------------------------------------------------------------
# Redis Cluster
# ---------------------------------------------------------------------------

resource "aws_elasticache_cluster" "main" {
  cluster_id           = "${local.name_prefix}-redis"
  engine               = "redis"
  engine_version       = "7.1"
  node_type            = var.redis_node_type   # "cache.t3.micro" = 0.5 GB RAM
  num_cache_nodes      = 1                      # single node for MVP

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.redis.id]

  # Persist the dataset to disk so a node restart doesn't cold-start the cache.
  # "rdb" saves a point-in-time snapshot; "aof" logs every write.
  # For a 5-min TTL cache, "rdb" is sufficient — a restart costs at most 5 min
  # of extra DB load while Redis warms up.
  snapshot_retention_limit = 1

  # Automatic minor version upgrades (e.g. 7.1.0 → 7.1.1) happen in the
  # next maintenance window — they are non-breaking for Redis clients.
  auto_minor_version_upgrade = true

  # Maintenance window (low-traffic period)
  maintenance_window = "sun:04:00-sun:05:00"

  tags = { Name = "${local.name_prefix}-redis" }
}
