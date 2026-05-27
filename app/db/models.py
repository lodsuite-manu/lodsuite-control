"""SQLAlchemy ORM models."""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class JobStatus(str, Enum):
    """Job status states for the state machine."""

    BRIEFING_RECEIVED = "briefing_received"
    SCRIPT_GENERATING = "script_generating"
    SCRIPT_PENDING_REVIEW = "script_pending_review"
    SCRIPT_APPROVED = "script_approved"
    STILLS_SELECTING = "stills_selecting"
    VIDEO_RENDERING = "video_rendering"
    AUDIO_RENDERING = "audio_rendering"
    LIPSYNC_RUNNING = "lipsync_running"
    ASSEMBLY_RUNNING = "assembly_running"
    FINAL_PENDING_REVIEW = "final_pending_review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobMode(str, Enum):
    """Job creation mode."""

    BRIEF = "brief"
    STRUCTURED = "structured"
    FILE = "file"


class SceneStatus(str, Enum):
    """Scene rendering status."""

    PENDING = "pending"
    RENDERING = "rendering"
    READY = "ready"
    APPROVED = "approved"
    FAILED = "failed"


class StillImageSource(str, Enum):
    """Source of still image for scene."""

    LIBRARY = "library"
    GENERATED = "generated"
    UPLOADED = "uploaded"


class Job(Base):
    """Main job entity tracking the entire ad generation process."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    telegram_user_id: Mapped[int]
    telegram_chat_id: Mapped[int]

    status: Mapped[str] = mapped_column(String(50), default=JobStatus.BRIEFING_RECEIVED.value)
    mode: Mapped[str] = mapped_column(String(20), default=JobMode.BRIEF.value)

    briefing: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    total_duration_sec: Mapped[float] = mapped_column(default=0.0)
    aspect_ratio: Mapped[str] = mapped_column(String(10), default="9:16")
    character_key: Mapped[str] = mapped_column(String(100), default="markus_industrial")

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    scenes: Mapped[list["Scene"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="Scene.order"
    )

    @property
    def job_status(self) -> JobStatus:
        """Get status as enum."""
        return JobStatus(self.status)

    @property
    def job_mode(self) -> JobMode:
        """Get mode as enum."""
        return JobMode(self.mode)


class Scene(Base):
    """Individual scene within a job."""

    __tablename__ = "scenes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    order: Mapped[int]
    duration_sec: Mapped[float] = mapped_column(default=5.0)

    # Visual
    location_key: Mapped[str] = mapped_column(String(100))
    location_prompt: Mapped[str] = mapped_column(Text, default="")
    camera_key: Mapped[str] = mapped_column(String(100))
    action_key: Mapped[str] = mapped_column(String(100))

    still_image_source: Mapped[str] = mapped_column(
        String(20), default=StillImageSource.LIBRARY.value
    )
    still_image_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Audio
    voiceover_de: Mapped[str] = mapped_column(Text, default="")
    needs_lipsync: Mapped[bool] = mapped_column(default=True)

    # Overlays
    caption_overlay: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    caption_position: Mapped[str] = mapped_column(String(20), default="top")

    # Generation
    variant_count: Mapped[int] = mapped_column(default=3)
    seed: Mapped[Optional[int]] = mapped_column(nullable=True)

    status: Mapped[str] = mapped_column(String(20), default=SceneStatus.PENDING.value)
    selected_variant_idx: Mapped[Optional[int]] = mapped_column(nullable=True)

    # Relationships
    job: Mapped["Job"] = relationship(back_populates="scenes")
    variants: Mapped[list["SceneVariant"]] = relationship(
        back_populates="scene", cascade="all, delete-orphan", order_by="SceneVariant.idx"
    )

    @property
    def scene_status(self) -> SceneStatus:
        """Get status as enum."""
        return SceneStatus(self.status)

    @property
    def image_source(self) -> StillImageSource:
        """Get still image source as enum."""
        return StillImageSource(self.still_image_source)


class SceneVariant(Base):
    """Variant of a rendered scene."""

    __tablename__ = "scene_variants"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"))
    idx: Mapped[int]

    video_path: Mapped[str] = mapped_column(String(500))
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    seed: Mapped[int]
    duration_sec: Mapped[float]

    # Relationships
    scene: Mapped["Scene"] = relationship(back_populates="variants")


class Character(Base):
    """Character/Avatar for video generation."""

    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), unique=True)  # e.g. "markus_industrial"
    name: Mapped[str] = mapped_column(String(255))  # Display name
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Image paths
    image_path: Mapped[str] = mapped_column(String(500))  # Main character image
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Voice settings (for F5-TTS)
    voice_reference_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    voice_language: Mapped[str] = mapped_column(String(10), default="de")

    # Metadata
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(default=True)
