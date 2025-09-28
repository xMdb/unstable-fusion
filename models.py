# GENERATIVE AI DISCLAIMER
#
# A portion of this code was generated with the assistance of generative AI. Any files that do not contain a disclaimer were either written by a human without AI assistance or generated with developer tooling such as Vite.

import enum
import uuid
import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Enum, Boolean
import sqlalchemy as sa
from pydantic import BaseModel
from database import Base
from config import DEFAULT_MODEL

# Enums
class JobStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"

# Database Models
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
    steps = Column(Integer, nullable=False, default=20)
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
    path = Column(String(1024), nullable=True)  # Local path (legacy)
    s3_key = Column(String(1024), nullable=True)  # S3 object key
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

# Pydantic Schemas
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class EnqueueRequest(BaseModel):
    prompt: str
    width: Optional[int] = 256
    height: Optional[int] = 256
    steps: Optional[int] = 20
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
    path: Optional[str] = None  # Legacy local path
    s3_key: Optional[str] = None  # S3 object key
    download_url: Optional[str] = None  # Pre-signed download URL
    created_at: datetime.datetime
    likes_count: int
    model_name: Optional[str] = None
    liked_by_user: Optional[bool] = False

class PresignedUploadResponse(BaseModel):
    upload_url: str
    fields: dict
    key: str
    
class PresignedDownloadResponse(BaseModel):
    download_url: str
    expires_in: int