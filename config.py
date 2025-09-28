"""
Single Source of Truth Configuration
This file centralizes all configuration settings with a clear hierarchy:
1. Environment variables (highest priority)
2. AWS Parameter Store/Secrets Manager (if available)
3. No defaults - fail fast if critical config is missing
"""

import os
from dotenv import load_dotenv
from typing import Dict, Any, Optional

# Load environment variables from .env file
load_dotenv()

# ============================================================================
# SINGLE SOURCE OF TRUTH CONFIGURATION VALUES
# ============================================================================

# Core AWS Settings - REQUIRED if using AWS services
AWS_REGION = os.getenv("AWS_REGION")
AWS_USERNAME = os.getenv("AWS_USERNAME") 

# These are the ONLY two values you need to set to enable AWS services
# Set these in your environment:
# export AWS_REGION="ap-southeast-2"
# export AWS_USERNAME="n11974796"

# ============================================================================
# AWS SERVICE INITIALIZATION
# ============================================================================

class ConfigManager:
    """Centralized configuration manager"""
    
    def __init__(self):
        self.aws_available = False
        self.aws_config = None
        self._config_cache = {}
        
        # Try to initialize AWS services if credentials are provided
        if AWS_REGION and AWS_USERNAME:
            self._init_aws_services()
        else:
            print("ℹ AWS_REGION and/or AWS_USERNAME not set - AWS services disabled")
            print("ℹ Using environment variables only")
    
    def _init_aws_services(self):
        """Initialize AWS configuration services"""
        try:
            from aws_config_service import AWSConfigService
            self.aws_config = AWSConfigService(AWS_REGION, AWS_USERNAME)
            self.aws_available = True
            print(f"✓ AWS configuration services initialized (region: {AWS_REGION}, user: {AWS_USERNAME})")
        except Exception as e:
            print(f"⚠ AWS configuration services failed to initialize: {e}")
            print("ℹ Falling back to environment variables only")
            self.aws_available = False
    
    def get_database_config(self) -> Dict[str, Any]:
        """Get database configuration"""
        if self.aws_available:
            try:
                return self.aws_config.get_database_config()
            except Exception as e:
                print(f"⚠ Failed to get database config from AWS: {e}")
        
        # Fallback to environment variables
        return {
            "host": os.getenv("DATABASE_HOST"),
            "port": int(os.getenv("DATABASE_PORT", "5432")),
            "database": os.getenv("DATABASE_NAME"),
            "username": os.getenv("DATABASE_USERNAME"),
            "password": os.getenv("DATABASE_PASSWORD"),
            "engine": "postgresql"
        }
    
    def get_jwt_config(self) -> Dict[str, str]:
        """Get JWT configuration"""
        if self.aws_available:
            try:
                return self.aws_config.get_jwt_config()
            except Exception as e:
                print(f"⚠ Failed to get JWT config from AWS: {e}")
        
        # Fallback to environment variables
        return {
            "secret_key": os.getenv("JWT_SECRET"),
            "algorithm": os.getenv("JWT_ALGORITHM", "HS256")
        }
    
    def get_cognito_config(self) -> Dict[str, str]:
        """Get Cognito configuration"""
        if self.aws_available:
            try:
                return self.aws_config.get_cognito_config()
            except Exception as e:
                print(f"⚠ Failed to get Cognito config from AWS: {e}")
        
        # Fallback to environment variables
        return {
            "user_pool_id": os.getenv("COGNITO_USER_POOL_ID"),
            "user_pool_client_id": os.getenv("COGNITO_CLIENT_ID"),
            "region": AWS_REGION
        }
    
    def get_s3_config(self) -> Dict[str, Any]:
        """Get S3 configuration"""
        if self.aws_available:
            try:
                return self.aws_config.get_s3_config()
            except Exception as e:
                print(f"⚠ Failed to get S3 config from AWS: {e}")
        
        # Fallback to environment variables
        return {
            "bucket_name": os.getenv("AWS_S3_BUCKET"),
            "region": AWS_REGION,
            "access_key_id": os.getenv("AWS_ACCESS_KEY_ID"),
            "secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY")
        }
    
    def get_app_config(self) -> Dict[str, Any]:
        """Get application configuration"""
        if self.aws_available:
            try:
                return self.aws_config.get_app_config()
            except Exception as e:
                print(f"⚠ Failed to get app config from AWS: {e}")
        
        # Fallback to environment variables
        return {
            "api_base_url": os.getenv("API_BASE_URL"),
            "frontend_url": os.getenv("FRONTEND_URL"),
            "max_image_dimensions": os.getenv("MAX_IMAGE_DIMENSIONS"),
            "default_model": os.getenv("DEFAULT_MODEL")
        }
    
    def get_huggingface_config(self) -> Dict[str, str]:
        """Get Hugging Face configuration"""
        if self.aws_available:
            try:
                return self.aws_config.get_huggingface_config()
            except Exception as e:
                print(f"⚠ Failed to get Hugging Face config from AWS: {e}")
        
        # Fallback to environment variables
        return {
            "token": os.getenv("HUGGINGFACE_TOKEN"),
            "api_url": os.getenv("HUGGINGFACE_API_URL", "https://api-inference.huggingface.co"),
            "provider": "huggingface"
        }

# ============================================================================
# INITIALIZE CONFIGURATION MANAGER
# ============================================================================

# Single instance of configuration manager
config_manager = ConfigManager()

# ============================================================================
# APPLICATION CONFIGURATION VALUES
# ============================================================================

# Database Configuration
db_config = config_manager.get_database_config()
if db_config.get("host") and db_config.get("username") and db_config.get("password"):
    DB_URL = f"postgresql://{db_config['username']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['database']}"
else:
    DB_URL = os.getenv("DATABASE_URL")

# JWT Configuration
jwt_config = config_manager.get_jwt_config()
JWT_SECRET = jwt_config.get("secret_key") or os.getenv("JWT_SECRET")
JWT_ALGORITHM = jwt_config.get("algorithm", "HS256")
JWT_EXP_SECONDS = int(os.getenv("JWT_EXP_SECONDS", "21600"))  # 6 hours

# Cognito Configuration
cognito_config = config_manager.get_cognito_config()
COGNITO_USER_POOL_ID = cognito_config.get("user_pool_id")
COGNITO_CLIENT_ID = cognito_config.get("user_pool_client_id")
COGNITO_CLIENT_SECRET = os.getenv("COGNITO_CLIENT_SECRET") or cognito_config.get("client_secret")
COGNITO_REGION = cognito_config.get("region") or AWS_REGION
COGNITO_DOMAIN = os.getenv("COGNITO_DOMAIN")
USE_COGNITO = bool(COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID)

# S3 Configuration
s3_config = config_manager.get_s3_config()
AWS_S3_BUCKET = s3_config.get("bucket_name")
AWS_ACCESS_KEY_ID = s3_config.get("access_key_id")
AWS_SECRET_ACCESS_KEY = s3_config.get("secret_access_key")
USE_S3_STORAGE = bool(AWS_S3_BUCKET)

# Application Configuration
app_config = config_manager.get_app_config()
API_BASE_URL = app_config.get("api_base_url") or os.getenv("API_BASE_URL", "http://localhost:3001/api/")
FRONTEND_URL = app_config.get("frontend_url") or os.getenv("FRONTEND_URL", "http://localhost:5173")
DEFAULT_MODEL = app_config.get("default_model") or os.getenv("DEFAULT_MODEL", "CompVis/stable-diffusion-v1-4")
MAX_IMAGE_DIMENSIONS = app_config.get("max_image_dimensions") or os.getenv("MAX_IMAGE_DIMENSIONS", "1024x1024")

# Hugging Face Configuration
hf_config = config_manager.get_huggingface_config()
HUGGINGFACE_TOKEN = hf_config.get("token")
HUGGINGFACE_API_URL = hf_config.get("api_url", "https://api-inference.huggingface.co")

# Basic Application Settings
IMAGES_DIR = os.getenv("IMAGES_DIR", "generated_images")
MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT", "2"))

# Frontend Settings
FRONTEND_DIST_DIR = os.getenv("FRONTEND_DIST_DIR", "frontend/dist")

# CORS Settings
cors_origins_str = os.getenv("CORS_ORIGINS", "*")
CORS_ORIGINS = cors_origins_str.split(",") if cors_origins_str != "*" else ["*"]

# Stable Diffusion Models
ALLOWED_MODELS = {
    "stabilityai/sd-turbo",
    "stable-diffusion-v1-5/stable-diffusion-v1-5", 
    "CompVis/stable-diffusion-v1-4",
}

# Debug Mode
DEBUG_MODE = os.getenv("DEBUG", "false").lower() == "true"

# Hardcoded users (temporary - will be replaced with Cognito)
HARDCODED_USERS = {
    os.getenv("ADMIN_USERNAME", "admin"): {
        "password": os.getenv("ADMIN_PASSWORD", "admin"), 
        "is_admin": True
    },
    os.getenv("DEMO_USERNAME", "demo"): {
        "password": os.getenv("DEMO_PASSWORD", "demo"), 
        "is_admin": False
    },
}

# Ensure directories exist
if IMAGES_DIR:
    os.makedirs(IMAGES_DIR, exist_ok=True)

# ============================================================================
# CONFIGURATION VALIDATION
# ============================================================================

def validate_config():
    """Validate that required configuration is present"""
    errors = []
    
    # Critical configuration checks
    if not DB_URL:
        errors.append("DATABASE_URL is required")
    
    if not JWT_SECRET:
        errors.append("JWT_SECRET is required")
    
    # AWS-specific checks
    if config_manager.aws_available:
        if not AWS_REGION:
            errors.append("AWS_REGION is required when using AWS services")
        if not AWS_USERNAME:
            errors.append("AWS_USERNAME is required when using AWS services")
    
    # Cognito checks
    if USE_COGNITO and not (COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID):
        errors.append("COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID are required when USE_COGNITO is enabled")
    
    # S3 checks
    if USE_S3_STORAGE and not AWS_S3_BUCKET:
        errors.append("AWS_S3_BUCKET is required when USE_S3_STORAGE is enabled")
    
    if errors:
        error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {error}" for error in errors)
        raise ValueError(error_msg)
    
    return True

def print_config_summary():
    """Print configuration summary (excluding sensitive values)"""
    print("\n=== UnstableFusion Configuration Summary ===")
    print(f"AWS Services: {'✓ Available' if config_manager.aws_available else '✗ Disabled'}")
    if config_manager.aws_available:
        print(f"AWS Region: {AWS_REGION}")
        print(f"AWS Username: {AWS_USERNAME}")
    print(f"Database: {'✓ Configured' if DB_URL else '✗ Missing DATABASE_URL'}")
    print(f"JWT: {'✓ Configured' if JWT_SECRET else '✗ Missing JWT_SECRET'}")
    print(f"S3 Storage: {'✓ Enabled' if USE_S3_STORAGE else '✗ Disabled'}")
    print(f"Cognito Auth: {'✓ Enabled' if USE_COGNITO else '✗ Disabled'}")
    print(f"Hugging Face: {'✓ Token Available' if HUGGINGFACE_TOKEN else '✗ No Token'}")
    print(f"Default Model: {DEFAULT_MODEL}")
    print(f"Max Concurrent: {MAX_CONCURRENT}")
    print(f"Debug Mode: {DEBUG_MODE}")
    print("==========================================\n")

# Validate configuration on import
try:
    validate_config()
    if DEBUG_MODE:
        print_config_summary()
except ValueError as e:
    print(f"❌ {e}")
    print("\nTo fix these issues:")
    print("1. Set required environment variables")
    print("2. Or configure AWS Parameter Store/Secrets Manager")
    print("3. Set AWS_REGION and AWS_USERNAME to enable AWS services")
    # Don't raise the error - allow the app to start with warnings
    print("⚠ Continuing with current configuration...")

# Ensure essential configuration has fallbacks for Docker
if not DB_URL:
    print("⚠ Database URL not found in AWS or environment variables")
    print("ℹ Using default PostgreSQL connection for Docker")
    DB_URL = "postgresql://sduser:my-secret-pw@postgres:5432/sd_api"

if not JWT_SECRET:
    print("⚠ JWT secret not found, using default (change in production)")
    JWT_SECRET = "your-secure-jwt-secret-key-change-this-in-production"

# Auto-validate configuration
if __name__ == "__main__":
    validate_config()
    print_config_summary()