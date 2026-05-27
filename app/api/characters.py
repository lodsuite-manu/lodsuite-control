"""Character management endpoints."""

import shutil
import uuid
from pathlib import Path
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status, Form
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.database import get_session
from app.db.models import Character

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/characters", tags=["characters"])


# Pydantic schemas
from pydantic import BaseModel


class CharacterResponse(BaseModel):
    id: int
    key: str
    name: str
    description: Optional[str] = None
    image_url: str
    voice_language: str
    is_active: bool

    class Config:
        from_attributes = True


class CharacterListResponse(BaseModel):
    characters: list[CharacterResponse]
    total: int


@router.get("", response_model=CharacterListResponse)
async def list_characters(
    session: AsyncSession = Depends(get_session),
) -> CharacterListResponse:
    """List all characters."""
    result = await session.execute(
        select(Character).where(Character.is_active == True).order_by(Character.name)
    )
    characters = list(result.scalars().all())

    return CharacterListResponse(
        characters=[
            CharacterResponse(
                id=c.id,
                key=c.key,
                name=c.name,
                description=c.description,
                image_url=f"/api/v1/characters/{c.key}/image",
                voice_language=c.voice_language,
                is_active=c.is_active,
            )
            for c in characters
        ],
        total=len(characters),
    )


@router.get("/{key}", response_model=CharacterResponse)
async def get_character(
    key: str,
    session: AsyncSession = Depends(get_session),
) -> CharacterResponse:
    """Get character by key."""
    result = await session.execute(select(Character).where(Character.key == key))
    character = result.scalar_one_or_none()

    if character is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character not found: {key}",
        )

    return CharacterResponse(
        id=character.id,
        key=character.key,
        name=character.name,
        description=character.description,
        image_url=f"/api/v1/characters/{character.key}/image",
        voice_language=character.voice_language,
        is_active=character.is_active,
    )


@router.post("", response_model=CharacterResponse, status_code=status.HTTP_201_CREATED)
async def create_character(
    name: str = Form(...),
    key: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    voice_language: str = Form("de"),
    image: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> CharacterResponse:
    """Create a new character with image upload."""
    # Generate key from name if not provided
    if not key:
        key = name.lower().replace(" ", "_").replace("-", "_")
        # Remove special characters
        key = "".join(c for c in key if c.isalnum() or c == "_")

    # Check if key already exists
    result = await session.execute(select(Character).where(Character.key == key))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Character with key '{key}' already exists",
        )

    # Save image
    settings = get_settings()
    characters_dir = settings.characters_dir / key
    characters_dir.mkdir(parents=True, exist_ok=True)

    # Determine file extension
    ext = Path(image.filename).suffix if image.filename else ".png"
    image_path = characters_dir / f"avatar{ext}"

    with open(image_path, "wb") as f:
        content = await image.read()
        f.write(content)

    # Create character record
    character = Character(
        key=key,
        name=name,
        description=description,
        image_path=str(image_path),
        voice_language=voice_language,
    )
    session.add(character)
    await session.flush()
    await session.refresh(character)

    logger.info("Character created", key=key, name=name)

    return CharacterResponse(
        id=character.id,
        key=character.key,
        name=character.name,
        description=character.description,
        image_url=f"/api/v1/characters/{character.key}/image",
        voice_language=character.voice_language,
        is_active=character.is_active,
    )


@router.get("/{key}/image")
async def get_character_image(
    key: str,
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    """Get character image."""
    result = await session.execute(select(Character).where(Character.key == key))
    character = result.scalar_one_or_none()

    if character is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character not found: {key}",
        )

    image_path = Path(character.image_path)
    if not image_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character image not found",
        )

    return FileResponse(
        path=image_path,
        media_type="image/png",
        filename=f"{key}.png",
    )


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_character(
    key: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a character."""
    result = await session.execute(select(Character).where(Character.key == key))
    character = result.scalar_one_or_none()

    if character is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character not found: {key}",
        )

    # Delete image files
    settings = get_settings()
    characters_dir = settings.characters_dir / key
    if characters_dir.exists():
        shutil.rmtree(characters_dir)

    await session.delete(character)
    await session.flush()

    logger.info("Character deleted", key=key)


@router.post("/{key}/voice")
async def upload_voice_reference(
    key: str,
    audio: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Upload voice reference audio for character."""
    result = await session.execute(select(Character).where(Character.key == key))
    character = result.scalar_one_or_none()

    if character is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character not found: {key}",
        )

    # Save audio file
    settings = get_settings()
    characters_dir = settings.characters_dir / key
    characters_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(audio.filename).suffix if audio.filename else ".wav"
    audio_path = characters_dir / f"voice_reference{ext}"

    with open(audio_path, "wb") as f:
        content = await audio.read()
        f.write(content)

    # Update character
    character.voice_reference_path = str(audio_path)
    await session.flush()

    logger.info("Voice reference uploaded", key=key)

    return {"status": "ok", "path": str(audio_path)}
