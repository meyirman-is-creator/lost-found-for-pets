from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum


class PetStatus(str, Enum):
    LOST = "lost"
    FOUND = "found"
    HOME = "home"


class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    phone: Optional[str] = None


class UserCreate(UserBase):
    password: str

    @validator('password')
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return v


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    password: Optional[str] = None


class User(UserBase):
    id: int
    is_active: bool
    is_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True


class PetPhotoBase(BaseModel):
    is_primary: bool = False


class PetPhotoCreate(PetPhotoBase):
    pass


class PetPhoto(PetPhotoBase):
    id: int
    pet_id: int
    photo_url: str
    created_at: datetime

    class Config:
        from_attributes = True


class PetBase(BaseModel):
    name: str
    species: str
    breed: Optional[str] = None
    age: Optional[int] = None
    color: Optional[str] = None
    gender: Optional[str] = None
    distinctive_features: Optional[str] = None
    last_seen_location: Optional[str] = None


class PetCreate(PetBase):
    pass


class PetUpdate(BaseModel):
    name: Optional[str] = None
    breed: Optional[str] = None
    age: Optional[int] = None
    color: Optional[str] = None
    gender: Optional[str] = None
    distinctive_features: Optional[str] = None
    status: Optional[PetStatus] = None
    last_seen_location: Optional[str] = None


class Pet(PetBase):
    id: int
    photos: List[PetPhoto] = []
    status: PetStatus
    created_at: datetime
    updated_at: datetime
    lost_date: Optional[datetime] = None
    owner_id: int
    coordX: Optional[str] = None
    coordY: Optional[str] = None

    class Config:
        from_attributes = True


class FirstMessageCreate(BaseModel):
    message: str


class PetMatchBase(BaseModel):
    found_pet_id: int
    lost_pet_id: int
    similarity_score: float


class PetMatchCreate(PetMatchBase):
    pass


class PetMatch(PetMatchBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class PetMatchWithDetails(PetMatch):
    lost_pet: Pet
    found_pet: Pet

    class Config:
        from_attributes = True


class NotificationBase(BaseModel):
    user_id: int
    match_id: int
    message: str


class NotificationCreate(NotificationBase):
    pass


class Notification(NotificationBase):
    id: int
    is_read: bool
    created_at: datetime
    match: PetMatch

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    email: Optional[str] = None


class Login(BaseModel):
    email: EmailStr
    password: str


class VerificationRequest(BaseModel):
    email: EmailStr
    code: str


class FoundPetInfo(BaseModel):
    photo_base64: str
    species: str
    breed: Optional[str] = None
    color: Optional[str] = None
    location: Optional[str] = None
    distinctive_features: Optional[str] = None


class SimilarityResult(BaseModel):
    pet: Pet
    similarity_score: float

    class Config:
        from_attributes = True


class SimilarityResponse(BaseModel):
    matches: List[SimilarityResult]

    class Config:
        from_attributes = True


class ChatMessageBase(BaseModel):
    content: str


class ChatMessageCreate(ChatMessageBase):
    pass


class ChatMessage(ChatMessageBase):
    id: int
    chat_id: int
    sender_id: int
    whoid: Optional[int] = None
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ChatBase(BaseModel):
    pet_id: Optional[int] = None


class ChatCreate(ChatBase):
    user2_id: int


class Chat(ChatBase):
    id: int
    user1_id: int
    user2_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChatWithLastMessage(Chat):
    last_message: Optional[ChatMessage] = None
    unread_count: int = 0
    pet_photo_url: Optional[str] = None
    pet_name: Optional[str] = None
    pet_status: Optional[PetStatus] = None
    other_user_name: Optional[str] = None

    class Config:
        from_attributes = True


class WebSocketMessage(BaseModel):
    message: str
    chat_id: int
    sender_id: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class WebSocketResponse(BaseModel):
    message_id: int
    content: str
    chat_id: int
    sender_id: int
    is_read: bool
    created_at: datetime


class MessageType(str, Enum):
    TEXT = "text"
    TYPING_STARTED = "typing_started"
    TYPING_ENDED = "typing_ended"
    USER_ONLINE = "user_online"
    USER_OFFLINE = "user_offline"
    MESSAGE_READ = "message_read"


class WebSocketMessageRequest(BaseModel):
    message_type: MessageType
    content: Optional[str] = None
    message_id: Optional[int] = None


class WebSocketStatusResponse(BaseModel):
    user_id: int
    status_type: MessageType
    last_active_at: Optional[datetime] = None
    message_id: Optional[int] = None