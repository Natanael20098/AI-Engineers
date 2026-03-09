# ──────────────────────────────────────────────────────────────
# RDS Subnet Group
# ──────────────────────────────────────────────────────────────
resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-${var.environment}-db-subnet-group"
  subnet_ids = aws_subnet.private[*].id

  tags = {
    Name = "${var.project_name}-${var.environment}-db-subnet-group"
  }
}

# ──────────────────────────────────────────────────────────────
# RDS Parameter Group
# ──────────────────────────────────────────────────────────────
resource "aws_db_parameter_group" "main" {
  name   = "${var.project_name}-${var.environment}-pg16"
  family = "postgres16"

  parameter {
    name  = "log_connections"
    value = "1"
  }

  parameter {
    name  = "log_disconnections"
    value = "1"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-pg16"
  }
}

# ──────────────────────────────────────────────────────────────
# RDS Instance (Multi-AZ for high availability)
# ──────────────────────────────────────────────────────────────
resource "aws_db_instance" "main" {
  identifier = "${var.project_name}-${var.environment}-db"

  engine         = "postgres"
  engine_version = "16.2"
  instance_class = var.db_instance_class

  db_name  = var.db_name
  username = var.db_username
  password = var.db_password

  allocated_storage     = 20
  max_allocated_storage = 100
  storage_type          = "gp3"
  storage_encrypted     = true

  multi_az               = true
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  parameter_group_name   = aws_db_parameter_group.main.name

  backup_retention_period   = 7
  backup_window             = "03:00-04:00"
  maintenance_window        = "sun:04:00-sun:05:00"
  auto_minor_version_upgrade = true

  deletion_protection = true
  skip_final_snapshot = false
  final_snapshot_identifier = "${var.project_name}-${var.environment}-final-snapshot"

  performance_insights_enabled          = true
  performance_insights_retention_period = 7

  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  tags = {
    Name = "${var.project_name}-${var.environment}-db"
  }
}

# ──────────────────────────────────────────────────────────────
# Initial Schema via SSM (ECS connectivity)
# ──────────────────────────────────────────────────────────────
resource "aws_ssm_parameter" "db_endpoint" {
  name  = "/${var.project_name}/${var.environment}/db/endpoint"
  type  = "String"
  value = aws_db_instance.main.endpoint

  tags = {
    Name = "${var.project_name}-${var.environment}-db-endpoint"
  }
}

resource "aws_ssm_parameter" "db_name" {
  name  = "/${var.project_name}/${var.environment}/db/name"
  type  = "String"
  value = var.db_name

  tags = {
    Name = "${var.project_name}-${var.environment}-db-name"
  }
}
