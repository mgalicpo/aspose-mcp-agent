"""Tests for analyze_release.py and analyze_release_aspose.py — pure functions."""
import json
import pytest
from scripts.analyze_release import _candidate_urls
from scripts.analyze_release import _html_to_text
from scripts.analyze_release_aspose import (
    _parse_json_response,
    _validate_schema,
    _validate_analysis,
    CONFIDENCE_THRESHOLD,
)


class TestCandidateUrls:
    def test_returns_three_candidates(self):
        urls = _candidate_urls("zip", "26.4.0")
        assert len(urls) == 3

    def test_year_derived_from_major(self):
        urls = _candidate_urls("zip", "26.4.0")
        assert all("2026" in u for u in urls)

    def test_version_in_urls(self):
        urls = _candidate_urls("zip", "26.4.0")
        assert any("26-4-0" in u for u in urls)
        assert any("26-4" in u for u in urls)

    def test_slug_in_urls(self):
        urls = _candidate_urls("font", "26.2.0")
        assert all("font" in u for u in urls)

    def test_two_digit_minor(self):
        urls = _candidate_urls("note", "25.12.0")
        assert any("25-12" in u for u in urls)


class TestHtmlToText:
    def test_strips_html_tags(self):
        result = _html_to_text("<p>Hello <b>world</b></p>")
        assert "Hello" in result
        assert "world" in result
        assert "<" not in result

    def test_skips_script_content(self):
        result = _html_to_text("<p>Content</p><script>evil()</script><p>More</p>")
        assert "Content" in result
        assert "evil" not in result

    def test_skips_style_content(self):
        result = _html_to_text("<style>.cls{color:red}</style><p>Text</p>")
        assert "Text" in result
        assert "color" not in result

    def test_empty_html(self):
        result = _html_to_text("")
        assert result == ""

    def test_nested_skip_tags(self):
        result = _html_to_text("<nav><div>menu</div></nav><p>page</p>")
        assert "menu" not in result
        assert "page" in result


class TestParseJsonResponse:
    def test_plain_json(self):
        raw = '{"safe_to_merge": true, "reason": "ok"}'
        result = _parse_json_response(raw)
        assert result["safe_to_merge"] is True

    def test_strips_markdown_fences(self):
        raw = '```json\n{"safe_to_merge": false}\n```'
        result = _parse_json_response(raw)
        assert result["safe_to_merge"] is False

    def test_strips_fences_without_lang(self):
        raw = '```\n{"key": "value"}\n```'
        result = _parse_json_response(raw)
        assert result["key"] == "value"

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_json_response("not json at all")


class TestValidateSchema:
    def _valid(self, **overrides):
        base = {
            "safe_to_merge": True,
            "reason": "only bug fixes",
            "confidence": 0.9,
            "new_tools": [],
            "breaking_changes": [],
            "next_step": "merge it",
        }
        base.update(overrides)
        return base

    def test_valid_decision_passes(self):
        _validate_schema(self._valid())  # must not raise

    def test_safe_to_merge_must_be_bool(self):
        with pytest.raises(ValueError):
            _validate_schema(self._valid(safe_to_merge="yes"))

    def test_reason_must_be_string(self):
        with pytest.raises(ValueError):
            _validate_schema(self._valid(reason=None))

    def test_new_tools_must_be_list(self):
        with pytest.raises(ValueError):
            _validate_schema(self._valid(new_tools="none"))

    def test_breaking_changes_must_be_list(self):
        with pytest.raises(ValueError):
            _validate_schema(self._valid(breaking_changes=None))

    def test_confidence_must_be_number_if_present(self):
        with pytest.raises(ValueError):
            _validate_schema(self._valid(confidence="high"))

    def test_confidence_none_is_allowed(self):
        _validate_schema(self._valid(confidence=None))  # must not raise


class TestValidateAnalysis:
    def _decision(self, safe=True, tools=None):
        return {
            "safe_to_merge": safe,
            "new_tools": tools or [],
        }

    def test_passes_when_version_known_safe(self):
        # Use a version known to exist on NuGet (26.4.0)
        decision = self._decision(safe=True)
        failures = _validate_analysis(decision, "26.4.0", "Aspose.ZIP", "some release notes text")
        assert failures == []

    def test_flags_api_class_not_in_notes(self):
        decision = self._decision(tools=[{
            "name": "zip_create", "api_class": "InventedClass999", "description": "..."
        }])
        failures = _validate_analysis(decision, "26.4.0", "Aspose.ZIP", "no mention here")
        assert any("InventedClass999" in f for f in failures)

    def test_passes_when_api_class_in_notes(self):
        decision = self._decision(tools=[{
            "name": "zip_create", "api_class": "AppleArchive", "description": "..."
        }])
        failures = _validate_analysis(decision, "26.4.0", "Aspose.ZIP",
                                      "The new AppleArchive class enables .aar creation")
        assert failures == []

    def test_confidence_threshold_value(self):
        assert CONFIDENCE_THRESHOLD == 0.7
