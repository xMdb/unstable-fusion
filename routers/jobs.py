# GENERATIVE AI DISCLAIMER
#
# A portion of this code was generated with the assistance of generative AI. Any files that do not contain a disclaimer were either written by a human without AI assistance or generated with developer tooling such as Vite.

import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from database import SessionLocal
from models import Job, JobStatus, JobOut, EnqueueRequest, User
from universal_auth import get_current_user_universal, UniversalUser
from config import ALLOWED_MODELS, DEFAULT_MODEL

router = APIRouter(prefix="/jobs", tags=["jobs"])

@router.post("", response_model=JobOut)
async def create_job(req: EnqueueRequest, current_user: UniversalUser = Depends(get_current_user_universal)):
    """Create a new image generation job"""
    # Validate model_name
    model_name = req.model_name or DEFAULT_MODEL
    if model_name not in ALLOWED_MODELS:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported model '{model_name}'. Supported: {sorted(list(ALLOWED_MODELS))}"
        )

    db = SessionLocal()
    try:
        job = Job(
            user_id=current_user.id,
            prompt=req.prompt,
            width=req.width or 256,
            height=req.height or 256,
            steps=req.steps or 20,
            model_name=model_name,
            status=JobStatus.queued,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        
        return JobOut(
            id=job.id,
            uuid=job.uuid,
            prompt=job.prompt,
            model_name=job.model_name,
            status=job.status,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            output_path=job.output_path,
            error=job.error
        )
    finally:
        db.close()

@router.get("", response_model=List[JobOut])
async def list_jobs(
    status: Optional[JobStatus] = None, 
    skip: int = 0, 
    limit: int = 20, 
    current_user: UniversalUser = Depends(get_current_user_universal)
):
    """List user's jobs with optional filtering"""
    db = SessionLocal()
    try:
        query = db.query(Job).filter(Job.user_id == current_user.id)
        if status:
            query = query.filter(Job.status == status)
        jobs = query.order_by(Job.created_at.desc()).offset(skip).limit(limit).all()
        
        return [JobOut(
            id=job.id,
            uuid=job.uuid,
            prompt=job.prompt,
            model_name=job.model_name,
            status=job.status,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            output_path=job.output_path,
            error=job.error
        ) for job in jobs]
    finally:
        db.close()

@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: int, current_user: UniversalUser = Depends(get_current_user_universal)):
    """Get a specific job by ID"""
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id, Job.user_id == current_user.id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        return JobOut(
            id=job.id,
            uuid=job.uuid,
            prompt=job.prompt,
            model_name=job.model_name,
            status=job.status,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            output_path=job.output_path,
            error=job.error
        )
    finally:
        db.close()

@router.post("/{job_id}/cancel")
def cancel_job(job_id: int, current_user: UniversalUser = Depends(get_current_user_universal)):
    """Cancel a job"""
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id, Job.user_id == current_user.id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        if job.status == JobStatus.cancelled:
            raise HTTPException(status_code=400, detail="Job already cancelled")

        if job.status in [JobStatus.done, JobStatus.failed]:
            raise HTTPException(status_code=400, detail="Cannot cancel finished job")

        # If job is processing, we mark it cancelled; processing logic checks for cancelled before generation step.
        job.status = JobStatus.cancelled
        job.finished_at = datetime.datetime.utcnow()
        db.add(job)
        db.commit()
        return {"detail": "cancelled"}
    finally:
        db.close()