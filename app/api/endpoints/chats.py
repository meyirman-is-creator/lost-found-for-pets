from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_, desc, func, asc
from typing import Any, List
from app.api.dependencies import get_current_user, get_verified_user
from app.db.database import get_db
from app.models.models import Chat, ChatMessage, User, Pet, PetPhoto
from app.schemas.schemas import Chat as ChatSchema, ChatCreate, ChatMessage as ChatMessageSchema, ChatWithLastMessage, FirstMessageCreate
from datetime import datetime

router = APIRouter()


@router.get("", response_model=List[ChatWithLastMessage])
def get_user_chats(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    chats = db.query(Chat).filter(
        or_(
            Chat.user1_id == current_user.id,
            Chat.user2_id == current_user.id
        )
    ).order_by(Chat.updated_at.desc()).all()

    result = []
    for chat in chats:
        last_message = db.query(ChatMessage).filter(
            ChatMessage.chat_id == chat.id
        ).order_by(ChatMessage.created_at.desc()).first()

        unread_count = db.query(func.count(ChatMessage.id)).filter(
            ChatMessage.chat_id == chat.id,
            ChatMessage.sender_id != current_user.id,
            ChatMessage.is_read == False
        ).scalar()

        other_user_id = chat.user2_id if chat.user1_id == current_user.id else chat.user1_id

        other_user = db.query(User).filter(User.id == other_user_id).first()
        other_user_name = other_user.full_name if other_user else "Unknown User"

        pet_photo_url = None
        pet_name = None
        pet_status = None

        if chat.pet_id:
            pet = db.query(Pet).filter(Pet.id == chat.pet_id).options(joinedload(Pet.photos)).first()
            if pet:
                pet_name = pet.name
                pet_status = pet.status

                primary_photo = next((photo for photo in pet.photos if photo.is_primary), None)
                if primary_photo:
                    pet_photo_url = primary_photo.photo_url
                elif pet.photos:
                    pet_photo_url = pet.photos[0].photo_url

        chat_with_last = ChatWithLastMessage(
            id=chat.id,
            user1_id=chat.user1_id,
            user2_id=chat.user2_id,
            pet_id=chat.pet_id,
            created_at=chat.created_at,
            updated_at=chat.updated_at,
            last_message=last_message,
            unread_count=unread_count,
            pet_photo_url=pet_photo_url,
            pet_name=pet_name,
            pet_status=pet_status,
            other_user_name=other_user_name
        )
        result.append(chat_with_last)

    return result


@router.post("", response_model=ChatSchema)
def create_chat(
        chat_in: ChatCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    user2 = db.query(User).filter(User.id == chat_in.user2_id).first()
    if not user2:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if chat_in.pet_id:
        pet = db.query(Pet).filter(Pet.id == chat_in.pet_id).first()
        if not pet:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pet not found"
            )

    existing_chat_query = db.query(Chat).filter(
        or_(
            and_(Chat.user1_id == current_user.id, Chat.user2_id == chat_in.user2_id),
            and_(Chat.user1_id == chat_in.user2_id, Chat.user2_id == current_user.id)
        )
    )

    if chat_in.pet_id:
        existing_chat_query = existing_chat_query.filter(Chat.pet_id == chat_in.pet_id)

    existing_chat = existing_chat_query.first()

    if existing_chat:
        return existing_chat

    db_chat = Chat(
        user1_id=current_user.id,
        user2_id=chat_in.user2_id,
        pet_id=chat_in.pet_id
    )
    db.add(db_chat)
    db.commit()
    db.refresh(db_chat)

    return db_chat


@router.post("/pet/{pet_id}/message", response_model=dict)
def create_chat_and_send_first_message(
        pet_id: int,
        message_data: FirstMessageCreate = Body(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    pet = db.query(Pet).filter(Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pet not found"
        )

    if pet.owner_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create chat with yourself"
        )

    existing_chat = db.query(Chat).filter(
        or_(
            and_(Chat.user1_id == current_user.id, Chat.user2_id == pet.owner_id, Chat.pet_id == pet_id),
            and_(Chat.user1_id == pet.owner_id, Chat.user2_id == current_user.id, Chat.pet_id == pet_id)
        )
    ).first()

    if existing_chat:
        chat = existing_chat
    else:
        chat = Chat(
            user1_id=current_user.id,
            user2_id=pet.owner_id,
            pet_id=pet_id
        )
        db.add(chat)
        db.commit()
        db.refresh(chat)

    message = ChatMessage(
        chat_id=chat.id,
        sender_id=current_user.id,
        content=message_data.message,
        is_read=False
    )
    db.add(message)

    chat.updated_at = datetime.utcnow()
    db.add(chat)
    db.commit()

    return {
        "chat_id": chat.id,
        "message_id": message.id,
        "success": True,
        "message": "Chat created and first message sent successfully"
    }


@router.get("/{chat_id}", response_model=ChatSchema)
def get_chat(
        chat_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )

    if chat.user1_id != current_user.id and chat.user2_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )

    return chat


@router.get("/{chat_id}/messages", response_model=List[ChatMessageSchema])
def get_chat_messages(
        chat_id: int,
        skip: int = 0,
        limit: int = 100,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )

    if chat.user1_id != current_user.id and chat.user2_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )

    messages = db.query(ChatMessage).filter(
        ChatMessage.chat_id == chat_id
    ).order_by(ChatMessage.created_at.asc()).offset(skip).limit(limit).all()

    # Add whoid attribute to each message
    for message in messages:
        setattr(message, 'whoid', message.sender_id)

    db.query(ChatMessage).filter(
        ChatMessage.chat_id == chat_id,
        ChatMessage.sender_id != current_user.id,
        ChatMessage.is_read == False
    ).update({"is_read": True})
    db.commit()

    return messages


@router.delete("/{chat_id}", response_model=dict)
def delete_chat(
        chat_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )

    if chat.user1_id != current_user.id and chat.user2_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )

    db.delete(chat)
    db.commit()

    return {"message": "Chat deleted successfully"}