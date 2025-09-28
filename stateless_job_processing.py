"""
Stateless Job Processing Service
Implements journaling pattern for reliable, stateless job processing
"""

import json
import uuid
import time
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from enum import Enum

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

class JournalStatus(Enum):
    """Journal entry status types"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CLEANING_UP = "cleaning_up"

class JobProcessingJournal:
    """
    Manages job processing journal for stateless operation
    
    Journal entries track the complete lifecycle of job processing:
    1. PENDING: Job received, metadata to be written
    2. PROCESSING: File being generated/stored  
    3. COMPLETED: All operations successful
    4. FAILED: Error occurred, needs cleanup
    5. CLEANING_UP: Cleanup in progress
    """
    
    def __init__(self, region_name: str = "ap-southeast-2", username: str = "n11974796"):
        self.region_name = region_name
        self.username = username
        self.table_name = f"unstable-fusion-{username}-job-journal"
        
        # Initialize AWS clients
        self.dynamodb = boto3.resource('dynamodb', region_name=region_name)
        self.sqs = boto3.client('sqs', region_name=region_name) 
        self.s3 = boto3.client('s3', region_name=region_name)
        
        # Get table references
        self.journal_table = self.dynamodb.Table(self.table_name)
    
    def create_journal_entry(self, job_data: Dict[str, Any]) -> str:
        """
        Create a new journal entry for job processing
        
        Args:
            job_data: Job information including prompt, model, parameters
            
        Returns:
            journal_id: Unique identifier for this journal entry
        """
        journal_id = str(uuid.uuid4())
        current_time = datetime.utcnow()
        expires_at = int((current_time + timedelta(hours=24)).timestamp())
        
        journal_entry = {
            'journal_id': journal_id,
            'job_id': job_data.get('job_id'),
            'status': JournalStatus.PENDING.value,
            'created_at': current_time.isoformat(),
            'updated_at': current_time.isoformat(),
            'expires_at': expires_at,
            'job_data': job_data,
            'operations': {
                'database_write': False,
                's3_upload': False,
                'cleanup_complete': False
            },
            'retry_count': 0,
            'error_message': None
        }
        
        try:
            self.journal_table.put_item(Item=journal_entry)
            logger.info(f"Created journal entry: {journal_id} for job: {job_data.get('job_id')}")
            return journal_id
        except ClientError as e:
            logger.error(f"Failed to create journal entry: {e}")
            raise
    
    def update_journal_status(self, journal_id: str, status: JournalStatus, 
                            operations: Optional[Dict[str, bool]] = None,
                            error_message: Optional[str] = None) -> bool:
        """
        Update journal entry status and operations
        
        Args:
            journal_id: Journal entry identifier
            status: New status
            operations: Operation completion flags
            error_message: Error message if status is FAILED
            
        Returns:
            bool: Success status
        """
        update_expression = "SET #status = :status, updated_at = :updated_at"
        expression_values = {
            ':status': status.value,
            ':updated_at': datetime.utcnow().isoformat()
        }
        expression_names = {'#status': 'status'}
        
        if operations:
            update_expression += ", operations = :operations"
            expression_values[':operations'] = operations
        
        if error_message:
            update_expression += ", error_message = :error_message"
            expression_values[':error_message'] = error_message
        
        try:
            self.journal_table.update_item(
                Key={'journal_id': journal_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_names,
                ExpressionAttributeValues=expression_values
            )
            logger.info(f"Updated journal {journal_id} to status: {status.value}")
            return True
        except ClientError as e:
            logger.error(f"Failed to update journal {journal_id}: {e}")
            return False
    
    def get_journal_entry(self, journal_id: str) -> Optional[Dict[str, Any]]:
        """Get journal entry by ID"""
        try:
            response = self.journal_table.get_item(Key={'journal_id': journal_id})
            return response.get('Item')
        except ClientError as e:
            logger.error(f"Failed to get journal entry {journal_id}: {e}")
            return None
    
    def find_incomplete_jobs(self) -> List[Dict[str, Any]]:
        """
        Find journal entries that need recovery
        
        Returns:
            List of incomplete journal entries
        """
        incomplete_statuses = [
            JournalStatus.PENDING.value,
            JournalStatus.PROCESSING.value,
            JournalStatus.FAILED.value
        ]
        
        incomplete_entries = []
        
        for status in incomplete_statuses:
            try:
                response = self.journal_table.query(
                    IndexName='status-created-index',
                    KeyConditionExpression='#status = :status',
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={':status': status},
                    FilterExpression='created_at < :threshold',
                    ExpressionAttributeValues={
                        ':status': status,
                        ':threshold': (datetime.utcnow() - timedelta(minutes=5)).isoformat()
                    }
                )
                incomplete_entries.extend(response.get('Items', []))
            except ClientError as e:
                logger.error(f"Failed to query incomplete jobs for status {status}: {e}")
        
        return incomplete_entries
    
    def complete_journal_entry(self, journal_id: str) -> bool:
        """Mark journal entry as completed and schedule for cleanup"""
        try:
            # Update status to completed
            success = self.update_journal_status(
                journal_id, 
                JournalStatus.COMPLETED,
                operations={
                    'database_write': True,
                    's3_upload': True,
                    'cleanup_complete': True
                }
            )
            
            if success:
                # Schedule cleanup after delay to avoid race conditions
                self._schedule_cleanup(journal_id, delay_seconds=300)  # 5 minutes
            
            return success
        except Exception as e:
            logger.error(f"Failed to complete journal entry {journal_id}: {e}")
            return False
    
    def _schedule_cleanup(self, journal_id: str, delay_seconds: int = 300):
        """Schedule journal entry cleanup"""
        cleanup_message = {
            'action': 'cleanup_journal',
            'journal_id': journal_id,
            'scheduled_at': datetime.utcnow().isoformat()
        }
        
        try:
            # Send to cleanup queue with delay
            queue_url = f"https://sqs.{self.region_name}.amazonaws.com/123456789012/unstable-fusion-{self.username}-cleanup"
            self.sqs.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps(cleanup_message),
                DelaySeconds=delay_seconds
            )
            logger.info(f"Scheduled cleanup for journal {journal_id}")
        except ClientError as e:
            logger.error(f"Failed to schedule cleanup for journal {journal_id}: {e}")


class StatelessJobProcessor:
    """
    Stateless job processor that can handle interruptions gracefully
    
    Implements the journaling pattern:
    1. Create journal entry
    2. Write job metadata to database  
    3. Generate and store image in S3
    4. Update job status in database
    5. Complete journal entry
    """
    
    def __init__(self, journal: JobProcessingJournal):
        self.journal = journal
        
    def process_job_stateless(self, job_id: str, prompt: str, model: str, 
                            width: int, height: int, steps: int) -> Dict[str, Any]:
        """
        Process job using stateless pattern with journaling
        
        Args:
            job_id: Unique job identifier
            prompt: Text prompt for image generation
            model: AI model to use
            width: Image width
            height: Image height  
            steps: Generation steps
            
        Returns:
            Processing result with journal_id
        """
        job_data = {
            'job_id': job_id,
            'prompt': prompt,
            'model': model,
            'width': width,
            'height': height,
            'steps': steps,
            'created_at': datetime.utcnow().isoformat()
        }
        
        # Step 1: Create journal entry (this makes the operation traceable)
        journal_id = self.journal.create_journal_entry(job_data)
        
        try:
            # Step 2: Write job metadata to database FIRST
            # This ensures we have a record even if file generation fails
            self._write_job_metadata(job_id, job_data)
            self.journal.update_journal_status(
                journal_id, 
                JournalStatus.PROCESSING,
                operations={'database_write': True, 's3_upload': False}
            )
            
            # Step 3: Generate and store image
            s3_key = self._generate_and_store_image(job_id, job_data)
            self.journal.update_journal_status(
                journal_id,
                JournalStatus.PROCESSING, 
                operations={'database_write': True, 's3_upload': True}
            )
            
            # Step 4: Update job with completion status
            self._update_job_completion(job_id, s3_key)
            
            # Step 5: Complete journal entry
            self.journal.complete_journal_entry(journal_id)
            
            return {
                'success': True,
                'job_id': job_id,
                'journal_id': journal_id,
                's3_key': s3_key
            }
            
        except Exception as e:
            logger.error(f"Job processing failed for {job_id}: {e}")
            self.journal.update_journal_status(
                journal_id,
                JournalStatus.FAILED,
                error_message=str(e)
            )
            return {
                'success': False,
                'job_id': job_id,
                'journal_id': journal_id,
                'error': str(e)
            }
    
    def _write_job_metadata(self, job_id: str, job_data: Dict[str, Any]):
        """Write job metadata to database"""
        from database import get_db
        from models import Job
        
        # This would integrate with your existing database models
        # For now, simulating the database write
        logger.info(f"Writing job metadata for {job_id}")
        # db_job = Job(
        #     id=job_id,
        #     prompt=job_data['prompt'],
        #     model=job_data['model'],
        #     status='processing',
        #     created_at=datetime.utcnow()
        # )
        # db.add(db_job)
        # db.commit()
    
    def _generate_and_store_image(self, job_id: str, job_data: Dict[str, Any]) -> str:
        """Generate image and store in S3"""
        # This would integrate with your existing image generation pipeline
        logger.info(f"Generating and storing image for {job_id}")
        
        # Simulate image generation and S3 upload
        s3_key = f"images/{job_id}.jpg"
        
        # In real implementation:
        # 1. Generate image using your pipeline
        # 2. Upload to S3 with s3_key
        # 3. Return s3_key
        
        return s3_key
    
    def _update_job_completion(self, job_id: str, s3_key: str):
        """Update job status to completed"""
        logger.info(f"Updating job {job_id} completion with S3 key: {s3_key}")
        # db_job.status = 'completed'
        # db_job.output_path = s3_key
        # db_job.completed_at = datetime.utcnow()
        # db.commit()


class JournalRecoveryService:
    """
    Service for recovering from interrupted operations
    Runs periodically to check for incomplete journal entries
    """
    
    def __init__(self, journal: JobProcessingJournal):
        self.journal = journal
    
    def recover_incomplete_operations(self):
        """
        Find and recover incomplete operations
        This implements the recovery logic described in the slides
        """
        logger.info("Starting journal recovery process")
        
        incomplete_entries = self.journal.find_incomplete_jobs()
        logger.info(f"Found {len(incomplete_entries)} incomplete journal entries")
        
        for entry in incomplete_entries:
            self._recover_journal_entry(entry)
    
    def _recover_journal_entry(self, entry: Dict[str, Any]):
        """
        Recover individual journal entry based on its state
        
        Recovery logic:
        1. PENDING + old timestamp: Delete journal record (timeout)
        2. PROCESSING + database_write=True, s3_upload=False: Complete S3 upload
        3. PROCESSING + both operations complete: Update to COMPLETED
        4. FAILED: Attempt cleanup of partial operations
        """
        journal_id = entry['journal_id']
        job_id = entry['job_id']
        status = entry['status']
        operations = entry.get('operations', {})
        created_at = datetime.fromisoformat(entry['created_at'])
        
        logger.info(f"Recovering journal entry {journal_id} with status {status}")
        
        # Check if entry is too old and should be cleaned up
        if created_at < datetime.utcnow() - timedelta(hours=1):
            if status == JournalStatus.PENDING.value:
                self._cleanup_stale_pending_entry(journal_id, job_id)
                return
        
        # Recover based on current state
        if status == JournalStatus.PROCESSING.value:
            if operations.get('database_write') and not operations.get('s3_upload'):
                # Case: Metadata written but S3 upload incomplete
                self._complete_s3_upload_recovery(journal_id, job_id, entry['job_data'])
            elif operations.get('database_write') and operations.get('s3_upload'):
                # Case: Both operations complete but journal not cleaned up
                self.journal.complete_journal_entry(journal_id)
        
        elif status == JournalStatus.FAILED.value:
            # Attempt cleanup of any partial operations
            self._cleanup_failed_operations(journal_id, job_id, operations)
    
    def _cleanup_stale_pending_entry(self, journal_id: str, job_id: str):
        """Clean up stale pending entries (likely timed out)"""
        logger.info(f"Cleaning up stale pending entry {journal_id}")
        try:
            # Delete the journal entry
            self.journal.journal_table.delete_item(Key={'journal_id': journal_id})
            
            # Clean up any database records that might exist
            # self._cleanup_database_record(job_id)
            
        except Exception as e:
            logger.error(f"Failed to cleanup stale entry {journal_id}: {e}")
    
    def _complete_s3_upload_recovery(self, journal_id: str, job_id: str, job_data: Dict[str, Any]):
        """Complete S3 upload for recovered job"""
        logger.info(f"Completing S3 upload recovery for {journal_id}")
        try:
            # Generate and upload the image
            processor = StatelessJobProcessor(self.journal)
            s3_key = processor._generate_and_store_image(job_id, job_data)
            
            # Update job completion
            processor._update_job_completion(job_id, s3_key)
            
            # Complete journal entry
            self.journal.complete_journal_entry(journal_id)
            
        except Exception as e:
            logger.error(f"Failed to complete S3 upload recovery for {journal_id}: {e}")
            self.journal.update_journal_status(
                journal_id, 
                JournalStatus.FAILED,
                error_message=f"Recovery failed: {str(e)}"
            )
    
    def _cleanup_failed_operations(self, journal_id: str, job_id: str, operations: Dict[str, bool]):
        """Clean up partial operations from failed jobs"""
        logger.info(f"Cleaning up failed operations for {journal_id}")
        try:
            # If S3 upload was successful but database write failed, clean up S3
            if operations.get('s3_upload') and not operations.get('database_write'):
                s3_key = f"images/{job_id}.jpg"
                self.journal.s3.delete_object(Bucket='your-bucket-name', Key=s3_key)
            
            # If database write was successful but S3 upload failed, leave as-is
            # The database record shows the job as failed, which is correct
            
            # Mark journal as cleaning up, then completed
            self.journal.update_journal_status(journal_id, JournalStatus.CLEANING_UP)
            self.journal.complete_journal_entry(journal_id)
            
        except Exception as e:
            logger.error(f"Failed to cleanup failed operations for {journal_id}: {e}")


# Global instances for easy access
journal_service = None
recovery_service = None

def get_journal_service() -> JobProcessingJournal:
    """Get or create journal service instance"""
    global journal_service
    if journal_service is None:
        journal_service = JobProcessingJournal()
    return journal_service

def get_recovery_service() -> JournalRecoveryService:
    """Get or create recovery service instance"""
    global recovery_service
    if recovery_service is None:
        journal = get_journal_service()
        recovery_service = JournalRecoveryService(journal)
    return recovery_service