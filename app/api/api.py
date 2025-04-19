from fastapi import APIRouter
from app.api.endpoints import auth, users, pets, notifications, chats, websockets
api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(pets.router, prefix="/pets", tags=["pets"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(chats.router, prefix="/chats", tags=["chats"])
api_router.include_router(websockets.router, tags=["websockets"])