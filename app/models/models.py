# app/models/models.py (обновление модели Pet)
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Float, DateTime, Enum, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.db.database import Base
import uuid
from datetime import datetime


class PetStatus(str, enum.Enum):
    LOST = "lost"
    FOUND = "found"
    HOME = "home"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, index=True)
    phone = Column(String)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    last_active_at = Column(DateTime, nullable=True)
    is_online = Column(Boolean, default=False)

    pets = relationship("Pet", back_populates="owner")
    notifications = relationship("Notification", back_populates="user")
    verification_codes = relationship("VerificationCode", back_populates="user")


class Pet(Base):
    __tablename__ = "pets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    species = Column(String, index=True)
    breed = Column(String, index=True)
    age = Column(Integer, nullable=True)
    color = Column(String)
    gender = Column(String)
    distinctive_features = Column(Text, nullable=True)
    status = Column(Enum(PetStatus), default=PetStatus.HOME)
    last_seen_location = Column(String, nullable=True)
    coordX = Column(String, nullable=True)
    coordY = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    lost_date = Column(DateTime, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="pets")
    photos = relationship("PetPhoto", back_populates="pet", cascade="all, delete-orphan")
    matches = relationship("PetMatch", foreign_keys="[PetMatch.found_pet_id]", back_populates="found_pet", cascade="all, delete-orphan")
    lost_matches = relationship("PetMatch", foreign_keys="[PetMatch.lost_pet_id]", back_populates="lost_pet", cascade="all, delete-orphan")
    chats = relationship("Chat", back_populates="pet", cascade="all, delete-orphan")


class PetPhoto(Base):
    __tablename__ = "pet_photos"

    id = Column(Integer, primary_key=True, index=True)
    pet_id = Column(Integer, ForeignKey("pets.id"), nullable=False)
    photo_url = Column(String, nullable=False)
    is_primary = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())

    pet = relationship("Pet", back_populates="photos")


class PetMatch(Base):
    __tablename__ = "pet_matches"

    id = Column(Integer, primary_key=True, index=True)
    found_pet_id = Column(Integer, ForeignKey("pets.id"))
    lost_pet_id = Column(Integer, ForeignKey("pets.id"))
    similarity_score = Column(Float)
    created_at = Column(DateTime, default=func.now())

    found_pet = relationship("Pet", foreign_keys=[found_pet_id], back_populates="matches")
    lost_pet = relationship("Pet", foreign_keys=[lost_pet_id], back_populates="lost_matches")
    notifications = relationship("Notification", back_populates="match", cascade="all, delete-orphan")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    match_id = Column(Integer, ForeignKey("pet_matches.id"))
    message = Column(Text)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())

    user = relationship("User", back_populates="notifications")
    match = relationship("PetMatch", back_populates="notifications")


class VerificationCode(Base):
    __tablename__ = "verification_codes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    code = Column(String, nullable=False)
    is_used = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=func.now())

    user = relationship("User", back_populates="verification_codes")


class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    user1_id = Column(Integer, ForeignKey("users.id"))
    user2_id = Column(Integer, ForeignKey("users.id"))
    pet_id = Column(Integer, ForeignKey("pets.id", ondelete="CASCADE"), nullable=True)

    user1 = relationship("User", foreign_keys=[user1_id])
    user2 = relationship("User", foreign_keys=[user2_id])
    pet = relationship("Pet", foreign_keys=[pet_id], back_populates="chats")
    messages = relationship("ChatMessage", back_populates="chat", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())

    chat = relationship("Chat", back_populates="messages")
    sender = relationship("User")