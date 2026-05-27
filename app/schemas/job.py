"""Pydantic schemas for jobs."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.db.models import JobMode, JobStatus, SceneStatus


class SceneVariantResponse(BaseModel):
    """Response schema for scene variant."""

    id: int
    idx: int
    video_path: str
    thumbnail_path: Optional[str] = None
    seed: int
    duration_sec: float

    class Config:
        from_attributes = True


class SceneResponse(BaseModel):
    """Response schema for scene."""

    id: int
    order: int
    duration_sec: float
    location_key: str
    location_prompt: str
    camera_key: str
    action_key: str
    still_image_source: str
    still_image_path: Optional[str] = None
    voiceover_de: str
    needs_lipsync: bool
    caption_overlay: Optional[str] = None
    caption_position: str
    variant_count: int
    seed: Optional[int] = None
    status: SceneStatus
    selected_variant_idx: Optional[int] = None
    variants: list[SceneVariantResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True


class JobResponse(BaseModel):
    """Response schema for job."""

    id: str
    telegram_user_id: int
    telegram_chat_id: int
    status: JobStatus
    mode: JobMode
    briefing: str
    title: Optional[str] = None
    total_duration_sec: float
    aspect_ratio: str
    character_key: str
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str] = None
    scenes: list[SceneResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True


class JobCreateRequest(BaseModel):
    """Request schema for creating a job."""

    telegram_user_id: int
    telegram_chat_id: int
    briefing: str = ""
    mode: JobMode = JobMode.BRIEF
    character_key: str = "markus_industrial"


class JobListResponse(BaseModel):
    """Response schema for job list."""

    jobs: list[JobResponse]
    total: int


class SceneStatusUpdate(BaseModel):
    """Request schema for updating scene status."""

    status: SceneStatus
    error_message: Optional[str] = None


class VariantUploadResponse(BaseModel):
    """Response schema for variant upload."""

    variant_id: int
    scene_id: int
    idx: int
    video_path: str


class RenderTaskResponse(BaseModel):
    """Response schema for render task."""

    job_id: str
    scene_order: int
    scene_id: int
    task_type: str
    location_key: str
    location_prompt: str
    camera_key: str
    action_key: str
    duration_sec: float
    voiceover_de: str
    needs_lipsync: bool
    variant_count: int
    character_key: str


class HealthResponse(BaseModel):
    """Response schema for health check."""

    status: str
    mock_render: bool
    mock_script: bool
