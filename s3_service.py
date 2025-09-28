# GENERATIVE AI DISCLAIMER
#
# A portion of this code was generated with the assistance of generative AI. Any files that do not contain a disclaimer were either written by a human without AI assistance or generated with developer tooling such as Vite.

import os
import boto3
import uuid
from typing import Optional
from botocore.exceptions import ClientError
from botocore.config import Config
import logging

logger = logging.getLogger(__name__)

class S3Service:
    """Service for handling S3 operations including pre-signed URLs"""
    
    def __init__(self, s3_config: dict = None):
        # Use provided config or get from config manager
        if s3_config is None:
            from config import config_manager
            s3_config = config_manager.get_s3_config()
        
        self.bucket_name = s3_config.get("bucket_name")
        self.region = s3_config.get("region")
        
        # Only initialize if S3 is configured
        if not self.bucket_name:
            logger.warning("S3 not configured - S3 operations will not be available")
            self.s3_client = None
            return
        
        # Configure boto3 client
        config = Config(
            region_name=self.region,
            retries={
                'max_attempts': 3,
                'mode': 'adaptive'
            }
        )
        
        # Use provided credentials if available
        aws_kwargs = {}
        if s3_config.get("access_key_id") and s3_config.get("secret_access_key"):
            aws_kwargs["aws_access_key_id"] = s3_config["access_key_id"]
            aws_kwargs["aws_secret_access_key"] = s3_config["secret_access_key"]
        
        self.s3_client = boto3.client('s3', config=config, **aws_kwargs)
        logger.info(f"S3 service initialized for bucket: {self.bucket_name}")
    
    def generate_unique_key(self, user_id: int, filename: str = None) -> str:
        """Generate a unique S3 key for an image"""
        unique_id = str(uuid.uuid4())
        if filename:
            # Extract extension from filename
            ext = os.path.splitext(filename)[1] or '.jpg'
        else:
            ext = '.jpg'
        
        return f"images/user_{user_id}/{unique_id}{ext}"
    
    def generate_presigned_upload_url(self, user_id: int, filename: str = None, 
                                    content_type: str = "image/jpeg", 
                                    expiration: int = 3600) -> dict:
        """
        Generate a pre-signed URL for uploading an image to S3
        
        Args:
            user_id: ID of the user uploading the image
            filename: Original filename (optional)
            content_type: MIME type of the file
            expiration: URL expiration time in seconds
            
        Returns:
            Dictionary containing upload URL and fields
        """
        if not self.s3_client:
            raise ValueError("S3 is not configured")
        
        key = self.generate_unique_key(user_id, filename)
        
        try:
            response = self.s3_client.generate_presigned_post(
                Bucket=self.bucket_name,
                Key=key,
                Fields={
                    'Content-Type': content_type,
                    'Cache-Control': 'max-age=31536000'  # 1 year
                },
                Conditions=[
                    {'Content-Type': content_type},
                    ['content-length-range', 100, 10485760]  # 100 bytes to 10MB
                ],
                ExpiresIn=expiration
            )
            
            response['key'] = key
            return response
            
        except ClientError as e:
            logger.error(f"Error generating presigned upload URL: {e}")
            raise
    
    def generate_presigned_download_url(self, key: str, expiration: int = 3600) -> str:
        """
        Generate a pre-signed URL for downloading an image from S3
        
        Args:
            key: S3 object key
            expiration: URL expiration time in seconds
            
        Returns:
            Pre-signed download URL
        """
        if not self.s3_client:
            raise ValueError("S3 is not configured")
        
        try:
            response = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': key},
                ExpiresIn=expiration
            )
            return response
            
        except ClientError as e:
            logger.error(f"Error generating presigned download URL: {e}")
            raise
    
    def upload_file(self, file_path: str, key: str, content_type: str = "image/jpeg") -> bool:
        """
        Upload a file directly to S3 (for server-side uploads)
        
        Args:
            file_path: Local file path
            key: S3 object key
            content_type: MIME type of the file
            
        Returns:
            True if successful, False otherwise
        """
        if not self.s3_client:
            logger.warning("S3 not configured - cannot upload file")
            return False
        
        try:
            self.s3_client.upload_file(
                file_path, 
                self.bucket_name, 
                key,
                ExtraArgs={
                    'ContentType': content_type,
                    'CacheControl': 'max-age=31536000'  # 1 year
                }
            )
            return True
            
        except ClientError as e:
            logger.error(f"Error uploading file to S3: {e}")
            return False
    
    def delete_object(self, key: str) -> bool:
        """
        Delete an object from S3
        
        Args:
            key: S3 object key
            
        Returns:
            True if successful, False otherwise
        """
        if not self.s3_client:
            logger.warning("S3 not configured - cannot delete object")
            return False
        
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
            return True
            
        except ClientError as e:
            logger.error(f"Error deleting object from S3: {e}")
            return False
    
    def object_exists(self, key: str) -> bool:
        """
        Check if an object exists in S3
        
        Args:
            key: S3 object key
            
        Returns:
            True if object exists, False otherwise
        """
        if not self.s3_client:
            return False
        
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            logger.error(f"Error checking object existence: {e}")
            return False
    
    def get_object_url(self, key: str) -> str:
        """
        Get the public URL for an S3 object (without pre-signing)
        This should only be used for public objects
        
        Args:
            key: S3 object key
            
        Returns:
            Public S3 URL
        """
        if not self.bucket_name or not self.region:
            raise ValueError("S3 is not configured")
        
        return f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{key}"

# Global S3 service instance - initialized lazily to avoid import errors
s3_service = None

def get_s3_service() -> S3Service:
    """Get or create the global S3 service instance"""
    global s3_service
    if s3_service is None:
        s3_service = S3Service()
    return s3_service