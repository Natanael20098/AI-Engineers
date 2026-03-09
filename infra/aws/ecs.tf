# ──────────────────────────────────────────────────────────────
# ECS Cluster
# ──────────────────────────────────────────────────────────────
resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-cluster"
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.main.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    base              = 1
    weight            = 100
    capacity_provider = "FARGATE"
  }
}

# ──────────────────────────────────────────────────────────────
# IAM Roles for ECS
# ──────────────────────────────────────────────────────────────
resource "aws_iam_role" "ecs_task_execution" {
  name = "${var.project_name}-${var.environment}-ecs-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "ecs_task" {
  name = "${var.project_name}-${var.environment}-ecs-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "ecs_task_cloudwatch" {
  name = "cloudwatch-logs"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ]
      Resource = "arn:aws:logs:*:*:*"
    }]
  })
}

# ──────────────────────────────────────────────────────────────
# Application Load Balancer
# ──────────────────────────────────────────────────────────────
resource "aws_lb" "main" {
  name               = "${var.project_name}-${var.environment}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  enable_deletion_protection = false

  tags = {
    Name = "${var.project_name}-${var.environment}-alb"
  }
}

resource "aws_lb_target_group" "authentication" {
  name        = "${var.project_name}-${var.environment}-auth-tg"
  port        = 5000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    enabled             = true
    path                = "/health"
    port                = "traffic-port"
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    matcher             = "200"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.authentication.arn
  }
}

# ──────────────────────────────────────────────────────────────
# CloudWatch Log Groups
# ──────────────────────────────────────────────────────────────
resource "aws_cloudwatch_log_group" "authentication" {
  name              = "/ecs/${var.project_name}-${var.environment}/authentication"
  retention_in_days = 30
}

# ──────────────────────────────────────────────────────────────
# ECS Task Definition: Authentication Service
# ──────────────────────────────────────────────────────────────
resource "aws_ecs_task_definition" "authentication" {
  family                   = "${var.project_name}-${var.environment}-authentication"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.ecs_task_cpu
  memory                   = var.ecs_task_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "authentication"
    image     = var.authentication_image
    essential = true

    portMappings = [{
      containerPort = 5000
      protocol      = "tcp"
    }]

    environment = [
      { name = "FLASK_ENV", value = var.environment },
      { name = "TOKEN_BLACKLIST_BACKEND", value = "redis" }
    ]

    secrets = [
      { name = "SECRET_KEY", valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:SECRET_KEY::" },
      { name = "REDIS_URL", valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:REDIS_URL::" }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.authentication.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:5000/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }
  }])

  tags = {
    Name = "${var.project_name}-${var.environment}-authentication-task"
  }
}

# ──────────────────────────────────────────────────────────────
# Secrets Manager
# ──────────────────────────────────────────────────────────────
resource "aws_secretsmanager_secret" "app_secrets" {
  name        = "${var.project_name}/${var.environment}/app-secrets"
  description = "Application secrets for Natanael microservices"

  tags = {
    Name = "${var.project_name}-${var.environment}-app-secrets"
  }
}

# ──────────────────────────────────────────────────────────────
# ECS Service: Authentication
# ──────────────────────────────────────────────────────────────
resource "aws_ecs_service" "authentication" {
  name            = "${var.project_name}-${var.environment}-authentication"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.authentication.arn
  desired_count   = 2
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.authentication.arn
    container_name   = "authentication"
    container_port   = 5000
  }

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  depends_on = [aws_lb_listener.http]

  tags = {
    Name = "${var.project_name}-${var.environment}-authentication-service"
  }
}

# ──────────────────────────────────────────────────────────────
# Auto Scaling for ECS Service
# ──────────────────────────────────────────────────────────────
resource "aws_appautoscaling_target" "authentication" {
  max_capacity       = 10
  min_capacity       = 2
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.authentication.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "authentication_cpu" {
  name               = "${var.project_name}-${var.environment}-auth-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.authentication.resource_id
  scalable_dimension = aws_appautoscaling_target.authentication.scalable_dimension
  service_namespace  = aws_appautoscaling_target.authentication.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 70.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}
