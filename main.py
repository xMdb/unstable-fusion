# GENERATIVE AI DISCLAIMER
#
# A portion of this code was generated with the assistance of generative AI. Any files that do not contain a disclaimer were either written by a human without AI assistance or generated with developer tooling such as Vite.
#
# Models used:
# GPT-5 by OpenAI (August 2025 version)
# Used for the first draft and overall structure of this Python app and RESTful API.
# 
# Claude Sonnet 4 by Anthropic (August 2025 version)
# Used in Agent and Ask mode to fix bugs and add width/height/steps parameters to the API.
#
# GPT-4.1 Copilot by OpenAI (August 2025 VS Code version)
# Used in the IDE to suggest code completions.
#
# REFERENCES
# 
# This code was adapted from the following articles:
# https://medium.com/@nttp/text-to-image-on-cpu-only-hardware-bd98f291dead
# https://medium.com/latinxinai/text-to-image-with-stable-diffusion-4df16da2cfd5
#
# The following models are downloaded and used by this Python app:
# https://huggingface.co/stabilityai/sd-turbo
# https://huggingface.co/CompVis/stable-diffusion-v1-4
# https://huggingface.co/Stable-Diffusion-v1-5/stable-diffusion-v1-5

import os
import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Import configuration and setup
print("⏳ Importing config...")
start_time = time.time()
from config import CORS_ORIGINS, FRONTEND_DIST_DIR
print(f"✓ config imported ({time.time() - start_time:.2f}s)")

print("⏳ Importing database...")
start_time = time.time()
from database import create_tables
print(f"✓ database imported ({time.time() - start_time:.2f}s)")

print("⏳ Importing auth...")
start_time = time.time()
from auth import create_or_sync_hardcoded_users
print(f"✓ auth imported ({time.time() - start_time:.2f}s)")

print("⏳ Importing worker...")
start_time = time.time()
from worker import start_worker, stop_worker_gracefully, reset_processing_jobs
print(f"✓ worker imported ({time.time() - start_time:.2f}s)")

# Import routers
print("⏳ Importing routers...")
start_time = time.time()
from routers.auth import router as auth_router
from routers.jobs import router as jobs_router
from routers.images import router as images_router
from routers.queue import router as queue_router
from routers.s3 import router as s3_router
print(f"✓ routers imported ({time.time() - start_time:.2f}s)")

# Try to import Cognito auth router, but continue without it if it fails
try:
    import time
    print("⏳ Loading Cognito authentication router...")
    start_time = time.time()
    
    from routers.cognito_auth import router as cognito_auth_router
    cognito_available = True
    
    load_time = time.time() - start_time
    print(f"✓ Cognito authentication router loaded ({load_time:.2f}s)")
except Exception as e:
    print(f"⚠ Cognito authentication not available: {e}")
    cognito_auth_router = None
    cognito_available = False

# Create FastAPI app
app = FastAPI(
    title="Unstable Fusion REST API",
    description="AI-powered image generation service with Stable Diffusion",
    version="2.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
if cognito_available:
    app.include_router(cognito_auth_router)  # Cognito authentication (optional)
app.include_router(jobs_router)
app.include_router(images_router)
app.include_router(queue_router)
app.include_router(s3_router)

@app.on_event("startup")
def startup_event():
    """Initialize application on startup"""
    print("Starting Unstable Fusion API...")
    
    # Create database tables
    create_tables()
    print("Database tables created/verified")
    
    # Create or sync hardcoded users
    create_or_sync_hardcoded_users()
    print("Hardcoded users synchronized")
    
    # Reset any jobs that were processing back to queued
    reset_processing_jobs()
    
    # Start background worker
    start_worker()
    
    print("Unstable Fusion API startup completed")

@app.on_event("shutdown")
def shutdown_event():
    """Clean shutdown"""
    print("Shutting down Unstable Fusion API...")
    stop_worker_gracefully()
    print("Unstable Fusion API shutdown complete")

# Serve React frontend
app.mount("/static", StaticFiles(directory=FRONTEND_DIST_DIR, html=True), name="static")

@app.get("/")
def serve_index():
    """Serve the React frontend"""
    index_path = os.path.join(FRONTEND_DIST_DIR, "index.html")
    return FileResponse(index_path)

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "unstable-fusion-api"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3001)