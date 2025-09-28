"""
Cognito authentication router for user management and authentication.

Provides endpoints for:
- User registration and email confirmation
- User login with JWT tokens
- MFA setup and verification
- User group management
- Federated authentication
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Optional, List
import logging
import time

print("⏳ Importing cognito_service...")
start_time = time.time()
from cognito_service import cognito_service
load_time = time.time() - start_time
print(f"✓ cognito_service imported ({load_time:.2f}s)")

print("⏳ Importing config...")
start_time = time.time()
from config import USE_COGNITO, COGNITO_DOMAIN
load_time = time.time() - start_time
print(f"✓ config imported ({load_time:.2f}s)")

logger = logging.getLogger(__name__)

# Security scheme for JWT tokens
security = HTTPBearer()

router = APIRouter(prefix="/auth", tags=["Authentication"])


def get_token_from_cookie_or_header(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = None):
    """
    Get token from either cookie or Authorization header.
    Prioritizes cookie over header for security.
    """
    # First try to get from cookie
    access_token = request.cookies.get("access_token")
    if access_token:
        return access_token
    
    # Fall back to Authorization header
    if credentials:
        return credentials.credentials
    
    return None


# Pydantic models
class SignUpRequest(BaseModel):
    username: str
    password: str
    email: EmailStr


class ConfirmSignUpRequest(BaseModel):
    username: str
    confirmation_code: str


class LoginRequest(BaseModel):
    username: str
    password: str


class MFAChallengeRequest(BaseModel):
    username: str
    session: str
    challenge_name: str
    mfa_code: str


class MFASetupResponse(BaseModel):
    secret_code: str
    qr_code_url: str
    message: str


class UserInfoResponse(BaseModel):
    username: str
    email: str
    email_verified: bool
    groups: List[str]
    mfa_enabled: bool
    user_status: str


class AuthResponse(BaseModel):
    access_token: str
    id_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"
    groups: List[str] = []


# Dependency to get current user from JWT token or cookie
async def get_current_user(request: Request):
    """Extract and verify user from JWT token (cookie or header)"""
    if not USE_COGNITO:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Cognito authentication not configured"
        )
    
    # Try to get credentials from header (optional)
    credentials = None
    try:
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            from fastapi.security.utils import get_authorization_scheme_param
            scheme, token = get_authorization_scheme_param(auth_header)
            if scheme.lower() == "bearer":
                credentials = HTTPAuthorizationCredentials(scheme=scheme, credentials=token)
    except:
        pass
    
    # Get token from cookie or header
    token = get_token_from_cookie_or_header(request, credentials)
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No authentication token provided",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    payload = await cognito_service.verify_jwt_token(token)
    
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return payload


# Dependency to require admin role
async def get_admin_user(current_user: dict = Depends(get_current_user)):
    """Require admin role"""
    user_groups = current_user.get('cognito:groups', [])
    if 'Admin' not in user_groups:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


@router.post("/signup", summary="Register new user")
async def sign_up(request: SignUpRequest):
    """
    Register a new user with email verification.
    
    - **username**: Unique username for the user
    - **password**: Password meeting security requirements
    - **email**: Email address for verification
    """
    if not USE_COGNITO:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Cognito authentication not configured"
        )
    
    result = await cognito_service.sign_up(
        username=request.username,
        password=request.password,
        email=request.email
    )
    
    if not result['success']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result['message']
        )
    
    return {
        "message": result['message'],
        "user_confirmed": result['user_confirmed']
    }


@router.post("/confirm", summary="Confirm user registration")
async def confirm_sign_up(request: ConfirmSignUpRequest):
    """
    Confirm user registration with verification code from email.
    
    - **username**: Username to confirm
    - **confirmation_code**: Verification code from email
    """
    if not USE_COGNITO:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Cognito authentication not configured"
        )
    
    result = await cognito_service.confirm_sign_up(
        username=request.username,
        confirmation_code=request.confirmation_code
    )
    
    if not result['success']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result['message']
        )
    
    return {"message": result['message']}


@router.post("/login", response_model=AuthResponse, summary="User login")
async def login(request: LoginRequest, response: Response):
    """
    Authenticate user and return JWT tokens.
    Also sets secure HTTP-only cookies for browser-based authentication.
    
    - **username**: Username or email
    - **password**: User password
    """
    if not USE_COGNITO:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Cognito authentication not configured"
        )
    
    result = await cognito_service.authenticate(
        username=request.username,
        password=request.password
    )
    
    if not result['success']:
        if 'challenge' in result:
            # MFA challenge required
            raise HTTPException(
                status_code=status.HTTP_202_ACCEPTED,
                detail=result,
                headers={"X-Challenge-Name": result['challenge']}
            )
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=result['message']
        )
    
    # Set secure HTTP-only cookies for tokens (same as OAuth callback)
    expires_in = result.get('expires_in', 3600)  # Default 1 hour
    
    # Set access token cookie
    response.set_cookie(
        key="access_token",
        value=result['access_token'],
        max_age=expires_in,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax"
    )
    
    # Set ID token cookie if available
    if result.get('id_token'):
        response.set_cookie(
            key="id_token",
            value=result['id_token'],
            max_age=expires_in,
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite="lax"
        )
    
    # Set refresh token cookie if available (longer expiry)
    if result.get('refresh_token'):
        response.set_cookie(
            key="refresh_token",
            value=result['refresh_token'],
            max_age=86400 * 30,  # 30 days
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite="lax"
        )

    return AuthResponse(
        access_token=result['access_token'],
        id_token=result['id_token'],
        refresh_token=result['refresh_token'],
        expires_in=result['expires_in'],
        groups=result['groups']
    )


@router.post("/mfa/challenge", response_model=AuthResponse, summary="Respond to MFA challenge")
async def mfa_challenge(request: MFAChallengeRequest):
    """
    Respond to MFA challenge with authenticator code.
    
    - **username**: Username
    - **session**: Challenge session from login response
    - **challenge_name**: Type of challenge (e.g., SOFTWARE_TOKEN_MFA)
    - **mfa_code**: Code from authenticator app
    """
    if not USE_COGNITO:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Cognito authentication not configured"
        )
    
    result = await cognito_service.respond_to_mfa_challenge(
        username=request.username,
        session=request.session,
        challenge_name=request.challenge_name,
        mfa_code=request.mfa_code
    )
    
    if not result['success']:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=result['message']
        )
    
    return AuthResponse(
        access_token=result['access_token'],
        id_token=result['id_token'],
        refresh_token=result['refresh_token'],
        expires_in=result['expires_in'],
        groups=result['groups']
    )


@router.post("/mfa/setup", summary="Setup MFA for user")
async def setup_mfa(current_user: dict = Depends(get_current_user)):
    """
    Initiate MFA setup for the current user.
    Returns secret code for authenticator app setup.
    """
    # Extract access token from the request (this is a simplified approach)
    # In a real implementation, you'd store the access token properly
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="MFA setup requires access token management - implement token storage"
    )


@router.post("/mfa/verify", summary="Verify MFA setup")
async def verify_mfa_setup(mfa_code: str, current_user: dict = Depends(get_current_user)):
    """
    Verify MFA setup with code from authenticator app.
    """
    # Similar to setup_mfa, requires proper access token management
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="MFA verification requires access token management - implement token storage"
    )


@router.get("/me", response_model=UserInfoResponse, summary="Get current user info")
async def get_me(current_user: dict = Depends(get_current_user), response: Response = None):
    """
    Get current user information from JWT token.
    """
    # Add cache-busting headers to prevent browser caching issues
    if response:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache" 
        response.headers["Expires"] = "0"
    
    return UserInfoResponse(
        username=current_user.get('cognito:username', ''),
        email=current_user.get('email', ''),
        email_verified=current_user.get('email_verified', False),
        groups=current_user.get('cognito:groups', []),
        mfa_enabled=False,  # Would need access token to check properly
        user_status='CONFIRMED'  # Simplified
    )


@router.get("/federated/google", summary="Google OAuth login")
async def google_oauth():
    """
    Redirect to Google OAuth for federated authentication.
    """
    if not USE_COGNITO:
        return {
            "error": "Cognito authentication not configured",
            "status": "disabled",
            "message": "Please configure AWS Cognito to enable federated authentication"
        }
    
    if not COGNITO_DOMAIN:
        return {
            "error": "Cognito domain not configured",
            "status": "misconfigured", 
            "message": "Please set COGNITO_DOMAIN environment variable"
        }
    
    # Construct Google OAuth URL
    oauth_url = (
        f"https://{COGNITO_DOMAIN}.auth.{cognito_service.region}.amazoncognito.com/oauth2/authorize"
        f"?client_id={cognito_service.client_id}"
        f"&response_type=code"
        f"&scope=email+openid+profile"
        f"&redirect_uri=http://localhost:3001/auth/callback"
        f"&identity_provider=Google"
    )
    
    return {"oauth_url": oauth_url}


@router.get("/callback", summary="OAuth callback")
async def oauth_callback(code: str, response: Response):
    """
    Handle OAuth callback from federated identity provider.
    Exchange authorization code for tokens and set secure cookies.
    """
    if not USE_COGNITO:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Cognito authentication not configured"
        )
    
    # Exchange authorization code for tokens
    redirect_uri = "http://localhost:3001/auth/callback"
    token_result = await cognito_service.exchange_code_for_tokens(code, redirect_uri)
    
    if not token_result or not token_result.get('success'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to exchange authorization code for tokens"
        )
    
    # Set secure HTTP-only cookies for tokens
    expires_in = token_result.get('expires_in', 3600)  # Default 1 hour
    
    # Set access token cookie
    response.set_cookie(
        key="access_token",
        value=token_result['access_token'],
        max_age=expires_in,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax"
    )
    
    # Set ID token cookie if available
    if token_result.get('id_token'):
        response.set_cookie(
            key="id_token",
            value=token_result['id_token'],
            max_age=expires_in,
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite="lax"
        )
    
    # Set refresh token cookie if available (longer expiry)
    if token_result.get('refresh_token'):
        response.set_cookie(
            key="refresh_token",
            value=token_result['refresh_token'],
            max_age=86400 * 30,  # 30 days
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite="lax"
        )
    
    # Redirect back to the main page after successful authentication
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/", status_code=303)


@router.post("/logout", summary="Logout user")
async def logout(response: Response):
    """
    Logout user by clearing authentication cookies.
    """
    # Clear all authentication cookies
    response.delete_cookie(key="access_token", httponly=True, samesite="lax")
    response.delete_cookie(key="id_token", httponly=True, samesite="lax")
    response.delete_cookie(key="refresh_token", httponly=True, samesite="lax")
    
    return {"message": "Logged out successfully"}


# Admin endpoints
@router.post("/admin/add-user-to-group", summary="Add user to group (Admin only)")
async def add_user_to_group(username: str, group_name: str, 
                           admin_user: dict = Depends(get_admin_user)):
    """
    Add a user to a group (Admin only).
    
    - **username**: Username to add to group
    - **group_name**: Group name (Admin or User)
    """
    if group_name not in ['Admin', 'User']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid group name. Must be 'Admin' or 'User'"
        )
    
    success = await cognito_service.add_user_to_group(username, group_name)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to add user to group"
        )
    
    return {"message": f"User {username} added to group {group_name}"}


@router.delete("/admin/remove-user-from-group", summary="Remove user from group (Admin only)")
async def remove_user_from_group(username: str, group_name: str,
                                admin_user: dict = Depends(get_admin_user)):
    """
    Remove a user from a group (Admin only).
    
    - **username**: Username to remove from group
    - **group_name**: Group name (Admin or User)
    """
    success = await cognito_service.remove_user_from_group(username, group_name)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to remove user from group"
        )
    
    return {"message": f"User {username} removed from group {group_name}"}


@router.get("/health", summary="Authentication service health check")
async def health_check():
    """Check if Cognito authentication is properly configured."""
    return {
        "cognito_enabled": USE_COGNITO,
        "user_pool_configured": bool(cognito_service.user_pool_id),
        "client_configured": bool(cognito_service.client_id),
        "status": "healthy" if USE_COGNITO else "disabled"
    }