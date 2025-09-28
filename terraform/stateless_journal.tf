# Job Processing Journal System for Stateless Operations
# Implements journaling pattern to handle interrupted tasks safely

# DynamoDB table for job processing journal
resource "aws_dynamodb_table" "job_journal" {
  name           = "${var.project_name}-${var.username}-job-journal"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "journal_id"
  
  attribute {
    name = "journal_id"
    type = "S"
  }
  
  attribute {
    name = "job_id"
    type = "S"
  }
  
  attribute {
    name = "status"
    type = "S"
  }
  
  attribute {
    name = "created_at"
    type = "S"
  }
  
  # Global secondary index for querying by job_id
  global_secondary_index {
    name            = "job-id-index"
    hash_key        = "job_id"
    projection_type = "ALL"
  }
  
  # Global secondary index for querying by status and created_at (for cleanup)
  global_secondary_index {
    name            = "status-created-index"
    hash_key        = "status"
    range_key       = "created_at"
    projection_type = "ALL"
  }
  
  # TTL for automatic cleanup of old records
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
  
  # point_in_time_recovery {
  #   enabled = false
  # }

  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
    component    = "job-journal"
  }

  # lifecycle {
  #   ignore_changes = [
  #     point_in_time_recovery,
  #   ]
  # }
}

# DynamoDB table for distributed locks (prevents race conditions)
resource "aws_dynamodb_table" "distributed_locks" {
  name           = "${var.project_name}-${var.username}-locks"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "lock_key"
  
  attribute {
    name = "lock_key"
    type = "S"
  }
  
  attribute {
    name = "expires_at"
    type = "N"
  }
  
  # Global secondary index for cleanup of expired locks
  global_secondary_index {
    name            = "expires-at-index"
    hash_key        = "expires_at"
    projection_type = "ALL"
  }
  
  # TTL for automatic cleanup of expired locks
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
  
  # point_in_time_recovery {
  #   enabled = false
  # }

  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
    component    = "distributed-locks"
  }

  # lifecycle {
  #   ignore_changes = [
  #     point_in_time_recovery,
  #   ]
  # }
}

# SQS queue for reliable job processing
resource "aws_sqs_queue" "job_processing" {
  name                       = "${var.project_name}-${var.username}-job-processing"
  delay_seconds              = 0
  max_message_size           = 262144
  message_retention_seconds  = 1209600  # 14 days
  receive_wait_time_seconds  = 20       # Long polling
  visibility_timeout_seconds = 300      # 5 minutes to process
  
  # Dead letter queue for failed jobs
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.job_processing_dlq.arn
    maxReceiveCount     = 3
  })
  
  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
    component    = "job-queue"
  }
}

# Dead letter queue for failed jobs
resource "aws_sqs_queue" "job_processing_dlq" {
  name                      = "${var.project_name}-${var.username}-job-processing-dlq"
  message_retention_seconds = 1209600  # 14 days
  
  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
    component    = "job-dlq"
  }
}

# SQS queue for cleanup operations
resource "aws_sqs_queue" "cleanup_operations" {
  name                       = "${var.project_name}-${var.username}-cleanup"
  delay_seconds              = 0
  max_message_size           = 262144
  message_retention_seconds  = 604800   # 7 days
  receive_wait_time_seconds  = 20       # Long polling
  visibility_timeout_seconds = 120      # 2 minutes to process
  
  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
    component    = "cleanup-queue"
  }
}

# CloudWatch Events rule for periodic cleanup
resource "aws_cloudwatch_event_rule" "cleanup_schedule" {
  name                = "${var.project_name}-${var.username}-cleanup-schedule" 
  description         = "Trigger cleanup operations every 5 minutes"
  schedule_expression = "rate(5 minutes)"
  
  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
  }
}

# CloudWatch Events rule for journal recovery
resource "aws_cloudwatch_event_rule" "journal_recovery_schedule" {
  name                = "${var.project_name}-${var.username}-journal-recovery"
  description         = "Trigger journal recovery every 2 minutes"
  schedule_expression = "rate(2 minutes)"
  
  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
  }
}