# GENERATIVE AI DISCLAIMER
#
# A portion of this code was generated with the assistance of generative AI. Any files that do not contain a disclaimer were either written by a human without AI assistance or generated with developer tooling such as Vite.

from fastapi import APIRouter, Depends
from database import SessionLocal
from models import Job, JobStatus, User
from universal_auth import get_current_user_universal, UniversalUser
from pipeline_manager import get_pipeline_status

router = APIRouter(prefix="/queue", tags=["queue"])

@router.get("")
async def queue_status(current_user: UniversalUser = Depends(get_current_user_universal)):
    """Get current queue status and processing information"""
    db = SessionLocal()
    try:
        total_queued = db.query(Job).filter(Job.status == JobStatus.queued).count()
        total_processing = db.query(Job).filter(Job.status == JobStatus.processing).count()
        total_done = db.query(Job).filter(Job.status == JobStatus.done).count()
        
        next_jobs = db.query(Job).filter(Job.status == JobStatus.queued).order_by(
            Job.created_at.asc()
        ).limit(10).all()
        
        next_list = [{
            "id": job.id, 
            "uuid": job.uuid, 
            "prompt": job.prompt, 
            "created_at": job.created_at, 
            "model_name": job.model_name
        } for job in next_jobs]
        
        # Get pipeline status
        pipeline_info = get_pipeline_status()
        
        return {
            "concurrency_limit": pipeline_info["concurrency_limit"],
            "in_use": pipeline_info["in_use"],
            "queued": total_queued,
            "processing": total_processing,
            "done": total_done,
            "next_jobs": next_list,
            "models_loaded": pipeline_info["models_loaded"]
        }
    finally:
        db.close()