from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_, desc, func, asc
from typing import Any, List
from app.api.dependencies import get_current_user, get_verified_user
from app.db.database import get_db
from app.models.models import Chat, ChatMessage, User, Pet, PetPhoto
from app.schemas.schemas import Chat as ChatSchema, ChatCreate, ChatMessage as ChatMessageSchema, ChatWithLastMessage, \
    FirstMessageCreate
from datetime import datetime
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("", response_model=List[ChatWithLastMessage])
def get_user_chats(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    logger.info(f"=== GET CHATS REQUEST ===")
    logger.info(f"User ID: {current_user.id}, Email: {current_user.email}")

    try:
        chats = db.query(Chat).filter(
            or_(
                Chat.user1_id == current_user.id,
                Chat.user2_id == current_user.id
            )
        ).order_by(Chat.updated_at.desc()).all()

        logger.info(f"Found {len(chats)} chats for user {current_user.id}")

        result = []
        for chat in chats:
            logger.debug(f"Processing chat ID: {chat.id}, user1: {chat.user1_id}, user2: {chat.user2_id}")

            last_message = db.query(ChatMessage).filter(
                ChatMessage.chat_id == chat.id
            ).order_by(ChatMessage.created_at.desc()).first()

            if last_message:
                logger.debug(
                    f"Last message in chat {chat.id}: '{last_message.content[:50]}...' from user {last_message.sender_id}")

            unread_count = db.query(func.count(ChatMessage.id)).filter(
                ChatMessage.chat_id == chat.id,
                ChatMessage.sender_id != current_user.id,
                ChatMessage.is_read == False
            ).scalar()

            logger.debug(f"Unread count for chat {chat.id}: {unread_count}")

            other_user_id = chat.user2_id if chat.user1_id == current_user.id else chat.user1_id
            logger.debug(f"Other user ID in chat {chat.id}: {other_user_id}")

            other_user = db.query(User).filter(User.id == other_user_id).first()
            other_user_name = other_user.full_name if other_user and other_user.full_name else f"User {other_user_id}"
            logger.debug(f"Other user name: {other_user_name}")

            pet_photo_url = None
            pet_name = None
            pet_status = None

            if chat.pet_id:
                logger.debug(f"Chat {chat.id} has pet_id: {chat.pet_id}")
                pet = db.query(Pet).filter(Pet.id == chat.pet_id).options(joinedload(Pet.photos)).first()
                if pet:
                    pet_name = pet.name
                    pet_status = pet.status
                    logger.debug(f"Pet found: name={pet_name}, status={pet_status}")

                    primary_photo = next((photo for photo in pet.photos if photo.is_primary), None)
                    if primary_photo:
                        pet_photo_url = primary_photo.photo_url
                        logger.debug(f"Primary photo URL: {pet_photo_url}")
                    elif pet.photos:
                        pet_photo_url = pet.photos[0].photo_url
                        logger.debug(f"Using first photo URL: {pet_photo_url}")

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

        logger.info(f"Successfully prepared {len(result)} chats for response")
        return result

    except Exception as e:
        logger.error(f"Error getting chats: {e}", exc_info=True)
        raise


@router.post("", response_model=ChatSchema)
def create_chat(
        chat_in: ChatCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    logger.info(f"=== CREATE CHAT REQUEST ===")
    logger.info(f"Current user: {current_user.id}, Target user: {chat_in.user2_id}, Pet ID: {chat_in.pet_id}")

    try:
        user2 = db.query(User).filter(User.id == chat_in.user2_id).first()
        if not user2:
            logger.warning(f"User {chat_in.user2_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        logger.debug(f"Target user found: {user2.email}")

        if chat_in.pet_id:
            pet = db.query(Pet).filter(Pet.id == chat_in.pet_id).first()
            if not pet:
                logger.warning(f"Pet {chat_in.pet_id} not found")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Pet not found"
                )
            logger.debug(f"Pet found: {pet.name}")

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
            logger.info(f"Chat already exists with ID: {existing_chat.id}")
            return existing_chat

        db_chat = Chat(
            user1_id=current_user.id,
            user2_id=chat_in.user2_id,
            pet_id=chat_in.pet_id
        )
        db.add(db_chat)
        db.commit()
        db.refresh(db_chat)

        logger.info(f"New chat created with ID: {db_chat.id}")
        return db_chat

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating chat: {e}", exc_info=True)
        db.rollback()
        raise


@router.post("/pet/{pet_id}/message", response_model=dict)
def create_chat_and_send_first_message(
        pet_id: int,
        message_data: FirstMessageCreate = Body(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    logger.info(f"=== CREATE CHAT WITH FIRST MESSAGE ===")
    logger.info(f"User: {current_user.id}, Pet: {pet_id}, Message: '{message_data.message[:50]}...'")

    try:
        pet = db.query(Pet).filter(Pet.id == pet_id).first()
        if not pet:
            logger.warning(f"Pet {pet_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pet not found"
            )
        logger.debug(f"Pet found: {pet.name}, Owner: {pet.owner_id}")

        if pet.owner_id == current_user.id:
            logger.warning(f"User {current_user.id} trying to create chat with themselves")
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
            logger.info(f"Using existing chat ID: {chat.id}")
        else:
            chat = Chat(
                user1_id=current_user.id,
                user2_id=pet.owner_id,
                pet_id=pet_id
            )
            db.add(chat)
            db.commit()
            db.refresh(chat)
            logger.info(f"Created new chat ID: {chat.id}")

        message = ChatMessage(
            chat_id=chat.id,
            sender_id=current_user.id,
            content=message_data.message,
            is_read=False
        )
        db.add(message)
        logger.debug(f"Adding message to chat {chat.id}: '{message.content[:50]}...'")

        chat.updated_at = datetime.utcnow()
        db.add(chat)
        db.commit()

        logger.info(f"Successfully created chat {chat.id} with first message ID: {message.id}")

        return {
            "chat_id": chat.id,
            "message_id": message.id,
            "success": True,
            "message": "Chat created and first message sent successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating chat with message: {e}", exc_info=True)
        db.rollback()
        raise


@router.get("/{chat_id}", response_model=ChatSchema)
def get_chat(
        chat_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    logger.info(f"=== GET CHAT DETAILS ===")
    logger.info(f"Chat ID: {chat_id}, User ID: {current_user.id}")

    try:
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if not chat:
            logger.warning(f"Chat {chat_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat not found"
            )

        logger.debug(f"Chat found: user1={chat.user1_id}, user2={chat.user2_id}")

        if chat.user1_id != current_user.id and chat.user2_id != current_user.id:
            logger.warning(f"User {current_user.id} doesn't have access to chat {chat_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions"
            )

        other_user_id = chat.user2_id if chat.user1_id == current_user.id else chat.user1_id
        logger.debug(f"Other user in chat: {other_user_id}")

        other_user = db.query(User).filter(User.id == other_user_id).first()

        chat_dict = {
            "id": chat.id,
            "user1_id": chat.user1_id,
            "user2_id": chat.user2_id,
            "pet_id": chat.pet_id,
            "created_at": chat.created_at,
            "updated_at": chat.updated_at,
            "other_user_name": other_user.full_name if other_user and other_user.full_name else f"User {other_user_id}"
        }

        logger.debug(f"Other user name: {chat_dict['other_user_name']}")

        if chat.pet_id:
            pet = db.query(Pet).filter(Pet.id == chat.pet_id).first()
            if pet:
                chat_dict["pet_name"] = pet.name
                chat_dict["pet_status"] = pet.status
                logger.debug(f"Pet info: name={pet.name}, status={pet.status}")

        logger.info(f"Successfully retrieved chat {chat_id} details")
        return chat_dict

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting chat details: {e}", exc_info=True)
        raise


@router.get("/{chat_id}/messages", response_model=List[ChatMessageSchema])
def get_chat_messages(
        chat_id: int,
        skip: int = 0,
        limit: int = 100,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    logger.info(f"=== GET CHAT MESSAGES ===")
    logger.info(f"Chat ID: {chat_id}, User ID: {current_user.id}, Skip: {skip}, Limit: {limit}")

    try:
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if not chat:
            logger.warning(f"Chat {chat_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat not found"
            )

        if chat.user1_id != current_user.id and chat.user2_id != current_user.id:
            logger.warning(f"User {current_user.id} doesn't have access to chat {chat_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions"
            )

        messages = db.query(ChatMessage).filter(
            ChatMessage.chat_id == chat_id
        ).order_by(ChatMessage.created_at.asc()).offset(skip).limit(limit).all()

        logger.info(f"Found {len(messages)} messages in chat {chat_id}")

        for i, message in enumerate(messages):
            setattr(message, 'whoid', current_user.id)
            sender = db.query(User).filter(User.id == message.sender_id).first()
            if sender:
                setattr(message, 'sender_name', sender.full_name if sender.full_name else f"User {sender.id}")
                logger.debug(
                    f"Message {i + 1}: ID={message.id}, Sender={message.sender_id} ({message.sender_name}), Content='{message.content[:30]}...', Read={message.is_read}")

        # Mark messages as read
        unread_count = db.query(ChatMessage).filter(
            ChatMessage.chat_id == chat_id,
            ChatMessage.sender_id != current_user.id,
            ChatMessage.is_read == False
        ).count()

        if unread_count > 0:
            logger.info(f"Marking {unread_count} messages as read in chat {chat_id}")
            db.query(ChatMessage).filter(
                ChatMessage.chat_id == chat_id,
                ChatMessage.sender_id != current_user.id,
                ChatMessage.is_read == False
            ).update({"is_read": True})
            db.commit()

        logger.info(f"Successfully retrieved messages for chat {chat_id}")
        return messages

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting chat messages: {e}", exc_info=True)
        raise


@router.delete("/{chat_id}", response_model=dict)
def delete_chat(
        chat_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    logger.info(f"=== DELETE CHAT REQUEST ===")
    logger.info(f"Chat ID: {chat_id}, User ID: {current_user.id}")

    try:
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if not chat:
            logger.warning(f"Chat {chat_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat not found"
            )

        if chat.user1_id != current_user.id and chat.user2_id != current_user.id:
            logger.warning(f"User {current_user.id} doesn't have permission to delete chat {chat_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions"
            )

        # Get message count before deletion for logging
        message_count = db.query(ChatMessage).filter(ChatMessage.chat_id == chat_id).count()
        logger.info(f"Deleting chat {chat_id} with {message_count} messages")

        db.delete(chat)
        db.commit()

        logger.info(f"Successfully deleted chat {chat_id}")
        return {"message": "Chat deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting chat: {e}", exc_info=True)
        db.rollback()
        raise