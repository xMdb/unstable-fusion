"""
AWS Parameter Store and Secrets Manager Service
Provides access to application configuration and secrets
"""

import boto3
import json
import logging
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError, NoCredentialsError
from functools import lru_cache

logger = logging.getLogger(__name__)

class AWSConfigService:
    """Service for accessing AWS Parameter Store and Secrets Manager"""
    
    def __init__(self, region_name: str, username: str):
        """
        Initialize AWS config service
        
        Args:
            region_name: AWS region
            username: Username for parameter paths
        """
        self.region_name = region_name
        self.username = username
        self.parameter_prefix = f"/unstablefusion/{username}"
        self.secret_prefix = f"unstablefusion/{username}"
        
        try:
            # Initialize AWS clients
            self.ssm_client = boto3.client('ssm', region_name=region_name)
            self.secrets_client = boto3.client('secretsmanager', region_name=region_name)
            logger.info(f"AWS config service initialized for region: {region_name}")
        except NoCredentialsError:
            logger.warning("AWS credentials not found. Service will return default values.")
            self.ssm_client = None
            self.secrets_client = None
    
    @lru_cache(maxsize=128)
    def get_parameter(self, parameter_name: str, decrypt: bool = False) -> Optional[str]:
        """
        Get parameter from AWS Parameter Store
        
        Args:
            parameter_name: Name of the parameter (without prefix)
            decrypt: Whether to decrypt secure strings
            
        Returns:
            Parameter value or None if not found
        """
        if not self.ssm_client:
            logger.warning(f"SSM client not available, returning None for parameter: {parameter_name}")
            return None
            
        full_name = f"{self.parameter_prefix}/{parameter_name}"
        
        try:
            response = self.ssm_client.get_parameter(
                Name=full_name,
                WithDecryption=decrypt
            )
            value = response['Parameter']['Value']
            logger.debug(f"Retrieved parameter: {parameter_name}")
            return value
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ParameterNotFound':
                logger.warning(f"Parameter not found: {full_name}")
            else:
                logger.error(f"Error retrieving parameter {full_name}: {e}")
            return None
    
    @lru_cache(maxsize=128)
    def get_secret(self, secret_name: str) -> Optional[Dict[str, Any]]:
        """
        Get secret from AWS Secrets Manager
        
        Args:
            secret_name: Name of the secret (without prefix)
            
        Returns:
            Secret value as dictionary or None if not found
        """
        if not self.secrets_client:
            logger.warning(f"Secrets client not available, returning None for secret: {secret_name}")
            return None
            
        full_name = f"{self.secret_prefix}/{secret_name}"
        
        try:
            response = self.secrets_client.get_secret_value(SecretId=full_name)
            secret_string = response['SecretString']
            secret_data = json.loads(secret_string)
            logger.debug(f"Retrieved secret: {secret_name}")
            return secret_data
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ResourceNotFoundException':
                logger.warning(f"Secret not found: {full_name}")
            else:
                logger.error(f"Error retrieving secret {full_name}: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing secret JSON {full_name}: {e}")
            return None
    
    def get_database_config(self) -> Dict[str, Any]:
        """
        Get database configuration from secrets and parameters
        
        Returns:
            Database configuration dictionary
        """
        # Try to get from secrets first (preferred for credentials)
        db_secret = self.get_secret("database-credentials")
        if db_secret:
            return {
                "host": db_secret.get("host"),
                "port": int(db_secret.get("port", 5432)),
                "database": db_secret.get("dbname"),
                "username": db_secret.get("username"),
                "password": db_secret.get("password"),
                "engine": db_secret.get("engine", "postgresql")
            }
        
        # Fallback to individual parameters
        return {
            "host": self.get_parameter("database_host") or "localhost",
            "port": int(self.get_parameter("database_port") or "5432"),
            "database": self.get_parameter("database_name") or "unstablefusion",
            "username": self.get_parameter("database_username"),
            "password": None,  # Should not store passwords in Parameter Store
            "engine": "postgresql"
        }
    
    def get_cognito_config(self) -> Dict[str, str]:
        """
        Get Cognito configuration from Parameter Store
        
        Returns:
            Cognito configuration dictionary
        """
        return {
            "user_pool_id": self.get_parameter("cognito_user_pool_id"),
            "user_pool_client_id": self.get_parameter("cognito_user_pool_client_id"),
            "region": self.get_parameter("aws_region") or self.region_name
        }
    
    def get_s3_config(self) -> Dict[str, Any]:
        """
        Get S3 configuration from Parameter Store and Secrets Manager
        
        Returns:
            S3 configuration dictionary
        """
        # Get bucket name from Parameter Store
        bucket_name = self.get_parameter("s3_bucket_name")
        
        # Get access keys from Secrets Manager
        s3_secret = self.get_secret("s3-access-keys")
        
        config = {
            "bucket_name": bucket_name,
            "region": self.get_parameter("aws_region") or self.region_name
        }
        
        if s3_secret:
            config.update({
                "access_key_id": s3_secret.get("access_key_id"),
                "secret_access_key": s3_secret.get("secret_access_key")
            })
        
        return config
    
    def get_jwt_config(self) -> Dict[str, str]:
        """
        Get JWT configuration from Secrets Manager
        
        Returns:
            JWT configuration dictionary
        """
        jwt_secret = self.get_secret("jwt-secret")
        if jwt_secret:
            return {
                "secret_key": jwt_secret.get("secret") or jwt_secret.get("secret_key"),
                "algorithm": jwt_secret.get("algorithm", "HS256")
            }
        
        # Fallback to environment variable or default
        import os
        return {
            "secret_key": os.getenv("JWT_SECRET", "fallback-secret-key"),
            "algorithm": "HS256"
        }
    
    def get_huggingface_config(self) -> Dict[str, str]:
        """
        Get Hugging Face API configuration from Secrets Manager
        
        Returns:
            Hugging Face configuration dictionary
        """
        hf_secret = self.get_secret("huggingface-token")
        if hf_secret:
            return {
                "token": hf_secret.get("token"),
                "api_url": hf_secret.get("api_url", "https://api-inference.huggingface.co"),
                "provider": hf_secret.get("provider", "huggingface")
            }
        
        # Fallback to environment variable
        import os
        return {
            "token": os.getenv("HUGGINGFACE_TOKEN"),
            "api_url": "https://api-inference.huggingface.co",
            "provider": "huggingface"
        }
    
    def get_app_config(self) -> Dict[str, Any]:
        """
        Get application configuration from Parameter Store and Secrets Manager
        
        Returns:
            Application configuration dictionary
        """
        # Get app config from secrets
        app_secret = self.get_secret("app-config")
        
        base_config = {
            "api_base_url": self.get_parameter("api_base_url") or "http://localhost:8000/api/",
            "frontend_url": self.get_parameter("frontend_url") or "http://localhost:5173",
            "max_image_dimensions": self.get_parameter("max_image_dimensions") or "1024x1024",
            "default_model": self.get_parameter("default_model") or "stabilityai/sd-turbo"
        }
        
        if app_secret:
            base_config.update(app_secret)
        
        return base_config
    
    def get_all_parameters(self) -> Dict[str, str]:
        """
        Get all parameters with the configured prefix
        
        Returns:
            Dictionary of all parameters
        """
        if not self.ssm_client:
            return {}
            
        try:
            response = self.ssm_client.get_parameters_by_path(
                Path=self.parameter_prefix,
                Recursive=True,
                WithDecryption=True
            )
            
            parameters = {}
            for param in response['Parameters']:
                # Remove prefix from name for cleaner keys
                key = param['Name'].replace(f"{self.parameter_prefix}/", "")
                parameters[key] = param['Value']
            
            return parameters
            
        except ClientError as e:
            logger.error(f"Error retrieving parameters by path {self.parameter_prefix}: {e}")
            return {}


# Global instance for easy access (initialized when needed)
config_service = None


def get_config_service(region: str, username: str) -> AWSConfigService:
    """
    Get or create a config service instance
    
    Args:
        region: AWS region
        username: Username for parameter paths
        
    Returns:
        AWSConfigService instance
    """
    return AWSConfigService(region, username)


# Convenience functions for common configurations
def get_database_config() -> Dict[str, Any]:
    """Get database configuration"""
    if config_service is None:
        return {}
    return config_service.get_database_config()


def get_cognito_config() -> Dict[str, str]:
    """Get Cognito configuration"""
    if config_service is None:
        return {}
    return config_service.get_cognito_config()


def get_s3_config() -> Dict[str, Any]:
    """Get S3 configuration"""
    if config_service is None:
        return {}
    return config_service.get_s3_config()


def get_app_config() -> Dict[str, Any]:
    """Get application configuration"""
    if config_service is None:
        return {}
    return config_service.get_app_config()