output "s3_bucket_name" {
  description = "Name of the S3 bucket"
  value       = aws_s3_bucket.images.bucket
}

output "s3_bucket_arn" {
  description = "ARN of the S3 bucket"
  value       = aws_s3_bucket.images.arn
}

output "shared_db_host" {
  description = "Shared PostgreSQL database host"
  value       = var.shared_db_host
}

output "shared_db_port" {
  description = "Shared PostgreSQL database port"
  value       = var.shared_db_port
}

output "shared_db_name" {
  description = "Shared PostgreSQL database name"
  value       = var.shared_db_name
}

output "database_url" {
  description = "PostgreSQL database connection URL"
  value       = "postgresql://${var.shared_db_username}:${var.shared_db_password}@${var.shared_db_host}:${var.shared_db_port}/${var.shared_db_name}?sslmode=require"
  sensitive   = true
}

output "shared_db_username" {
  description = "Shared PostgreSQL database username"
  value       = var.shared_db_username
  sensitive   = true
}

output "shared_db_password" {
  description = "Shared PostgreSQL database password"
  value       = var.shared_db_password
  sensitive   = true
}

output "vpc_id" {
  description = "ID of the existing VPC"
  value       = data.aws_vpc.existing.id
}

output "public_subnet_id" {
  description = "ID of the public subnet"
  value       = data.aws_subnet.public.id
}

output "private_subnet_id" {
  description = "ID of the private subnet"
  value       = data.aws_subnet.private.id
}

output "app_security_group_id" {
  description = "ID of the application security group"
  value       = data.aws_security_group.app.id
}

# Note: RDS security group not needed for shared PostgreSQL database

# output "iam_role_name" {
#   description = "Name of the existing IAM role for EC2 instances"
#   value       = data.aws_iam_role.app_role.name
# }

output "aws_region" {
  description = "AWS region"
  value       = var.aws_region
}

# Cognito outputs
output "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  value       = aws_cognito_user_pool.main.id
}

output "cognito_user_pool_client_id" {
  description = "Cognito User Pool Client ID"
  value       = aws_cognito_user_pool_client.main.id
}

output "cognito_user_pool_client_secret" {
  description = "Cognito User Pool Client Secret"
  value       = aws_cognito_user_pool_client.main.client_secret
  sensitive   = true
}

output "cognito_user_pool_domain" {
  description = "Cognito User Pool Domain"
  value       = aws_cognito_user_pool_domain.main.domain
}

output "cognito_hosted_ui_url" {
  description = "Cognito Hosted UI URL for authentication"
  value       = "https://${aws_cognito_user_pool_domain.main.domain}.auth.${var.aws_region}.amazoncognito.com"
}

output "google_oauth_enabled" {
  description = "Whether Google OAuth is enabled"
  value       = var.google_client_id != ""
}

output "cognito_oauth_urls" {
  description = "Cognito OAuth URLs for different flows"
  value = {
    login = "https://${aws_cognito_user_pool_domain.main.domain}.auth.${var.aws_region}.amazoncognito.com/login?client_id=${aws_cognito_user_pool_client.main.id}&response_type=code&scope=email+openid+profile&redirect_uri=http://localhost:3001/auth/callback"
    google_login = var.google_client_id != "" ? "https://${aws_cognito_user_pool_domain.main.domain}.auth.${var.aws_region}.amazoncognito.com/oauth2/authorize?client_id=${aws_cognito_user_pool_client.main.id}&response_type=code&scope=email+openid+profile&redirect_uri=http://localhost:3001/auth/callback&identity_provider=Google" : ""
    logout = "https://${aws_cognito_user_pool_domain.main.domain}.auth.${var.aws_region}.amazoncognito.com/logout?client_id=${aws_cognito_user_pool_client.main.id}&logout_uri=http://localhost:3001"
  }
}

# output "cognito_identity_pool_id" {
#   description = "Cognito Identity Pool ID"
#   value       = aws_cognito_identity_pool.main.id
# }

# Parameter Store Outputs
output "parameter_store_parameters" {
  description = "Parameter Store parameter names and ARNs"
  value = {
    api_base_url = {
      name = aws_ssm_parameter.api_base_url.name
      arn  = aws_ssm_parameter.api_base_url.arn
    }
    frontend_url = {
      name = aws_ssm_parameter.frontend_url.name
      arn  = aws_ssm_parameter.frontend_url.arn
    }
    s3_bucket_name = {
      name = aws_ssm_parameter.s3_bucket_name.name
      arn  = aws_ssm_parameter.s3_bucket_name.arn
    }
    cognito_user_pool_id = {
      name = aws_ssm_parameter.cognito_user_pool_id.name
      arn  = aws_ssm_parameter.cognito_user_pool_id.arn
    }
    cognito_user_pool_client_id = {
      name = aws_ssm_parameter.cognito_user_pool_client_id.name
      arn  = aws_ssm_parameter.cognito_user_pool_client_id.arn
    }
  }
}

# Secrets Manager Outputs  
output "secrets_manager_secrets" {
  description = "Secrets Manager secret names and ARNs"
  value = {
    database_credentials = {
      name = aws_secretsmanager_secret.database_credentials.name
      arn  = aws_secretsmanager_secret.database_credentials.arn
    }
    jwt_secret = {
      name = aws_secretsmanager_secret.jwt_secret.name
      arn  = aws_secretsmanager_secret.jwt_secret.arn
    }
    huggingface_token = {
      name = aws_secretsmanager_secret.huggingface_token.name
      arn  = aws_secretsmanager_secret.huggingface_token.arn
    }
    s3_access_keys = {
      name = aws_secretsmanager_secret.s3_access_keys.name
      arn  = aws_secretsmanager_secret.s3_access_keys.arn
    }
    app_config = {
      name = aws_secretsmanager_secret.app_config.name
      arn  = aws_secretsmanager_secret.app_config.arn
    }
  }
}

# AWS Config Service Access Information
output "aws_config_info" {
  description = "Information for accessing AWS Parameter Store and Secrets Manager"
  value = {
    region = var.aws_region
    parameter_prefix = "/unstablefusion/${var.username}"
    secret_prefix = "unstablefusion/${var.username}"
    username = var.username
  }
}