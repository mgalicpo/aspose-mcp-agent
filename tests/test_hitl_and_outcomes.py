"""Tests for HITL and outcome tracking — pure function tests."""
import json
import os
import tempfile
import pytest
from scripts.analyze_release_aspose import _check_escalation, _print_result, CONFIDENCE_THRESHOLD
from scripts.upgrade_product import _update_product_fields


# ── _check_escalation ─────────────────────────────────────────────────────────

class TestCheckEscalation:
    def _decision(self, confidence=0.9):
        return {"safe_to_merge": True, "reason": "ok", "confidence": confidence}

    def test_no_warnings_on_high_confidence(self):
        warnings = _check_escalation(self._decision(0.9), react_iterations=1)
        assert warnings == []

    def test_warns_on_low_confidence(self):
        warnings = _check_escalation(self._decision(0.5), react_iterations=1)
        assert len(warnings) == 1
        assert "0.50" in warnings[0]

    def test_warns_at_threshold_boundary(self):
        # Exactly at threshold — should NOT warn (< not <=)
        warnings = _check_escalation(self._decision(CONFIDENCE_THRESHOLD), react_iterations=1)
        assert warnings == []

    def test_warns_just_below_threshold(self):
        warnings = _check_escalation(self._decision(CONFIDENCE_THRESHOLD - 0.01), react_iterations=1)
        assert len(warnings) == 1

    def test_warns_when_react_did_not_converge(self):
        from scripts.analyze_release_aspose import MAX_REACT_ITERATIONS
        warnings = _check_escalation(self._decision(0.9), react_iterations=MAX_REACT_ITERATIONS)
        assert any("converge" in w.lower() or "iteration" in w.lower() for w in warnings)

    def test_double_warning_low_confidence_and_no_convergence(self):
        from scripts.analyze_release_aspose import MAX_REACT_ITERATIONS
        warnings = _check_escalation(self._decision(0.4), react_iterations=MAX_REACT_ITERATIONS)
        assert len(warnings) == 2

    def test_no_confidence_field_no_warning(self):
        decision = {"safe_to_merge": True, "reason": "ok"}
        warnings = _check_escalation(decision, react_iterations=1)
        assert warnings == []


# ── _print_result return value ────────────────────────────────────────────────

class TestPrintResultReturnValue:
    def _decision(self, confidence=0.9):
        return {
            "safe_to_merge": True, "reason": "ok", "confidence": confidence,
            "new_tools": [], "breaking_changes": [], "next_step": "merge"
        }

    def test_returns_false_when_no_warnings(self, capsys):
        escalated = _print_result(self._decision(0.9), [])
        assert escalated is False

    def test_returns_true_when_warnings_present(self, capsys):
        escalated = _print_result(self._decision(0.5), ["Low confidence warning"])
        assert escalated is True

    def test_confidence_shown_in_output(self, capsys):
        _print_result(self._decision(0.85), [])
        out = capsys.readouterr().out
        assert "0.85" in out


# ── _update_product_fields ────────────────────────────────────────────────────

class TestUpdateProductFields:
    def _make_products_file(self, tmp_path):
        data = {
            "products": [
                {"slug": "zip", "display": "Aspose.ZIP", "current_version": "26.4.0"},
                {"slug": "font", "display": "Aspose.Font", "current_version": "26.4.0"},
            ]
        }
        path = tmp_path / "products.json"
        path.write_text(json.dumps(data, indent=2))
        return str(path)

    def test_updates_correct_product(self, tmp_path, monkeypatch):
        products_file = self._make_products_file(tmp_path)
        monkeypatch.setattr("scripts.upgrade_product.PRODUCTS_FILE", products_file)

        _update_product_fields("zip", {"last_upgrade": "2026-05-07", "last_ci_status": "PASS"})

        with open(products_file) as f:
            config = json.load(f)

        zip_product = next(p for p in config["products"] if p["slug"] == "zip")
        assert zip_product["last_upgrade"] == "2026-05-07"
        assert zip_product["last_ci_status"] == "PASS"

    def test_does_not_affect_other_products(self, tmp_path, monkeypatch):
        products_file = self._make_products_file(tmp_path)
        monkeypatch.setattr("scripts.upgrade_product.PRODUCTS_FILE", products_file)

        _update_product_fields("zip", {"last_ci_status": "FAIL"})

        with open(products_file) as f:
            config = json.load(f)

        font_product = next(p for p in config["products"] if p["slug"] == "font")
        assert "last_ci_status" not in font_product

    def test_preserves_existing_fields(self, tmp_path, monkeypatch):
        products_file = self._make_products_file(tmp_path)
        monkeypatch.setattr("scripts.upgrade_product.PRODUCTS_FILE", products_file)

        _update_product_fields("zip", {"last_ci_status": "PASS"})

        with open(products_file) as f:
            config = json.load(f)

        zip_product = next(p for p in config["products"] if p["slug"] == "zip")
        assert zip_product["current_version"] == "26.4.0"  # unchanged

    def test_overwrites_existing_field(self, tmp_path, monkeypatch):
        products_file = self._make_products_file(tmp_path)
        monkeypatch.setattr("scripts.upgrade_product.PRODUCTS_FILE", products_file)

        _update_product_fields("zip", {"last_ci_status": "PENDING"})
        _update_product_fields("zip", {"last_ci_status": "PASS"})

        with open(products_file) as f:
            config = json.load(f)

        zip_product = next(p for p in config["products"] if p["slug"] == "zip")
        assert zip_product["last_ci_status"] == "PASS"
