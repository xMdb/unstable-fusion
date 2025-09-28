# GENERATIVE AI DISCLAIMER
#
# A portion of this code was generated with the assistance of generative AI. Any files that do not contain a disclaimer were either written by a human without AI assistance or generated with developer tooling such as Vite.

"""
Database migration script to add S3 support to the images table.

This script adds the s3_key column to the images table and makes the path column nullable
to support both S3 and local storage.

Run this script once before deploying the updated application.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from database import SessionLocal, engine
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_database():
    """Apply database migration to add S3 support"""
    
    migrations = [
        {
            "name": "Add s3_key column to images table",
            "sql": "ALTER TABLE images ADD COLUMN s3_key VARCHAR(1024) NULL"
        },
        {
            "name": "Make path column nullable in images table",
            "sql": "ALTER TABLE images ALTER COLUMN path DROP NOT NULL"
        }
    ]
    
    db = SessionLocal()
    try:
        for migration in migrations:
            try:
                logger.info(f"Applying migration: {migration['name']}")
                db.execute(text(migration['sql']))
                db.commit()
                logger.info(f"Successfully applied: {migration['name']}")
                
            except Exception as e:
                # Check if the error is because the column already exists
                error_msg = str(e).lower()
                if "duplicate column name" in error_msg or "already exists" in error_msg:
                    logger.info(f"Migration already applied: {migration['name']}")
                elif "unknown column" in error_msg and "modify" in migration['sql'].lower():
                    logger.info(f"Column already nullable: {migration['name']}")
                else:
                    logger.error(f"Error applying migration {migration['name']}: {e}")
                    raise
                    
                db.rollback()
    
    finally:
        db.close()

if __name__ == "__main__":
    logger.info("Starting database migration for S3 support...")
    try:
        migrate_database()
        logger.info("Database migration completed successfully!")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)