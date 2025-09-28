
# ElastiCache subnet group
resource "aws_elasticache_subnet_group" "session_cache" {
  name       = "${var.project_name}-${var.username}-session-cache"
  subnet_ids = [var.existing_private_subnet_id]
  
  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
    component    = "session-cache"
  }
}

# ElastiCache Redis cluster for session storage
resource "aws_elasticache_cluster" "session_cache" {
  cluster_id           = "${var.project_name}-${var.username}-session-cluster"
  engine               = "redis"
  node_type            = "cache.t4g.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  port                 = 6379
  
  subnet_group_name    = aws_elasticache_subnet_group.session_cache.name
  security_group_ids   = [var.existing_app_security_group_id]
  
  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
    component    = "session-cache"
  }
}

# Store Redis connection info in Parameter Store
resource "aws_ssm_parameter" "redis_endpoint" {
  name        = "/unstablefusion/${var.username}/redis_endpoint"
  description = "Redis endpoint for session storage"
  type        = "String"
  value       = aws_elasticache_cluster.session_cache.cache_nodes[0].address
  
  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
  }
}

resource "aws_ssm_parameter" "redis_port" {
  name        = "/unstablefusion/${var.username}/redis_port"
  description = "Redis port for session storage"
  type        = "String"
  value       = tostring(aws_elasticache_cluster.session_cache.port)
  
  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
  }
}

# Application Load Balancer for stateless scaling
resource "aws_lb" "application" {
  name               = "${var.project_name}-${var.username}-alb"
  internal           = false
  load_balancer_type = "application"
  subnets           = [var.existing_public_subnet_id, var.existing_private_subnet_id]

  enable_deletion_protection = false

  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
    component    = "load-balancer"
  }
}

# Target group for application instances
resource "aws_lb_target_group" "application" {
  name     = "${var.project_name}-${var.username}-app-tg"
  port     = 8000
  protocol = "HTTP"
  vpc_id   = var.existing_vpc_id

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 10
    interval            = 30
    path                = "/health"
    matcher             = "200"
    port                = "traffic-port"
    protocol            = "HTTP"
  }

  # Enable session stickiness (can be disabled for true statelessness)
  stickiness {
    type            = "lb_cookie"
    cookie_duration = 86400  # 24 hours
    enabled         = false  # Disabled for stateless operation
  }

  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
    component    = "target-group"
  }
}

# ALB listener for HTTP traffic
resource "aws_lb_listener" "application" {
  load_balancer_arn = aws_lb.application.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.application.arn
  }

  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
  }
}