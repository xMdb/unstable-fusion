"""
Persistent Connection Manager
Handles WebSocket connections, Server-Sent Events, and graceful connection management
"""

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager

try:
    import websockets
    from websockets.exceptions import ConnectionClosed, ConnectionClosedError
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    print("WebSockets not available. Install with: pip install websockets")
    WEBSOCKETS_AVAILABLE = False

try:
    import boto3
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    print("boto3 not available. Install with: pip install boto3")
    BOTO3_AVAILABLE = False

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    print("redis not available. Install with: pip install redis")
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)

@dataclass
class ConnectionInfo:
    """Information about an active connection"""
    connection_id: str
    user_id: str
    connection_type: str  # 'websocket', 'sse', 'polling'
    instance_id: str
    created_at: float
    last_heartbeat: float
    metadata: Dict[str, Any]

@dataclass
class ProgressUpdate:
    """Progress update for a job or operation"""
    job_id: str
    user_id: str
    progress: float  # 0.0 to 1.0
    status: str
    message: str
    timestamp: float
    data: Optional[Dict[str, Any]] = None

class PersistentConnectionManager:
    """
    Manages persistent connections with graceful handling of disconnections
    Supports WebSockets, Server-Sent Events, and fallback polling
    """
    
    def __init__(self, redis_client=None, dynamodb_client=None, sns_client=None):
        self.redis_client = redis_client
        self.dynamodb_client = dynamodb_client
        self.sns_client = sns_client
        
        # In-memory connection tracking for this instance
        self.active_connections: Dict[str, ConnectionInfo] = {}
        self.websocket_connections: Dict[str, Any] = {}  # WebSocket objects
        self.sse_connections: Dict[str, Any] = {}  # SSE response objects
        
        # Instance identification
        self.instance_id = self._get_instance_id()
        
        # Configuration
        self.heartbeat_interval = 30  # seconds
        self.connection_timeout = 300  # 5 minutes
        self.cleanup_interval = 60  # 1 minute
        
        # Background tasks
        self._cleanup_task = None
        self._heartbeat_task = None
        
        logger.info(f"Initialized PersistentConnectionManager for instance {self.instance_id}")
    
    def _get_instance_id(self) -> str:
        """Get unique instance identifier"""
        import os
        return os.getenv('INSTANCE_ID', f"instance-{uuid.uuid4().hex[:8]}")
    
    async def start_background_tasks(self):
        """Start background tasks for connection management"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        if self._heartbeat_task is None:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        logger.info("Background tasks started")
    
    async def stop_background_tasks(self):
        """Stop background tasks"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Background tasks stopped")
    
    async def register_connection(self, user_id: str, connection_type: str, 
                                metadata: Dict[str, Any] = None) -> str:
        """
        Register a new persistent connection
        
        Args:
            user_id: User identifier
            connection_type: Type of connection ('websocket', 'sse', 'polling')
            metadata: Additional connection metadata
            
        Returns:
            connection_id: Unique connection identifier
        """
        connection_id = str(uuid.uuid4())
        current_time = time.time()
        
        connection_info = ConnectionInfo(
            connection_id=connection_id,
            user_id=user_id,
            connection_type=connection_type,
            instance_id=self.instance_id,
            created_at=current_time,
            last_heartbeat=current_time,
            metadata=metadata or {}
        )
        
        # Store in local memory
        self.active_connections[connection_id] = connection_info
        
        # Store in DynamoDB for cross-instance visibility
        if self.dynamodb_client:
            try:
                expires_at = int(current_time + self.connection_timeout)
                
                self.dynamodb_client.put_item(
                    TableName=self._get_connections_table(),
                    Item={
                        'connection_id': {'S': connection_id},
                        'user_id': {'S': user_id},
                        'connection_type': {'S': connection_type},
                        'instance_id': {'S': self.instance_id},
                        'created_at': {'N': str(current_time)},
                        'last_heartbeat': {'N': str(current_time)},
                        'expires_at': {'N': str(expires_at)},
                        'metadata': {'S': json.dumps(metadata or {})}
                    }
                )
                
                logger.info(f"Registered connection {connection_id} for user {user_id}")
                
            except ClientError as e:
                logger.error(f"Failed to register connection in DynamoDB: {e}")
        
        # Store in Redis for fast access
        if self.redis_client:
            try:
                connection_data = asdict(connection_info)
                self.redis_client.hset(
                    f"connection:{connection_id}",
                    mapping={k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) 
                            for k, v in connection_data.items()}
                )
                self.redis_client.expire(f"connection:{connection_id}", self.connection_timeout)
                
                # Add to user's connection set
                self.redis_client.sadd(f"user_connections:{user_id}", connection_id)
                
            except Exception as e:
                logger.error(f"Failed to store connection in Redis: {e}")
        
        return connection_id
    
    async def unregister_connection(self, connection_id: str):
        """
        Unregister a connection
        
        Args:
            connection_id: Connection identifier to remove
        """
        connection_info = self.active_connections.get(connection_id)
        
        if connection_info:
            # Remove from local memory
            del self.active_connections[connection_id]
            
            # Clean up WebSocket/SSE objects
            if connection_id in self.websocket_connections:
                del self.websocket_connections[connection_id]
            
            if connection_id in self.sse_connections:
                del self.sse_connections[connection_id]
            
            # Remove from DynamoDB
            if self.dynamodb_client:
                try:
                    self.dynamodb_client.delete_item(
                        TableName=self._get_connections_table(),
                        Key={'connection_id': {'S': connection_id}}
                    )
                except ClientError as e:
                    logger.error(f"Failed to remove connection from DynamoDB: {e}")
            
            # Remove from Redis
            if self.redis_client:
                try:
                    self.redis_client.delete(f"connection:{connection_id}")
                    self.redis_client.srem(f"user_connections:{connection_info.user_id}", connection_id)
                except Exception as e:
                    logger.error(f"Failed to remove connection from Redis: {e}")
            
            logger.info(f"Unregistered connection {connection_id}")
    
    async def send_to_connection(self, connection_id: str, message: Dict[str, Any]) -> bool:
        """
        Send message to a specific connection
        
        Args:
            connection_id: Target connection ID
            message: Message to send
            
        Returns:
            success: True if message was sent successfully
        """
        connection_info = self.active_connections.get(connection_id)
        
        if not connection_info:
            logger.warning(f"Connection {connection_id} not found")
            return False
        
        message_json = json.dumps(message)
        
        try:
            if connection_info.connection_type == 'websocket':
                return await self._send_websocket_message(connection_id, message_json)
            
            elif connection_info.connection_type == 'sse':
                return await self._send_sse_message(connection_id, message_json)
            
            elif connection_info.connection_type == 'polling':
                return await self._queue_polling_message(connection_id, message)
            
            else:
                logger.error(f"Unknown connection type: {connection_info.connection_type}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send message to connection {connection_id}: {e}")
            # Connection may be dead, schedule for cleanup
            await self._mark_connection_stale(connection_id)
            return False
    
    async def send_to_user(self, user_id: str, message: Dict[str, Any]) -> int:
        """
        Send message to all connections for a user
        
        Args:
            user_id: Target user ID
            message: Message to send
            
        Returns:
            count: Number of connections that received the message successfully
        """
        user_connections = await self._get_user_connections(user_id)
        
        if not user_connections:
            logger.info(f"No active connections found for user {user_id}")
            return 0
        
        success_count = 0
        tasks = []
        
        for connection_id in user_connections:
            task = asyncio.create_task(self.send_to_connection(connection_id, message))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, bool) and result:
                success_count += 1
            elif isinstance(result, Exception):
                logger.error(f"Error sending to user connection: {result}")
        
        logger.info(f"Sent message to {success_count}/{len(user_connections)} connections for user {user_id}")
        return success_count
    
    async def broadcast_progress_update(self, progress_update: ProgressUpdate) -> int:
        """
        Broadcast progress update to user's connections
        
        Args:
            progress_update: Progress information to broadcast
            
        Returns:
            count: Number of connections that received the update
        """
        message = {
            'type': 'progress_update',
            'job_id': progress_update.job_id,
            'progress': progress_update.progress,
            'status': progress_update.status,
            'message': progress_update.message,
            'timestamp': progress_update.timestamp,
            'data': progress_update.data
        }
        
        # Store progress in Redis for connection recovery
        if self.redis_client:
            try:
                progress_key = f"progress:{progress_update.job_id}"
                self.redis_client.set(progress_key, json.dumps(asdict(progress_update)), ex=3600)
            except Exception as e:
                logger.error(f"Failed to store progress in Redis: {e}")
        
        # Store progress in DynamoDB for persistence
        if self.dynamodb_client:
            try:
                self.dynamodb_client.put_item(
                    TableName=self._get_state_table(),
                    Item={
                        'state_key': {'S': f"progress:{progress_update.job_id}"},
                        'user_id': {'S': progress_update.user_id},
                        'job_id': {'S': progress_update.job_id},
                        'data': {'S': json.dumps(asdict(progress_update))},
                        'expires_at': {'N': str(int(time.time() + 3600))}
                    }
                )
            except ClientError as e:
                logger.error(f"Failed to store progress in DynamoDB: {e}")
        
        # Send to all user connections
        return await self.send_to_user(progress_update.user_id, message)
    
    async def handle_connection_loss(self, connection_id: str):
        """
        Handle graceful connection loss
        
        Args:
            connection_id: ID of the lost connection
        """
        connection_info = self.active_connections.get(connection_id)
        
        if connection_info:
            logger.info(f"Handling connection loss for {connection_id} (user: {connection_info.user_id})")
            
            # Notify other services about connection loss
            if self.sns_client:
                try:
                    message = {
                        'event': 'connection_lost',
                        'connection_id': connection_id,
                        'user_id': connection_info.user_id,
                        'instance_id': self.instance_id,
                        'timestamp': time.time()
                    }
                    
                    self.sns_client.publish(
                        TopicArn=self._get_events_topic_arn(),
                        Message=json.dumps(message),
                        Subject='Connection Lost'
                    )
                    
                except ClientError as e:
                    logger.error(f"Failed to publish connection loss event: {e}")
            
            # Unregister the connection
            await self.unregister_connection(connection_id)
    
    async def get_latest_progress(self, job_id: str) -> Optional[ProgressUpdate]:
        """
        Get latest progress for a job (for connection recovery)
        
        Args:
            job_id: Job identifier
            
        Returns:
            progress_update: Latest progress update or None
        """
        # Try Redis first (faster)
        if self.redis_client:
            try:
                progress_key = f"progress:{job_id}"
                progress_data = self.redis_client.get(progress_key)
                
                if progress_data:
                    progress_dict = json.loads(progress_data)
                    return ProgressUpdate(**progress_dict)
                    
            except Exception as e:
                logger.error(f"Failed to get progress from Redis: {e}")
        
        # Fallback to DynamoDB
        if self.dynamodb_client:
            try:
                response = self.dynamodb_client.get_item(
                    TableName=self._get_state_table(),
                    Key={'state_key': {'S': f"progress:{job_id}"}}
                )
                
                if 'Item' in response:
                    progress_data = json.loads(response['Item']['data']['S'])
                    return ProgressUpdate(**progress_data)
                    
            except ClientError as e:
                logger.error(f"Failed to get progress from DynamoDB: {e}")
        
        return None
    
    # WebSocket-specific methods
    async def register_websocket(self, websocket, user_id: str, metadata: Dict[str, Any] = None) -> str:
        """Register a WebSocket connection"""
        connection_id = await self.register_connection(user_id, 'websocket', metadata)
        self.websocket_connections[connection_id] = websocket
        
        # Send initial connection confirmation
        await self._send_websocket_message(connection_id, json.dumps({
            'type': 'connection_established',
            'connection_id': connection_id,
            'timestamp': time.time()
        }))
        
        return connection_id
    
    async def handle_websocket_message(self, connection_id: str, message: str):
        """Handle incoming WebSocket message"""
        try:
            data = json.loads(message)
            
            if data.get('type') == 'heartbeat':
                await self._update_heartbeat(connection_id)
                await self._send_websocket_message(connection_id, json.dumps({
                    'type': 'heartbeat_ack',
                    'timestamp': time.time()
                }))
            
            elif data.get('type') == 'subscribe_progress':
                job_id = data.get('job_id')
                if job_id:
                    # Send latest progress if available
                    progress = await self.get_latest_progress(job_id)
                    if progress:
                        await self.send_to_connection(connection_id, {
                            'type': 'progress_update',
                            **asdict(progress)
                        })
            
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON message from connection {connection_id}: {message}")
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")
    
    async def websocket_handler(self, websocket, path):
        """WebSocket connection handler"""
        if not WEBSOCKETS_AVAILABLE:
            logger.error("WebSockets not available")
            return
        
        connection_id = None
        
        try:
            # Extract user info from query parameters or headers
            user_id = self._extract_user_from_websocket(websocket)
            
            if not user_id:
                await websocket.close(code=4001, reason="Authentication required")
                return
            
            # Register connection
            connection_id = await self.register_websocket(websocket, user_id)
            logger.info(f"WebSocket connected: {connection_id} for user {user_id}")
            
            # Handle messages
            async for message in websocket:
                await self.handle_websocket_message(connection_id, message)
                
        except ConnectionClosed:
            logger.info(f"WebSocket connection closed: {connection_id}")
        except ConnectionClosedError:
            logger.info(f"WebSocket connection closed with error: {connection_id}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            if connection_id:
                await self.handle_connection_loss(connection_id)
    
    # Server-Sent Events methods
    async def register_sse(self, response_object, user_id: str, metadata: Dict[str, Any] = None) -> str:
        """Register a Server-Sent Events connection"""
        connection_id = await self.register_connection(user_id, 'sse', metadata)
        self.sse_connections[connection_id] = response_object
        
        # Send initial connection event
        await self._send_sse_message(connection_id, json.dumps({
            'type': 'connection_established',
            'connection_id': connection_id,
            'timestamp': time.time()
        }))
        
        return connection_id
    
    # Private helper methods
    async def _send_websocket_message(self, connection_id: str, message: str) -> bool:
        """Send message via WebSocket"""
        websocket = self.websocket_connections.get(connection_id)
        
        if not websocket:
            return False
        
        try:
            await websocket.send(message)
            return True
        except (ConnectionClosed, ConnectionClosedError):
            await self.handle_connection_loss(connection_id)
            return False
        except Exception as e:
            logger.error(f"WebSocket send error: {e}")
            await self.handle_connection_loss(connection_id)
            return False
    
    async def _send_sse_message(self, connection_id: str, message: str) -> bool:
        """Send message via Server-Sent Events"""
        response = self.sse_connections.get(connection_id)
        
        if not response:
            return False
        
        try:
            sse_data = f"data: {message}\n\n"
            # Implementation depends on your web framework
            # For FastAPI: await response.send(sse_data)
            # For Flask: response.write(sse_data)
            return True
        except Exception as e:
            logger.error(f"SSE send error: {e}")
            await self.handle_connection_loss(connection_id)
            return False
    
    async def _queue_polling_message(self, connection_id: str, message: Dict[str, Any]) -> bool:
        """Queue message for polling connection"""
        if self.redis_client:
            try:
                # Store message in a queue for polling
                queue_key = f"polling_queue:{connection_id}"
                self.redis_client.lpush(queue_key, json.dumps(message))
                self.redis_client.expire(queue_key, 300)  # 5 minute TTL
                return True
            except Exception as e:
                logger.error(f"Failed to queue polling message: {e}")
        
        return False
    
    async def _get_user_connections(self, user_id: str) -> List[str]:
        """Get all active connections for a user"""
        connections = []
        
        # Check Redis first
        if self.redis_client:
            try:
                redis_connections = self.redis_client.smembers(f"user_connections:{user_id}")
                connections.extend([conn.decode() for conn in redis_connections])
            except Exception as e:
                logger.error(f"Failed to get user connections from Redis: {e}")
        
        # Fallback to local connections
        for conn_id, conn_info in self.active_connections.items():
            if conn_info.user_id == user_id and conn_id not in connections:
                connections.append(conn_id)
        
        return connections
    
    async def _update_heartbeat(self, connection_id: str):
        """Update heartbeat timestamp for a connection"""
        current_time = time.time()
        
        # Update local connection
        if connection_id in self.active_connections:
            self.active_connections[connection_id].last_heartbeat = current_time
        
        # Update Redis
        if self.redis_client:
            try:
                self.redis_client.hset(f"connection:{connection_id}", "last_heartbeat", str(current_time))
            except Exception as e:
                logger.error(f"Failed to update heartbeat in Redis: {e}")
        
        # Update DynamoDB
        if self.dynamodb_client:
            try:
                self.dynamodb_client.update_item(
                    TableName=self._get_connections_table(),
                    Key={'connection_id': {'S': connection_id}},
                    UpdateExpression='SET last_heartbeat = :heartbeat',
                    ExpressionAttributeValues={':heartbeat': {'N': str(current_time)}}
                )
            except ClientError as e:
                logger.error(f"Failed to update heartbeat in DynamoDB: {e}")
    
    async def _mark_connection_stale(self, connection_id: str):
        """Mark a connection as stale for cleanup"""
        if self.redis_client:
            try:
                stale_key = f"stale_connections:{self.instance_id}"
                self.redis_client.sadd(stale_key, connection_id)
                self.redis_client.expire(stale_key, 300)
            except Exception as e:
                logger.error(f"Failed to mark connection as stale: {e}")
    
    async def _cleanup_loop(self):
        """Background loop for cleaning up stale connections"""
        while True:
            try:
                await self._cleanup_stale_connections()
                await asyncio.sleep(self.cleanup_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(self.cleanup_interval)
    
    async def _heartbeat_loop(self):
        """Background loop for sending heartbeats"""
        while True:
            try:
                await self._send_heartbeats()
                await asyncio.sleep(self.heartbeat_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")
                await asyncio.sleep(self.heartbeat_interval)
    
    async def _cleanup_stale_connections(self):
        """Clean up connections that haven't sent heartbeats"""
        current_time = time.time()
        stale_connections = []
        
        for connection_id, connection_info in self.active_connections.items():
            if current_time - connection_info.last_heartbeat > self.connection_timeout:
                stale_connections.append(connection_id)
        
        for connection_id in stale_connections:
            logger.info(f"Cleaning up stale connection: {connection_id}")
            await self.handle_connection_loss(connection_id)
    
    async def _send_heartbeats(self):
        """Send heartbeat pings to all WebSocket connections"""
        heartbeat_message = json.dumps({
            'type': 'heartbeat_ping',
            'timestamp': time.time()
        })
        
        for connection_id in list(self.websocket_connections.keys()):
            try:
                await self._send_websocket_message(connection_id, heartbeat_message)
            except Exception as e:
                logger.error(f"Failed to send heartbeat to {connection_id}: {e}")
    
    def _extract_user_from_websocket(self, websocket) -> Optional[str]:
        """Extract user ID from WebSocket connection"""
        # Implementation depends on your authentication system
        # This is a placeholder - implement based on your auth mechanism
        try:
            # Example: Extract from query parameters
            if hasattr(websocket, 'query_string'):
                query_string = websocket.query_string.decode()
                # Parse query string to get user_id or token
                pass
            
            # Example: Extract from headers
            if hasattr(websocket, 'request_headers'):
                auth_header = websocket.request_headers.get('Authorization')
                if auth_header:
                    # Validate token and extract user_id
                    pass
                    
            # Placeholder return
            return "user123"  # Replace with actual user extraction logic
            
        except Exception as e:
            logger.error(f"Failed to extract user from WebSocket: {e}")
            return None
    
    def _get_connections_table(self) -> str:
        """Get DynamoDB connections table name"""
        return os.getenv('CONNECTIONS_TABLE', 'unstablefusion-active-connections')
    
    def _get_state_table(self) -> str:
        """Get DynamoDB state table name"""
        return os.getenv('STATE_TABLE', 'unstablefusion-connection-state')
    
    def _get_events_topic_arn(self) -> str:
        """Get SNS events topic ARN"""
        return os.getenv('SNS_TOPIC_ARN', '')


# Factory functions for dependency injection
def get_connection_manager() -> Optional[PersistentConnectionManager]:
    """Get connection manager instance"""
    try:
        redis_client = None
        if REDIS_AVAILABLE:
            import os
            redis_endpoint = os.getenv('REDIS_ENDPOINT', 'localhost:6379')
            host, port = redis_endpoint.split(':')
            redis_client = redis.Redis(host=host, port=int(port), decode_responses=True)
        
        dynamodb_client = None
        sns_client = None
        if BOTO3_AVAILABLE:
            dynamodb_client = boto3.client('dynamodb')
            sns_client = boto3.client('sns')
        
        return PersistentConnectionManager(
            redis_client=redis_client,
            dynamodb_client=dynamodb_client,
            sns_client=sns_client
        )
        
    except Exception as e:
        logger.error(f"Failed to create connection manager: {e}")
        return None


# Connection recovery utilities
class ConnectionRecoveryManager:
    """Manages connection recovery and graceful degradation"""
    
    def __init__(self, connection_manager: PersistentConnectionManager):
        self.connection_manager = connection_manager
        self.recovery_strategies = {
            'websocket': self._recover_websocket,
            'sse': self._recover_sse,
            'polling': self._recover_polling
        }
    
    async def handle_instance_shutdown(self, instance_id: str):
        """Handle graceful shutdown of an instance"""
        logger.info(f"Handling shutdown for instance {instance_id}")
        
        # Get all connections for this instance
        if self.connection_manager.dynamodb_client:
            try:
                response = self.connection_manager.dynamodb_client.query(
                    TableName=self.connection_manager._get_connections_table(),
                    IndexName='instance-id-index',
                    KeyConditionExpression='instance_id = :instance_id',
                    ExpressionAttributeValues={':instance_id': {'S': instance_id}}
                )
                
                # Notify clients to reconnect
                for item in response.get('Items', []):
                    connection_id = item['connection_id']['S']
                    user_id = item['user_id']['S']
                    connection_type = item['connection_type']['S']
                    
                    # Send reconnection message to other instances
                    await self._trigger_reconnection(user_id, connection_type, connection_id)
                
            except Exception as e:
                logger.error(f"Failed to handle instance shutdown: {e}")
    
    async def _trigger_reconnection(self, user_id: str, connection_type: str, old_connection_id: str):
        """Trigger reconnection for a user"""
        recovery_strategy = self.recovery_strategies.get(connection_type)
        
        if recovery_strategy:
            await recovery_strategy(user_id, old_connection_id)
        else:
            logger.warning(f"No recovery strategy for connection type: {connection_type}")
    
    async def _recover_websocket(self, user_id: str, old_connection_id: str):
        """Recover WebSocket connection"""
        # Send message to any existing connections to trigger client-side reconnection
        message = {
            'type': 'reconnection_required',
            'reason': 'instance_shutdown',
            'old_connection_id': old_connection_id,
            'timestamp': time.time()
        }
        
        await self.connection_manager.send_to_user(user_id, message)
    
    async def _recover_sse(self, user_id: str, old_connection_id: str):
        """Recover Server-Sent Events connection"""
        # Similar to WebSocket recovery
        message = {
            'type': 'reconnection_required',
            'reason': 'instance_shutdown',
            'old_connection_id': old_connection_id,
            'timestamp': time.time()
        }
        
        await self.connection_manager.send_to_user(user_id, message)
    
    async def _recover_polling(self, user_id: str, old_connection_id: str):
        """Recover polling connection"""
        # For polling connections, just ensure messages are queued properly
        # The client will pick them up on next poll
        logger.info(f"Polling connection {old_connection_id} for user {user_id} will recover on next poll")


if __name__ == "__main__":
    # Example usage
    async def main():
        connection_manager = get_connection_manager()
        
        if connection_manager:
            await connection_manager.start_background_tasks()
            
            # Example: Register a connection
            user_id = "test_user_123"
            connection_id = await connection_manager.register_connection(user_id, 'websocket', {'test': True})
            
            # Example: Send progress update
            progress = ProgressUpdate(
                job_id="job_123",
                user_id=user_id,
                progress=0.5,
                status="processing",
                message="Image generation 50% complete",
                timestamp=time.time()
            )
            
            await connection_manager.broadcast_progress_update(progress)
            
            # Cleanup
            await connection_manager.stop_background_tasks()
        
        else:
            print("Connection manager not available")
    
    asyncio.run(main())