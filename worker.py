# GENERATIVE AI DISCLAIMER
#
# A portion of this code was generated with the assistance of generative AI. Any files that do not contain a disclaimer were either written by a human without AI assistance or generated with developer tooling such as Vite.

import os
import time
import threading
import datetime
import tempfile
from concurrent.futures import ThreadPoolExecutor
from database import SessionLocal
from models import Job, JobStatus, ImageModel
from pipeline_manager import (
    generate_with_pipeline, 
    acquire_processing_slot, 
    release_processing_slot,
    increment_in_use,
    decrement_in_use
)
from config import ALLOWED_MODELS, DEFAULT_MODEL, IMAGES_DIR, MAX_CONCURRENT, USE_S3_STORAGE
from s3_service import get_s3_service
import logging

logger = logging.getLogger(__name__)

# Worker control
stop_worker = threading.Event()
executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT)

def process_job(job_id: int, model_name: str):
    """Process a single job in the background"""
    # increment in-use counter
    increment_in_use()
    
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            # Job disappeared, nothing to do
            return
        
        # If cancelled meanwhile, mark and exit
        if job.status == JobStatus.cancelled:
            job.finished_at = datetime.datetime.utcnow()
            db.add(job)
            db.commit()
            return

        out_filename = f"{job.uuid}.jpg"
        
        try:
            # Ensure the model is valid
            if model_name not in ALLOWED_MODELS:
                raise RuntimeError(f"Model '{model_name}' is not allowed. Allowed: {sorted(list(ALLOWED_MODELS))}")

            # Handle S3 storage vs local storage
            if USE_S3_STORAGE:
                # Use temporary file for generation, then upload to S3
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
                    temp_path = temp_file.name
                
                try:
                    # Run generation to temporary file
                    generate_with_pipeline(job.prompt, job.width, job.height, job.steps, model_name, temp_path)
                    
                    # Generate S3 key and upload
                    s3_service = get_s3_service()
                    s3_key = s3_service.generate_unique_key(job.user_id, out_filename)
                    
                    success = s3_service.upload_file(temp_path, s3_key, content_type="image/jpeg")
                    if not success:
                        raise RuntimeError("Failed to upload image to S3")
                    
                    # Save image record with S3 key
                    img = ImageModel(
                        user_id=job.user_id, 
                        job_id=job.id, 
                        s3_key=s3_key,
                        prompt=job.prompt
                    )
                    db.add(img)
                    
                    job.output_path = s3_key  # Store S3 key as output path
                    
                    logger.info(f"Successfully uploaded image to S3: {s3_key}")
                    
                finally:
                    # Clean up temporary file
                    try:
                        os.unlink(temp_path)
                    except OSError:
                        pass
            else:
                # Local storage (legacy)
                out_path = os.path.join(IMAGES_DIR, out_filename)
                
                # Run generation to local file
                generate_with_pipeline(job.prompt, job.width, job.height, job.steps, model_name, out_path)
                
                # Save image record with local path
                img = ImageModel(
                    user_id=job.user_id, 
                    job_id=job.id, 
                    path=out_path, 
                    prompt=job.prompt
                )
                db.add(img)
                
                job.output_path = out_path

            job.status = JobStatus.done
            job.error = None
            
        except Exception as e:
            # Capture error on job
            job.status = JobStatus.failed
            job.error = str(e)
        finally:
            job.finished_at = datetime.datetime.utcnow()
            db.add(job)
            db.commit()
            
    finally:
        db.close()
        # Decrement in-use counter and release processing slot
        decrement_in_use()
        release_processing_slot()

def worker_loop():
    """Main worker loop: poll DB for queued jobs and process them"""
    print("Worker thread started; monitoring the job queue...")
    
    while not stop_worker.is_set():
        try:
            db = SessionLocal()
            # Fetch the oldest queued job
            job = db.query(Job).filter(Job.status == JobStatus.queued).order_by(Job.created_at.asc()).first()
            db.close()
            
            if not job:
                # Nothing to do right now
                time.sleep(0.8)
                continue

            # Attempt to acquire the global semaphore (limit concurrency)
            acquired = acquire_processing_slot()
            if not acquired:
                # No slot currently available
                time.sleep(0.2)
                continue

            # At this point we have reserved a slot - mark job processing and submit to threadpool
            db = SessionLocal()
            try:
                # Re-query to get fresh row and ensure it wasn't updated by someone else
                fresh_job = db.query(Job).filter(Job.id == job.id).with_for_update(read=True).first()
                if not fresh_job:
                    # Race condition: job disappeared - release semaphore and continue
                    release_processing_slot()
                    continue
                
                # If job was cancelled in the window, respect it
                if fresh_job.status == JobStatus.cancelled:
                    release_processing_slot()
                    continue
                
                # Mark as processing
                fresh_job.status = JobStatus.processing
                fresh_job.started_at = datetime.datetime.utcnow()
                db.add(fresh_job)
                db.commit()
                
                job_id = fresh_job.id
                model_name = fresh_job.model_name or DEFAULT_MODEL
                
            finally:
                db.close()

            # Launch processing in executor
            executor.submit(process_job, job_id, model_name)

        except Exception as e:
            # Keep looping (do not crash worker)
            print("Worker loop error:", e)
            time.sleep(1.0)

def start_worker():
    """Start the background worker thread"""
    worker_thread = threading.Thread(target=worker_loop, daemon=True)
    worker_thread.start()
    print("Background worker started.")

def stop_worker_gracefully():
    """Signal worker to stop and shutdown the executor"""
    stop_worker.set()
    executor.shutdown(wait=True)
    print("Background worker stopped.")

def reset_processing_jobs():
    """Reset any jobs that were processing back to queued (for startup recovery)"""
    db = SessionLocal()
    try:
        recovering = db.query(Job).filter(Job.status == JobStatus.processing).all()
        for job in recovering:
            job.status = JobStatus.queued
            job.started_at = None
            db.add(job)
        db.commit()
        if recovering:
            print(f"Reset {len(recovering)} processing jobs back to queued")
    finally:
        db.close()