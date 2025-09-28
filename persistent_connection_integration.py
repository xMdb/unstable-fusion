"""
Persistent Connection Integration
Integrates persistent connection management with the main FastAPI application
"""

import asyncio
import json
import logging
import time
from typing import Dict, Optional, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, BackgroundTasks
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from persistent_connection_manager import (
    PersistentConnectionManager, 
    ProgressUpdate, 
    get_connection_manager,
    ConnectionRecoveryManager
)

logger = logging.getLogger(__name__)

class ConnectionIntegratedApp:
    """
    FastAPI application with integrated persistent connection management
    """
    
    def __init__(self, app: FastAPI):
        self.app = app
        self.connection_manager = get_connection_manager()
        self.recovery_manager = None
        
        if self.connection_manager:
            self.recovery_manager = ConnectionRecoveryManager(self.connection_manager)
            self._setup_routes()
            self._setup_startup_shutdown()
            logger.info("Persistent connection integration enabled")
        else:
            logger.warning("Connection manager not available - persistent connections disabled")
    
    def _setup_routes(self):
        """Setup routes for persistent connections"""
        
        # WebSocket endpoint
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self._handle_websocket(websocket)
        
        # Server-Sent Events endpoint
        @self.app.get("/api/events")
        async def sse_endpoint(request: Request):
            return await self._handle_sse(request)
        
        # Polling endpoints
        @self.app.post("/api/connections/register")
        async def register_polling_connection(request: Request):
            return await self._register_polling_connection(request)
        
        @self.app.get("/api/connections/poll")
        async def poll_messages(request: Request):
            return await self._poll_messages(request)
        
        @self.app.post("/api/connections/message")
        async def send_message(request: Request):
            return await self._handle_message(request)
        
        # Progress endpoints
        @self.app.get("/api/jobs/{job_id}/progress")
        async def get_job_progress(job_id: str, request: Request):
            return await self._get_job_progress(job_id, request)
        
        # Health check with connection status
        @self.app.get("/api/connection-health")
        async def connection_health():
            return await self._get_connection_health()
    
    def _setup_startup_shutdown(self):
        """Setup application startup and shutdown handlers"""
        
        @self.app.on_event("startup")
        async def startup():
            if self.connection_manager:
                await self.connection_manager.start_background_tasks()
                logger.info("Connection manager started")
        
        @self.app.on_event("shutdown")
        async def shutdown():
            if self.connection_manager:
                await self.connection_manager.stop_background_tasks()
                
                # Notify about instance shutdown
                if self.recovery_manager:
                    await self.recovery_manager.handle_instance_shutdown(
                        self.connection_manager.instance_id
                    )
                
                logger.info("Connection manager stopped")
    
    async def _handle_websocket(self, websocket: WebSocket):
        """Handle WebSocket connections"""
        if not self.connection_manager:
            await websocket.close(code=1013, reason="Service unavailable")
            return
        
        await websocket.accept()
        connection_id = None
        
        try:
            # Extract user info from query parameters or headers
            user_id = self._extract_user_from_request(websocket)
            
            if not user_id:
                await websocket.close(code=1008, reason="Authentication required")
                return
            
            # Register WebSocket connection
            connection_id = await self.connection_manager.register_websocket(
                websocket, user_id, {"client_info": "web"}
            )
            
            logger.info(f"WebSocket connected: {connection_id}")
            
            # Handle incoming messages
            while True:
                try:
                    data = await websocket.receive_text()
                    await self.connection_manager.handle_websocket_message(connection_id, data)
                except WebSocketDisconnect:
                    break
                    
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            if connection_id:
                await self.connection_manager.handle_connection_loss(connection_id)
    
    async def _handle_sse(self, request: Request):
        """Handle Server-Sent Events connections"""
        if not self.connection_manager:
            return {"error": "Service unavailable"}
        
        user_id = self._extract_user_from_request(request)
        
        if not user_id:
            return {"error": "Authentication required"}
        
        async def event_generator():
            connection_id = None
            
            try:
                # Register SSE connection (simplified - would need proper SSE handling)
                connection_id = await self.connection_manager.register_connection(
                    user_id, 'sse', {"client_info": "sse"}
                )
                
                # Send connection established event
                yield {
                    "event": "connection_established",
                    "data": json.dumps({
                        "connection_id": connection_id,
                        "timestamp": time.time()
                    })
                }
                
                # Keep connection alive and handle events
                while True:
                    # In a real implementation, you'd listen for events from Redis/queue
                    await asyncio.sleep(1)
                    
                    # Send heartbeat
                    yield {
                        "event": "heartbeat",
                        "data": json.dumps({"timestamp": time.time()})
                    }
                    
            except Exception as e:
                logger.error(f"SSE error: {e}")
            finally:
                if connection_id:
                    await self.connection_manager.handle_connection_loss(connection_id)
        
        return EventSourceResponse(event_generator())
    
    async def _register_polling_connection(self, request: Request):
        """Register a polling connection"""
        if not self.connection_manager:
            return {"error": "Service unavailable"}
        
        try:
            data = await request.json()
            user_id = data.get('user_id') or self._extract_user_from_request(request)
            
            if not user_id:
                return {"error": "User ID required"}
            
            connection_id = await self.connection_manager.register_connection(
                user_id, 'polling', {"client_info": "polling"}
            )
            
            return {
                "success": True,
                "connection_id": connection_id
            }
            
        except Exception as e:
            logger.error(f"Failed to register polling connection: {e}")
            return {"error": "Registration failed"}
    
    async def _poll_messages(self, request: Request):
        """Poll for messages (polling connection)"""
        if not self.connection_manager:
            return {"error": "Service unavailable"}
        
        user_id = self._extract_user_from_request(request)
        
        if not user_id:
            return {"error": "Authentication required"}
        
        try:
            # Get messages from Redis queue
            if self.connection_manager.redis_client:
                messages = []
                
                # Get all user connections to find polling connections
                user_connections = await self.connection_manager._get_user_connections(user_id)
                
                for connection_id in user_connections:
                    connection_info = self.connection_manager.active_connections.get(connection_id)
                    
                    if connection_info and connection_info.connection_type == 'polling':
                        # Get messages from polling queue
                        queue_key = f"polling_queue:{connection_id}"
                        
                        while True:
                            message_data = self.connection_manager.redis_client.rpop(queue_key)
                            if not message_data:
                                break
                            
                            try:
                                message = json.loads(message_data)
                                messages.append(message)
                            except json.JSONDecodeError:
                                continue
                
                return {"messages": messages}
            
            return {"messages": []}
            
        except Exception as e:
            logger.error(f"Polling failed: {e}")
            return {"error": "Polling failed"}
    
    async def _handle_message(self, request: Request):
        """Handle incoming message from client"""
        if not self.connection_manager:
            return {"error": "Service unavailable"}
        
        try:
            data = await request.json()
            user_id = self._extract_user_from_request(request)
            
            if not user_id:
                return {"error": "Authentication required"}
            
            # Process the message based on type
            message_type = data.get('type')
            
            if message_type == 'subscribe_progress':
                job_id = data.get('job_id')
                if job_id:
                    # Send latest progress if available
                    progress = await self.connection_manager.get_latest_progress(job_id)
                    if progress:
                        await self.connection_manager.send_to_user(user_id, {
                            'type': 'progress_update',
                            'job_id': progress.job_id,
                            'progress': progress.progress,
                            'status': progress.status,
                            'message': progress.message,
                            'timestamp': progress.timestamp,
                            'data': progress.data
                        })
            
            return {"success": True}
            
        except Exception as e:
            logger.error(f"Failed to handle message: {e}")
            return {"error": "Message handling failed"}
    
    async def _get_job_progress(self, job_id: str, request: Request):
        """Get current progress for a job"""
        if not self.connection_manager:
            return {"error": "Service unavailable"}
        
        user_id = self._extract_user_from_request(request)
        
        if not user_id:
            return {"error": "Authentication required"}
        
        try:
            progress = await self.connection_manager.get_latest_progress(job_id)
            
            if progress:
                return {
                    "job_id": progress.job_id,
                    "progress": progress.progress,
                    "status": progress.status,
                    "message": progress.message,
                    "timestamp": progress.timestamp,
                    "data": progress.data
                }
            else:
                return {"error": "Progress not found"}
                
        except Exception as e:
            logger.error(f"Failed to get job progress: {e}")
            return {"error": "Failed to get progress"}
    
    async def _get_connection_health(self):
        """Get connection system health status"""
        if not self.connection_manager:
            return {"status": "unavailable"}
        
        try:
            health = {
                "status": "healthy",
                "instance_id": self.connection_manager.instance_id,
                "active_connections": len(self.connection_manager.active_connections),
                "connection_types": {},
                "services": {}
            }
            
            # Count connection types
            for conn_info in self.connection_manager.active_connections.values():
                conn_type = conn_info.connection_type
                health["connection_types"][conn_type] = health["connection_types"].get(conn_type, 0) + 1
            
            # Check service health
            if self.connection_manager.redis_client:
                try:
                    self.connection_manager.redis_client.ping()
                    health["services"]["redis"] = "healthy"
                except:
                    health["services"]["redis"] = "unhealthy"
                    health["status"] = "degraded"
            
            if self.connection_manager.dynamodb_client:
                try:
                    # Simple health check
                    health["services"]["dynamodb"] = "healthy"
                except:
                    health["services"]["dynamodb"] = "unhealthy"
                    health["status"] = "degraded"
            
            return health
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {"status": "error", "error": str(e)}
    
    def _extract_user_from_request(self, request) -> Optional[str]:
        """Extract user ID from request (WebSocket or HTTP)"""
        try:
            # Try to extract from query parameters
            if hasattr(request, 'query_params'):
                user_id = request.query_params.get('user_id')
                if user_id:
                    return user_id
            
            # Try to extract from headers (Bearer token, etc.)
            if hasattr(request, 'headers'):
                auth_header = request.headers.get('Authorization')
                if auth_header and auth_header.startswith('Bearer '):
                    # Decode JWT token to get user_id
                    # This is a placeholder - implement based on your auth system
                    token = auth_header.split(' ')[1]
                    # decoded = decode_jwt(token)
                    # return decoded.get('user_id')
                    pass
            
            # Placeholder - implement based on your authentication system
            return "demo_user"  # For testing
            
        except Exception as e:
            logger.error(f"Failed to extract user from request: {e}")
            return None
    
    async def send_progress_update(self, job_id: str, user_id: str, progress: float, 
                                 status: str, message: str, data: Dict[str, Any] = None):
        """
        Convenience method to send progress updates
        
        Args:
            job_id: Job identifier
            user_id: User identifier
            progress: Progress value (0.0 to 1.0)
            status: Status string
            message: Human-readable message
            data: Additional data
        """
        if not self.connection_manager:
            logger.warning("Cannot send progress update: connection manager not available")
            return 0
        
        progress_update = ProgressUpdate(
            job_id=job_id,
            user_id=user_id,
            progress=progress,
            status=status,
            message=message,
            timestamp=time.time(),
            data=data
        )
        
        return await self.connection_manager.broadcast_progress_update(progress_update)


# Integration with existing FastAPI app
def integrate_persistent_connections(app: FastAPI) -> ConnectionIntegratedApp:
    """
    Integrate persistent connection management with existing FastAPI app
    
    Args:
        app: Existing FastAPI application
        
    Returns:
        ConnectionIntegratedApp: Integrated application with connection management
    """
    return ConnectionIntegratedApp(app)


# Example usage in main application
if __name__ == "__main__":
    from fastapi import FastAPI
    import uvicorn
    
    # Create FastAPI app
    app = FastAPI(title="UnstableFusion with Persistent Connections")
    
    # Integrate persistent connections
    connection_app = integrate_persistent_connections(app)
    
    # Example job endpoint that sends progress updates
    @app.post("/api/jobs")
    async def create_job(request: Request, background_tasks: BackgroundTasks):
        # Extract job details from request
        data = await request.json()
        prompt = data.get('prompt', 'Default prompt')
        user_id = connection_app._extract_user_from_request(request)
        
        if not user_id:
            return {"error": "Authentication required"}
        
        # Generate job ID
        import uuid
        job_id = str(uuid.uuid4())
        
        # Start background job processing with progress updates
        background_tasks.add_task(
            process_job_with_progress, 
            connection_app, job_id, user_id, prompt
        )
        
        return {
            "job_id": job_id,
            "status": "queued",
            "message": "Job started"
        }
    
    async def process_job_with_progress(connection_app: ConnectionIntegratedApp, 
                                      job_id: str, user_id: str, prompt: str):
        """Example background job with progress updates"""
        try:
            # Send initial progress
            await connection_app.send_progress_update(
                job_id, user_id, 0.0, "starting", "Job started"
            )
            
            # Simulate processing with progress updates
            for i in range(10):
                await asyncio.sleep(1)  # Simulate work
                
                progress = (i + 1) / 10
                await connection_app.send_progress_update(
                    job_id, user_id, progress, "processing", 
                    f"Processing step {i+1}/10"
                )
            
            # Send completion
            await connection_app.send_progress_update(
                job_id, user_id, 1.0, "completed", "Job completed successfully",
                {"result": f"Generated image for: {prompt}"}
            )
            
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            await connection_app.send_progress_update(
                job_id, user_id, 0.0, "failed", f"Job failed: {str(e)}"
            )
    
    # Run the application
    uvicorn.run(app, host="0.0.0.0", port=8000)