"""Script parsing from YAML files."""

from pathlib import Path
from typing import Union

import structlog
import yaml

from app.schemas.script import Script, SceneScript, ScriptYAML
from app.services.library import get_library

logger = structlog.get_logger()


class ScriptParseError(Exception):
    """Raised when script parsing fails."""

    pass


def parse_yaml_script(content: str) -> Script:
    """Parse a YAML script string into a Script object."""
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise ScriptParseError(f"Invalid YAML: {e}")

    if not isinstance(data, dict):
        raise ScriptParseError("Script must be a YAML dictionary")

    # Validate required fields
    if "title" not in data:
        raise ScriptParseError("Script must have a 'title' field")

    if "scenes" not in data or not isinstance(data["scenes"], list):
        raise ScriptParseError("Script must have a 'scenes' list")

    if len(data["scenes"]) < 1:
        raise ScriptParseError("Script must have at least one scene")

    # Parse using Pydantic
    try:
        yaml_script = ScriptYAML(
            title=data["title"],
            aspect_ratio=data.get("aspect_ratio", "9:16"),
            character=data.get("character", "markus_industrial"),
            scenes=data["scenes"],
        )
        return yaml_script.to_script()
    except Exception as e:
        raise ScriptParseError(f"Script validation failed: {e}")


def parse_yaml_file(file_path: Union[str, Path]) -> Script:
    """Parse a YAML script file."""
    path = Path(file_path)
    if not path.exists():
        raise ScriptParseError(f"File not found: {path}")

    with open(path) as f:
        content = f.read()

    return parse_yaml_script(content)


def validate_script(script: Script) -> list[str]:
    """Validate a script and return list of warnings/errors."""
    warnings = []
    library = get_library()

    # Check total duration
    if script.total_duration_sec < 15:
        warnings.append(f"Total duration ({script.total_duration_sec}s) is very short")
    if script.total_duration_sec > 120:
        warnings.append(f"Total duration ({script.total_duration_sec}s) is very long")

    # Check each scene
    for scene in script.scenes:
        # Validate location
        if scene.location_key and scene.location_key not in library.get_location_keys():
            warnings.append(f"Scene {scene.order}: Unknown location '{scene.location_key}'")

        # Validate camera
        if scene.camera_key and scene.camera_key not in library.get_camera_keys():
            warnings.append(f"Scene {scene.order}: Unknown camera '{scene.camera_key}'")

        # Validate action
        if scene.action_key and scene.action_key not in library.get_action_keys():
            warnings.append(f"Scene {scene.order}: Unknown action '{scene.action_key}'")

        # Check camera-action compatibility
        if scene.camera_key and scene.action_key:
            if not library.is_camera_compatible(scene.camera_key, scene.action_key):
                warnings.append(
                    f"Scene {scene.order}: Camera '{scene.camera_key}' may not work well "
                    f"with action '{scene.action_key}'"
                )

        # Validate voiceover
        if scene.needs_lipsync and not scene.voiceover_de:
            warnings.append(f"Scene {scene.order}: Lipsync enabled but no voiceover text")

        # Check scene duration
        if scene.duration_sec < 2:
            warnings.append(f"Scene {scene.order}: Duration ({scene.duration_sec}s) is very short")
        if scene.duration_sec > 15:
            warnings.append(f"Scene {scene.order}: Duration ({scene.duration_sec}s) is very long")

    return warnings


def script_to_yaml(script: Script) -> str:
    """Convert a Script object to YAML string."""
    data = {
        "title": script.title,
        "aspect_ratio": script.aspect_ratio,
        "character": script.character_key,
        "scenes": [],
    }

    for scene in script.scenes:
        scene_data = {
            "order": scene.order,
            "duration": scene.duration_sec,
            "location": scene.location_key,
            "camera": scene.camera_key,
            "action": scene.action_key,
            "voiceover": scene.voiceover_de,
            "lipsync": scene.needs_lipsync,
        }
        if scene.caption_overlay:
            scene_data["caption"] = scene.caption_overlay
            scene_data["caption_position"] = scene.caption_position
        if scene.location_prompt:
            scene_data["location_prompt"] = scene.location_prompt

        data["scenes"].append(scene_data)

    return yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)


def format_script_for_display(script: Script) -> str:
    """Format a script for Telegram display."""
    library = get_library()
    lines = []

    # Header
    lines.append(f"📋 Skript \"{script.title}\"")
    lines.append(f"⏱ {script.total_duration_sec:.0f}s | {len(script.scenes)} Szenen | Charakter: {script.character_key}")
    lines.append("")

    # Scenes
    for scene in script.scenes:
        # Calculate time range
        start_time = sum(s.duration_sec for s in script.scenes if s.order < scene.order)
        end_time = start_time + scene.duration_sec

        # Scene header
        lines.append(f"{scene.order}️⃣ {start_time:.0f}-{end_time:.0f}s | {scene.location_key} | {scene.camera_key}")

        # Voiceover
        if scene.voiceover_de:
            vo_preview = scene.voiceover_de[:60] + "..." if len(scene.voiceover_de) > 60 else scene.voiceover_de
            lines.append(f"   🎙 \"{vo_preview}\"")

        # Caption
        if scene.caption_overlay:
            lines.append(f"   💬 \"{scene.caption_overlay}\"")

        # Lipsync indicator
        if scene.needs_lipsync:
            lines.append("   ✓ Lipsync")

        lines.append("")

    return "\n".join(lines)
