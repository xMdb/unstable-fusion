/**
 * Persistent Connection Client
 * Handles WebSocket connections with automatic reconnection and fallback to polling
 * Provides graceful degradation when connections are lost
 */

class PersistentConnectionClient {
    constructor(options = {}) {
        // Configuration
        this.baseUrl = options.baseUrl || window.location.origin;
        this.userId = options.userId;
        this.authToken = options.authToken;
        
        // Connection settings
        this.maxReconnectAttempts = options.maxReconnectAttempts || 10;
        this.reconnectDelay = options.reconnectDelay || 1000; // Start with 1 second
        this.maxReconnectDelay = options.maxReconnectDelay || 30000; // Max 30 seconds
        this.heartbeatInterval = options.heartbeatInterval || 30000; // 30 seconds
        this.pollingInterval = options.pollingInterval || 5000; // 5 seconds
        
        // State
        this.connectionId = null;
        this.reconnectAttempts = 0;
        this.isConnected = false;
        this.connectionType = 'disconnected'; // 'websocket', 'sse', 'polling', 'disconnected'
        this.subscribedJobs = new Set();
        
        // WebSocket state
        this.websocket = null;
        this.heartbeatTimer = null;
        this.reconnectTimer = null;
        
        // SSE state
        this.eventSource = null;
        
        // Polling state
        this.pollingTimer = null;
        this.lastPollingTimestamp = Date.now();
        
        // Event handlers
        this.eventHandlers = {
            'connection_established': [],
            'connection_lost': [],
            'progress_update': [],
            'reconnection_required': [],
            'error': [],
            'message': []
        };
        
        console.log('PersistentConnectionClient initialized');
    }
    
    /**
     * Connect using the best available method
     */
    async connect() {
        console.log('Attempting to connect...');
        
        // Try WebSocket first
        if (this.supportsWebSocket()) {
            try {
                await this.connectWebSocket();
                return;
            } catch (error) {
                console.warn('WebSocket connection failed, trying SSE:', error);
            }
        }
        
        // Fallback to Server-Sent Events
        if (this.supportsSSE()) {
            try {
                await this.connectSSE();
                return;
            } catch (error) {
                console.warn('SSE connection failed, falling back to polling:', error);
            }
        }
        
        // Final fallback to polling
        this.connectPolling();
    }
    
    /**
     * Disconnect and clean up
     */
    disconnect() {
        console.log('Disconnecting...');
        
        this.isConnected = false;
        this.connectionType = 'disconnected';
        
        // Clear timers
        if (this.heartbeatTimer) {
            clearInterval(this.heartbeatTimer);
            this.heartbeatTimer = null;
        }
        
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
        
        if (this.pollingTimer) {
            clearInterval(this.pollingTimer);
            this.pollingTimer = null;
        }
        
        // Close connections
        this.closeWebSocket();
        this.closeSSE();
        
        this.emit('connection_lost', { reason: 'manual_disconnect' });
    }
    
    /**
     * Subscribe to progress updates for a job
     */
    subscribeToJob(jobId) {
        this.subscribedJobs.add(jobId);
        
        if (this.isConnected) {
            this.sendMessage({
                type: 'subscribe_progress',
                job_id: jobId
            });
        }
        
        console.log(`Subscribed to job progress: ${jobId}`);
    }
    
    /**
     * Unsubscribe from job progress updates
     */
    unsubscribeFromJob(jobId) {
        this.subscribedJobs.delete(jobId);
        
        if (this.isConnected) {
            this.sendMessage({
                type: 'unsubscribe_progress',
                job_id: jobId
            });
        }
        
        console.log(`Unsubscribed from job progress: ${jobId}`);
    }
    
    /**
     * Send a message (if connected)
     */
    sendMessage(message) {
        if (!this.isConnected) {
            console.warn('Cannot send message: not connected');
            return false;
        }
        
        const messageStr = JSON.stringify(message);
        
        if (this.connectionType === 'websocket' && this.websocket) {
            this.websocket.send(messageStr);
            return true;
        }
        
        // For SSE and polling, we might need to use POST requests
        if (this.connectionType === 'sse' || this.connectionType === 'polling') {
            this.sendHttpMessage(message);
            return true;
        }
        
        return false;
    }
    
    /**
     * Add event listener
     */
    on(event, handler) {
        if (!this.eventHandlers[event]) {
            this.eventHandlers[event] = [];
        }
        this.eventHandlers[event].push(handler);
    }
    
    /**
     * Remove event listener
     */
    off(event, handler) {
        if (this.eventHandlers[event]) {
            const index = this.eventHandlers[event].indexOf(handler);
            if (index > -1) {
                this.eventHandlers[event].splice(index, 1);
            }
        }
    }
    
    /**
     * Emit event to handlers
     */
    emit(event, data) {
        if (this.eventHandlers[event]) {
            this.eventHandlers[event].forEach(handler => {
                try {
                    handler(data);
                } catch (error) {
                    console.error('Error in event handler:', error);
                }
            });
        }
    }
    
    // WebSocket implementation
    supportsWebSocket() {
        return 'WebSocket' in window;
    }
    
    async connectWebSocket() {
        return new Promise((resolve, reject) => {
            const wsUrl = this.getWebSocketUrl();
            console.log(`Connecting to WebSocket: ${wsUrl}`);
            
            try {
                this.websocket = new WebSocket(wsUrl);
                
                this.websocket.onopen = () => {
                    console.log('WebSocket connected');
                    this.connectionType = 'websocket';
                    this.isConnected = true;
                    this.reconnectAttempts = 0;
                    
                    this.startHeartbeat();
                    this.resubscribeToJobs();
                    
                    resolve();
                };
                
                this.websocket.onmessage = (event) => {
                    this.handleMessage(JSON.parse(event.data));
                };
                
                this.websocket.onclose = (event) => {
                    console.log('WebSocket closed:', event.code, event.reason);
                    this.handleConnectionLoss();
                };
                
                this.websocket.onerror = (error) => {
                    console.error('WebSocket error:', error);
                    this.emit('error', { type: 'websocket', error });
                    reject(error);
                };
                
            } catch (error) {
                reject(error);
            }
        });
    }
    
    closeWebSocket() {
        if (this.websocket) {
            this.websocket.close();
            this.websocket = null;
        }
    }
    
    getWebSocketUrl() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        let url = `${protocol}//${host}/ws`;
        
        // Add authentication parameters
        const params = new URLSearchParams();
        if (this.userId) params.append('user_id', this.userId);
        if (this.authToken) params.append('token', this.authToken);
        
        if (params.toString()) {
            url += `?${params.toString()}`;
        }
        
        return url;
    }
    
    // Server-Sent Events implementation
    supportsSSE() {
        return 'EventSource' in window;
    }
    
    async connectSSE() {
        return new Promise((resolve, reject) => {
            const sseUrl = this.getSSEUrl();
            console.log(`Connecting to SSE: ${sseUrl}`);
            
            try {
                this.eventSource = new EventSource(sseUrl);
                
                this.eventSource.onopen = () => {
                    console.log('SSE connected');
                    this.connectionType = 'sse';
                    this.isConnected = true;
                    this.reconnectAttempts = 0;
                    
                    this.resubscribeToJobs();
                    resolve();
                };
                
                this.eventSource.onmessage = (event) => {
                    this.handleMessage(JSON.parse(event.data));
                };
                
                this.eventSource.onerror = (error) => {
                    console.error('SSE error:', error);
                    
                    if (this.eventSource.readyState === EventSource.CLOSED) {
                        this.handleConnectionLoss();
                    } else {
                        this.emit('error', { type: 'sse', error });
                    }
                    
                    reject(error);
                };
                
            } catch (error) {
                reject(error);
            }
        });
    }
    
    closeSSE() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
    }
    
    getSSEUrl() {
        let url = `${this.baseUrl}/api/events`;
        
        // Add authentication parameters
        const params = new URLSearchParams();
        if (this.userId) params.append('user_id', this.userId);
        if (this.authToken) params.append('token', this.authToken);
        
        if (params.toString()) {
            url += `?${params.toString()}`;
        }
        
        return url;
    }
    
    // Polling implementation
    connectPolling() {
        console.log('Starting polling connection');
        
        this.connectionType = 'polling';
        this.isConnected = true;
        this.reconnectAttempts = 0;
        
        // Send initial connection request
        this.registerPollingConnection();
        
        // Start polling loop
        this.pollingTimer = setInterval(() => {
            this.pollForMessages();
        }, this.pollingInterval);
        
        this.resubscribeToJobs();
        this.emit('connection_established', { type: 'polling' });
    }
    
    async registerPollingConnection() {
        try {
            const response = await fetch(`${this.baseUrl}/api/connections/register`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(this.authToken && { 'Authorization': `Bearer ${this.authToken}` })
                },
                body: JSON.stringify({
                    user_id: this.userId,
                    connection_type: 'polling'
                })
            });
            
            if (response.ok) {
                const data = await response.json();
                this.connectionId = data.connection_id;
                console.log('Polling connection registered:', this.connectionId);
            }
            
        } catch (error) {
            console.error('Failed to register polling connection:', error);
        }
    }
    
    async pollForMessages() {
        try {
            const response = await fetch(`${this.baseUrl}/api/connections/poll`, {
                method: 'GET',
                headers: {
                    ...(this.authToken && { 'Authorization': `Bearer ${this.authToken}` })
                }
            });
            
            if (response.ok) {
                const data = await response.json();
                
                if (data.messages) {
                    data.messages.forEach(message => {
                        this.handleMessage(message);
                    });
                }
            }
            
        } catch (error) {
            console.error('Polling failed:', error);
            this.handleConnectionLoss();
        }
    }
    
    // Message handling
    handleMessage(message) {
        console.log('Received message:', message);
        
        switch (message.type) {
            case 'connection_established':
                this.connectionId = message.connection_id;
                this.emit('connection_established', message);
                break;
                
            case 'progress_update':
                this.emit('progress_update', message);
                break;
                
            case 'reconnection_required':
                console.log('Reconnection required:', message.reason);
                this.handleReconnectionRequired(message);
                break;
                
            case 'heartbeat_ping':
                this.sendHeartbeatResponse();
                break;
                
            case 'heartbeat_ack':
                // Heartbeat acknowledged
                break;
                
            default:
                this.emit('message', message);
                break;
        }
    }
    
    handleConnectionLoss() {
        console.log('Connection lost, attempting to reconnect...');
        
        this.isConnected = false;
        this.connectionType = 'disconnected';
        
        // Clear timers
        if (this.heartbeatTimer) {
            clearInterval(this.heartbeatTimer);
            this.heartbeatTimer = null;
        }
        
        this.emit('connection_lost', { reason: 'connection_error' });
        
        // Attempt reconnection
        this.scheduleReconnect();
    }
    
    handleReconnectionRequired(message) {
        console.log('Server requested reconnection:', message);
        
        // Close current connection
        this.closeWebSocket();
        this.closeSSE();
        
        // Reconnect immediately
        this.reconnectAttempts = 0;
        this.connect();
    }
    
    scheduleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('Max reconnection attempts reached, giving up');
            this.emit('error', { 
                type: 'reconnection_failed', 
                message: 'Max reconnection attempts reached' 
            });
            return;
        }
        
        const delay = Math.min(
            this.reconnectDelay * Math.pow(2, this.reconnectAttempts),
            this.maxReconnectDelay
        );
        
        console.log(`Scheduling reconnection attempt ${this.reconnectAttempts + 1} in ${delay}ms`);
        
        this.reconnectTimer = setTimeout(() => {
            this.reconnectAttempts++;
            this.connect();
        }, delay);
    }
    
    // Heartbeat handling
    startHeartbeat() {
        if (this.connectionType === 'websocket') {
            this.heartbeatTimer = setInterval(() => {
                this.sendHeartbeat();
            }, this.heartbeatInterval);
        }
    }
    
    sendHeartbeat() {
        if (this.connectionType === 'websocket' && this.websocket) {
            this.sendMessage({ type: 'heartbeat' });
        }
    }
    
    sendHeartbeatResponse() {
        if (this.connectionType === 'websocket' && this.websocket) {
            this.sendMessage({ type: 'heartbeat_response' });
        }
    }
    
    // Utility methods
    resubscribeToJobs() {
        // Resubscribe to all jobs after reconnection
        this.subscribedJobs.forEach(jobId => {
            this.sendMessage({
                type: 'subscribe_progress',
                job_id: jobId
            });
        });
        
        if (this.subscribedJobs.size > 0) {
            console.log(`Resubscribed to ${this.subscribedJobs.size} jobs`);
        }
    }
    
    async sendHttpMessage(message) {
        try {
            const response = await fetch(`${this.baseUrl}/api/connections/message`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(this.authToken && { 'Authorization': `Bearer ${this.authToken}` })
                },
                body: JSON.stringify(message)
            });
            
            return response.ok;
            
        } catch (error) {
            console.error('Failed to send HTTP message:', error);
            return false;
        }
    }
    
    // Status methods
    getStatus() {
        return {
            isConnected: this.isConnected,
            connectionType: this.connectionType,
            connectionId: this.connectionId,
            reconnectAttempts: this.reconnectAttempts,
            subscribedJobs: Array.from(this.subscribedJobs)
        };
    }
    
    isHealthy() {
        return this.isConnected && this.reconnectAttempts === 0;
    }
}

// Progress tracking utility
class ProgressTracker {
    constructor(connectionClient) {
        this.client = connectionClient;
        this.jobs = new Map(); // jobId -> { progress, status, callbacks }
        
        // Listen for progress updates
        this.client.on('progress_update', (data) => {
            this.handleProgressUpdate(data);
        });
        
        // Handle connection loss
        this.client.on('connection_lost', () => {
            console.log('Connection lost - progress updates paused');
        });
        
        this.client.on('connection_established', () => {
            console.log('Connection established - resuming progress tracking');
            // Request latest progress for all tracked jobs
            this.requestLatestProgress();
        });
    }
    
    trackJob(jobId, callbacks = {}) {
        console.log(`Starting progress tracking for job: ${jobId}`);
        
        this.jobs.set(jobId, {
            progress: 0,
            status: 'pending',
            callbacks: {
                onProgress: callbacks.onProgress || (() => {}),
                onComplete: callbacks.onComplete || (() => {}),
                onError: callbacks.onError || (() => {})
            }
        });
        
        // Subscribe to updates
        this.client.subscribeToJob(jobId);
        
        // Request current progress if available
        this.requestJobProgress(jobId);
    }
    
    stopTracking(jobId) {
        console.log(`Stopping progress tracking for job: ${jobId}`);
        
        this.jobs.delete(jobId);
        this.client.unsubscribeFromJob(jobId);
    }
    
    handleProgressUpdate(data) {
        const jobId = data.job_id;
        const jobInfo = this.jobs.get(jobId);
        
        if (!jobInfo) {
            return; // Not tracking this job
        }
        
        // Update job info
        jobInfo.progress = data.progress;
        jobInfo.status = data.status;
        
        console.log(`Progress update for ${jobId}: ${(data.progress * 100).toFixed(1)}% - ${data.status}`);
        
        // Call callbacks
        try {
            jobInfo.callbacks.onProgress(data);
            
            if (data.status === 'completed') {
                jobInfo.callbacks.onComplete(data);
                this.stopTracking(jobId);
            } else if (data.status === 'failed' || data.status === 'error') {
                jobInfo.callbacks.onError(data);
                this.stopTracking(jobId);
            }
        } catch (error) {
            console.error('Error in progress callback:', error);
        }
    }
    
    async requestJobProgress(jobId) {
        // This would make an HTTP request to get current progress
        try {
            const response = await fetch(`${this.client.baseUrl}/api/jobs/${jobId}/progress`, {
                headers: {
                    ...(this.client.authToken && { 'Authorization': `Bearer ${this.client.authToken}` })
                }
            });
            
            if (response.ok) {
                const data = await response.json();
                if (data.progress !== undefined) {
                    this.handleProgressUpdate(data);
                }
            }
        } catch (error) {
            console.error('Failed to request job progress:', error);
        }
    }
    
    requestLatestProgress() {
        // Request latest progress for all tracked jobs
        this.jobs.forEach((_, jobId) => {
            this.requestJobProgress(jobId);
        });
    }
    
    getJobStatus(jobId) {
        return this.jobs.get(jobId);
    }
    
    getAllJobs() {
        return Array.from(this.jobs.entries()).map(([jobId, info]) => ({
            jobId,
            progress: info.progress,
            status: info.status
        }));
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { PersistentConnectionClient, ProgressTracker };
}

// Global availability for browser
if (typeof window !== 'undefined') {
    window.PersistentConnectionClient = PersistentConnectionClient;
    window.ProgressTracker = ProgressTracker;
}