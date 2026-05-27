"""Pydantic schemas for scripts."""

from typing import Optional

from pydantic import BaseModel, Field


class SceneScript(BaseModel):
    """Schema for a single scene in a script."""

    order: int
    duration_sec: float = Field(default=5.0, ge=1.0, le=30.0)
    location_key: str
    location_prompt: str = ""
    camera_key: str
    action_key: str
    voiceover_de: str
    needs_lipsync: bool = True
    caption_overlay: Optional[str] = None
    caption_position: str = "top"

    class Config:
        extra = "ignore"


class Script(BaseModel):
    """Schema for a complete script."""

    title: str
    total_duration_sec: float = 0.0
    aspect_ratio: str = "9:16"
    character_key: str = "markus_industrial"
    scenes: list[SceneScript] = Field(default_factory=list)

    def model_post_init(self, __context) -> None:
        """Calculate total duration after initialization."""
        if self.total_duration_sec == 0.0 and self.scenes:
            self.total_duration_sec = sum(s.duration_sec for s in self.scenes)

    class Config:
        extra = "ignore"


class ScriptGenerationRequest(BaseModel):
    """Request for script generation."""

    briefing: str
    character_key: str = "markus_industrial"
    target_duration_sec: float = Field(default=60.0, ge=15.0, le=180.0)
    scene_count: Optional[int] = Field(default=None, ge=3, le=15)


class ScriptYAML(BaseModel):
    """Schema for YAML script file format."""

    title: str
    aspect_ratio: str = "9:16"
    character: str = "markus_industrial"
    scenes: list[dict]

    def to_script(self) -> Script:
        """Convert YAML format to Script."""
        parsed_scenes = []
        for i, scene_data in enumerate(self.scenes, start=1):
            scene = SceneScript(
                order=scene_data.get("order", i),
                duration_sec=scene_data.get("duration", scene_data.get("duration_sec", 5.0)),
                location_key=scene_data.get("location", scene_data.get("location_key", "")),
                location_prompt=scene_data.get("location_prompt", ""),
                camera_key=scene_data.get("camera", scene_data.get("camera_key", "")),
                action_key=scene_data.get("action", scene_data.get("action_key", "")),
                voiceover_de=scene_data.get("voiceover", scene_data.get("voiceover_de", "")),
                needs_lipsync=scene_data.get("lipsync", scene_data.get("needs_lipsync", True)),
                caption_overlay=scene_data.get("caption", scene_data.get("caption_overlay")),
                caption_position=scene_data.get("caption_position", "top"),
            )
            parsed_scenes.append(scene)

        return Script(
            title=self.title,
            aspect_ratio=self.aspect_ratio,
            character_key=self.character,
            scenes=parsed_scenes,
        )
