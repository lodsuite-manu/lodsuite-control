"""Tests for script parser."""

import pytest

from app.schemas.script import Script, SceneScript
from app.services.script_parser import (
    parse_yaml_script,
    ScriptParseError,
    validate_script,
    script_to_yaml,
    format_script_for_display,
)


class TestParseYamlScript:
    """Tests for YAML script parsing."""

    def test_parse_valid_script(self, sample_yaml_script: str):
        script = parse_yaml_script(sample_yaml_script)

        assert script.title == "Test Video"
        assert script.aspect_ratio == "9:16"
        assert script.character_key == "markus_industrial"
        assert len(script.scenes) == 2

    def test_parse_scene_details(self, sample_yaml_script: str):
        script = parse_yaml_script(sample_yaml_script)
        scene = script.scenes[0]

        assert scene.order == 1
        assert scene.duration_sec == 5.0
        assert scene.location_key == "warehouse_modern"
        assert scene.camera_key == "selfie_pov_arm_visible"
        assert scene.action_key == "talking_to_camera_confident"
        assert "POV" in scene.voiceover_de
        assert scene.needs_lipsync is True
        assert scene.caption_overlay == "POV: Industrie 2026"

    def test_parse_calculates_total_duration(self, sample_yaml_script: str):
        script = parse_yaml_script(sample_yaml_script)
        assert script.total_duration_sec == 10.0

    def test_parse_invalid_yaml(self):
        with pytest.raises(ScriptParseError) as exc_info:
            parse_yaml_script("invalid: yaml: content: [")

        assert "Invalid YAML" in str(exc_info.value)

    def test_parse_missing_title(self):
        yaml_content = """
scenes:
  - order: 1
    location: warehouse_modern
"""
        with pytest.raises(ScriptParseError) as exc_info:
            parse_yaml_script(yaml_content)

        assert "title" in str(exc_info.value).lower()

    def test_parse_missing_scenes(self):
        yaml_content = """
title: "Test"
"""
        with pytest.raises(ScriptParseError) as exc_info:
            parse_yaml_script(yaml_content)

        assert "scenes" in str(exc_info.value).lower()

    def test_parse_empty_scenes(self):
        yaml_content = """
title: "Test"
scenes: []
"""
        with pytest.raises(ScriptParseError) as exc_info:
            parse_yaml_script(yaml_content)

        assert "at least one scene" in str(exc_info.value).lower()


class TestValidateScript:
    """Tests for script validation."""

    def test_validate_valid_script(self, sample_yaml_script: str):
        script = parse_yaml_script(sample_yaml_script)
        warnings = validate_script(script)

        # Should have no critical warnings for valid script
        assert not any("Unknown" in w for w in warnings)

    def test_validate_unknown_location(self):
        script = Script(
            title="Test",
            scenes=[
                SceneScript(
                    order=1,
                    duration_sec=5.0,
                    location_key="unknown_location",
                    camera_key="selfie_pov_arm_visible",
                    action_key="talking_to_camera_confident",
                    voiceover_de="Test",
                )
            ],
        )
        warnings = validate_script(script)

        assert any("Unknown location" in w for w in warnings)

    def test_validate_short_duration(self):
        script = Script(
            title="Test",
            total_duration_sec=10,
            scenes=[
                SceneScript(
                    order=1,
                    duration_sec=5.0,
                    location_key="warehouse_modern",
                    camera_key="selfie_pov_arm_visible",
                    action_key="talking_to_camera_confident",
                    voiceover_de="Test",
                )
            ],
        )
        warnings = validate_script(script)

        assert any("very short" in w.lower() for w in warnings)

    def test_validate_lipsync_without_voiceover(self):
        script = Script(
            title="Test",
            scenes=[
                SceneScript(
                    order=1,
                    duration_sec=5.0,
                    location_key="warehouse_modern",
                    camera_key="selfie_pov_arm_visible",
                    action_key="talking_to_camera_confident",
                    voiceover_de="",
                    needs_lipsync=True,
                )
            ],
        )
        warnings = validate_script(script)

        assert any("Lipsync" in w and "voiceover" in w.lower() for w in warnings)


class TestScriptToYaml:
    """Tests for script to YAML conversion."""

    def test_roundtrip_conversion(self, sample_yaml_script: str):
        original = parse_yaml_script(sample_yaml_script)
        yaml_output = script_to_yaml(original)
        roundtrip = parse_yaml_script(yaml_output)

        assert roundtrip.title == original.title
        assert roundtrip.aspect_ratio == original.aspect_ratio
        assert len(roundtrip.scenes) == len(original.scenes)

        for orig_scene, rt_scene in zip(original.scenes, roundtrip.scenes):
            assert rt_scene.location_key == orig_scene.location_key
            assert rt_scene.camera_key == orig_scene.camera_key
            assert rt_scene.voiceover_de == orig_scene.voiceover_de


class TestFormatScriptForDisplay:
    """Tests for script display formatting."""

    def test_format_includes_header(self, sample_yaml_script: str):
        script = parse_yaml_script(sample_yaml_script)
        formatted = format_script_for_display(script)

        assert "Skript" in formatted
        assert script.title in formatted

    def test_format_includes_scene_info(self, sample_yaml_script: str):
        script = parse_yaml_script(sample_yaml_script)
        formatted = format_script_for_display(script)

        assert "warehouse_modern" in formatted
        assert "POV" in formatted

    def test_format_includes_duration_info(self, sample_yaml_script: str):
        script = parse_yaml_script(sample_yaml_script)
        formatted = format_script_for_display(script)

        assert "10s" in formatted or "10" in formatted
        assert "2 Szenen" in formatted
