from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, desc, func
from typing import Any, List
from app.api.dependencies import get_current_user, get_verified_user
from app.db.database import get_db
from app.models.models import Chat, ChatMessage, User, Pet
from app.schemas.schemas import Chat as ChatSchema, ChatCreate, ChatMessage as ChatMessageSchema, ChatWithLastMessage

router = APIRouter()


@router.get("", response_model=List[ChatWithLastMessage])
def get_user_chats(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    """
    Get all chats for the current user with last message and unread count
    """
    # Найти все чаты пользователя
    chats = db.query(Chat).filter(
        or_(
            Chat.user1_id == current_user.id,
            Chat.user2_id == current_user.id
        )
    ).order_by(Chat.updated_at.desc()).all()

    result = []
    for chat in chats:
        # Получить последнее сообщение для чата
        last_message = db.query(ChatMessage).filter(
            ChatMessage.chat_id == chat.id
        ).order_by(ChatMessage.created_at.desc()).first()

        # Получить количество непрочитанных сообщений
        unread_count = db.query(func.count(ChatMessage.id)).filter(
            ChatMessage.chat_id == chat.id,
            ChatMessage.sender_id != current_user.id,
            ChatMessage.is_read == False
        ).scalar()

        # Создать объект с чатом, последним сообщением и счетчиком непрочитанных
        chat_with_last = ChatWithLastMessage(
            id=chat.id,
            user1_id=chat.user1_id,
            user2_id=chat.user2_id,
            pet_id=chat.pet_id,
            created_at=chat.created_at,
            updated_at=chat.updated_at,
            last_message=last_message,
            unread_count=unread_count
        )
        result.append(chat_with_last)

    return result


@router.post("", response_model=ChatSchema)
def create_chat(
        chat_in: ChatCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    """
    Create a new chat with another user
    """
    # Проверяем существование второго пользователя
    user2 = db.query(User).filter(User.id == chat_in.user2_id).first()
    if not user2:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Проверяем, существует ли уже чат между этими пользователями
    existing_chat = db.query(Chat).filter(
        or_(
            and_(Chat.user1_id == current_user.id, Chat.user2_id == chat_in.user2_id),
            and_(Chat.user1_id == chat_in.user2_id, Chat.user2_id == current_user.id)
        )
    )

    # Если указан питомец, то проверяем и его
    if chat_in.pet_id:
        pet = db.query(Pet).filter(Pet.id == chat_in.pet_id).first()
        if not pet:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pet not found"
            )

        # Уточняем поиск существующего чата с учетом питомца
        existing_chat = existing_chat.filter(Chat.pet_id == chat_in.pet_id)

    existing_chat = existing_chat.first()

    if existing_chat:
        return existing_chat

    # Создаем новый чат
    db_chat = Chat(
        user1_id=current_user.id,
        user2_id=chat_in.user2_id,
        pet_id=chat_in.pet_id
    )
    db.add(db_chat)
    db.commit()
    db.refresh(db_chat)

    return db_chat


@router.get("/{chat_id}", response_model=ChatSchema)
def get_chat(
        chat_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    """
    Get a specific chat
    """
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )

    # Проверка, что пользователь имеет доступ к чату
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
    """
    Get messages from a specific chat
    """
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )

    # Проверка, что пользователь имеет доступ к чату
    if chat.user1_id != current_user.id and chat.user2_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )

    # Получение сообщений
    messages = db.query(ChatMessage).filter(
        ChatMessage.chat_id == chat_id
    ).order_by(ChatMessage.created_at.desc()).offset(skip).limit(limit).all()

    # Отметить все сообщения от другого пользователя как прочитанные
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
    """
    Delete a chat
    """
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )

    # Проверка, что пользователь имеет доступ к чату
    if chat.user1_id != current_user.id and chat.user2_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )

    # Удаление чата (каскадное удаление сообщений настроено в модели)
    db.delete(chat)
    db.commit()

    return {"message": "Chat deleted successfully"}