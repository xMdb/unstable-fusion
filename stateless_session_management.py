"""
Session Management Service for Stateless Architecture
Uses Redis/ElastiCache for distributed session storage
"""

import json
import uuid
import time
import hashlib
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

try:
    import redis
    from redis.exceptions import ConnectionError, TimeoutError
except ImportError:
    # Fallback for when Redis is not available
    redis = None
    ConnectionError = Exception
    TimeoutError = Exception

logger = logging.getLogger(__name__)

class StatelessSessionManager:
    """
    Manages user sessions in Redis for stateless application architecture
    
    Features:
    - Distributed session storage
    - Session expiration and cleanup
    - Secure session tokens
    - Session data serialization
    """
    
    def __init__(self, redis_host: str, redis_port: int = 6379, 
                 redis_password: Optional[str] = None,
                 session_timeout: int = 3600):
        """
        Initialize session manager
        
        Args:
            redis_host: Redis server hostname/endpoint
            redis_port: Redis server port
            redis_password: Redis password (if using AUTH)
            session_timeout: Session timeout in seconds (default 1 hour)
        """
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.session_timeout = session_timeout
        
        # Initialize Redis connection
        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            password=redis_password,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True
        )
        
        # Test connection
        try:
            self.redis_client.ping()
            logger.info(f"Connected to Redis at {redis_host}:{redis_port}")
        except (ConnectionError, TimeoutError) as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    def create_session(self, user_data: Dict[str, Any]) -> str:
        """
        Create a new session for user
        
        Args:
            user_data: User information to store in session
            
        Returns:
            session_id: Unique session identifier
        """
        session_id = self._generate_session_id()
        session_key = f"session:{session_id}"
        
        # Prepare session data
        session_data = {
            'user_id': user_data.get('user_id'),
            'username': user_data.get('username'),
            'email': user_data.get('email'),
            'is_admin': user_data.get('is_admin', False),
            'groups': user_data.get('groups', []),
            'created_at': datetime.utcnow().isoformat(),
            'last_accessed': datetime.utcnow().isoformat(),
            'ip_address': user_data.get('ip_address'),
            'user_agent': user_data.get('user_agent')
        }
        
        try:
            # Store session data with expiration
            self.redis_client.setex(
                session_key,
                self.session_timeout,
                json.dumps(session_data)
            )
            
            # Add to active sessions set for cleanup
            self.redis_client.sadd("active_sessions", session_id)
            
            logger.info(f"Created session {session_id} for user {user_data.get('username')}")
            return session_id
            
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            raise
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve session data
        
        Args:
            session_id: Session identifier
            
        Returns:
            Session data or None if not found/expired
        """
        session_key = f"session:{session_id}"
        
        try:
            session_data_str = self.redis_client.get(session_key)
            if not session_data_str:
                return None
            
            session_data = json.loads(session_data_str)
            
            # Update last accessed time
            session_data['last_accessed'] = datetime.utcnow().isoformat()
            self.redis_client.setex(
                session_key,
                self.session_timeout,
                json.dumps(session_data)
            )
            
            return session_data
            
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Failed to get session {session_id}: {e}")
            return None
    
    def update_session(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update session data
        
        Args:
            session_id: Session identifier
            updates: Data to update in session
            
        Returns:
            Success status
        """
        session_key = f"session:{session_id}"
        
        try:
            # Get existing session data
            session_data_str = self.redis_client.get(session_key)
            if not session_data_str:
                return False
            
            session_data = json.loads(session_data_str)
            
            # Apply updates
            session_data.update(updates)
            session_data['last_accessed'] = datetime.utcnow().isoformat()
            
            # Store updated data
            self.redis_client.setex(
                session_key,
                self.session_timeout,
                json.dumps(session_data)
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to update session {session_id}: {e}")
            return False
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete session (logout)
        
        Args:
            session_id: Session identifier
            
        Returns:
            Success status
        """
        session_key = f"session:{session_id}"
        
        try:
            # Delete session data
            self.redis_client.delete(session_key)
            
            # Remove from active sessions set
            self.redis_client.srem("active_sessions", session_id)
            
            logger.info(f"Deleted session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False
    
    def validate_session(self, session_id: str) -> bool:
        """
        Check if session is valid and not expired
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if session is valid
        """
        if not session_id:
            return False
        
        session_data = self.get_session(session_id)
        return session_data is not None
    
    def get_active_sessions_count(self) -> int:
        """Get count of active sessions"""
        try:
            return self.redis_client.scard("active_sessions")
        except Exception as e:
            logger.error(f"Failed to get active sessions count: {e}")
            return 0
    
    def cleanup_expired_sessions(self) -> int:
        """
        Clean up expired sessions from active sessions set
        
        Returns:
            Number of sessions cleaned up
        """
        try:
            active_sessions = self.redis_client.smembers("active_sessions")
            cleanup_count = 0
            
            for session_id in active_sessions:
                session_key = f"session:{session_id}"
                if not self.redis_client.exists(session_key):
                    # Session expired, remove from active set
                    self.redis_client.srem("active_sessions", session_id)
                    cleanup_count += 1
            
            logger.info(f"Cleaned up {cleanup_count} expired sessions")
            return cleanup_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired sessions: {e}")
            return 0
    
    def _generate_session_id(self) -> str:
        """Generate secure session ID"""
        # Use UUID4 + timestamp + random component for uniqueness
        unique_str = f"{uuid.uuid4()}{time.time()}{uuid.uuid4()}"
        return hashlib.sha256(unique_str.encode()).hexdigest()


class StatelessWebSocketManager:
    """
    Manages WebSocket connections in a stateless manner
    
    For the job progress reporting use case, this handles:
    - Connection state storage in Redis
    - Message broadcasting across instances
    - Connection recovery after instance restart
    """
    
    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client
        self.pubsub = redis_client.pubsub()
    
    def register_connection(self, connection_id: str, user_id: str, job_id: str):
        """
        Register WebSocket connection for job progress updates
        
        Args:
            connection_id: Unique connection identifier
            user_id: User who owns the connection
            job_id: Job being monitored
        """
        connection_data = {
            'user_id': user_id,
            'job_id': job_id,
            'connected_at': datetime.utcnow().isoformat(),
            'last_ping': datetime.utcnow().isoformat()
        }
        
        connection_key = f"ws_connection:{connection_id}"
        job_connections_key = f"job_connections:{job_id}"
        
        try:
            # Store connection data (expires in 1 hour)
            self.redis_client.setex(
                connection_key,
                3600,
                json.dumps(connection_data)
            )
            
            # Add to job connections set
            self.redis_client.sadd(job_connections_key, connection_id)
            self.redis_client.expire(job_connections_key, 3600)
            
            logger.info(f"Registered WebSocket connection {connection_id} for job {job_id}")
            
        except Exception as e:
            logger.error(f"Failed to register WebSocket connection: {e}")
    
    def unregister_connection(self, connection_id: str, job_id: str):
        """Remove WebSocket connection registration"""
        connection_key = f"ws_connection:{connection_id}"
        job_connections_key = f"job_connections:{job_id}"
        
        try:
            self.redis_client.delete(connection_key)
            self.redis_client.srem(job_connections_key, connection_id)
            
        except Exception as e:
            logger.error(f"Failed to unregister WebSocket connection: {e}")
    
    def broadcast_job_update(self, job_id: str, update_data: Dict[str, Any]):
        """
        Broadcast job update to all connected clients
        
        This uses Redis pub/sub to notify all application instances
        """
        message = {
            'job_id': job_id,
            'update_data': update_data,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        try:
            # Publish to Redis channel
            channel = f"job_updates:{job_id}"
            self.redis_client.publish(channel, json.dumps(message))
            
        except Exception as e:
            logger.error(f"Failed to broadcast job update: {e}")
    
    def get_job_connections(self, job_id: str) -> List[str]:
        """Get all connection IDs monitoring a specific job"""
        job_connections_key = f"job_connections:{job_id}"
        
        try:
            return list(self.redis_client.smembers(job_connections_key))
        except Exception as e:
            logger.error(f"Failed to get job connections: {e}")
            return []


class StatelessCacheManager:
    """
    Manages application cache in Redis for stateless architecture
    
    Handles:
    - Model outputs caching
    - Configuration caching
    - Temporary data storage
    """
    
    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client
    
    def cache_model_output(self, prompt_hash: str, model: str, output_data: Dict[str, Any],
                          ttl: int = 86400):
        """
        Cache model output for duplicate prompt detection
        
        Args:
            prompt_hash: Hash of the input prompt and parameters
            model: Model name used
            output_data: Generated output data
            ttl: Time to live in seconds (default 24 hours)
        """
        cache_key = f"model_cache:{model}:{prompt_hash}"
        
        try:
            self.redis_client.setex(
                cache_key,
                ttl, 
                json.dumps(output_data)
            )
            logger.info(f"Cached model output for {prompt_hash}")
            
        except Exception as e:
            logger.error(f"Failed to cache model output: {e}")
    
    def get_cached_output(self, prompt_hash: str, model: str) -> Optional[Dict[str, Any]]:
        """Get cached model output"""
        cache_key = f"model_cache:{model}:{prompt_hash}"
        
        try:
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
            return None
            
        except Exception as e:
            logger.error(f"Failed to get cached output: {e}")
            return None
    
    def cache_user_preferences(self, user_id: str, preferences: Dict[str, Any]):
        """Cache user preferences"""
        cache_key = f"user_prefs:{user_id}"
        
        try:
            self.redis_client.setex(
                cache_key,
                86400,  # 24 hours
                json.dumps(preferences)
            )
        except Exception as e:
            logger.error(f"Failed to cache user preferences: {e}")
    
    def get_user_preferences(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get cached user preferences"""
        cache_key = f"user_prefs:{user_id}"
        
        try:
            prefs_data = self.redis_client.get(cache_key) 
            if prefs_data:
                return json.loads(prefs_data)
            return None
            
        except Exception as e:
            logger.error(f"Failed to get user preferences: {e}")
            return None


# Global instances
session_manager = None
cache_manager = None
websocket_manager = None

def get_session_manager() -> StatelessSessionManager:
    """Get or create session manager instance"""
    global session_manager
    if session_manager is None:
        from aws_config_service import get_config_service
        config = get_config_service()
        
        redis_host = config.get_parameter("redis_endpoint") or "localhost"
        redis_port = int(config.get_parameter("redis_port") or "6379")
        
        session_manager = StatelessSessionManager(
            redis_host=redis_host,
            redis_port=redis_port
        )
    return session_manager

def get_cache_manager() -> StatelessCacheManager:
    """Get or create cache manager instance"""
    global cache_manager
    if cache_manager is None:
        session_mgr = get_session_manager()
        cache_manager = StatelessCacheManager(session_mgr.redis_client)
    return cache_manager

def get_websocket_manager() -> StatelessWebSocketManager:
    """Get or create WebSocket manager instance"""
    global websocket_manager
    if websocket_manager is None:
        session_mgr = get_session_manager()
        websocket_manager = StatelessWebSocketManager(session_mgr.redis_client)
    return websocket_manager