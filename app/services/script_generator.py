"""Script generation using Claude API (with mock mode)."""

import structlog

from app.config import get_settings
from app.schemas.script import Script, SceneScript, ScriptGenerationRequest
from app.services.library import get_library

logger = structlog.get_logger()


class ScriptGenerationError(Exception):
    """Raised when script generation fails."""

    pass


def generate_mock_script(briefing: str) -> Script:
    """Return a hardcoded 3-scene script for testing."""
    logger.info("Generating mock script", briefing_preview=briefing[:50])

    return Script(
        title="Industrie-Effizienz 2026",
        aspect_ratio="9:16",
        character_key="markus_industrial",
        scenes=[
            SceneScript(
                order=1,
                duration_sec=5.0,
                location_key="warehouse_modern",
                location_prompt="modern logistics warehouse, tall shelving with pallets, polished concrete, LED lighting",
                camera_key="selfie_pov_arm_visible",
                action_key="talking_to_camera_confident",
                voiceover_de="POV: Du leitest 2026 ein mittelständisches Unternehmen und fragst dich, wie du mit der Konkurrenz mithalten kannst.",
                needs_lipsync=True,
                caption_overlay="POV: Industrie 2026",
                caption_position="top",
            ),
            SceneScript(
                order=2,
                duration_sec=5.0,
                location_key="office_glass_wall",
                location_prompt="modern office with glass wall, city view, minimal furniture, standing desk",
                camera_key="medium_shot",
                action_key="pointing_at_screen",
                voiceover_de="Während deine Konkurrenz noch Excel-Tabellen pflegt, hast du alles auf einen Blick.",
                needs_lipsync=True,
                caption_overlay=None,
                caption_position="top",
            ),
            SceneScript(
                order=3,
                duration_sec=5.0,
                location_key="cnc_hall",
                location_prompt="CNC milling production hall, metal chips on floor, industrial green machinery",
                camera_key="walking_shot",
                action_key="walking_explaining",
                voiceover_de="Digitalisierung ist kein Luxus mehr – es ist Überleben. Klick auf den Link.",
                needs_lipsync=True,
                caption_overlay="Link in Bio",
                caption_position="bottom",
            ),
        ],
    )


async def generate_script(request: ScriptGenerationRequest) -> Script:
    """Generate a script from a briefing.

    In mock mode, returns a hardcoded script.
    In production mode, calls Claude API.
    """
    settings = get_settings()

    if settings.mock_script:
        return generate_mock_script(request.briefing)

    # Production mode - call Claude API
    return await _generate_script_with_claude(request)


async def _generate_script_with_claude(request: ScriptGenerationRequest) -> Script:
    """Generate script using Claude API."""
    settings = get_settings()
    library = get_library()

    if not settings.anthropic_api_key:
        raise ScriptGenerationError("ANTHROPIC_API_KEY not configured")

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        # Build the prompt
        system_prompt = _build_system_prompt(library)
        user_prompt = _build_user_prompt(request, library)

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        # Parse the response
        response_text = message.content[0].text
        script = _parse_claude_response(response_text)

        logger.info(
            "Generated script with Claude",
            title=script.title,
            scenes=len(script.scenes),
            duration=script.total_duration_sec,
        )

        return script

    except anthropic.APIError as e:
        logger.error("Claude API error", error=str(e))
        raise ScriptGenerationError(f"Claude API error: {e}")
    except Exception as e:
        logger.error("Script generation failed", error=str(e))
        raise ScriptGenerationError(f"Script generation failed: {e}")


def _build_system_prompt(library) -> str:
    """Build the system prompt for Claude."""
    location_keys = ", ".join(library.get_location_keys())
    camera_keys = ", ".join(library.get_camera_keys())
    action_keys = ", ".join(library.get_action_keys())

    return f"""Du bist ein Experte für B2B-Industrie-Werbung im POV-Selfie-Stil für deutschsprachige Zielgruppen.

Deine Aufgabe ist es, Skripte für kurze Video-Ads zu erstellen, die:
- Im POV/Selfie-Stil gedreht werden
- Auf KMU-Geschäftsführer in der DACH-Region abzielen
- Kurz, prägnant und actionable sind
- Deutsche Voiceover-Texte enthalten

VERFÜGBARE ASSETS:
- Locations: {location_keys}
- Kameras: {camera_keys}
- Actions: {action_keys}

FORMATIERUNG:
Antworte NUR mit einem YAML-Block im folgenden Format:

```yaml
title: "Titel des Videos"
scenes:
  - order: 1
    duration: 5
    location: warehouse_modern
    camera: selfie_pov_arm_visible
    action: talking_to_camera_confident
    voiceover: "Der deutsche Text hier..."
    lipsync: true
    caption: "Optional: Text-Overlay"
  - order: 2
    ...
```

REGELN:
- Verwende NUR die oben gelisteten location, camera und action Keys
- Jede Szene sollte 4-8 Sekunden dauern
- Gesamtdauer zwischen 30-60 Sekunden
- Voiceover muss auf Deutsch sein
- Beginne mit einem starken Hook (POV:...)
- Ende mit einem klaren Call-to-Action
"""


def _build_user_prompt(request: ScriptGenerationRequest, library) -> str:
    """Build the user prompt for Claude."""
    return f"""Erstelle ein Skript für folgendes Briefing:

{request.briefing}

Ziel-Länge: ca. {request.target_duration_sec:.0f} Sekunden
{f"Anzahl Szenen: {request.scene_count}" if request.scene_count else ""}
Charakter: {request.character_key}

Erstelle jetzt das YAML-Skript:"""


def _parse_claude_response(response: str) -> Script:
    """Parse Claude's YAML response into a Script object."""
    import yaml

    # Extract YAML block
    if "```yaml" in response:
        start = response.find("```yaml") + 7
        end = response.find("```", start)
        yaml_content = response[start:end].strip()
    elif "```" in response:
        start = response.find("```") + 3
        end = response.find("```", start)
        yaml_content = response[start:end].strip()
    else:
        yaml_content = response.strip()

    try:
        data = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        raise ScriptGenerationError(f"Failed to parse YAML: {e}")

    # Convert to Script
    scenes = []
    for i, scene_data in enumerate(data.get("scenes", []), start=1):
        scene = SceneScript(
            order=scene_data.get("order", i),
            duration_sec=float(scene_data.get("duration", 5)),
            location_key=scene_data.get("location", "warehouse_modern"),
            location_prompt=scene_data.get("location_prompt", ""),
            camera_key=scene_data.get("camera", "selfie_pov_arm_visible"),
            action_key=scene_data.get("action", "talking_to_camera_confident"),
            voiceover_de=scene_data.get("voiceover", ""),
            needs_lipsync=scene_data.get("lipsync", True),
            caption_overlay=scene_data.get("caption"),
            caption_position=scene_data.get("caption_position", "top"),
        )
        scenes.append(scene)

    return Script(
        title=data.get("title", "Unbenanntes Video"),
        aspect_ratio=data.get("aspect_ratio", "9:16"),
        character_key=data.get("character", "markus_industrial"),
        scenes=scenes,
    )
