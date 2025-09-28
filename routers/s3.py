# GENERATIVE AI DISCLAIMER
#
# A portion of this code was generated with the assistance of generative AI. Any files that do not contain a disclaimer were either written by a human without AI assistance or generated with developer tooling such as Vite.

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from auth import get_user_from_token
from models import User, PresignedUploadResponse, PresignedDownloadResponse
from s3_service import get_s3_service
from config import USE_S3_STORAGE
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/s3", tags=["s3"])

@router.post("/upload-url", response_model=PresignedUploadResponse)
def get_upload_url(
    filename: Optional[str] = None,
    content_type: str = "image/jpeg",
    current_user: User = Depends(get_user_from_token)
):
    """
    Generate a pre-signed URL for uploading an image directly to S3
    
    This endpoint returns a pre-signed POST URL that allows the client
    to upload images directly to S3 without going through the server.
    """
    if not USE_S3_STORAGE:
        raise HTTPException(
            status_code=501, 
            detail="S3 storage is not configured"
        )
    
    try:
        # Generate pre-signed upload URL
        s3_service = get_s3_service()
        response = s3_service.generate_presigned_upload_url(
            user_id=current_user.id,
            filename=filename,
            content_type=content_type,
            expiration=3600  # 1 hour
        )
        
        return PresignedUploadResponse(
            upload_url=response['url'],
            fields=response['fields'],
            key=response['key']
        )
        
    except Exception as e:
        logger.error(f"Error generating upload URL: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to generate upload URL"
        )

@router.get("/download-url/{s3_key:path}", response_model=PresignedDownloadResponse)
def get_download_url(
    s3_key: str,
    current_user: User = Depends(get_user_from_token)
):
    """
    Generate a pre-signed URL for downloading an image from S3
    
    This endpoint returns a pre-signed GET URL that allows the client
    to download images directly from S3.
    """
    if not USE_S3_STORAGE:
        raise HTTPException(
            status_code=501, 
            detail="S3 storage is not configured"
        )
    
    # Verify the user owns this image or is admin
    # Extract user_id from S3 key pattern: images/user_{user_id}/...
    try:
        key_parts = s3_key.split('/')
        if len(key_parts) >= 2 and key_parts[0] == 'images' and key_parts[1].startswith('user_'):
            key_user_id = int(key_parts[1].replace('user_', ''))
            
            if key_user_id != current_user.id and not current_user.is_admin:
                raise HTTPException(
                    status_code=403,
                    detail="Not authorized to access this image"
                )
        else:
            # Invalid key format, deny access
            raise HTTPException(
                status_code=403,
                detail="Invalid image key format"
            )
            
    except (ValueError, IndexError):
        raise HTTPException(
            status_code=400,
            detail="Invalid S3 key format"
        )
    
    try:
        # Check if object exists
        s3_service = get_s3_service()
        if not s3_service.object_exists(s3_key):
            raise HTTPException(
                status_code=404,
                detail="Image not found"
            )
        
        # Generate pre-signed download URL
        download_url = s3_service.generate_presigned_download_url(
            key=s3_key,
            expiration=3600  # 1 hour
        )
        
        return PresignedDownloadResponse(
            download_url=download_url,
            expires_in=3600
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating download URL: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to generate download URL"
        )