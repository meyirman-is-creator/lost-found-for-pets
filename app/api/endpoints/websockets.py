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
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.is_online = is_online
            user.last_active_at = datetime.utcnow()
            db.add(user)
            db.commit()
            logger.debug(f"Updated status for user {user_id}: {'online' if is_online else 'offline'}")
    except Exception as e:
        logger.error(f"Error updating user status: {e}")
        db.rollback()


async def broadcast_user_status(user_id: int, is_online: bool, last_active_at: Optional[datetime] = None):
    """Отправляет статус пользователя всем его собеседникам"""
    status_type = MessageType.USER_ONLINE if is_online else MessageType.USER_OFFLINE

    # Если не указано время последней активности, используем текущее время
    if not last_active_at:
        last_active_at = datetime.utcnow()

    # Обновляем статус в нашем локальном хранилище
    user_status[user_id] = {
        "is_online": is_online,
        "last_active_at": last_active_at
    }

    # Находим все чаты, в которых участвует пользователь
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
                    # Используем наш кастомный энкодер для datetime
                    await ws.send_text(json.dumps(status_response.model_dump(), cls=DateTimeEncoder))
                except Exception as e:
                    logger.error(f"Error sending status update to user {uid}: {e}")


async def mark_messages_as_read(db: Session, chat_id: int, user_id: int):
    """Отмечает все сообщения как прочитанные и отправляет уведомления"""
    try:
        # Получаем все непрочитанные сообщения от других пользователей
        unread_messages = db.query(ChatMessage).filter(
            ChatMessage.chat_id == chat_id,
            ChatMessage.sender_id != user_id,
            ChatMessage.is_read == False
        ).all()

        if not unread_messages:
            return

        # Обновляем статус в базе данных
        for message in unread_messages:
            message.is_read = True

        db.commit()
        logger.debug(f"Marked {len(unread_messages)} messages as read in chat {chat_id}")

        # Получаем чат для определения другого пользователя
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if not chat:
            return

        # Определяем ID другого пользователя
        other_user_id = chat.user1_id if chat.user1_id != user_id else chat.user2_id

        # Отправляем уведомления о прочтении
        if other_user_id in active_connections.get(chat_id, {}):
            for message in unread_messages:
                read_notification = WebSocketStatusResponse(
                    user_id=user_id,
                    status_type=MessageType.MESSAGE_READ,
                    message_id=message.id
                )
                try:
                    # Используем наш кастомный энкодер для datetime
                    await active_connections[chat_id][other_user_id].send_text(
                        json.dumps(read_notification.model_dump(), cls=DateTimeEncoder))
                except Exception as e:
                    logger.error(f"Error sending read receipt for message {message.id}: {e}")

    except Exception as e:
        logger.error(f"Error marking messages as read: {e}")
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
    db = SessionLocal()
    current_user = None

    try:
        logger.info(f"WebSocket connection attempt to chat {chat_id}")

        # Аутентификация пользователя по токену
        try:
            current_user = await get_current_user_from_token(token, db)
            logger.info(f"User authenticated: {current_user.id} ({current_user.email})")
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # Проверка прав доступа к чату
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if not chat:
            logger.warning(f"Chat {chat_id} not found")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

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
        if chat_id not in typing_users:
            typing_users[chat_id] = set()

        # Добавляем соединение
        active_connections[chat_id][current_user.id] = websocket

        # Обновляем статус пользователя
        await update_user_status(db, current_user.id, True)
        await broadcast_user_status(current_user.id, True)

        # Отмечаем сообщения как прочитанные
        await mark_messages_as_read(db, chat_id, current_user.id)

        # Отправляем информацию о статусе собеседника
        other_user_id = chat.user1_id if chat.user1_id != current_user.id else chat.user2_id
        other_user = db.query(User).filter(User.id == other_user_id).first()

        if other_user:
            is_online = other_user_id in user_status and user_status[other_user_id]["is_online"]
            status_response = WebSocketStatusResponse(
                user_id=other_user_id,
                status_type=MessageType.USER_ONLINE if is_online else MessageType.USER_OFFLINE,
                last_active_at=other_user.last_active_at
            )
            # Используем наш кастомный энкодер для datetime
            await websocket.send_text(json.dumps(status_response.model_dump(), cls=DateTimeEncoder))

        # Отправляем сообщение о успешном подключении
        await websocket.send_text(json.dumps({"message": "Connection established successfully", "type": "system"}))

        # Основной цикл обработки сообщений
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Received message from user {current_user.id}: {data}")

            try:
                # Попытка парсинга JSON
                try:
                    message_data = json.loads(data)
                    logger.debug(f"Parsed message data: {message_data}")
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON received from user {current_user.id}: {data}")
                    continue

                # Получаем тип сообщения или устанавливаем TEXT по умолчанию, если тип не указан
                message_type = message_data.get("message_type", MessageType.TEXT)
                logger.debug(f"Message type: {message_type}")

                # Обновляем время активности пользователя
                await update_user_status(db, current_user.id, True)

                # Обработка обычных текстовых сообщений
                if message_type == MessageType.TEXT or "content" in message_data:
                    content = message_data.get("content", "").strip()
                    logger.debug(f"Message content: {content}")

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

                        # Удаляем пользователя из списка печатающих
                        if current_user.id in typing_users.get(chat_id, set()):
                            typing_users[chat_id].remove(current_user.id)

                        # Создаем ответ для отправки
                        response = {
                            "message_id": new_message.id,
                            "content": new_message.content,
                            "chat_id": new_message.chat_id,
                            "sender_id": new_message.sender_id,
                            "is_read": new_message.is_read,
                            "created_at": new_message.created_at,
                            "type": "text"  # Добавляем тип для совместимости с клиентом
                        }

                        logger.debug(f"Sending message to all users in chat {chat_id}: {response}")

                        # Отправляем сообщение всем участникам чата включая отправителя
                        for user_id, conn in active_connections.get(chat_id, {}).items():
                            try:
                                # Если получатель - это другой пользователь и он онлайн,
                                # отмечаем сообщение как прочитанное
                                if user_id != current_user.id:
                                    new_message.is_read = True
                                    db.add(new_message)
                                    db.commit()
                                    logger.debug(f"Marked message as read for user {user_id}")

                                # Отправляем сообщение - используем наш кастомный энкодер
                                await conn.send_text(json.dumps(response, cls=DateTimeEncoder))
                                logger.debug(f"Message sent to user {user_id}")
                            except Exception as e:
                                logger.error(f"Error sending message to user {user_id}: {e}")

                    except Exception as e:
                        logger.error(f"Error processing text message: {e}")
                        db.rollback()
                        # Отправляем уведомление об ошибке отправителю
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": "Failed to process message"
                        }))

                # Обработка начала набора сообщения
                elif message_type == MessageType.TYPING_STARTED:
                    typing_users[chat_id].add(current_user.id)

                    # Уведомляем других участников
                    for user_id, conn in active_connections.get(chat_id, {}).items():
                        if user_id != current_user.id:
                            typing_notification = WebSocketStatusResponse(
                                user_id=current_user.id,
                                status_type=MessageType.TYPING_STARTED
                            )
                            try:
                                # Используем наш кастомный энкодер
                                await conn.send_text(json.dumps(typing_notification.model_dump(), cls=DateTimeEncoder))
                            except Exception as e:
                                logger.error(f"Error sending typing notification: {e}")

                # Обработка окончания набора сообщения
                elif message_type == MessageType.TYPING_ENDED:
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
                                # Используем наш кастомный энкодер
                                await conn.send_text(json.dumps(typing_notification.model_dump(), cls=DateTimeEncoder))
                            except Exception as e:
                                logger.error(f"Error sending typing notification: {e}")

                # Обработка прочтения сообщения
                elif message_type == MessageType.MESSAGE_READ:
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

                            # Уведомляем отправителя о прочтении
                            if message.sender_id in active_connections.get(chat_id, {}):
                                read_notification = WebSocketStatusResponse(
                                    user_id=current_user.id,
                                    status_type=MessageType.MESSAGE_READ,
                                    message_id=message.id
                                )
                                try:
                                    # Используем наш кастомный энкодер
                                    await active_connections[chat_id][message.sender_id].send_text(
                                        json.dumps(read_notification.model_dump(), cls=DateTimeEncoder))
                                except Exception as e:
                                    logger.error(f"Error sending read receipt: {e}")

                else:
                    logger.warning(f"Unknown message type: {message_type}")

            except Exception as e:
                logger.error(f"Unexpected error processing message: {e}")
                # Продолжаем работу, не прерывая соединение

    except WebSocketDisconnect:
        logger.info(
            f"WebSocket disconnected for user {current_user.id if current_user else 'unknown'} in chat {chat_id}")
    except Exception as e:
        logger.error(f"Unexpected WebSocket error: {e}")

    finally:
        # Очистка и обработка отключения
        if current_user:
            # Обновляем статус пользователя
            await update_user_status(db, current_user.id, False)
            await broadcast_user_status(current_user.id, False)

            # Удаляем соединение
            if chat_id in active_connections and current_user.id in active_connections[chat_id]:
                del active_connections[chat_id][current_user.id]
                if not active_connections[chat_id]:
                    del active_connections[chat_id]

            # Удаляем из списка печатающих
            if chat_id in typing_users and current_user.id in typing_users[chat_id]:
                typing_users[chat_id].remove(current_user.id)
                if not typing_users[chat_id]:
                    del typing_users[chat_id]

        # Закрываем сессию базы данных
        db.close()