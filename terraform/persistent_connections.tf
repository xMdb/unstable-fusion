# SQS Queue for connection management
resource "aws_sqs_queue" "connection_management" {
  name                       = "${var.student_id}-${var.project_name}-connection-mgmt"
  delay_seconds              = 0
  max_message_size           = 262144
  message_retention_seconds  = 1209600  # 14 days
  receive_wait_time_seconds  = 0
  visibility_timeout_seconds = 300

  # Dead letter queue configuration
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.connection_management_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Name         = "${var.student_id}-${var.project_name}-connection-mgmt"
    qut-username = var.student_email
    purpose      = var.purpose
  }
}

# Dead Letter Queue for connection management
resource "aws_sqs_queue" "connection_management_dlq" {
  name = "${var.student_id}-${var.project_name}-connection-mgmt-dlq"

  tags = {
    Name         = "${var.student_id}-${var.project_name}-connection-mgmt-dlq"
    qut-username = var.student_email
    purpose      = var.purpose
  }
}

# DynamoDB table for active connections
resource "aws_dynamodb_table" "active_connections" {
  name           = "${var.student_id}-${var.project_name}-active-connections"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "connection_id"

  attribute {
    name = "connection_id"
    type = "S"
  }

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "instance_id"
    type = "S"
  }

  attribute {
    name = "connection_type"
    type = "S"
  }

  # GSI for querying by user_id
  global_secondary_index {
    name            = "user-id-index"
    hash_key        = "user_id"
    projection_type = "ALL"
  }

  # GSI for querying by instance_id
  global_secondary_index {
    name            = "instance-id-index"
    hash_key        = "instance_id"
    projection_type = "ALL"
  }

  # GSI for querying by connection type
  global_secondary_index {
    name            = "connection-type-index"
    hash_key        = "connection_type"
    projection_type = "ALL"
  }

  # TTL for automatic cleanup of stale connections
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  # point_in_time_recovery {
  #   enabled = false
  # }

  tags = {
    Name         = "${var.student_id}-${var.project_name}-active-connections"
    qut-username = var.student_email
    purpose      = var.purpose
  }

  # lifecycle {
  #   ignore_changes = [
  #     point_in_time_recovery,
  #   ]
  # }
}

# DynamoDB table for connection state/progress
resource "aws_dynamodb_table" "connection_state" {
  name           = "${var.student_id}-${var.project_name}-connection-state"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "state_key"

  attribute {
    name = "state_key"
    type = "S"
  }

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "job_id"
    type = "S"
  }

  # GSI for querying by user_id
  global_secondary_index {
    name            = "user-id-index"
    hash_key        = "user_id"
    projection_type = "ALL"
  }

  # GSI for querying by job_id
  global_secondary_index {
    name            = "job-id-index"
    hash_key        = "job_id"
    projection_type = "ALL"
  }

  # TTL for automatic cleanup
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  # point_in_time_recovery {
  #   enabled = false
  # }

  tags = {
    Name         = "${var.student_id}-${var.project_name}-connection-state"
    qut-username = var.student_email
    purpose      = var.purpose
  }

  # lifecycle {
  #   ignore_changes = [
  #     point_in_time_recovery,
  #   ]
  # }
}

# ElastiCache Redis cluster for real-time connection data
resource "aws_elasticache_subnet_group" "connection_cache" {
  name       = "${var.student_id}-${var.project_name}-connection-cache"
  subnet_ids = [var.existing_private_subnet_id]
}

resource "aws_elasticache_cluster" "connection_cache" {
  cluster_id           = "${var.student_id}-${var.project_name}-conn-cache"
  engine               = "redis"
  node_type            = "cache.t4g.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  port                 = 6379
  
  subnet_group_name    = aws_elasticache_subnet_group.connection_cache.name
  security_group_ids   = [var.existing_app_security_group_id]

  tags = {
    Name         = "${var.student_id}-${var.project_name}-connection-cache"
    qut-username = var.student_email
    purpose      = var.purpose
  }
}

# API Gateway WebSocket API
resource "aws_apigatewayv2_api" "websocket" {
  name                       = "${var.student_id}-${var.project_name}-websocket"
  protocol_type             = "WEBSOCKET"
  route_selection_expression = "$request.body.action"

  tags = {
    Name         = "${var.student_id}-${var.project_name}-websocket"
    qut-username = var.student_email
    purpose      = var.purpose
  }
}

# WebSocket stage
resource "aws_apigatewayv2_stage" "websocket" {
  api_id = aws_apigatewayv2_api.websocket.id
  name   = "production"

  tags = {
    Name         = "${var.student_id}-${var.project_name}-websocket-stage"
    qut-username = var.student_email
    purpose      = var.purpose
  }
}

output "connection_management_queue_url" {
  description = "URL of the SQS queue for connection management"
  value       = aws_sqs_queue.connection_management.url
}

output "active_connections_table_name" {
  description = "Name of the DynamoDB table for active connections"
  value       = aws_dynamodb_table.active_connections.name
}

output "connection_state_table_name" {
  description = "Name of the DynamoDB table for connection state"
  value       = aws_dynamodb_table.connection_state.name
}

output "connection_cache_endpoint" {
  description = "Redis endpoint for connection cache"
  value       = aws_elasticache_cluster.connection_cache.cache_nodes[0].address
}

output "websocket_api_endpoint" {
  description = "WebSocket API endpoint"
  value       = aws_apigatewayv2_api.websocket.api_endpoint
}

output "websocket_api_id" {
  description = "WebSocket API ID"
  value       = aws_apigatewayv2_api.websocket.id
}