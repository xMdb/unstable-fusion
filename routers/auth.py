# GENERATIVE AI DISCLAIMER
#
# A portion of this code was generated with the assistance of generative AI. Any files that do not contain a disclaimer were either written by a human without AI assistance or generated with developer tooling such as Vite.

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordRequestForm
from database import SessionLocal
from models import TokenResponse
from auth import authenticate_user, create_jwt

router = APIRouter(prefix="/auth", tags=["authentication"])

@router.post("/token", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Authenticate user and return JWT token"""
    db = SessionLocal()
    try:
        user = authenticate_user(db, form_data.username, form_data.password)
        if not user:
            raise HTTPException(status_code=400, detail="Incorrect username or password")
        token = create_jwt(user)
        return {"access_token": token, "token_type": "bearer"}
    finally:
        db.close()