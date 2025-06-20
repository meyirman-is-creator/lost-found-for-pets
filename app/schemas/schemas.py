from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum
import re


class PetStatus(str, Enum):
    LOST = "lost"
    FOUND = "found"
    HOME = "home"


class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    phone: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=100)
    full_name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., min_length=10, max_length=20)

    @field_validator('password')
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one number')
        return v

    @field_validator('phone')
    @classmethod
    def phone_validation(cls, v: str) -> str:
        # Remove spaces and hyphens
        cleaned = re.sub(r'[\s\-\(\)]', '', v)
        # Check if it starts with + and contains only digits after that
        if not re.match(r'^\+?\d{10,15}$', cleaned):
            raise ValueError('Invalid phone number format')
        return cleaned

    @field_validator('full_name')
    @classmethod
    def name_validation(cls, v: str) -> str:
        if not v or len(v.strip()) < 2:
            raise ValueError('Full name must be at least 2 characters long')
        if not re.match(r'^[a-zA-Z\s\-\']+$', v):
            raise ValueError('Full name can only contain letters, spaces, hyphens and apostrophes')
        return v.strip()


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    phone: Optional[str] = Field(None, min_length=10, max_length=20)
    password: Optional[str] = Field(None, min_length=8, max_length=100)

    @field_validator('password')
    @classmethod
    def password_strength(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one number')
        return v

    @field_validator('phone')
    @classmethod
    def phone_validation(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        cleaned = re.sub(r'[\s\-\(\)]', '', v)
        if not re.match(r'^\+?\d{10,15}$', cleaned):
            raise ValueError('Invalid phone number format')
        return cleaned


class User(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    is_verified: bool
    created_at: datetime


class PetPhotoBase(BaseModel):
    is_primary: bool = False


class PetPhotoCreate(PetPhotoBase):
    pass


class PetPhoto(PetPhotoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pet_id: int
    photo_url: str
    created_at: datetime


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
    model_config = ConfigDict(from_attributes=True)

    id: int
    photos: List[PetPhoto] = []
    status: PetStatus
    created_at: datetime
    updated_at: datetime
    lost_date: Optional[datetime] = None
    owner_id: int
    coordX: Optional[str] = None
    coordY: Optional[str] = None
    owner_phone: Optional[str] = None


class FirstMessageCreate(BaseModel):
    message: str


class PetMatchBase(BaseModel):
    found_pet_id: int
    lost_pet_id: int
    similarity_score: float


class PetMatchCreate(PetMatchBase):
    pass


class PetMatch(PetMatchBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class PetMatchWithDetails(PetMatch):
    model_config = ConfigDict(from_attributes=True)

    lost_pet: Pet
    found_pet: Pet


class NotificationBase(BaseModel):
    user_id: int
    match_id: int
    message: str


class NotificationCreate(NotificationBase):
    pass


class Notification(NotificationBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_read: bool
    created_at: datetime
    match: PetMatch


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    email: Optional[str] = None


class Login(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)

    @field_validator('email')
    @classmethod
    def email_lowercase(cls, v: str) -> str:
        return v.lower()


class VerificationRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., pattern=r'^\d{6}$')

    @field_validator('email')
    @classmethod
    def email_lowercase(cls, v: str) -> str:
        return v.lower()


class ResendVerificationRequest(BaseModel):
    email: EmailStr

    @field_validator('email')
    @classmethod
    def email_lowercase(cls, v: str) -> str:
        return v.lower()


class FoundPetInfo(BaseModel):
    photo_base64: str
    species: str
    breed: Optional[str] = None
    color: Optional[str] = None
    location: Optional[str] = None
    distinctive_features: Optional[str] = None


class SimilarityResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pet: Pet
    similarity_score: float


class SimilarityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    matches: List[SimilarityResult]


class ChatMessageBase(BaseModel):
    content: str


class ChatMessageCreate(ChatMessageBase):
    pass


class ChatMessage(ChatMessageBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chat_id: int
    sender_id: int
    whoid: Optional[int] = None
    is_read: bool
    created_at: datetime


class ChatBase(BaseModel):
    pet_id: Optional[int] = None


class ChatCreate(ChatBase):
    user2_id: int


class Chat(ChatBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user1_id: int
    user2_id: int
    created_at: datetime
    updated_at: datetime


class ChatWithLastMessage(Chat):
    model_config = ConfigDict(from_attributes=True)

    last_message: Optional[ChatMessage] = None
    unread_count: int = 0
    pet_photo_url: Optional[str] = None
    pet_name: Optional[str] = None
    pet_status: Optional[PetStatus] = None
    other_user_name: Optional[str] = None


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