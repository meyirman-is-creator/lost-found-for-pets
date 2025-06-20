from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status, Query
from sqlalchemy.orm import Session
from typing import Dict, List, Any, Optional, Set
import json
from datetime import datetime
import asyncio
import logging

from app.api.dependencies import get_current_user_from_token
from app.db.database import SessionLocal
from app.models.models import User, Chat, ChatMessage
from app.schemas.schemas import WebSocketStatusResponse, MessageType


# Настраиваем собственный JSON энкодер для datetime объектов
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


router = APIRouter()
logger = logging.getLogger(__name__)

# Хранение активных соединений: chat_id -> {user_id: WebSocket}
active_connections: Dict[int, Dict[int, WebSocket]] = {}

# Хранение информации о печатающих пользователях: chat_id -> set(user_ids)
typing_users: Dict[int, Set[int]] = {}

# Хранение информации о статусе пользователей: user_id -> {"is_online": bool, "last_active_at": datetime}
user_status: Dict[int, Dict[str, Any]] = {}


async def update_user_status(db: Session, user_id: int, is_online: bool):
    """Обновляет статус пользователя в базе данных"""
    logger.info(f"=== UPDATING USER STATUS ===")
    logger.info(f"User ID: {user_id}, Online: {is_online}")

    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.is_online = is_online
            user.last_active_at = datetime.utcnow()
            db.add(user)
            db.commit()
            logger.info(f"User {user_id} status updated: {'ONLINE' if is_online else 'OFFLINE'}")
        else:
            logger.warning(f"User {user_id} not found in database")
    except Exception as e:
        logger.error(f"Error updating user status: {e}", exc_info=True)
        db.rollback()


async def broadcast_user_status(user_id: int, is_online: bool, last_active_at: Optional[datetime] = None):
    """Отправляет статус пользователя всем его собеседникам"""
    logger.info(f"=== BROADCASTING USER STATUS ===")
    logger.info(f"User ID: {user_id}, Broadcasting: {'ONLINE' if is_online else 'OFFLINE'}")

    status_type = MessageType.USER_ONLINE if is_online else MessageType.USER_OFFLINE

    # Если не указано время последней активности, используем текущее время
    if not last_active_at:
        last_active_at = datetime.utcnow()

    # Обновляем статус в нашем локальном хранилище
    user_status[user_id] = {
        "is_online": is_online,
        "last_active_at": last_active_at
    }

    logger.debug(f"Updated local status for user {user_id}: {user_status[user_id]}")

    # Находим все чаты, в которых участвует пользователь
    broadcast_count = 0
    for chat_id, users in active_connections.items():
        for uid, ws in users.items():
            if uid != user_id:  # Другой участник чата
                try:
                    # Отправляем статус пользователя
                    status_response = WebSocketStatusResponse(
                        user_id=user_id,
                        status_type=status_type,
                        last_active_at=last_active_at
                    )
                    status_json = json.dumps(status_response.model_dump(), cls=DateTimeEncoder)
                    logger.debug(f"Sending status update to user {uid} in chat {chat_id}: {status_json}")
                    await ws.send_text(status_json)
                    broadcast_count += 1
                except Exception as e:
                    logger.error(f"Error sending status update to user {uid}: {e}")

    logger.info(f"Status broadcasted to {broadcast_count} users")


async def mark_messages_as_read(db: Session, chat_id: int, user_id: int):
    """Отмечает все сообщения как прочитанные и отправляет уведомления"""
    logger.info(f"=== MARKING MESSAGES AS READ ===")
    logger.info(f"Chat ID: {chat_id}, User ID: {user_id}")

    try:
        # Получаем все непрочитанные сообщения от других пользователей
        unread_messages = db.query(ChatMessage).filter(
            ChatMessage.chat_id == chat_id,
            ChatMessage.sender_id != user_id,
            ChatMessage.is_read == False
        ).all()

        if not unread_messages:
            logger.debug(f"No unread messages in chat {chat_id}")
            return

        logger.info(f"Found {len(unread_messages)} unread messages")

        # Обновляем статус в базе данных
        for message in unread_messages:
            message.is_read = True
            logger.debug(f"Marking message {message.id} as read")

        db.commit()
        logger.info(f"Marked {len(unread_messages)} messages as read in database")

        # Получаем чат для определения другого пользователя
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if not chat:
            logger.warning(f"Chat {chat_id} not found")
            return

        # Определяем ID другого пользователя
        other_user_id = chat.user1_id if chat.user1_id != user_id else chat.user2_id
        logger.debug(f"Other user in chat: {other_user_id}")

        # Отправляем уведомления о прочтении
        if other_user_id in active_connections.get(chat_id, {}):
            for message in unread_messages:
                read_notification = WebSocketStatusResponse(
                    user_id=user_id,
                    status_type=MessageType.MESSAGE_READ,
                    message_id=message.id
                )
                try:
                    notification_json = json.dumps(read_notification.model_dump(), cls=DateTimeEncoder)
                    logger.debug(f"Sending read receipt for message {message.id} to user {other_user_id}")
                    await active_connections[chat_id][other_user_id].send_text(notification_json)
                except Exception as e:
                    logger.error(f"Error sending read receipt for message {message.id}: {e}")

    except Exception as e:
        logger.error(f"Error marking messages as read: {e}", exc_info=True)
        db.rollback()


@router.websocket("/ws/{chat_id}")
async def websocket_endpoint(
        websocket: WebSocket,
        chat_id: int,
        token: str = Query(...)  # Обязательный параметр
):
    """
    WebSocket endpoint для чата
    """
    logger.info(f"=== WEBSOCKET CONNECTION ATTEMPT ===")
    logger.info(f"Chat ID: {chat_id}")

    db = SessionLocal()
    current_user = None

    try:
        # Аутентификация пользователя по токену
        try:
            current_user = await get_current_user_from_token(token, db)
            logger.info(f"User authenticated: ID={current_user.id}, Email={current_user.email}")
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # Проверка прав доступа к чату
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if not chat:
            logger.warning(f"Chat {chat_id} not found")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        logger.debug(f"Chat found: user1={chat.user1_id}, user2={chat.user2_id}")

        if chat.user1_id != current_user.id and chat.user2_id != current_user.id:
            logger.warning(f"User {current_user.id} is not a participant of chat {chat_id}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # Принимаем соединение
        await websocket.accept()
        logger.info(f"WebSocket connection accepted for user {current_user.id} in chat {chat_id}")

        # Инициализируем структуры данных, если необходимо
        if chat_id not in active_connections:
            active_connections[chat_id] = {}
            logger.debug(f"Created new connection dict for chat {chat_id}")

        if chat_id not in typing_users:
            typing_users[chat_id] = set()
            logger.debug(f"Created new typing users set for chat {chat_id}")

        # Добавляем соединение
        active_connections[chat_id][current_user.id] = websocket
        logger.info(
            f"Added connection to active_connections. Chat {chat_id} now has {len(active_connections[chat_id])} connections")

        # Обновляем статус пользователя
        await update_user_status(db, current_user.id, True)
        await broadcast_user_status(current_user.id, True)

        # Отмечаем сообщения как прочитанные
        await mark_messages_as_read(db, chat_id, current_user.id)

        # Отправляем информацию о статусе собеседника
        other_user_id = chat.user1_id if chat.user1_id != current_user.id else chat.user2_id
        logger.debug(f"Other user in chat: {other_user_id}")

        other_user = db.query(User).filter(User.id == other_user_id).first()

        if other_user:
            is_online = other_user_id in user_status and user_status[other_user_id]["is_online"]
            logger.debug(f"Other user {other_user_id} is {'online' if is_online else 'offline'}")

            status_response = WebSocketStatusResponse(
                user_id=other_user_id,
                status_type=MessageType.USER_ONLINE if is_online else MessageType.USER_OFFLINE,
                last_active_at=other_user.last_active_at
            )
            status_json = json.dumps(status_response.model_dump(), cls=DateTimeEncoder)
            logger.debug(f"Sending initial status: {status_json}")
            await websocket.send_text(status_json)

        # Отправляем сообщение о успешном подключении
        success_message = json.dumps({"message": "Connection established successfully", "type": "system"})
        logger.debug(f"Sending success message: {success_message}")
        await websocket.send_text(success_message)

        # Основной цикл обработки сообщений
        while True:
            data = await websocket.receive_text()
            logger.info(f"=== RECEIVED WEBSOCKET MESSAGE ===")
            logger.info(f"From user {current_user.id} in chat {chat_id}")
            logger.debug(f"Raw data: {data}")

            try:
                # Попытка парсинга JSON
                try:
                    message_data = json.loads(data)
                    logger.debug(f"Parsed message data: {json.dumps(message_data, indent=2)}")
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON received: {e}")
                    logger.error(f"Data: {data}")
                    continue

                # Получаем тип сообщения или устанавливаем TEXT по умолчанию, если тип не указан
                message_type = message_data.get("message_type", MessageType.TEXT)
                logger.info(f"Message type: {message_type}")

                # Обновляем время активности пользователя
                await update_user_status(db, current_user.id, True)

                # Обработка обычных текстовых сообщений
                if message_type == MessageType.TEXT or "content" in message_data:
                    content = message_data.get("content", "").strip()
                    logger.info(f"Text message content: '{content[:50]}...'")

                    if not content:
                        logger.warning("Empty message content, skipping")
                        continue

                    try:
                        # Создаем новое сообщение в отдельной транзакции
                        new_message = ChatMessage(
                            chat_id=chat_id,
                            sender_id=current_user.id,
                            content=content,
                            is_read=False
                        )
                        db.add(new_message)
                        db.commit()
                        db.refresh(new_message)
                        logger.info(f"Message saved to DB with ID: {new_message.id}")

                        # Обновляем время последней активности чата
                        chat.updated_at = datetime.utcnow()
                        db.add(chat)
                        db.commit()
                        logger.debug(f"Updated chat {chat_id} timestamp")

                        # Удаляем пользователя из списка печатающих
                        if current_user.id in typing_users.get(chat_id, set()):
                            typing_users[chat_id].remove(current_user.id)
                            logger.debug(f"Removed user {current_user.id} from typing list")

                        # Получаем информацию об отправителе
                        sender = db.query(User).filter(User.id == current_user.id).first()
                        sender_name = sender.full_name if sender and sender.full_name else f"User {current_user.id}"

                        # Создаем ответ для отправки
                        response = {
                            "message_id": new_message.id,
                            "content": new_message.content,
                            "chat_id": new_message.chat_id,
                            "sender_id": new_message.sender_id,
                            "is_read": new_message.is_read,
                            "created_at": new_message.created_at,
                            "sender_name": sender_name,
                            "type": "text"
                        }

                        response_json = json.dumps(response, cls=DateTimeEncoder)
                        logger.info(f"Broadcasting message to all users in chat {chat_id}")
                        logger.debug(f"Response JSON: {response_json}")

                        # Отправляем сообщение всем участникам чата включая отправителя
                        for user_id, conn in active_connections.get(chat_id, {}).items():
                            try:
                                # Если получатель - это другой пользователь и он онлайн,
                                # отмечаем сообщение как прочитанное
                                if user_id != current_user.id:
                                    new_message.is_read = True
                                    db.add(new_message)
                                    db.commit()
                                    logger.debug(f"Marked message as read for online user {user_id}")

                                # Отправляем сообщение
                                await conn.send_text(response_json)
                                logger.debug(f"Message sent to user {user_id}")
                            except Exception as e:
                                logger.error(f"Error sending message to user {user_id}: {e}")

                    except Exception as e:
                        logger.error(f"Error processing text message: {e}", exc_info=True)
                        db.rollback()
                        # Отправляем уведомление об ошибке отправителю
                        error_message = json.dumps({
                            "type": "error",
                            "message": "Failed to process message"
                        })
                        await websocket.send_text(error_message)

                # Обработка начала набора сообщения
                elif message_type == MessageType.TYPING_STARTED:
                    logger.info(f"User {current_user.id} started typing")
                    typing_users[chat_id].add(current_user.id)

                    # Уведомляем других участников
                    for user_id, conn in active_connections.get(chat_id, {}).items():
                        if user_id != current_user.id:
                            typing_notification = WebSocketStatusResponse(
                                user_id=current_user.id,
                                status_type=MessageType.TYPING_STARTED
                            )
                            try:
                                notification_json = json.dumps(typing_notification.model_dump(), cls=DateTimeEncoder)
                                logger.debug(f"Sending typing started to user {user_id}")
                                await conn.send_text(notification_json)
                            except Exception as e:
                                logger.error(f"Error sending typing notification: {e}")

                # Обработка окончания набора сообщения
                elif message_type == MessageType.TYPING_ENDED:
                    logger.info(f"User {current_user.id} stopped typing")
                    if current_user.id in typing_users.get(chat_id, set()):
                        typing_users[chat_id].remove(current_user.id)

                    # Уведомляем других участников
                    for user_id, conn in active_connections.get(chat_id, {}).items():
                        if user_id != current_user.id:
                            typing_notification = WebSocketStatusResponse(
                                user_id=current_user.id,
                                status_type=MessageType.TYPING_ENDED
                            )
                            try:
                                notification_json = json.dumps(typing_notification.model_dump(), cls=DateTimeEncoder)
                                logger.debug(f"Sending typing ended to user {user_id}")
                                await conn.send_text(notification_json)
                            except Exception as e:
                                logger.error(f"Error sending typing notification: {e}")

                # Обработка прочтения сообщения
                elif message_type == MessageType.MESSAGE_READ:
                    message_id = message_data.get("message_id")
                    logger.info(f"User {current_user.id} marking message {message_id} as read")

                    if message_id:
                        message = db.query(ChatMessage).filter(
                            ChatMessage.id == message_id,
                            ChatMessage.chat_id == chat_id
                        ).first()

                        if message and not message.is_read:
                            message.is_read = True
                            db.add(message)
                            db.commit()
                            logger.debug(f"Message {message_id} marked as read in DB")

                            # Уведомляем отправителя о прочтении
                            if message.sender_id in active_connections.get(chat_id, {}):
                                read_notification = WebSocketStatusResponse(
                                    user_id=current_user.id,
                                    status_type=MessageType.MESSAGE_READ,
                                    message_id=message.id
                                )
                                try:
                                    notification_json = json.dumps(read_notification.model_dump(), cls=DateTimeEncoder)
                                    logger.debug(f"Sending read receipt to user {message.sender_id}")
                                    await active_connections[chat_id][message.sender_id].send_text(notification_json)
                                except Exception as e:
                                    logger.error(f"Error sending read receipt: {e}")

                else:
                    logger.warning(f"Unknown message type: {message_type}")

            except Exception as e:
                logger.error(f"Unexpected error processing message: {e}", exc_info=True)
                # Продолжаем работу, не прерывая соединение

    except WebSocketDisconnect:
        logger.info(f"=== WEBSOCKET DISCONNECTED ===")
        logger.info(f"User {current_user.id if current_user else 'unknown'} disconnected from chat {chat_id}")
    except Exception as e:
        logger.error(f"Unexpected WebSocket error: {e}", exc_info=True)

    finally:
        # Очистка и обработка отключения
        if current_user:
            logger.info(f"=== CLEANING UP CONNECTION ===")
            logger.info(f"User ID: {current_user.id}, Chat ID: {chat_id}")

            # Обновляем статус пользователя
            await update_user_status(db, current_user.id, False)
            await broadcast_user_status(current_user.id, False)

            # Удаляем соединение
            if chat_id in active_connections and current_user.id in active_connections[chat_id]:
                del active_connections[chat_id][current_user.id]
                logger.debug(
                    f"Removed connection. Chat {chat_id} now has {len(active_connections[chat_id])} connections")

                if not active_connections[chat_id]:
                    del active_connections[chat_id]
                    logger.debug(f"Removed empty chat {chat_id} from active connections")

            # Удаляем из списка печатающих
            if chat_id in typing_users and current_user.id in typing_users[chat_id]:
                typing_users[chat_id].remove(current_user.id)
                logger.debug(f"Removed user from typing list")

                if not typing_users[chat_id]:
                    del typing_users[chat_id]
                    logger.debug(f"Removed empty typing users set for chat {chat_id}")

        # Закрываем сессию базы данных
        db.close()
        logger.info("Database session closed")