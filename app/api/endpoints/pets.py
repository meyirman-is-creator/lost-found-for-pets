from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from sqlalchemy.orm import Session, joinedload
from typing import Any, List, Optional
from datetime import datetime
import json

from app.api.dependencies import get_current_user, get_verified_user
from app.db.database import get_db
from app.models.models import Pet, PetStatus, User, PetPhoto
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

router = APIRouter()


@router.get("/lost", response_model=List[PetSchema])
def get_lost_pets(
        skip: int = 0,
        limit: int = 100,
        species: Optional[str] = None,
        db: Session = Depends(get_db)
) -> Any:
    """
    Get list of lost pets
    """
    query = db.query(Pet).filter(Pet.status == PetStatus.LOST)

    if species:
        query = query.filter(Pet.species == species)

    # Используем joinedload для подгрузки фотографий питомцев
    pets = (query
            .options(joinedload(Pet.photos))
            .order_by(Pet.lost_date.desc())
            .offset(skip)
            .limit(limit)
            .all())
    return pets


@router.get("/lost/{pet_id}", response_model=PetSchema)
def get_lost_pet(
        pet_id: int,
        db: Session = Depends(get_db)
) -> Any:
    """
    Get details of a specific lost pet
    """
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
    """
    Get list of current user's pets
    """
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
    """
    Create a new pet with multiple photos
    """
    # Create pet without photos first
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

    # Process and upload photos
    primary_photo_set = False
    for i, photo in enumerate(photos):
        file_content = await photo.read()
        photo_url = s3_client.upload_file(
            file_content,
            f"{current_user.id}_{db_pet.id}_{datetime.now().timestamp()}_{photo.filename}"
        )

        if not photo_url:
            # If photo upload fails, continue with next photo
            continue

        # First photo is set as primary by default
        is_primary = (i == 0) or not primary_photo_set
        if is_primary:
            primary_photo_set = True

        # Create photo record
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
    """
    Update pet information
    """
    pet = (db.query(Pet)
           .filter(Pet.id == pet_id, Pet.owner_id == current_user.id)
           .options(joinedload(Pet.photos))
           .first())
    if not pet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pet not found"
        )

    # Update status if changed to "lost"
    original_status = pet.status

    # Update pet fields
    for key, value in pet_in.dict(exclude_unset=True).items():
        setattr(pet, key, value)

    # If status changed to lost, update lost_date
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
    """
    Add new photos to an existing pet
    """
    pet = db.query(Pet).filter(Pet.id == pet_id, Pet.owner_id == current_user.id).first()
    if not pet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pet not found"
        )

    # Check if there are any existing photos to determine if we need to set primary
    existing_photos = db.query(PetPhoto).filter(PetPhoto.pet_id == pet_id).all()
    has_primary = any(photo.is_primary for photo in existing_photos)

    # Process and upload photos
    uploaded_photos = []
    for i, photo in enumerate(photos):
        file_content = await photo.read()
        photo_url = s3_client.upload_file(
            file_content,
            f"{current_user.id}_{pet_id}_{datetime.now().timestamp()}_{photo.filename}"
        )

        if not photo_url:
            # If photo upload fails, continue with next photo
            continue

        # Set as primary if requested or if no primary exists
        is_primary = (i == 0 and set_primary) or (i == 0 and not has_primary)

        # If we're setting a new primary, unset all others
        if is_primary:
            db.query(PetPhoto).filter(
                PetPhoto.pet_id == pet_id,
                PetPhoto.is_primary == True
            ).update({"is_primary": False})

        # Create photo record
        db_photo = PetPhoto(
            pet_id=pet_id,
            photo_url=photo_url,
            is_primary=is_primary
        )
        db.add(db_photo)
        uploaded_photos.append(db_photo)

    db.commit()

    # Refresh all photos to get their IDs
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
    """
    Set a specific photo as the primary photo for a pet
    """
    # Verify the pet belongs to the current user
    pet = db.query(Pet).filter(Pet.id == pet_id, Pet.owner_id == current_user.id).first()
    if not pet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pet not found"
        )

    # Get the photo to set as primary
    photo = db.query(PetPhoto).filter(PetPhoto.id == photo_id, PetPhoto.pet_id == pet_id).first()
    if not photo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found"
        )

    # Set all photos as non-primary
    db.query(PetPhoto).filter(PetPhoto.pet_id == pet_id).update({"is_primary": False})

    # Set the selected photo as primary
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
    """
    Delete a pet photo
    """
    # Verify the pet belongs to the current user
    pet = db.query(Pet).filter(Pet.id == pet_id, Pet.owner_id == current_user.id).first()
    if not pet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pet not found"
        )

    # Get the photo to delete
    photo = db.query(PetPhoto).filter(PetPhoto.id == photo_id, PetPhoto.pet_id == pet_id).first()
    if not photo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found"
        )

    # If this is the primary photo, find another photo to set as primary
    if photo.is_primary:
        next_photo = db.query(PetPhoto).filter(
            PetPhoto.pet_id == pet_id,
            PetPhoto.id != photo_id
        ).first()

        if next_photo:
            next_photo.is_primary = True
            db.add(next_photo)

    # Try to delete from S3 first
    if photo.photo_url:
        s3_client.delete_file(photo.photo_url)

    # Delete from database
    db.delete(photo)
    db.commit()

    return {"message": "Photo deleted successfully"}


@router.delete("/{pet_id}", response_model=dict)
def delete_pet(
        pet_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    """
    Delete a pet and all its photos
    """
    pet = db.query(Pet).filter(Pet.id == pet_id, Pet.owner_id == current_user.id).first()
    if not pet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pet not found"
        )

    # Get all photos to delete from S3
    photos = db.query(PetPhoto).filter(PetPhoto.pet_id == pet_id).all()

    # Delete photos from S3
    for photo in photos:
        if photo.photo_url:
            s3_client.delete_file(photo.photo_url)

    # The pet and its photos will be deleted from the database (cascade delete)
    db.delete(pet)
    db.commit()

    return {"message": "Pet deleted successfully"}