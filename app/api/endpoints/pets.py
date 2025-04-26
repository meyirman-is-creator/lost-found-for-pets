# app/api/endpoints/pets.py
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from sqlalchemy.orm import Session, joinedload
from typing import Any, List, Optional
from datetime import datetime
import json
import logging

from app.api.dependencies import get_current_user, get_verified_user
from app.db.database import get_db
from app.models.models import Pet, PetStatus, User, PetPhoto, Chat, PetMatch, Notification, FoundPet
from app.schemas.schemas import (
    Pet as PetSchema,
    PetCreate,
    PetUpdate,
    FoundPetInfo,
    SimilarityResponse,
    SimilarityResult,
    PetPhoto as PetPhotoSchema
)
from app.services.aws.s3 import s3_client
from app.services.cv.similarity import similarity_service
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/lost", response_model=List[PetSchema])
def get_lost_pets(
        skip: int = 0,
        limit: int = 100,
        species: Optional[str] = None,
        db: Session = Depends(get_db)
) -> Any:
    query = db.query(Pet).filter(Pet.status == PetStatus.LOST)

    if species:
        query = query.filter(Pet.species == species)

    pets = (query
            .options(joinedload(Pet.photos))
            .order_by(Pet.lost_date.desc())
            .offset(skip)
            .limit(limit)
            .all())
    return pets


@router.get("/found", response_model=List[PetSchema])
def get_found_pets(
        skip: int = 0,
        limit: int = 100,
        species: Optional[str] = None,
        db: Session = Depends(get_db)
) -> Any:
    query = db.query(Pet).filter(Pet.status == PetStatus.FOUND)

    if species:
        query = query.filter(Pet.species == species)

    # Получаем найденных питомцев с фотографиями
    pets = (query
            .options(joinedload(Pet.photos))
            .options(joinedload(Pet.found_locations))  # Добавляем подгрузку координат
            .order_by(Pet.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all())

    # Заполняем координаты для каждого питомца из связанной таблицы found_locations
    for pet in pets:
        if pet.found_locations and len(pet.found_locations) > 0:
            pet.coordX = pet.found_locations[0].coordX
            pet.coordY = pet.found_locations[0].coordY

    return pets


@router.get("/found/{pet_id}", response_model=PetSchema)
def get_found_pet(
        pet_id: int,
        db: Session = Depends(get_db)
) -> Any:
    pet = (db.query(Pet)
           .filter(Pet.id == pet_id, Pet.status == PetStatus.FOUND)
           .options(joinedload(Pet.photos))
           .options(joinedload(Pet.found_locations))  # Добавляем подгрузку координат
           .first())
    if not pet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pet not found"
        )

    # Заполняем координаты из связанной таблицы found_locations
    if pet.found_locations and len(pet.found_locations) > 0:
        pet.coordX = pet.found_locations[0].coordX
        pet.coordY = pet.found_locations[0].coordY

    return pet

@router.get("/lost/{pet_id}", response_model=PetSchema)
def get_lost_pet(
        pet_id: int,
        db: Session = Depends(get_db)
) -> Any:
    pet = (db.query(Pet)
           .filter(Pet.id == pet_id, Pet.status == PetStatus.LOST)
           .options(joinedload(Pet.photos))
           .first())
    if not pet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pet not found"
        )
    return pet


@router.get("/my", response_model=List[PetSchema])
def get_my_pets(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    pets = (db.query(Pet)
            .filter(Pet.owner_id == current_user.id)
            .options(joinedload(Pet.photos))
            .all())
    return pets


@router.post("", response_model=PetSchema)
async def create_pet(
        name: str = Form(...),
        species: str = Form(...),
        breed: Optional[str] = Form(None),
        age: Optional[int] = Form(None),
        color: Optional[str] = Form(None),
        gender: Optional[str] = Form(None),
        distinctive_features: Optional[str] = Form(None),
        photos: List[UploadFile] = File(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    db_pet = Pet(
        name=name,
        species=species,
        breed=breed,
        age=age,
        color=color,
        gender=gender,
        distinctive_features=distinctive_features,
        status=PetStatus.HOME,
        owner_id=current_user.id
    )

    db.add(db_pet)
    db.commit()
    db.refresh(db_pet)

    primary_photo_set = False
    for i, photo in enumerate(photos):
        file_content = await photo.read()
        photo_url = s3_client.upload_file(
            file_content,
            f"{current_user.id}_{db_pet.id}_{datetime.now().timestamp()}_{photo.filename}"
        )

        if not photo_url:
            continue

        is_primary = (i == 0) or not primary_photo_set
        if is_primary:
            primary_photo_set = True

        db_photo = PetPhoto(
            pet_id=db_pet.id,
            photo_url=photo_url,
            is_primary=is_primary
        )
        db.add(db_photo)

    db.commit()
    db.refresh(db_pet)

    return db_pet


@router.patch("/{pet_id}", response_model=PetSchema)
def update_pet(
        pet_id: int,
        pet_in: PetUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    pet = (db.query(Pet)
           .filter(Pet.id == pet_id, Pet.owner_id == current_user.id)
           .options(joinedload(Pet.photos))
           .first())
    if not pet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pet not found"
        )

    original_status = pet.status

    for key, value in pet_in.dict(exclude_unset=True).items():
        setattr(pet, key, value)

    if original_status != PetStatus.LOST and pet.status == PetStatus.LOST:
        pet.lost_date = datetime.utcnow()

    db.add(pet)
    db.commit()
    db.refresh(pet)

    return pet


@router.post("/{pet_id}/photos", response_model=List[PetPhotoSchema])
async def add_pet_photos(
        pet_id: int,
        photos: List[UploadFile] = File(...),
        set_primary: bool = Query(False, description="Set first uploaded photo as primary"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    pet = db.query(Pet).filter(Pet.id == pet_id, Pet.owner_id == current_user.id).first()
    if not pet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pet not found"
        )

    existing_photos = db.query(PetPhoto).filter(PetPhoto.pet_id == pet_id).all()
    has_primary = any(photo.is_primary for photo in existing_photos)

    uploaded_photos = []
    for i, photo in enumerate(photos):
        file_content = await photo.read()
        photo_url = s3_client.upload_file(
            file_content,
            f"{current_user.id}_{pet_id}_{datetime.now().timestamp()}_{photo.filename}"
        )

        if not photo_url:
            continue

        is_primary = (i == 0 and set_primary) or (i == 0 and not has_primary)

        if is_primary:
            db.query(PetPhoto).filter(
                PetPhoto.pet_id == pet_id,
                PetPhoto.is_primary == True
            ).update({"is_primary": False})

        db_photo = PetPhoto(
            pet_id=pet_id,
            photo_url=photo_url,
            is_primary=is_primary
        )
        db.add(db_photo)
        uploaded_photos.append(db_photo)

    db.commit()

    for photo in uploaded_photos:
        db.refresh(photo)

    return uploaded_photos


@router.patch("/{pet_id}/photos/{photo_id}/set-primary", response_model=PetPhotoSchema)
def set_primary_photo(
        pet_id: int,
        photo_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    pet = db.query(Pet).filter(Pet.id == pet_id, Pet.owner_id == current_user.id).first()
    if not pet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pet not found"
        )

    photo = db.query(PetPhoto).filter(PetPhoto.id == photo_id, PetPhoto.pet_id == pet_id).first()
    if not photo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found"
        )

    db.query(PetPhoto).filter(PetPhoto.pet_id == pet_id).update({"is_primary": False})

    photo.is_primary = True
    db.add(photo)
    db.commit()
    db.refresh(photo)

    return photo


@router.delete("/{pet_id}/photos/{photo_id}", response_model=dict)
def delete_pet_photo(
        pet_id: int,
        photo_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    pet = db.query(Pet).filter(Pet.id == pet_id, Pet.owner_id == current_user.id).first()
    if not pet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pet not found"
        )

    photo = db.query(PetPhoto).filter(PetPhoto.id == photo_id, PetPhoto.pet_id == pet_id).first()
    if not photo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found"
        )

    if photo.is_primary:
        next_photo = db.query(PetPhoto).filter(
            PetPhoto.pet_id == pet_id,
            PetPhoto.id != photo_id
        ).first()

        if next_photo:
            next_photo.is_primary = True
            db.add(next_photo)

    if photo.photo_url:
        s3_client.delete_file(photo.photo_url)

    db.delete(photo)
    db.commit()

    return {"message": "Photo deleted successfully"}


@router.delete("/{pet_id}", response_model=dict)
def delete_pet(
        pet_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    pet = db.query(Pet).filter(Pet.id == pet_id, Pet.owner_id == current_user.id).first()
    if not pet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pet not found"
        )

    photos = db.query(PetPhoto).filter(PetPhoto.pet_id == pet_id).all()

    for photo in photos:
        if photo.photo_url:
            s3_client.delete_file(photo.photo_url)

    try:
        db.delete(pet)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting pet {pet_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete pet. There might be related records."
        )

    return {"message": "Pet deleted successfully"}


@router.post("/search", response_model=SimilarityResponse)
async def search_pets(
        photo: UploadFile = File(...),
        species: str = Form(...),
        color: str = Form(...),
        save: bool = Form(...),
        coordX: Optional[str] = Form(None),
        coordY: Optional[str] = Form(None),
        gender: Optional[str] = Form(None),
        breed: Optional[str] = Form(None),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    if save and (coordX is None or coordY is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Coordinates (coordX and coordY) are required when saving a found pet"
        )

    photo_content = await photo.read()

    found_pet_photo_url = s3_client.upload_file(
        photo_content,
        f"found_pets/{current_user.id}_{datetime.now().timestamp()}_{photo.filename}"
    )

    if not found_pet_photo_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload photo"
        )

    if save:
        # Создаем новую запись о питомце без координат в основной таблице
        db_pet = Pet(
            name=f"Found {species.capitalize()}",
            species=species,
            breed=breed,
            color=color,
            gender=gender,
            status=PetStatus.FOUND,
            last_seen_location=f"Coordinates: {coordX}, {coordY}",
            owner_id=current_user.id
        )

        db.add(db_pet)
        db.commit()
        db.refresh(db_pet)

        # Добавляем фото питомца
        db_photo = PetPhoto(
            pet_id=db_pet.id,
            photo_url=found_pet_photo_url,
            is_primary=True
        )
        db.add(db_photo)

        # Создаем запись о координатах найденного питомца
        db_found_pet = FoundPet(
            pet_id=db_pet.id,
            coordX=coordX,
            coordY=coordY
        )
        db.add(db_found_pet)
        db.commit()

    query = db.query(Pet).filter(Pet.status == PetStatus.LOST)

    query = query.filter(Pet.species == species)

    query = query.filter(Pet.color.ilike(f"%{color}%"))

    if gender:
        query = query.filter(Pet.gender == gender)

    if breed:
        query = query.filter(Pet.breed.ilike(f"%{breed}%"))

    potential_matches = query.options(joinedload(Pet.photos)).all()

    logger.info(f"Found {len(potential_matches)} potential matches after filtering")

    if not potential_matches:
        if not save:
            s3_client.delete_file(found_pet_photo_url)
        return {"matches": []}

    similarity_results = []

    similarity_threshold = 0.35

    for pet in potential_matches:
        pet_photos = [photo for photo in pet.photos if photo.is_primary]
        if not pet_photos and pet.photos:
            pet_photos = [pet.photos[0]]

        if not pet_photos:
            continue

        pet_photo_url = pet_photos[0].photo_url

        try:
            similarity_score = similarity_service.compute_similarity(
                found_pet_photo_url, pet_photo_url
            )

            logger.info(f"Pet ID {pet.id}, similarity score: {similarity_score}")

            if similarity_score >= similarity_threshold:
                similarity_results.append(
                    SimilarityResult(
                        pet=pet,
                        similarity_score=similarity_score
                    )
                )
        except Exception as e:
            logger.error(f"Error computing similarity for pet {pet.id}: {e}")
            continue

    similarity_results.sort(key=lambda x: x.similarity_score, reverse=True)

    if not save:
        s3_client.delete_file(found_pet_photo_url)

    return {"matches": similarity_results}