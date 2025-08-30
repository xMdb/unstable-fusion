# ---------------------------
# Imports
# ---------------------------

# Common
import os
import io
import time
import uuid
import threading
import datetime
from typing import Optional, List, Dict
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor

# FastAPI/backend
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Enum, Boolean
import enum
import jwt
from passlib.context import CryptContext

# Diffusers/Torch
import torch
from diffusers import StableDiffusionPipeline
from PIL import Image

# ---------------------------
# Configuration
# ---------------------------
DB_URL = os.environ.get("DATABASE_URL", "mysql+pymysql://root:password@localhost:3306/sd_api")
IMAGES_DIR = os.environ.get("IMAGES_DIR", "./generated_images")
JWT_SECRET = os.environ.get("JWT_SECRET", "changemeplease")
JWT_ALGORITHM = "HS256"
JWT_EXP_SECONDS = 60 * 60 * 6  # 6 hours
MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT", "2"))  # maximum concurrent generation jobs

# Models accepted
ALLOWED_MODELS = {
    "stabilityai/sd-turbo",
    "stable-diffusion-v1-5/stable-diffusion-v1-5",
    "CompVis/stable-diffusion-v1-4",
}
DEFAULT_MODEL = "CompVis/stable-diffusion-v1-4"

os.makedirs(IMAGES_DIR, exist_ok=True)

# ensure torch uses all available threads - doesnt actually work lol
torch.set_num_threads(torch.get_num_threads())

# ---------------------------
# Database ops
# ---------------------------
engine = sa.create_engine(DB_URL, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class JobStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False)

class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    prompt = Column(Text, nullable=False)
    height = Column(Integer, nullable=False, default=256)
    width = Column(Integer, nullable=False, default=256)
    model_name = Column(String(255), nullable=False, default=DEFAULT_MODEL)
    status = Column(Enum(JobStatus), default=JobStatus.queued)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    output_path = Column(String(1024), nullable=True)
    error = Column(Text, nullable=True)

class ImageModel(Base):
    __tablename__ = "images"
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=True)
    path = Column(String(1024), nullable=False)
    prompt = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    likes_count = Column(Integer, default=0)

class Like(Base):
    __tablename__ = "likes"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    image_id = Column(Integer, ForeignKey("images.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    __table_args__ = (sa.UniqueConstraint("user_id", "image_id", name="uix_user_image"),)

# create tables if missing
Base.metadata.create_all(bind=engine)

# ---------------------------
# Auth stuff with hardcoded users
# ---------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
HARDCODED_USERS = {
    "admin": {"password": "admin", "is_admin": True},
    "demo": {"password": "demo", "is_admin": False},
}

def create_or_sync_hardcoded_users():
    db = SessionLocal()
    try:
        for username, data in HARDCODED_USERS.items():
            u = db.query(User).filter(User.username == username).first()
            if not u:
                u = User(username=username, hashed_password=pwd_context.hash(data["password"]), is_admin=data["is_admin"])
                db.add(u)
            else:
                # rehash
                u.hashed_password = pwd_context.hash(data["password"])
                u.is_admin = data["is_admin"]
        db.commit()
    finally:
        db.close()

create_or_sync_hardcoded_users()

def authenticate_user(db, username: str, password: str):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return None
    if not pwd_context.verify(password, user.hashed_password):
        return None
    return user

def create_jwt(user: User):
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(seconds=JWT_EXP_SECONDS)
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

def get_user_from_token(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        uid = int(payload.get("sub"))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == uid).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    finally:
        db.close()

# ---------------------------
# Pydantic schemas
# ---------------------------
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class EnqueueRequest(BaseModel):
    prompt: str
    width: Optional[int] = 256
    height: Optional[int] = 256
    model_name: Optional[str] = DEFAULT_MODEL

class JobOut(BaseModel):
    id: int
    uuid: str
    prompt: str
    model_name: str
    status: JobStatus
    created_at: datetime.datetime
    started_at: Optional[datetime.datetime]
    finished_at: Optional[datetime.datetime]
    output_path: Optional[str]
    error: Optional[str]

class ImageOut(BaseModel):
    id: int
    uuid: str
    prompt: str
    path: str
    created_at: datetime.datetime
    likes_count: int
    model_name: Optional[str] = None
    liked_by_user: Optional[bool] = False

# ---------------------------
# Pipeline pool and worker
# ---------------------------
# 1 pipeline pool per model (size = MAX_CONCURRENT, one per CPU core available)
# Each job checks out one pipeline instance
pipelines_pools: Dict[str, Queue] = {}       # model_name -> Queue[StableDiffusionPipeline]
pipelines_lock = threading.Lock()
pipeline_init_lock = threading.Lock()        # protect concurrent pool init stuff

# thread-safe counter for in-use pipelines blah blah blah
in_use_counter = 0
in_use_counter_lock = threading.Lock()

# concurrency!!!!! semaphore threading
from threading import Semaphore
semaphore = Semaphore(MAX_CONCURRENT)

# ThreadPoolExecutor to run generation tasks (workers)
executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT)

# Worker control
stop_worker = threading.Event()

def create_pipeline_instance(model_name: str):
    """
    Create a new StableDiffusionPipeline instance for the given model_name.
    If loading fails, raises Exception to be caught by caller.
    """
    # model_name may need authentication or different hf repo; we try to load exactly what the user provided.
    # If this fails in your environment, change the string to the correct HF repo or add HF token.
    pipe = StableDiffusionPipeline.from_pretrained(model_name, torch_dtype=torch.float32, safety_checker=None)
    # CPU by default (update to .to("cuda") if you have GPU and compatible torch)
    pipe = pipe.to("cpu")
    pipe.enable_attention_slicing()
    return pipe

def ensure_pool_for_model(model_name: str):
    """
    Ensure there's a Queue pool for model_name with MAX_CONCURRENT pipeline instances.
    This is lazy-loaded; pool init can be heavy (loads model MAX_CONCURRENT times).
    """
    with pipeline_init_lock:
        if model_name in pipelines_pools:
            return pipelines_pools[model_name]
        q = Queue(maxsize=MAX_CONCURRENT)
        # Create up to MAX_CONCURRENT instances and push into queue
        # If any instance fails to load then raise exception
        created = []
        try:
            for i in range(MAX_CONCURRENT):
                inst = create_pipeline_instance(model_name)
                created.append(inst)
                q.put(inst)
        except Exception as e:
            # cleanup created pipelines if possible
            raise RuntimeError(f"Failed to load model '{model_name}': {e}")
        pipelines_pools[model_name] = q
        return q

def checkout_pipeline(model_name: str, timeout: float = 30.0):
    """
    Acquire a pipeline instance from the model pool (blocking up to timeout).
    Returns pipeline instance; caller MUST return it with return_pipeline().
    """
    q = ensure_pool_for_model(model_name)
    try:
        pipe = q.get(timeout=timeout)
        return pipe
    except Empty:
        raise RuntimeError("No pipeline instance available within timeout")

def return_pipeline(model_name: str, pipe):
    """
    Return a pipeline instance back into its pool.
    """
    q = pipelines_pools.get(model_name)
    if q is None:
        # drop silently
        return
    q.put(pipe)

# Generation function that uses pipeline checkout
def generate_with_pipeline(job_prompt: str, width: int, height: int, model_name: str, out_path: str):
    """
    Checkout pipeline instance from pool, run generation, save to out_path, and return.
    Errors propagate to caller.
    """
    pipe = None
    try:
        pipe = checkout_pipeline(model_name, timeout=30.0)
        result = pipe(job_prompt, height=height, width=width)
        img = result.images[0]
        img.save(out_path)
        return out_path
    finally:
        if pipe is not None:
            # return pipeline to pool even if generation failed
            return_pipeline(model_name, pipe)

# ---------------------------
# Worker loop: poll DB for queued jobs and process them
# ---------------------------
def worker_loop():
    print("Worker thread started; monitoring the job queue...")
    global in_use_counter
    while not stop_worker.is_set():
        try:
            db = SessionLocal()
            # fetch the oldest queued job
            job = db.query(Job).filter(Job.status == JobStatus.queued).order_by(Job.created_at.asc()).first()
            db.close()
            if not job:
                # nothing to do right now
                time.sleep(0.8)
                continue

            # attempt to acquire the global semaphore (limit concurrency)
            acquired = semaphore.acquire(timeout=1.0)
            if not acquired:
                # no slot currently available
                time.sleep(0.2)
                continue

            # At this point we have reserved a slot mark job processing and submit to threadpool
            db = SessionLocal()
            try:
                # re-query to get fresh row and ensure it wasn't updated by someone else
                j = db.query(Job).filter(Job.id == job.id).with_for_update(read=True).first()
                if not j:
                    # rarer race: job disappeared release semaphore and continue
                    semaphore.release()
                    continue
                # If job was cancelled in the window, respect it
                if j.status == JobStatus.cancelled:
                    semaphore.release()
                    continue
                # mark processing
                j.status = JobStatus.processing
                j.started_at = datetime.datetime.utcnow()
                db.add(j)
                db.commit()
                job_id = j.id
                model_name = j.model_name or DEFAULT_MODEL
            finally:
                db.close()

            # Launch processing in executor
            def process_job(job_id_inner: int, model_name_inner: str):
                global in_use_counter
                # increment in-use
                with in_use_counter_lock:
                    in_use_counter += 1
                db2 = SessionLocal()
                try:
                    j2 = db2.query(Job).filter(Job.id == job_id_inner).first()
                    if not j2:
                        # nothing to do, mark as failed and exit
                        # release slot in finally
                        return
                    # if cancelled meanwhile, mark and exit
                    if j2.status == JobStatus.cancelled:
                        j2.finished_at = datetime.datetime.utcnow()
                        db2.add(j2)
                        db2.commit()
                        return

                    out_filename = f"{j2.uuid}.jpg"
                    out_path = os.path.join(IMAGES_DIR, out_filename)
                    try:
                        # Ensure the model is valid
                        if model_name_inner not in ALLOWED_MODELS:
                            raise RuntimeError(f"Model '{model_name_inner}' is not allowed. Allowed: {sorted(list(ALLOWED_MODELS))}")

                        # Run generation check out a pipeline instance from the pool
                        generate_with_pipeline(j2.prompt, j2.width, j2.height, model_name_inner, out_path)

                        # Save image record
                        img = ImageModel(user_id=j2.user_id, job_id=j2.id, path=out_path, prompt=j2.prompt)
                        db2.add(img)

                        j2.status = JobStatus.done
                        j2.output_path = out_path
                        j2.error = None
                    except Exception as e:
                        # capture error on job
                        j2.status = JobStatus.failed
                        j2.error = str(e)
                    finally:
                        j2.finished_at = datetime.datetime.utcnow()
                        db2.add(j2)
                        db2.commit()
                finally:
                    db2.close()
                    # decrement in-use and release slot
                    with in_use_counter_lock:
                        in_use_counter = max(0, in_use_counter - 1)
                    semaphore.release()

            executor.submit(process_job, job_id, model_name)

        except Exception as e:
            # keep looping (do not crash worker)
            print("Worker loop error:", e)
            time.sleep(1.0)

# ---------------------------
# FastAPI main app (holy bananas that is a lot of threading stuff)
# ---------------------------
app = FastAPI(title="SD REST API (robust worker & model pools)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    # reset any jobs that were processing back to queued
    db = SessionLocal()
    try:
        recovering = db.query(Job).filter(Job.status == JobStatus.processing).all()
        for r in recovering:
            r.status = JobStatus.queued
            r.started_at = None
            db.add(r)
        db.commit()
    finally:
        db.close()

    # start worker thread
    worker_thread = threading.Thread(target=worker_loop, daemon=True)
    worker_thread.start()
    print("Startup completed. Worker running.")

@app.on_event("shutdown")
def shutdown_event():
    # Signal worker to stop and shutdown the executor
    stop_worker.set()
    executor.shutdown(wait=True)
    print("Shutdown complete.")

# ---------------------------
# Serve React web client (le static build, should have been built with docker lol)
# ---------------------------
app.mount("/static", StaticFiles(directory="frontend/dist", html=True), name="static")

@app.get("/")
def serve_index():
    index_path = os.path.join("frontend", "dist", "index.html")
    return FileResponse(index_path)
    
# ---------------------------
# Auth endpoint
# ---------------------------
@app.post("/auth/token", response_model=TokenResponse)
def token(form_data: OAuth2PasswordRequestForm = Depends()):
    db = SessionLocal()
    try:
        user = authenticate_user(db, form_data.username, form_data.password)
        if not user:
            raise HTTPException(status_code=400, detail="Incorrect username or password")
        token = create_jwt(user)
        return {"access_token": token, "token_type": "bearer"}
    finally:
        db.close()

# ---------------------------
# Jobs endpoints
# ---------------------------
@app.post("/jobs", response_model=JobOut)
def create_job(req: EnqueueRequest, current_user: User = Depends(get_user_from_token)):
    # validate model_name
    model_name = req.model_name or DEFAULT_MODEL
    if model_name not in ALLOWED_MODELS:
        raise HTTPException(status_code=400, detail=f"Unsupported model '{model_name}'. Supported: {sorted(list(ALLOWED_MODELS))}")

    db = SessionLocal()
    try:
        job = Job(
            user_id=current_user.id,
            prompt=req.prompt,
            width=req.width or 256,
            height=req.height or 256,
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

@app.get("/jobs", response_model=List[JobOut])
def list_jobs(status: Optional[JobStatus] = None, skip: int = 0, limit: int = 20, current_user: User = Depends(get_user_from_token)):
    db = SessionLocal()
    try:
        q = db.query(Job).filter(Job.user_id == current_user.id)
        if status:
            q = q.filter(Job.status == status)
        q = q.order_by(Job.created_at.desc()).offset(skip).limit(limit)
        jobs = q.all()
        return [JobOut(
            id=j.id,
            uuid=j.uuid,
            prompt=j.prompt,
            model_name=j.model_name,
            status=j.status,
            created_at=j.created_at,
            started_at=j.started_at,
            finished_at=j.finished_at,
            output_path=j.output_path,
            error=j.error
        ) for j in jobs]
    finally:
        db.close()

@app.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, current_user: User = Depends(get_user_from_token)):
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

@app.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int, current_user: User = Depends(get_user_from_token)):
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id, Job.user_id == current_user.id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        if job.status == JobStatus.cancelled:
            raise HTTPException(status_code=400, detail="Job already cancelled")

        if job.status in [JobStatus.done, JobStatus.failed]:
            raise HTTPException(status_code=400, detail="Cannot cancel finished job")

        job.status = JobStatus.cancelled
        job.finished_at = datetime.datetime.utcnow()
        db.add(job)
        db.commit()
        return {"detail": "cancelled"}
    finally:
        db.close()

# ---------------------------
# Queue status endpoint
# ---------------------------
@app.get("/queue")
def queue_status(current_user: User = Depends(get_user_from_token)):
    db = SessionLocal()
    try:
        total_queued = db.query(Job).filter(Job.status == JobStatus.queued).count()
        total_processing = db.query(Job).filter(Job.status == JobStatus.processing).count()
        total_done = db.query(Job).filter(Job.status == JobStatus.done).count()
        next_jobs = db.query(Job).filter(Job.status == JobStatus.queued).order_by(Job.created_at.asc()).limit(10).all()
        next_list = [{"id": j.id, "uuid": j.uuid, "prompt": j.prompt, "created_at": j.created_at, "model_name": j.model_name} for j in next_jobs]
        with in_use_counter_lock:
            in_use = in_use_counter
        return {
            "concurrency_limit": MAX_CONCURRENT,
            "in_use": in_use,
            "queued": total_queued,
            "processing": total_processing,
            "done": total_done,
            "next_jobs": next_list
        }
    finally:
        db.close()

# ---------------------------
# Images endpoints
# ---------------------------
@app.get("/images", response_model=List[ImageOut])
def list_images(skip: int = 0, limit: int = 20, prompt_contains: Optional[str] = None, current_user: User = Depends(get_user_from_token)):
    db = SessionLocal()
    try:
        q = db.query(ImageModel).filter(ImageModel.user_id == current_user.id)
        if prompt_contains:
            q = q.filter(ImageModel.prompt.like(f"%{prompt_contains}%"))
        q = q.order_by(ImageModel.created_at.desc()).offset(skip).limit(limit)
        images = q.all()
        return [ImageOut(id=i.id, uuid=i.uuid, prompt=i.prompt, path=i.path, created_at=i.created_at, likes_count=i.likes_count) for i in images]
    finally:
        db.close()

@app.get("/images/{image_id}", response_model=ImageOut)
def get_image(image_id: int, current_user: User = Depends(get_user_from_token)):
    db = SessionLocal()
    try:
        image = db.query(ImageModel).filter(ImageModel.id == image_id, ImageModel.user_id == current_user.id).first()
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")
        return ImageOut(id=image.id, uuid=image.uuid, prompt=image.prompt, path=image.path, created_at=image.created_at, likes_count=image.likes_count)
    finally:
        db.close()

@app.delete("/images/{image_id}")
def delete_image(image_id: int, current_user: User = Depends(get_user_from_token)):
    db = SessionLocal()
    try:
        image = db.query(ImageModel).filter(ImageModel.id == image_id, ImageModel.user_id == current_user.id).first()
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")
        # delete file
        try:
            if os.path.exists(image.path):
                os.remove(image.path)
        except Exception as e:
            print("Error deleting file:", e)
        db.delete(image)
        db.commit()
        return {"detail": "deleted"}
    finally:
        db.close()

@app.get("/images/{image_id}/download")
def download_image(image_id: int, token: Optional[str] = None):
    # download thingy doesnt work so just yolo and use token param (secure? no. good practice? no. hotel? travago.)
    # change in the future!!!!
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        uid = int(payload.get("sub"))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == uid).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
            
        image = db.query(ImageModel).filter(ImageModel.id == image_id).first()
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")
        if image.user_id != user.id and not user.is_admin:
            raise HTTPException(status_code=403, detail="Not authorized")
        if not os.path.exists(image.path):
            raise HTTPException(status_code=404, detail="Image file not found")
        return FileResponse(image.path, media_type="image/jpeg", filename=os.path.basename(image.path))
    finally:
        db.close()

@app.post("/images/{image_id}/like")
def like_image(image_id: int, current_user: User = Depends(get_user_from_token)):
    db = SessionLocal()
    try:
        image = db.query(ImageModel).filter(ImageModel.id == image_id).first()
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")

        existing = db.query(Like).filter(Like.user_id == current_user.id, Like.image_id == image_id).first()
        if existing:
            # unlike
            db.delete(existing)
            image.likes_count = max(0, image.likes_count - 1)
            db.add(image)
            db.commit()
            return {"liked": False, "likes_count": image.likes_count}
        else:
            lk = Like(user_id=current_user.id, image_id=image_id)
            db.add(lk)
            image.likes_count = image.likes_count + 1
            db.add(image)
            db.commit()
            return {"liked": True, "likes_count": image.likes_count}
    finally:
        db.close()