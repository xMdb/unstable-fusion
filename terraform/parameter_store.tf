# Application API Base URL for frontend
resource "aws_ssm_parameter" "api_base_url" {
  name        = "/unstablefusion/${var.username}/api_base_url"
  description = "Base URL for the UnstableFusion API"
  type        = "String"
  value       = "http://localhost:8000/api/"
  
  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
  }
}

# Frontend URL for CORS and redirects
resource "aws_ssm_parameter" "frontend_url" {
  name        = "/unstablefusion/${var.username}/frontend_url"
  description = "Frontend URL for CORS configuration"
  type        = "String"
  value       = "http://localhost:5173"
  
  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
  }
}

# S3 bucket name for image storage
resource "aws_ssm_parameter" "s3_bucket_name" {
  name        = "/unstablefusion/${var.username}/s3_bucket_name"
  description = "S3 bucket name for image storage"
  type        = "String"
  value       = aws_s3_bucket.images.bucket
  
  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
  }
}

# AWS Region parameter
resource "aws_ssm_parameter" "aws_region" {
  name        = "/unstablefusion/${var.username}/aws_region"
  description = "AWS region for the application"
  type        = "String"
  value       = var.aws_region
  
  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
  }
}

# Cognito User Pool ID
resource "aws_ssm_parameter" "cognito_user_pool_id" {
  name        = "/unstablefusion/${var.username}/cognito_user_pool_id"
  description = "Cognito User Pool ID for authentication"
  type        = "String"
  value       = aws_cognito_user_pool.main.id
  
  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
  }
}

# Cognito User Pool Client ID
resource "aws_ssm_parameter" "cognito_user_pool_client_id" {
  name        = "/unstablefusion/${var.username}/cognito_user_pool_client_id"
  description = "Cognito User Pool Client ID for authentication"
  type        = "String"
  value       = aws_cognito_user_pool_client.main.id
  
  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
  }
}


# Cognito Hosted UI URL
resource "aws_ssm_parameter" "cognito_hosted_ui_url" {
  name        = "/unstablefusion/${var.username}/cognito_hosted_ui_url"
  description = "Cognito Hosted UI URL for authentication"
  type        = "String"
  value       = "https://${aws_cognito_user_pool_domain.main.domain}.auth.${var.aws_region}.amazoncognito.com"
  
  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
  }
}

# PostgreSQL database host
resource "aws_ssm_parameter" "database_host" {
  name        = "/unstablefusion/${var.username}/database_host"
  description = "PostgreSQL database host"
  type        = "String"
  value       = var.database_host
  
  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
  }
}

# Database name
resource "aws_ssm_parameter" "database_name" {
  name        = "/unstablefusion/${var.username}/database_name"
  description = "PostgreSQL database name"
  type        = "String"
  value       = var.database_name
  
  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
  }
}

# Maximum image generation dimensions
resource "aws_ssm_parameter" "max_image_dimensions" {
  name        = "/unstablefusion/${var.username}/max_image_dimensions"
  description = "Maximum allowed image dimensions for generation"
  type        = "String"
  value       = "1024x1024"
  
  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
  }
}

# Default model for image generation
resource "aws_ssm_parameter" "default_model" {
  name        = "/unstablefusion/${var.username}/default_model"
  description = "Default model for image generation"
  type        = "String"
  value       = "stabilityai/sd-turbo"
  
  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
  }
}