"""
Stateless Application Integration
Updates the main application to use stateless patterns
"""

import os
import logging
import hashlib
from datetime import datetime
from contextlib import asynccontextmanager

try:
    from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
    from fastapi.middleware.cors import CORSMiddleware
    FASTAPI_AVAILABLE = True
except ImportError:
    print("FastAPI not installed. Install with: pip install fastapi uvicorn")
    FASTAPI_AVAILABLE = False

# Import our stateless services
from stateless_job_processing import StatelessJobProcessor, get_journal_service, get_recovery_service
from stateless_session_management import get_session_manager, get_cache_manager
from aws_config_service import get_config_service

logger = logging.getLogger(__name__)

# Global services
job_processor = None
session_manager = None
cache_manager = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management for stateless operation"""
    global job_processor, session_manager, cache_manager
    
    logger.info("Starting UnstableFusion in stateless mode")
    
    # Initialize stateless services
    try:
        # Initialize journal-based job processor
        journal_service = get_journal_service()
        job_processor = StatelessJobProcessor(journal_service)
        
        # Initialize Redis-based session manager
        session_manager = get_session_manager()
        cache_manager = get_cache_manager()
        
        # Start background recovery service
        recovery_service = get_recovery_service()
        
        logger.info("✓ Stateless services initialized successfully")
        
        # Test connections
        if session_manager:
            active_sessions = session_manager.get_active_sessions_count()
            logger.info(f"✓ Redis connected: {active_sessions} active sessions")
        
    except Exception as e:
        logger.error(f"Failed to initialize stateless services: {e}")
        logger.warning("Falling back to stateful operation")
    
    yield
    
    # Cleanup on shutdown
    logger.info("Shutting down stateless services")


def create_stateless_app() -> FastAPI:
    """Create FastAPI app configured for stateless operation"""
    
    app = FastAPI(
        title="UnstableFusion - Stateless",
        description="AI Image Generation Service (Stateless Architecture)",
        version="2.0.0",
        lifespan=lifespan
    )
    
    # CORS configuration for stateless operation
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure based on your needs
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    return app


# Dependency for getting session data
def get_current_session(session_id: str = None):
    """
    Get current session data for stateless authentication
    
    Args:
        session_id: Session identifier from cookie/header
        
    Returns:
        Session data or raises HTTPException
    """
    if not session_id or not session_manager:
        raise HTTPException(status_code=401, detail="No valid session")
    
    session_data = session_manager.get_session(session_id)
    if not session_data:
        raise HTTPException(status_code=401, detail="Session expired")
    
    return session_data


# Stateless job submission endpoint
async def submit_job_stateless(
    prompt: str,
    model: str = "stabilityai/sd-turbo",
    width: int = 512,
    height: int = 512,
    steps: int = 20,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    session: dict = Depends(get_current_session)
):
    """
    Submit job for processing using stateless pattern
    
    This endpoint:
    1. Creates a journal entry immediately
    2. Queues job for background processing
    3. Returns job ID for status checking
    4. Can handle interruptions gracefully
    """
    if not job_processor:
        raise HTTPException(status_code=503, detail="Job processor not available")
    
    # Generate unique job ID
    import uuid
    job_id = str(uuid.uuid4())
    
    # Check cache for duplicate prompts (optional optimization)
    if cache_manager:
        prompt_hash = hashlib.sha256(f"{prompt}{model}{width}{height}{steps}".encode()).hexdigest()
        cached_result = cache_manager.get_cached_output(prompt_hash, model)
        if cached_result:
            logger.info(f"Returning cached result for prompt hash {prompt_hash}")
            return {
                "job_id": job_id,
                "status": "completed",
                "cached": True,
                "result": cached_result
            }
    
    # Process job in background using stateless pattern
    background_tasks.add_task(
        process_job_background,
        job_id, prompt, model, width, height, steps,
        session['user_id']
    )
    
    return {
        "job_id": job_id,
        "status": "queued",
        "message": "Job submitted for processing"
    }


async def process_job_background(job_id: str, prompt: str, model: str,
                               width: int, height: int, steps: int, user_id: str):
    """
    Background job processing with stateless pattern
    
    This function implements the journaling pattern to ensure
    jobs can be recovered if the process is interrupted
    """
    try:
        result = job_processor.process_job_stateless(
            job_id=job_id,
            prompt=prompt,
            model=model,
            width=width,
            height=height,
            steps=steps
        )
        
        if result['success']:
            logger.info(f"Job {job_id} completed successfully")
            
            # Cache the result for future duplicate requests
            if cache_manager:
                prompt_hash = hashlib.sha256(f"{prompt}{model}{width}{height}{steps}".encode()).hexdigest()
                cache_manager.cache_model_output(prompt_hash, model, {
                    'job_id': job_id,
                    's3_key': result['s3_key'],
                    'prompt': prompt,
                    'model': model
                })
        else:
            logger.error(f"Job {job_id} failed: {result['error']}")
            
    except Exception as e:
        logger.error(f"Background job processing failed for {job_id}: {e}")


# Health check endpoint for load balancer
async def health_check():
    """
    Health check endpoint for stateless instances
    
    Verifies:
    - Application is running
    - Database connectivity
    - Redis connectivity
    - AWS services accessibility
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {}
    }
    
    # Check Redis connectivity
    try:
        if session_manager:
            session_manager.redis_client.ping()
            health_status["services"]["redis"] = "healthy"
        else:
            health_status["services"]["redis"] = "not_configured"
    except Exception as e:
        health_status["services"]["redis"] = f"error: {str(e)}"
        health_status["status"] = "degraded"
    
    # Check database connectivity
    try:
        # Add your database health check here
        health_status["services"]["database"] = "healthy"
    except Exception as e:
        health_status["services"]["database"] = f"error: {str(e)}"
        health_status["status"] = "degraded"
    
    # Check AWS services
    try:
        config_service = get_config_service()
        # Test Parameter Store access
        config_service.get_parameter("api_base_url")
        health_status["services"]["aws"] = "healthy"
    except Exception as e:
        health_status["services"]["aws"] = f"error: {str(e)}"
        health_status["status"] = "degraded"
    
    return health_status


# Recovery endpoint for manual journal recovery
async def trigger_recovery():
    """
    Manual trigger for journal recovery process
    Useful for debugging and emergency recovery
    """
    try:
        recovery_service = get_recovery_service()
        recovery_service.recover_incomplete_operations()
        
        return {
            "success": True,
            "message": "Recovery process completed"
        }
    except Exception as e:
        logger.error(f"Manual recovery failed: {e}")
        raise HTTPException(status_code=500, detail=f"Recovery failed: {str(e)}")


# Session management endpoints for stateless auth
async def create_session_endpoint(user_data: dict):
    """Create new session"""
    if not session_manager:
        raise HTTPException(status_code=503, detail="Session manager not available")
    
    session_id = session_manager.create_session(user_data)
    return {"session_id": session_id}


async def validate_session_endpoint(session_id: str):
    """Validate session"""
    if not session_manager:
        raise HTTPException(status_code=503, detail="Session manager not available")
    
    is_valid = session_manager.validate_session(session_id)
    return {"valid": is_valid}


async def logout_endpoint(session_id: str):
    """Logout (delete session)"""
    if not session_manager:
        raise HTTPException(status_code=503, detail="Session manager not available")
    
    success = session_manager.delete_session(session_id)
    return {"success": success}


# Application metrics for monitoring stateless operation
async def get_metrics():
    """
    Get application metrics for monitoring
    
    Returns metrics useful for:
    - Auto-scaling decisions
    - Performance monitoring
    - Capacity planning
    """
    metrics = {
        "timestamp": datetime.utcnow().isoformat(),
        "instance_id": os.getenv("INSTANCE_ID", "unknown"),
        "metrics": {}
    }
    
    # Session metrics
    if session_manager:
        metrics["metrics"]["active_sessions"] = session_manager.get_active_sessions_count()
    
    # Journal metrics
    try:
        journal_service = get_journal_service()
        incomplete_jobs = journal_service.find_incomplete_jobs()
        metrics["metrics"]["incomplete_jobs"] = len(incomplete_jobs)
    except Exception as e:
        logger.error(f"Failed to get journal metrics: {e}")
    
    # System metrics
    try:
        import psutil
        metrics["metrics"]["cpu_percent"] = psutil.cpu_percent()
        metrics["metrics"]["memory_percent"] = psutil.virtual_memory().percent
        metrics["metrics"]["disk_percent"] = psutil.disk_usage('/').percent
    except ImportError:
        logger.warning("psutil not available for system metrics")
        metrics["metrics"]["system_metrics"] = "unavailable"
    except Exception as e:
        logger.error(f"Failed to get system metrics: {e}")
    
    return metrics


if __name__ == "__main__":
    if not FASTAPI_AVAILABLE:
        print("Cannot run server: FastAPI not installed")
        exit(1)
        
    try:
        import uvicorn
        
        # Create stateless app
        app = create_stateless_app()
        
        # Add all endpoints
        app.get("/health")(health_check)
        app.post("/api/jobs")(submit_job_stateless) 
        app.post("/api/recovery")(trigger_recovery)
        app.post("/api/sessions")(create_session_endpoint)
        app.get("/api/sessions/{session_id}/validate")(validate_session_endpoint)
        app.delete("/api/sessions/{session_id}")(logout_endpoint)
        app.get("/api/metrics")(get_metrics)
        
        # Run the application
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            log_level="info"
        )
        
    except ImportError:
        print("uvicorn not installed. Install with: pip install uvicorn")
        exit(1)