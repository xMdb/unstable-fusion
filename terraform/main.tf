terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.1"
    }
  }
}

provider "aws" {
    region = var.aws_region
    # profile = "CAB432-STUDENT-901444280953"
}

# Generate random suffix for S3 bucket
resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# Data sources for existing AWS resources
data "aws_vpc" "existing" {
  id = var.existing_vpc_id
}

data "aws_subnet" "public" {
  id = var.existing_public_subnet_id
}

data "aws_subnet" "private" {
  id = var.existing_private_subnet_id
}

data "aws_security_group" "app" {
  id = var.existing_app_security_group_id
}

# S3 Bucket for images
resource "aws_s3_bucket" "images" {
  bucket = "${var.student_id}-${var.project_name}-images-${random_id.bucket_suffix.hex}"

  tags = {
    Name         = "${var.student_id}-${var.project_name}-images"
    qut-username = var.student_email
    purpose      = var.purpose
  }
}

resource "aws_s3_bucket_versioning" "images" {
  bucket = aws_s3_bucket.images.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "images" {
  bucket = aws_s3_bucket.images.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "images" {
  bucket = aws_s3_bucket.images.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_cors_configuration" "images" {
  bucket = aws_s3_bucket.images.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "PUT", "POST", "DELETE", "HEAD"]
    allowed_origins = ["*"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}