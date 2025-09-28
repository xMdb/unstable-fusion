# GENERATIVE AI DISCLAIMER
#
# A portion of this code was generated with the assistance of generative AI. Any files that do not contain a disclaimer were either written by a human without AI assistance or generated with developer tooling such as Vite.

import datetime
import hashlib
import jwt
from fastapi import HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from database import SessionLocal
from models import User
from config import JWT_SECRET, JWT_ALGORITHM, JWT_EXP_SECONDS, HARDCODED_USERS

# Password hashing with safer configuration
try:
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
except Exception as e:
    print(f"⚠ bcrypt initialization failed: {e}")
    print("ℹ Falling back to simpler password hashing")
    # Fallback to a simpler hash for development/testing
    pwd_context = None

def safe_hash_password(password: str) -> str:
    """Safely hash a password, handling bcrypt limitations"""
    if pwd_context is None:
        # Fallback to SHA-256 for development
        return hashlib.sha256(password.encode()).hexdigest()
    
    try:
        # Truncate password to 72 bytes for bcrypt compatibility
        if len(password.encode('utf-8')) > 72:
            password = password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
        return pwd_context.hash(password)
    except Exception as e:
        print(f"⚠ Password hashing failed: {e}")
        # Fallback to SHA-256
        return hashlib.sha256(password.encode()).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    if pwd_context is None:
        # Fallback verification
        return hashlib.sha256(plain_password.encode()).hexdigest() == hashed_password
    
    try:
        # Truncate password to 72 bytes for bcrypt compatibility
        if len(plain_password.encode('utf-8')) > 72:
            plain_password = plain_password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        print(f"⚠ Password verification failed: {e}")
        # Fallback verification
        return hashlib.sha256(plain_password.encode()).hexdigest() == hashed_password

# OAuth2 setup
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

def create_or_sync_hardcoded_users():
    """Create or update hardcoded users in the database"""
    db = SessionLocal()
    try:
        for username, data in HARDCODED_USERS.items():
            u = db.query(User).filter(User.username == username).first()
            if not u:
                u = User(
                    username=username, 
                    hashed_password=safe_hash_password(data["password"]), 
                    is_admin=data["is_admin"]
                )
                db.add(u)
                print(f"✓ Created user: {username}")
            else:
                # rehash password
                u.hashed_password = safe_hash_password(data["password"])
                u.is_admin = data["is_admin"]
                print(f"✓ Updated user: {username}")
        db.commit()
    finally:
        db.close()

def authenticate_user(db, username: str, password: str):
    """Authenticate a user with username and password"""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user

def create_jwt(user: User):
    """Create a JWT token for a user"""
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(seconds=JWT_EXP_SECONDS)
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token

def get_user_from_token(token: str = Depends(oauth2_scheme)):
    """Get user from JWT token dependency"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        uid = int(payload.get("sub"))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == uid).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    finally:
        db.close()

def verify_token_for_download(token: str):
    """Verify token for image download (used with query parameter)"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        uid = int(payload.get("sub"))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == uid).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    finally:
        db.close()