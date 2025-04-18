from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, List, Any
import json
from datetime import datetime

from app.api.dependencies import get_current_user_from_token
from app.core.config import settings
from app.db.database import get_db
from app.models.models import User, Chat, ChatMessage
from app.schemas.schemas import WebSocketMessage, WebSocketResponse

router = APIRouter()

# Хранение активных соединений: chat_id -> {user_id: WebSocket}
active_connections: Dict[int, Dict[int, WebSocket]] = {}


@router.websocket("/ws/{chat_id}")
async def websocket_endpoint(
        websocket: WebSocket,
        chat_id: int,
        token: str,
        db: Session = Depends(get_db)
):
    # Аутентификация пользователя по токену
    try:
        current_user = await get_current_user_from_token(token, db)
    except HTTPException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Проверка, что пользователь является участником чата
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat or (chat.user1_id != current_user.id and chat.user2_id != current_user.id):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Принять соединение
    await websocket.accept()

    # Добавление нового соединения
    if chat_id not in active_connections:
        active_connections[chat_id] = {}
    active_connections[chat_id][current_user.id] = websocket

    # Отметить все сообщения как прочитанные для текущего пользователя
    db.query(ChatMessage).filter(
        ChatMessage.chat_id == chat_id,
        ChatMessage.sender_id != current_user.id,
        ChatMessage.is_read == False
    ).update({"is_read": True})
    db.commit()

    try:
        while True:
            # Ожидание сообщения от клиента
            data = await websocket.receive_text()
            try:
                message_data = json.loads(data)
                content = message_data.get("message", "").strip()

                if not content:
                    continue

                # Создание нового сообщения в базе данных
                new_message = ChatMessage(
                    chat_id=chat_id,
                    sender_id=current_user.id,
                    content=content,
                    is_read=False
                )
                db.add(new_message)
                db.commit()
                db.refresh(new_message)

                # Обновление времени последнего сообщения в чате
                chat.updated_at = datetime.utcnow()
                db.add(chat)
                db.commit()

                # Создание ответа
                response = WebSocketResponse(
                    message_id=new_message.id,
                    content=new_message.content,
                    chat_id=new_message.chat_id,
                    sender_id=new_message.sender_id,
                    is_read=new_message.is_read,
                    created_at=new_message.created_at
                )
                response_json = response.model_dump_json()

                # Отправка сообщения всем участникам чата
                for user_id, conn in active_connections.get(chat_id, {}).items():
                    try:
                        # Если это получатель сообщения и он онлайн, отмечаем как прочитанное
                        if user_id != current_user.id:
                            new_message.is_read = True
                            db.add(new_message)
                            db.commit()

                        await conn.send_text(response_json)
                    except Exception:
                        # Игнорируем ошибки отправки для неактивных соединений
                        pass

            except json.JSONDecodeError:
                # Игнорируем неправильный формат сообщений
                pass

    except WebSocketDisconnect:
        # Удаляем соединение при отключении
        if chat_id in active_connections and current_user.id in active_connections[chat_id]:
            del active_connections[chat_id][current_user.id]
            if not active_connections[chat_id]:
                del active_connections[chat_id]