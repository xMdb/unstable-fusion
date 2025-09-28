# GENERATIVE AI DISCLAIMER
#
# A portion of this code was generated with the assistance of generative AI. Any files that do not contain a disclaimer were either written by a human without AI assistance or generated with developer tooling such as Vite.

import os
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
import sqlalchemy as sa
from database import SessionLocal
from models import ImageModel, ImageOut, Job, Like, User
from auth import get_user_from_token, verify_token_for_download
from s3_service import get_s3_service
from config import USE_S3_STORAGE
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/images", tags=["images"])

@router.get("", response_model=List[ImageOut])
def list_images(
    skip: int = 0, 
    limit: int = 20, 
    prompt_contains: Optional[str] = None, 
    current_user: User = Depends(get_user_from_token)
):
    """List user's images with optional search"""
    db = SessionLocal()
    try:
        # Join with Job for model_name and Like for liked_by_user
        query = db.query(ImageModel, Job.model_name, Like.id.label('liked')).outerjoin(
            Job, ImageModel.job_id == Job.id
        ).outerjoin(
            Like, sa.and_(Like.image_id == ImageModel.id, Like.user_id == current_user.id)
        ).filter(ImageModel.user_id == current_user.id)
        
        if prompt_contains:
            query = query.filter(ImageModel.prompt.like(f"%{prompt_contains}%"))
        
        results = query.order_by(ImageModel.created_at.desc()).offset(skip).limit(limit).all()
        
        # Generate pre-signed download URLs for S3 images
        image_outputs = []
        for image, model_name, liked in results:
            download_url = None
            if USE_S3_STORAGE and image.s3_key:
                try:
                    s3_service = get_s3_service()
                    download_url = s3_service.generate_presigned_download_url(image.s3_key, expiration=3600)
                except Exception as e:
                    logger.error(f"Error generating download URL for image {image.id}: {e}")
            
            image_outputs.append(ImageOut(
                id=image.id, 
                uuid=image.uuid, 
                prompt=image.prompt, 
                path=image.path,  # Legacy local path
                s3_key=image.s3_key,  # S3 key
                download_url=download_url,  # Pre-signed URL
                created_at=image.created_at, 
                likes_count=image.likes_count,
                model_name=model_name or "unknown",
                liked_by_user=liked is not None
            ))
        
        return image_outputs
    finally:
        db.close()

@router.get("/{image_id}", response_model=ImageOut)
def get_image(image_id: int, current_user: User = Depends(get_user_from_token)):
    """Get a specific image by ID"""
    db = SessionLocal()
    try:
        result = db.query(ImageModel, Job.model_name, Like.id.label('liked')).outerjoin(
            Job, ImageModel.job_id == Job.id
        ).outerjoin(
            Like, sa.and_(Like.image_id == ImageModel.id, Like.user_id == current_user.id)
        ).filter(ImageModel.id == image_id, ImageModel.user_id == current_user.id).first()
        
        if not result:
            raise HTTPException(status_code=404, detail="Image not found")
        
        image, model_name, liked = result
        return ImageOut(
            id=image.id, 
            uuid=image.uuid, 
            prompt=image.prompt, 
            path=image.path, 
            created_at=image.created_at, 
            likes_count=image.likes_count,
            model_name=model_name or "unknown",
            liked_by_user=liked is not None
        )
    finally:
        db.close()

@router.delete("/{image_id}")
def delete_image(image_id: int, current_user: User = Depends(get_user_from_token)):
    """Delete an image"""
    db = SessionLocal()
    try:
        image = db.query(ImageModel).filter(
            ImageModel.id == image_id, 
            ImageModel.user_id == current_user.id
        ).first()
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")
        
        # Delete file from S3 or local filesystem
        if USE_S3_STORAGE and image.s3_key:
            try:
                s3_service = get_s3_service()
                s3_service.delete_object(image.s3_key)
                logger.info(f"Deleted S3 object: {image.s3_key}")
            except Exception as e:
                logger.error(f"Error deleting S3 object {image.s3_key}: {e}")
                # Continue with database deletion even if S3 deletion fails
        elif image.path:
            try:
                if os.path.exists(image.path):
                    os.remove(image.path)
                    logger.info(f"Deleted local file: {image.path}")
            except Exception as e:
                logger.error(f"Error deleting local file {image.path}: {e}")
        
        # Delete likes associated with this image
        db.query(Like).filter(Like.image_id == image_id).delete()
        
        db.delete(image)
        db.commit()
        return {"detail": "deleted"}
    finally:
        db.close()

@router.get("/{image_id}/download")
def download_image(image_id: int, token: Optional[str] = None):
    """
    Download an image file (requires token as query parameter)
    
    For S3 storage, this returns a redirect to a pre-signed URL.
    For local storage, this serves the file directly.
    """
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    user = verify_token_for_download(token)
    
    db = SessionLocal()
    try:
        image = db.query(ImageModel).filter(ImageModel.id == image_id).first()
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")
        
        if image.user_id != user.id and not user.is_admin:
            raise HTTPException(status_code=403, detail="Not authorized")
        
        # Handle S3 storage
        if USE_S3_STORAGE and image.s3_key:
            try:
                # Check if object exists in S3
                s3_service = get_s3_service()
                if not s3_service.object_exists(image.s3_key):
                    raise HTTPException(status_code=404, detail="Image file not found in S3")
                
                # Generate pre-signed download URL
                download_url = s3_service.generate_presigned_download_url(image.s3_key, expiration=300)  # 5 minutes
                
                # Return redirect to pre-signed URL
                from fastapi.responses import RedirectResponse
                return RedirectResponse(url=download_url, status_code=302)
                
            except Exception as e:
                logger.error(f"Error accessing S3 image {image.s3_key}: {e}")
                raise HTTPException(status_code=500, detail="Error accessing image file")
        
        # Handle local storage (legacy)
        elif image.path:
            if not os.path.exists(image.path):
                raise HTTPException(status_code=404, detail="Image file not found")
            
            return FileResponse(
                image.path, 
                media_type="image/jpeg", 
                filename=os.path.basename(image.path)
            )
        
        else:
            raise HTTPException(status_code=404, detail="Image file not found")
            
    finally:
        db.close()

@router.post("/{image_id}/like")
def like_image(image_id: int, current_user: User = Depends(get_user_from_token)):
    """Like or unlike an image"""
    db = SessionLocal()
    try:
        image = db.query(ImageModel).filter(ImageModel.id == image_id).first()
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")

        existing = db.query(Like).filter(
            Like.user_id == current_user.id, 
            Like.image_id == image_id
        ).first()
        
        if existing:
            # Unlike
            db.delete(existing)
            image.likes_count = max(0, image.likes_count - 1)
            db.add(image)
            db.commit()
            return {"liked": False, "likes_count": image.likes_count}
        else:
            # Like
            like = Like(user_id=current_user.id, image_id=image_id)
            db.add(like)
            image.likes_count = image.likes_count + 1
            db.add(image)
            db.commit()
            return {"liked": True, "likes_count": image.likes_count}
    finally:
        db.close()