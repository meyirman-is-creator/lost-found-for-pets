from fastapi import APIRouter, Depends, HTTPException, status, Body
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
from app.schemas.schemas import UserCreate, Token, VerificationRequest, Login, ResendVerificationRequest
from app.services.email_service import email_service
from typing import Any
from datetime import datetime
from pydantic import ValidationError
import logging

router = APIRouter(prefix="/auth", tags=["authentication"])
logger = logging.getLogger(__name__)


@router.post("/register", response_model=dict)
def register(user_in: UserCreate, db: Session = Depends(get_db)) -> Any:
    """
    Register a new user with comprehensive validation
    """
    try:
        # Normalize email to lowercase
        user_in.email = user_in.email.lower().strip()

        # Check if user already exists with more detailed error
        db_user = db.query(User).filter(User.email == user_in.email).first()
        if db_user:
            if db_user.is_verified:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "email_exists",
                        "message": "An account with this email already exists"
                    }
                )
            else:
                # User exists but not verified - could allow resending verification
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "email_exists_unverified",
                        "message": "An account with this email exists but is not verified. Please check your email for verification code."
                    }
                )

        # Check if phone number is already used
        if user_in.phone:
            phone_user = db.query(User).filter(User.phone == user_in.phone).first()
            if phone_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "phone_exists",
                        "message": "This phone number is already registered"
                    }
                )

        # Create new user
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

        # Generate verification code
        verification_code = generate_verification_code()
        expires_at = create_verification_token_expiry()

        # Save verification code to database
        db_verification = VerificationCode(
            user_id=db_user.id,
            code=verification_code,
            expires_at=expires_at
        )
        db.add(db_verification)
        db.commit()

        # Send verification email
        try:
            email_service.send_verification_email(db_user.email, verification_code)
            logger.info(f"Verification email sent to {db_user.email}")
        except Exception as e:
            logger.error(f"Failed to send verification email: {e}")
            # Don't fail registration if email sending fails
            # User can request resend later

        return {
            "success": True,
            "message": "Registration successful. Please check your email for verification code.",
            "email": db_user.email
        }

    except ValidationError as e:
        # Handle Pydantic validation errors
        errors = []
        for error in e.errors():
            field = error['loc'][0] if error['loc'] else 'unknown'
            message = error['msg']
            errors.append({"field": field, "message": message})

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "validation_error",
                "message": "Validation failed",
                "errors": errors
            }
        )
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "server_error",
                "message": "An unexpected error occurred during registration"
            }
        )


@router.post("/verify", response_model=dict)
def verify_email(verification_data: VerificationRequest, db: Session = Depends(get_db)) -> Any:
    """
    Verify user email with code
    """
    try:
        # Normalize email
        verification_data.email = verification_data.email.lower().strip()

        # Find user by email
        user = db.query(User).filter(User.email == verification_data.email).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "user_not_found",
                    "message": "No account found with this email address"
                }
            )

        if user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "already_verified",
                    "message": "This email is already verified"
                }
            )

        # Find valid verification code
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
            # Check if code exists but is expired
            expired_code = (
                db.query(VerificationCode)
                .filter(
                    VerificationCode.user_id == user.id,
                    VerificationCode.code == verification_data.code,
                    VerificationCode.is_used == False
                )
                .first()
            )

            if expired_code:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "code_expired",
                        "message": "This verification code has expired. Please request a new one."
                    }
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "invalid_code",
                        "message": "Invalid verification code. Please check and try again."
                    }
                )

        # Mark user as verified
        user.is_verified = True

        # Mark verification code as used
        verification.is_used = True

        db.commit()

        return {
            "success": True,
            "message": "Email verified successfully. You can now log in."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Verification error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "server_error",
                "message": "An unexpected error occurred during verification"
            }
        )


@router.post("/login", response_model=Token)
def login(login_data: Login, db: Session = Depends(get_db)) -> Any:
    """
    Login with email and password, get an access token for future requests
    """
    try:
        # Normalize email
        login_data.email = login_data.email.lower().strip()

        user = db.query(User).filter(User.email == login_data.email).first()

        # Don't reveal if email exists or not for security
        if not user or not verify_password(login_data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "invalid_credentials",
                    "message": "Invalid email or password"
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check if user is active
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "account_inactive",
                    "message": "Your account has been deactivated. Please contact support."
                }
            )

        # Check if user is verified
        if not user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "email_not_verified",
                    "message": "Please verify your email before logging in. Check your email for the verification code."
                }
            )

        # Create access token
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.email}, expires_delta=access_token_expires
        )

        # Update last login time
        user.last_active_at = datetime.utcnow()
        db.commit()

        return {"access_token": access_token, "token_type": "bearer"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "server_error",
                "message": "An unexpected error occurred during login"
            }
        )


@router.post("/resend-verification", response_model=dict)
def resend_verification(request: ResendVerificationRequest, db: Session = Depends(get_db)) -> Any:
    """
    Resend verification code
    """
    try:
        # Normalize email
        email = request.email.lower().strip()

        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "user_not_found",
                    "message": "No account found with this email address"
                }
            )

        if user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "already_verified",
                    "message": "This email is already verified"
                }
            )

        # Check for recent verification codes to prevent spam
        recent_code = (
            db.query(VerificationCode)
            .filter(
                VerificationCode.user_id == user.id,
                VerificationCode.created_at > datetime.utcnow() - timedelta(minutes=1),
                VerificationCode.is_used == False
            )
            .first()
        )

        if recent_code:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "too_many_requests",
                    "message": "Please wait a minute before requesting a new verification code"
                }
            )

        # Invalidate old unused codes
        db.query(VerificationCode).filter(
            VerificationCode.user_id == user.id,
            VerificationCode.is_used == False
        ).update({"is_used": True})

        # Generate new verification code
        verification_code = generate_verification_code()
        expires_at = create_verification_token_expiry()

        # Save verification code to database
        db_verification = VerificationCode(
            user_id=user.id,
            code=verification_code,
            expires_at=expires_at
        )
        db.add(db_verification)
        db.commit()

        # Send verification email
        try:
            email_service.send_verification_email(user.email, verification_code)
            logger.info(f"Verification email resent to {user.email}")
        except Exception as e:
            logger.error(f"Failed to send verification email: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "email_error",
                    "message": "Failed to send verification email. Please try again later."
                }
            )

        return {
            "success": True,
            "message": "Verification code sent successfully. Please check your email."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Resend verification error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "server_error",
                "message": "An unexpected error occurred"
            }
        )