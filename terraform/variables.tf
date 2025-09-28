variable "project_name" {
  description = "Name of the project"
  type        = string
  default     = "unstable-fusion"
}

variable "student_id" {
  description = "Student ID"
  type        = string
}

variable "student_email" {
  description = "Student email"
  type        = string
}

variable "purpose" {
  description = "Purpose tag for resources to prevent deletion"
  type        = string
  default     = "assessment 3"
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "ap-southeast-2"
}

# Shared PostgreSQL Database Configuration
variable "shared_db_host" {
  description = "Shared PostgreSQL database host"
  type        = string
}

variable "shared_db_port" {
  description = "Shared PostgreSQL database port"
  type        = string
}

variable "shared_db_name" {
  description = "Shared PostgreSQL database name"
  type        = string
}

variable "shared_db_username" {
  description = "Your assigned PostgreSQL database username"
  type        = string
}

variable "shared_db_password" {
  description = "Your assigned PostgreSQL database password"
  type        = string
  sensitive   = true
}

# Existing AWS Resources
variable "existing_vpc_id" {
  description = "ID of the existing VPC to use"
  type        = string
}

variable "existing_public_subnet_id" {
  description = "ID of the existing public subnet to use"
  type        = string
}

variable "existing_private_subnet_id" {
  description = "ID of the existing private subnet to use"
  type        = string
}

variable "existing_app_security_group_id" {
  description = "ID of the existing security group for application servers"
  type        = string
}

variable "existing_iam_role_name" {
  description = "Name of the existing IAM role for EC2 instances"
  type        = string
}

# Cognito Configuration
variable "google_client_id" {
  description = "Google OAuth client ID for federated authentication"
  type        = string
  default     = ""
}

# Parameter Store and Secrets Manager Variables
variable "username" {
  description = "Username for parameter store naming"
  type        = string
  default     = "unstablefusion"
}

variable "qut_username" {
  description = "QUT username for tagging resources"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, prod, etc.)"
  type        = string
  default     = "dev"
}

variable "database_host" {
  description = "Database host for parameter store"
  type        = string
  default     = "localhost"
}

variable "database_name" {
  description = "Database name for parameter store"
  type        = string
  default     = "unstablefusion"
}

# Secrets Manager Variables
variable "huggingface_token" {
  description = "Hugging Face API token for model access"
  type        = string
  sensitive   = true
  default     = ""
}

variable "google_client_secret" {
  description = "Google OAuth client secret for federated authentication"
  type        = string
  sensitive   = true
  default     = ""
}

# Network Configuration Variables
variable "vpc_id" {
  description = "VPC ID for networking resources"
  type        = string
  default     = ""
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs for internal resources"
  type        = list(string)
  default     = []
}

variable "public_subnet_ids" {
  description = "List of public subnet IDs for external resources"
  type        = list(string)
  default     = []
}

variable "app_security_group_id" {
  description = "Security group ID for application servers"
  type        = string
  default     = ""
}