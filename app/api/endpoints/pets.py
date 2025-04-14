from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Any, List, Optional
from datetime import datetime
import json

from app.api.dependencies import get_current_user, get_verified_user
from app.db.database import get_db
from app.models.models import Pet, PetStatus, User
from app.schemas.schemas import (
    Pet as PetSchema,
    PetCreate,
    PetUpdate,
    FoundPetInfo,
    SimilarityResponse,
    SimilarityResult
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

    pets = query.order_by(Pet.lost_date.desc()).offset(skip).limit(limit).all()
    return pets


@router.get("/lost/{pet_id}", response_model=PetSchema)
def get_lost_pet(
        pet_id: int,
        db: Session = Depends(get_db)
) -> Any:
    """
    Get details of a specific lost pet
    """
    pet = db.query(Pet).filter(Pet.id == pet_id, Pet.status == PetStatus.LOST).first()
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
    pets = db.query(Pet).filter(Pet.owner_id == current_user.id).all()
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
        photo: UploadFile = File(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    """
    Create a new pet
    """
    # Upload photo to S3
    file_content = await photo.read()
    photo_url = s3_client.upload_file(file_content, f"{current_user.id}_{datetime.now().timestamp()}_{photo.filename}")

    if not photo_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload photo"
        )

    # Create pet
    db_pet = Pet(
        name=name,
        species=species,
        breed=breed,
        age=age,
        color=color,
        gender=gender,
        distinctive_features=distinctive_features,
        photo_url=photo_url,
        status=PetStatus.HOME,
        owner_id=current_user.id
    )

    db.add(db_pet)
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
    pet = db.query(Pet).filter(Pet.id == pet_id, Pet.owner_id == current_user.id).first()
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


@router.post("/upload-photo/{pet_id}", response_model=PetSchema)
async def upload_pet_photo(
        pet_id: int,
        photo: UploadFile = File(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    """
    Upload a new photo for a pet
    """
    pet = db.query(Pet).filter(Pet.id == pet_id, Pet.owner_id == current_user.id).first()
    if not pet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pet not found"
        )

    # Upload photo to S3
    file_content = await photo.read()
    photo_url = s3_client.upload_file(file_content, f"{current_user.id}_{datetime.now().timestamp()}_{photo.filename}")

    if not photo_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload photo"
        )

    # Update pet photo URL
    pet.photo_url = photo_url
    db.add(pet)
    db.commit()
    db.refresh(pet)

    return pet


@router.delete("/{pet_id}", response_model=dict)
def delete_pet(
        pet_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_verified_user)
) -> Any:
    """
    Delete a pet
    """
    pet = db.query(Pet).filter(Pet.id == pet_id, Pet.owner_id == current_user.id).first()
    if not pet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pet not found"
        )

    db.delete(pet)
    db.commit()

    return {"message": "Pet deleted successfully"}


@router.post("/search", response_model=SimilarityResponse)
async def search_similar_pets(
        pet_info: FoundPetInfo,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
) -> Any:
    """
    Search for similar pets based on uploaded photo
    """
    # Upload photo to S3
    photo_url = s3_client.upload_base64_image(
        pet_info.photo_base64,
        f"found_{current_user.id}_{datetime.now().timestamp()}.jpg"
    )

    if not photo_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload photo"
        )

    # Get lost pets matching the species
    query = db.query(Pet).filter(Pet.status == PetStatus.LOST)

    if pet_info.species:
        query = query.filter(Pet.species == pet_info.species)

    lost_pets = query.all()

    # Calculate similarity for each lost pet
    matches = []
    for pet in lost_pets:
        similarity = similarity_service.compute_similarity(photo_url, pet.photo_url)
        matches.append({"pet": pet, "similarity_score": similarity})

    # Sort by similarity score (descending) and keep only significant matches
    matches.sort(key=lambda x: x["similarity_score"], reverse=True)
    significant_matches = [match for match in matches if match["similarity_score"] > 0.3]

    # Create a found pet entry for future reference
    found_pet = Pet(
        name="Found Pet",
        species=pet_info.species,
        breed=pet_info.breed,
        color=pet_info.color,
        distinctive_features=pet_info.distinctive_features,
        photo_url=photo_url,
        status=PetStatus.FOUND,
        last_seen_location=pet_info.location,
        owner_id=current_user.id
    )

    db.add(found_pet)
    db.commit()
    db.refresh(found_pet)

    # Return top matches
    return SimilarityResponse(
        matches=[
            SimilarityResult(pet=match["pet"], similarity_score=match["similarity_score"])
            for match in significant_matches
        ]
    )