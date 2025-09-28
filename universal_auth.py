"""
Universal Authentication Module

Provides a unified authentication dependency that works with both:
1. Legacy JWT authentication system (auth.py)
2. New AWS Cognito authentication system (cognito_auth.py)

This allows for gradual migration while maintaining backward compatibility.
"""

from fastapi import Depends, Request, HTTPException, status
from typing import Union, Optional
from config import USE_COGNITO
import logging

logger = logging.getLogger(__name__)

# Import authentication systems
from auth import get_user_from_token, oauth2_scheme
from models import User

# Conditionally import Cognito auth if available
try:
    if USE_COGNITO:
        from routers.cognito_auth import get_current_user as get_cognito_user
        COGNITO_AVAILABLE = True
    else:
        COGNITO_AVAILABLE = False
except ImportError:
    COGNITO_AVAILABLE = False
    logger.warning("Cognito authentication not available")


class UniversalUser:
    """Unified user object that works for both auth systems"""
    
    def __init__(self, legacy_user: Optional[User] = None, cognito_user: Optional[dict] = None):
        from database import SessionLocal
        
        self.legacy_user = legacy_user
        self.cognito_user = cognito_user
        
        if legacy_user:
            self.id = legacy_user.id
            self.username = legacy_user.username
            self.is_admin = getattr(legacy_user, 'is_admin', False)
            self.auth_type = 'legacy'
            self.cognito_sub = None
        elif cognito_user:
            # Extract user info from Cognito JWT payload
            self.cognito_sub = cognito_user.get('sub')  # Cognito user ID (UUID)
            self.username = cognito_user.get('cognito:username', cognito_user.get('username'))
            # Check if user is in Admin group
            groups = cognito_user.get('cognito:groups', [])
            self.is_admin = 'Admin' in groups
            self.auth_type = 'cognito'
            
            # For Cognito users, try to find or create a corresponding database user
            self.id = self._get_or_create_db_user_id()
        else:
            raise ValueError("Either legacy_user or cognito_user must be provided")
    
    def _get_or_create_db_user_id(self) -> int:
        """Get or create a database user ID for Cognito users"""
        from database import SessionLocal
        
        db = SessionLocal()
        try:
            # Try to find existing user by username
            existing_user = db.query(User).filter(User.username == self.username).first()
            if existing_user:
                return existing_user.id
            
            # Create new user for Cognito user
            # Use a placeholder password since Cognito handles authentication
            new_user = User(
                username=self.username,
                hashed_password="cognito_managed",  # Placeholder
                is_admin=self.is_admin
            )
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            logger.info(f"Created database user for Cognito user: {self.username} (ID: {new_user.id})")
            return new_user.id
        finally:
            db.close()
    
    def __repr__(self):
        return f"UniversalUser(id={self.id}, username={self.username}, auth_type={self.auth_type})"


async def get_current_user_universal(request: Request) -> UniversalUser:
    """
    Universal authentication dependency that supports both legacy and Cognito auth.
    
    Priority order:
    1. Try Cognito authentication (if available and cookies present)
    2. Fall back to legacy JWT authentication (if Authorization header present)
    """
    
    # Try Cognito authentication first if available
    if COGNITO_AVAILABLE and USE_COGNITO:
        try:
            # Check if we have Cognito cookies
            access_token = request.cookies.get("access_token")
            if access_token:
                cognito_user = await get_cognito_user(request)
                return UniversalUser(cognito_user=cognito_user)
        except HTTPException as e:
            # If Cognito auth fails with 401, try legacy auth
            if e.status_code != 401:
                raise
            logger.debug("Cognito authentication failed, trying legacy auth")
        except Exception as e:
            logger.warning(f"Cognito authentication error: {e}")
    
    # Try legacy authentication
    try:
        # Check if we have Authorization header
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            legacy_user = get_user_from_token(token)
            return UniversalUser(legacy_user=legacy_user)
    except HTTPException as e:
        if e.status_code != 401:
            raise
        logger.debug("Legacy authentication failed")
    except Exception as e:
        logger.warning(f"Legacy authentication error: {e}")
    
    # If both authentication methods fail, raise 401
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Please provide valid credentials via cookie (Cognito) or Authorization header (Legacy).",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user_universal_sync(token: str = Depends(oauth2_scheme)) -> UniversalUser:
    """
    Synchronous version for legacy compatibility.
    Only supports legacy JWT authentication.
    """
    legacy_user = get_user_from_token(token)
    return UniversalUser(legacy_user=legacy_user)


# Optional: Admin-only dependency
async def get_admin_user_universal(current_user: UniversalUser = Depends(get_current_user_universal)) -> UniversalUser:
    """Require admin privileges"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user