"""Asset library loading and matching."""

import json
from pathlib import Path
from typing import Optional

import structlog

from app.config import get_settings

logger = structlog.get_logger()


class AssetLibrary:
    """Loads and provides access to prompt library assets."""

    def __init__(self, library_dir: Optional[Path] = None):
        settings = get_settings()
        self.library_dir = library_dir or settings.library_dir
        self._locations: dict = {}
        self._cameras: dict = {}
        self._actions: dict = {}
        self._loaded = False

    def load(self) -> None:
        """Load all asset files."""
        if self._loaded:
            return

        prompts_dir = self.library_dir / "prompts"

        # Load locations
        locations_path = prompts_dir / "locations.json"
        if locations_path.exists():
            with open(locations_path) as f:
                self._locations = json.load(f)
            logger.info("Loaded locations", count=len(self._locations))

        # Load cameras
        cameras_path = prompts_dir / "cameras.json"
        if cameras_path.exists():
            with open(cameras_path) as f:
                self._cameras = json.load(f)
            logger.info("Loaded cameras", count=len(self._cameras))

        # Load actions
        actions_path = prompts_dir / "actions.json"
        if actions_path.exists():
            with open(actions_path) as f:
                self._actions = json.load(f)
            logger.info("Loaded actions", count=len(self._actions))

        self._loaded = True

    @property
    def locations(self) -> dict:
        """Get locations dictionary."""
        if not self._loaded:
            self.load()
        return self._locations

    @property
    def cameras(self) -> dict:
        """Get cameras dictionary."""
        if not self._loaded:
            self.load()
        return self._cameras

    @property
    def actions(self) -> dict:
        """Get actions dictionary."""
        if not self._loaded:
            self.load()
        return self._actions

    def get_location(self, key: str) -> Optional[dict]:
        """Get location by key."""
        return self.locations.get(key)

    def get_location_prompt(self, key: str) -> str:
        """Get location prompt string."""
        location = self.get_location(key)
        if location:
            return location.get("prompt", "")
        return ""

    def get_camera(self, key: str) -> Optional[dict]:
        """Get camera by key."""
        return self.cameras.get(key)

    def get_camera_prompt(self, key: str) -> str:
        """Get camera prompt string."""
        camera = self.get_camera(key)
        if camera:
            return camera.get("prompt", "")
        return ""

    def get_action(self, key: str) -> Optional[dict]:
        """Get action by key."""
        return self.actions.get(key)

    def get_action_prompt(self, key: str) -> str:
        """Get action prompt string."""
        action = self.get_action(key)
        if action:
            return action.get("prompt", "")
        return ""

    def action_needs_lipsync(self, key: str) -> bool:
        """Check if action requires lipsync."""
        action = self.get_action(key)
        if action:
            return action.get("needs_lipsync", True)
        return True

    def is_camera_compatible(self, camera_key: str, action_key: str) -> bool:
        """Check if camera and action are compatible."""
        camera = self.get_camera(camera_key)
        if not camera:
            return True  # If camera not found, allow it
        compatible = camera.get("compatible_actions", [])
        if not compatible:
            return True  # If no restrictions, allow it
        return action_key in compatible

    def get_location_keys(self) -> list[str]:
        """Get all location keys."""
        return list(self.locations.keys())

    def get_camera_keys(self) -> list[str]:
        """Get all camera keys."""
        return list(self.cameras.keys())

    def get_action_keys(self) -> list[str]:
        """Get all action keys."""
        return list(self.actions.keys())

    def get_locations_by_tag(self, tag: str) -> list[str]:
        """Get location keys that have a specific tag."""
        result = []
        for key, data in self.locations.items():
            if tag in data.get("tags", []):
                result.append(key)
        return result

    def build_scene_prompt(
        self,
        location_key: str,
        camera_key: str,
        action_key: str,
        character_description: str = "",
    ) -> str:
        """Build a complete prompt for scene generation."""
        parts = []

        # Add camera style
        camera_prompt = self.get_camera_prompt(camera_key)
        if camera_prompt:
            parts.append(camera_prompt)

        # Add character if provided
        if character_description:
            parts.append(character_description)

        # Add action
        action_prompt = self.get_action_prompt(action_key)
        if action_prompt:
            parts.append(action_prompt)

        # Add location
        location_prompt = self.get_location_prompt(location_key)
        if location_prompt:
            parts.append(f"in {location_prompt}")

        return ", ".join(parts)


# Global instance
_library: Optional[AssetLibrary] = None


def get_library() -> AssetLibrary:
    """Get or create the asset library instance."""
    global _library
    if _library is None:
        _library = AssetLibrary()
        _library.load()
    return _library
