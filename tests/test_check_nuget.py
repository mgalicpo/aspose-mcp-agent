"""Tests for scripts/check_nuget.py — pure function tests, no network."""
from scripts.check_nuget import build_issue_body


def _update(display="Aspose.ZIP", current="26.3.0", latest="26.4.0",
            slug="zip", nuget="Aspose.ZIP"):
    return {"display": display, "current": current, "latest": latest,
            "slug": slug, "nuget": nuget}


class TestBuildIssueBody:
    def test_contains_product_name(self):
        body = build_issue_body([_update(display="Aspose.ZIP")])
        assert "Aspose.ZIP" in body

    def test_contains_both_versions(self):
        body = build_issue_body([_update(current="26.3.0", latest="26.4.0")])
        assert "26.3.0" in body
        assert "26.4.0" in body

    def test_no_backticks(self):
        # Backticks in GitHub Actions shell break command substitution
        body = build_issue_body([_update()])
        assert "`" not in body

    def test_uses_bold_versions(self):
        body = build_issue_body([_update(current="26.3.0", latest="26.4.0")])
        assert "**26.3.0**" in body
        assert "**26.4.0**" in body

    def test_multiple_products(self):
        updates = [
            _update(display="Aspose.ZIP",  slug="zip",  nuget="Aspose.ZIP"),
            _update(display="Aspose.Font", slug="font", nuget="Aspose.Font"),
        ]
        body = build_issue_body(updates)
        assert "Aspose.ZIP" in body
        assert "Aspose.Font" in body

    def test_contains_nuget_link(self):
        body = build_issue_body([_update(nuget="Aspose.ZIP")])
        assert "nuget.org" in body

    def test_contains_next_steps(self):
        body = build_issue_body([_update()])
        assert "Next steps" in body or "next steps" in body.lower()
