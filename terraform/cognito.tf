# AWS Cognito User Pool for authentication
resource "aws_cognito_user_pool" "main" {
  name = "${var.student_id}-${var.project_name}-users"

  # User attributes
  alias_attributes         = ["email", "preferred_username"]
  auto_verified_attributes = ["email"]

  # Username configuration
  username_configuration {
    case_sensitive = false
  }

  # Password policy
  password_policy {
    minimum_length                   = 8
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 7
  }

  # Account recovery
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  # MFA Configuration
  mfa_configuration          = "OPTIONAL"
  software_token_mfa_configuration {
    enabled = true
  }

  # Email configuration using SES
  email_configuration {
    email_sending_account = "DEVELOPER"
    from_email_address    = "CAB432 Authentication <auth@cab432.com>"
    source_arn           = "arn:aws:ses:${var.aws_region}:${data.aws_caller_identity.current.account_id}:identity/cab432.com"
  }

  # User pool schema
  schema {
    attribute_data_type      = "String"
    developer_only_attribute = false
    mutable                  = true
    name                     = "email"
    required                 = true

    string_attribute_constraints {
      min_length = 1
      max_length = 256
    }
  }

  schema {
    attribute_data_type      = "String"
    developer_only_attribute = false
    mutable                  = true
    name                     = "preferred_username"
    required                 = false

    string_attribute_constraints {
      min_length = 1
      max_length = 256
    }
  }

  # Device configuration
  device_configuration {
    challenge_required_on_new_device      = false
    device_only_remembered_on_user_prompt = false
  }

  # Verification message templates
  verification_message_template {
    default_email_option = "CONFIRM_WITH_CODE"
    email_message        = "Your verification code is {####}"
    email_subject        = "Your verification code"
  }

  tags = {
    Name         = "${var.student_id}-${var.project_name}-user-pool"
    qut-username = var.student_email
    purpose      = var.purpose
  }
}

# User Pool Client
resource "aws_cognito_user_pool_client" "main" {
  name         = "${var.student_id}-${var.project_name}-client"
  user_pool_id = aws_cognito_user_pool.main.id

  # Authentication flows
  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_ADMIN_USER_PASSWORD_AUTH"
  ]

  # OAuth configuration for federated identities
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows = ["code", "implicit"]
  allowed_oauth_scopes = ["email", "openid", "profile", "aws.cognito.signin.user.admin"]

  # Supported identity providers (including Google)
  supported_identity_providers = concat(
    ["COGNITO"],
    var.google_client_id != "" ? ["Google"] : []
  )

  # Callback URLs for federated auth
  callback_urls = [
    "http://localhost:3001/auth/callback",
    "https://${var.project_name}.yourdomain.com/auth/callback"
  ]
  
  logout_urls = [
    "http://localhost:3001",
    "https://${var.project_name}.yourdomain.com"
  ]

  # Token validity
  access_token_validity  = 1    # 1 hour
  id_token_validity     = 1    # 1 hour
  refresh_token_validity = 30*24   # 30 days

  # Prevent user existence errors
  prevent_user_existence_errors = "ENABLED"

  # Read and write attributes
  read_attributes = [
    "email",
    "email_verified",
    "preferred_username"
  ]

  write_attributes = [
    "email",
    "preferred_username"
  ]

  generate_secret = true

  # Ensure Google identity provider is created first if configured
  depends_on = [aws_cognito_identity_provider.google]
}

# User Pool Domain for hosted UI
resource "aws_cognito_user_pool_domain" "main" {
  domain       = "${var.student_id}-${var.project_name}-auth"
  user_pool_id = aws_cognito_user_pool.main.id
}

# Google Identity Provider for User Pool
resource "aws_cognito_identity_provider" "google" {
  count         = var.google_client_id != "" ? 1 : 0
  user_pool_id  = aws_cognito_user_pool.main.id
  provider_name = "Google"
  provider_type = "Google"

  provider_details = {
    client_id                = var.google_client_id
    client_secret            = var.google_client_secret
    authorize_scopes         = "email openid profile"
    attributes_url           = "https://people.googleapis.com/v1/people/me?personFields="
    attributes_url_add_attributes = "true"
    authorize_url            = "https://accounts.google.com/o/oauth2/v2/auth"
    oidc_issuer              = "https://accounts.google.com"
    token_request_method     = "POST"
    token_url                = "https://www.googleapis.com/oauth2/v4/token"
  }

  attribute_mapping = {
    email      = "email"
    username   = "sub"
    given_name = "given_name"
    family_name = "family_name"
  }
}

# User Groups
resource "aws_cognito_user_group" "admin" {
  name         = "Admin"
  user_pool_id = aws_cognito_user_pool.main.id
  description  = "Administrator group with full permissions"
  precedence   = 1
}

resource "aws_cognito_user_group" "user" {
  name         = "User"
  user_pool_id = aws_cognito_user_pool.main.id
  description  = "Standard user group with limited permissions"
  precedence   = 2
}

# Data source for current AWS account
data "aws_caller_identity" "current" {}
