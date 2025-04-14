from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_user, get_verified_user
from app.core.security import get_password_hash
from app.db.database import get_db
from app.models.models import User
from app.schemas.schemas import User as UserSchema, UserUpdate
from typing import Any

router = APIRouter()


@router.get("/me", response_model=UserSchema)
def read_user_me(current_user: User = Depends(get_current_user)) -> Any:
    """
    Get current user
    """
    return current_user


@router.put("/me", response_model=UserSchema)
def update_user_me(
        user_in: UserUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
) -> Any:
    """
    Update current user
    """
    # Update user fields
    if user_in.full_name is not None:
        current_user.full_name = user_in.full_name
    if user_in.phone is not None:
        current_user.phone = user_in.phone
    if user_in.password is not None:
        current_user.hashed_password = get_password_hash(user_in.password)

    db.add(current_user)
    db.commit()
    db.refresh(current_user)

    return current_user


@router.delete("/me", response_model=dict)
def delete_user_me(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
) -> Any:
    """
    Delete current user
    """
    db.delete(current_user)
    db.commit()

    return {"message": "User deleted successfully"}