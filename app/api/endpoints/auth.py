from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from app.core.config import settings
from app.core.security import (
    create_access_token,
    verify_password,
    get_password_hash,
    generate_verification_code,
    create_verification_token_expiry
)
from app.db.database import get_db
from app.models.models import User, VerificationCode
from app.schemas.schemas import UserCreate, Token, VerificationRequest, Login, TokenWithUser
from app.services.email_service import email_service
from typing import Any
from datetime import datetime

router = APIRouter()


@router.post("/register", response_model=dict)
def register(user_in: UserCreate, db: Session = Depends(get_db)) -> Any:
    db_user = db.query(User).filter(User.email == user_in.email).first()
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    hashed_password = get_password_hash(user_in.password)
    db_user = User(
        email=user_in.email,
        hashed_password=hashed_password,
        full_name=user_in.full_name,
        phone=user_in.phone,
        is_active=True,
        is_verified=False
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    verification_code = generate_verification_code()
    expires_at = create_verification_token_expiry()

    db_verification = VerificationCode(
        user_id=db_user.id,
        code=verification_code,
        expires_at=expires_at
    )
    db.add(db_verification)
    db.commit()

    email_service.send_verification_email(db_user.email, verification_code)

    return {"message": "User registered successfully. Please check your email for verification code."}


@router.post("/verify", response_model=dict)
def verify_email(verification_data: VerificationRequest, db: Session = Depends(get_db)) -> Any:
    user = db.query(User).filter(User.email == verification_data.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    verification = (
        db.query(VerificationCode)
        .filter(
            VerificationCode.user_id == user.id,
            VerificationCode.is_used == False,
            VerificationCode.code == verification_data.code,
            VerificationCode.expires_at > datetime.utcnow()
        )
        .first()
    )

    if not verification:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code"
        )

    user.is_verified = True
    verification.is_used = True

    db.commit()

    return {"message": "Email verified successfully"}


@router.post("/login", response_model=TokenWithUser)
def login(login_data: Login, db: Session = Depends(get_db)) -> Any:
    user = db.query(User).filter(User.email == login_data.email).first()
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer", "user_id": user.id}


@router.post("/resend-verification", response_model=dict)
def resend_verification(email: str, db: Session = Depends(get_db)) -> Any:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already verified"
        )

    verification_code = generate_verification_code()
    expires_at = create_verification_token_expiry()

    db_verification = VerificationCode(
        user_id=user.id,
        code=verification_code,
        expires_at=expires_at
    )
    db.add(db_verification)
    db.commit()

    email_service.send_verification_email(user.email, verification_code)

    return {"message": "Verification code sent successfully"}