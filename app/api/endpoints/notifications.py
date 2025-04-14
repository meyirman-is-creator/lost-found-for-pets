from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Any, List
from app.api.dependencies import get_current_user, get_verified_user
from app.db.database import get_db
from app.models.models import Notification, User, PetMatch, Pet
from app.schemas.schemas import Notification as NotificationSchema
from sqlalchemy.orm import joinedload

router = APIRouter()


@router.get("", response_model=List[NotificationSchema])
def get_notifications(
        skip: int = 0,
        limit: int = 100,
        unread_only: bool = False,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    """
    Get user notifications
    """
    query = db.query(Notification).filter(Notification.user_id == current_user.id)

    if unread_only:
        query = query.filter(Notification.is_read == False)

    notifications = (
        query
        .options(joinedload(Notification.match))
        .order_by(Notification.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return notifications


@router.get("/{notification_id}", response_model=NotificationSchema)
def get_notification(
        notification_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    """
    Get a specific notification
    """
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == current_user.id)
        .options(joinedload(Notification.match))
        .first()
    )

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )

    return notification


@router.patch("/{notification_id}/mark-read", response_model=NotificationSchema)
def mark_notification_read(
        notification_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    """
    Mark a notification as read
    """
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == current_user.id)
        .first()
    )

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )

    notification.is_read = True
    db.add(notification)
    db.commit()
    db.refresh(notification)

    return notification


@router.patch("/mark-all-read", response_model=dict)
def mark_all_notifications_read(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    """
    Mark all notifications as read
    """
    db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    ).update({"is_read": True})

    db.commit()

    return {"message": "All notifications marked as read"}


@router.delete("/{notification_id}", response_model=dict)
def delete_notification(
        notification_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    """
    Delete a notification
    """
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == current_user.id)
        .first()
    )

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )

    db.delete(notification)
    db.commit()

    return {"message": "Notification deleted successfully"}