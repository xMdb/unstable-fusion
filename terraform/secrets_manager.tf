
# PostgreSQL Database Credentials
resource "aws_secretsmanager_secret" "database_credentials" {
  name                    = "unstablefusion/${var.username}/database-credentials"
  description             = "PostgreSQL database credentials for UnstableFusion"
  recovery_window_in_days = 7
  
  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
    type         = "database-credentials"
  }
}

resource "aws_secretsmanager_secret_version" "database_credentials" {
  secret_id = aws_secretsmanager_secret.database_credentials.id
  secret_string = jsonencode({
    username = var.shared_db_username
    password = var.shared_db_password
    engine   = "postgres"
    host     = var.shared_db_host
    port     = var.shared_db_port
    dbname   = var.shared_db_name
  })
}

# JWT Secret Key for authentication
resource "aws_secretsmanager_secret" "jwt_secret" {
  name                    = "unstablefusion/${var.username}/jwt-secret"
  description             = "JWT secret key for token signing"
  recovery_window_in_days = 7
  
  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
    type         = "jwt-secret"
  }
}

resource "aws_secretsmanager_secret_version" "jwt_secret" {
  secret_id = aws_secretsmanager_secret.jwt_secret.id
  secret_string = jsonencode({
    secret_key = random_password.jwt_secret.result
    algorithm  = "HS256"
  })
}

# Generate a random JWT secret
resource "random_password" "jwt_secret" {
  length  = 64
  special = true
}

# Hugging Face API Token (for AI model access)
resource "aws_secretsmanager_secret" "huggingface_token" {
  name                    = "unstablefusion/${var.username}/huggingface-token"
  description             = "Hugging Face API token for model access"
  recovery_window_in_days = 7
  
  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
    type         = "api-token"
  }
}

resource "aws_secretsmanager_secret_version" "huggingface_token" {
  secret_id = aws_secretsmanager_secret.huggingface_token.id
  secret_string = jsonencode({
    token     = var.huggingface_token
    api_url   = "https://api-inference.huggingface.co"
    provider  = "huggingface"
  })
}

# Google OAuth Client Secret (for federated authentication)
resource "aws_secretsmanager_secret" "google_oauth_secret" {
  count                   = var.google_client_secret != "" ? 1 : 0
  name                    = "unstablefusion/${var.username}/google-oauth-secret"
  description             = "Google OAuth client secret for federated authentication"
  recovery_window_in_days = 7
  
  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
    type         = "oauth-secret"
  }
}

resource "aws_secretsmanager_secret_version" "google_oauth_secret" {
  count     = var.google_client_secret != "" ? 1 : 0
  secret_id = aws_secretsmanager_secret.google_oauth_secret[0].id
  secret_string = jsonencode({
    client_id     = var.google_client_id
    client_secret = var.google_client_secret
    provider      = "google"
    scopes        = ["openid", "email", "profile"]
  })
}

# S3 Access Keys (if needed for direct access)
resource "aws_secretsmanager_secret" "s3_access_keys" {
  name                    = "unstablefusion/${var.username}/s3-access-keys"
  description             = "S3 access keys for image storage operations"
  recovery_window_in_days = 7
  
  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
    type         = "aws-credentials"
  }
}

resource "aws_secretsmanager_secret_version" "s3_access_keys" {
  secret_id = aws_secretsmanager_secret.s3_access_keys.id
  secret_string = jsonencode({
    access_key_id     = "PLACEHOLDER_ACCESS_KEY_ID"
    secret_access_key = "PLACEHOLDER_SECRET_ACCESS_KEY"
    region           = var.aws_region
    bucket_name      = aws_s3_bucket.images.bucket
  })
}

# Application Configuration Secret (for runtime config)
resource "aws_secretsmanager_secret" "app_config" {
  name                    = "unstablefusion/${var.username}/app-config"
  description             = "Application runtime configuration secrets"
  recovery_window_in_days = 7
  
  tags = {
    qut-username = var.qut_username
    purpose      = "assessment 2"
    environment  = var.environment
    service      = "unstablefusion"
    type         = "app-config"
  }
}

resource "aws_secretsmanager_secret_version" "app_config" {
  secret_id = aws_secretsmanager_secret.app_config.id
  secret_string = jsonencode({
    debug_mode           = var.environment == "dev"
    max_concurrent_jobs  = 10
    image_retention_days = 30
    rate_limit_per_user  = 100
    session_timeout      = 3600
    cors_origins         = [
      "http://localhost:5173",
      "http://localhost:3000"
    ]
  })
}