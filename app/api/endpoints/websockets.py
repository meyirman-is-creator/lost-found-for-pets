from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status, Query
from sqlalchemy.orm import Session
from typing import Dict, List, Any, Optional, Set
import json
from datetime import datetime
import logging

from app.api.dependencies import get_current_user_from_token
from app.db.database import SessionLocal
from app.models.models import User, Chat, ChatMessage
from app.schemas.schemas import WebSocketStatusResponse, MessageType

router = APIRouter()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

active_connections: Dict[int, Dict[int, WebSocket]] = {}
typing_users: Dict[int, Set[int]] = {}
user_status: Dict[int, Dict[str, Any]] = {}


async def update_user_status(db: Session, user_id: int, is_online: bool):
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.is_online = is_online
            user.last_active_at = datetime.utcnow()
            db.add(user)
            db.commit()
    except Exception as e:
        logger.error(f"Error updating user status: {e}")
        db.rollback()


async def broadcast_user_status(user_id: int, is_online: bool, last_active_at: Optional[datetime] = None):
    status_type = MessageType.USER_ONLINE if is_online else MessageType.USER_OFFLINE

    if not last_active_at:
        last_active_at = datetime.utcnow()

    user_status[user_id] = {
        "is_online": is_online,
        "last_active_at": last_active_at
    }

    for chat_id, users in active_connections.items():
        for uid, ws in users.items():
            if uid != user_id:
                try:
                    status_response = {
                        "user_id": user_id,
                        "status_type": status_type,
                        "last_active_at": last_active_at.isoformat() if last_active_at else None
                    }
                    await ws.send_text(json.dumps(status_response))
                except Exception as e:
                    logger.error(f"Error sending status update: {e}")


async def mark_messages_as_read(db: Session, chat_id: int, user_id: int):
    try:
        unread_messages = db.query(ChatMessage).filter(
            ChatMessage.chat_id == chat_id,
            ChatMessage.sender_id != user_id,
            ChatMessage.is_read == False
        ).all()

        if not unread_messages:
            return

        for message in unread_messages:
            message.is_read = True

        db.commit()

        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if not chat:
            return

        other_user_id = chat.user1_id if chat.user1_id != user_id else chat.user2_id

        if other_user_id in active_connections.get(chat_id, {}):
            for message in unread_messages:
                read_notification = {
                    "user_id": user_id,
                    "status_type": MessageType.MESSAGE_READ,
                    "message_id": message.id
                }
                try:
                    await active_connections[chat_id][other_user_id].send_text(json.dumps(read_notification))
                except Exception as e:
                    logger.error(f"Error sending read receipt: {e}")

    except Exception as e:
        logger.error(f"Error marking messages as read: {e}")
        db.rollback()


@router.websocket("/ws/{chat_id}")
async def websocket_endpoint(
        websocket: WebSocket,
        chat_id: int,
        token: str = Query(...)
):
    db = SessionLocal()
    current_user = None

    try:
        try:
            current_user = await get_current_user_from_token(token, db)
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if not chat:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        if chat.user1_id != current_user.id and chat.user2_id != current_user.id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        await websocket.accept()

        if chat_id not in active_connections:
            active_connections[chat_id] = {}
        if chat_id not in typing_users:
            typing_users[chat_id] = set()

        active_connections[chat_id][current_user.id] = websocket

        await update_user_status(db, current_user.id, True)
        await broadcast_user_status(current_user.id, True)
        await mark_messages_as_read(db, chat_id, current_user.id)

        other_user_id = chat.user1_id if chat.user1_id != current_user.id else chat.user2_id
        other_user = db.query(User).filter(User.id == other_user_id).first()

        if other_user:
            is_online = other_user_id in user_status and user_status[other_user_id]["is_online"]
            status_response = {
                "user_id": other_user_id,
                "status_type": MessageType.USER_ONLINE if is_online else MessageType.USER_OFFLINE,
                "last_active_at": other_user.last_active_at.isoformat() if other_user.last_active_at else None
            }
            await websocket.send_text(json.dumps(status_response))

        await websocket.send_text(json.dumps({"message": "Connection established successfully", "type": "system"}))

        while True:
            raw_data = await websocket.receive_text()

            await update_user_status(db, current_user.id, True)

            is_json = False
            message_type = MessageType.TEXT
            content = raw_data

            try:
                message_data = json.loads(raw_data)
                is_json = True

                if isinstance(message_data, dict):
                    message_type = message_data.get("message_type", MessageType.TEXT)

                    if message_type == MessageType.TEXT or "content" in message_data:
                        content = message_data.get("content", "").strip()
                else:
                    content = raw_data
            except json.JSONDecodeError:
                is_json = False
                message_type = MessageType.TEXT
                content = raw_data

            if message_type == MessageType.TEXT:
                if not content or content.strip() == "":
                    continue

                try:
                    new_message = ChatMessage(
                        chat_id=chat_id,
                        sender_id=current_user.id,
                        content=content,
                        is_read=False
                    )
                    db.add(new_message)
                    db.commit()
                    db.refresh(new_message)

                    chat.updated_at = datetime.utcnow()
                    db.add(chat)
                    db.commit()

                    if current_user.id in typing_users.get(chat_id, set()):
                        typing_users[chat_id].remove(current_user.id)

                    response = {
                        "message_id": new_message.id,
                        "content": new_message.content,
                        "chat_id": new_message.chat_id,
                        "sender_id": new_message.sender_id,
                        "is_read": new_message.is_read,
                        "created_at": new_message.created_at.isoformat(),
                        "type": "text"
                    }
                    response_json = json.dumps(response)

                    for user_id, conn in active_connections.get(chat_id, {}).items():
                        try:
                            if user_id != current_user.id:
                                new_message.is_read = True
                                db.add(new_message)
                                db.commit()

                            await conn.send_text(response_json)
                        except Exception as e:
                            logger.error(f"Error sending message: {e}")

                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    db.rollback()
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Failed to process message"
                    }))

            elif message_type == MessageType.TYPING_STARTED:
                typing_users[chat_id].add(current_user.id)

                for user_id, conn in active_connections.get(chat_id, {}).items():
                    if user_id != current_user.id:
                        typing_notification = {
                            "user_id": current_user.id,
                            "status_type": MessageType.TYPING_STARTED
                        }
                        try:
                            await conn.send_text(json.dumps(typing_notification))
                        except Exception as e:
                            logger.error(f"Error sending typing notification: {e}")

            elif message_type == MessageType.TYPING_ENDED:
                if current_user.id in typing_users.get(chat_id, set()):
                    typing_users[chat_id].remove(current_user.id)

                for user_id, conn in active_connections.get(chat_id, {}).items():
                    if user_id != current_user.id:
                        typing_notification = {
                            "user_id": current_user.id,
                            "status_type": MessageType.TYPING_ENDED
                        }
                        try:
                            await conn.send_text(json.dumps(typing_notification))
                        except Exception as e:
                            logger.error(f"Error sending typing notification: {e}")

            elif message_type == MessageType.MESSAGE_READ and is_json:
                message_id = message_data.get("message_id")

                if message_id:
                    message = db.query(ChatMessage).filter(
                        ChatMessage.id == message_id,
                        ChatMessage.chat_id == chat_id
                    ).first()

                    if message and not message.is_read:
                        message.is_read = True
                        db.add(message)
                        db.commit()

                        if message.sender_id in active_connections.get(chat_id, {}):
                            read_notification = {
                                "user_id": current_user.id,
                                "status_type": MessageType.MESSAGE_READ,
                                "message_id": message.id
                            }
                            try:
                                await active_connections[chat_id][message.sender_id].send_text(
                                    json.dumps(read_notification))
                            except Exception as e:
                                logger.error(f"Error sending read receipt: {e}")

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for user {current_user.id if current_user else 'unknown'}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")

    finally:
        if current_user:
            await update_user_status(db, current_user.id, False)
            await broadcast_user_status(current_user.id, False)

            if chat_id in active_connections and current_user.id in active_connections[chat_id]:
                del active_connections[chat_id][current_user.id]
                if not active_connections[chat_id]:
                    del active_connections[chat_id]

            if chat_id in typing_users and current_user.id in typing_users[chat_id]:
                typing_users[chat_id].remove(current_user.id)
                if not typing_users[chat_id]:
                    del typing_users[chat_id]

        db.close()