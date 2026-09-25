"""Tests for services/system/templates.py - JinjaTemplateService.

Pure filesystem + Jinja2 logic, no DB - uses pytest's tmp_path as the
template directory so nothing touches the real templates/ tree.
"""

import pytest

from services.system.templates import JinjaTemplateService


class TestRenderEmail:

    async def test_renders_template_with_context(self, tmp_path):
        (tmp_path / "greeting.html").write_text("Hello {{ name }}, welcome to {{ company_name }}!")
        service = JinjaTemplateService(template_dir=str(tmp_path))

        result = await service.render_email("greeting.html", {"name": "Ada"})
        assert "Hello Ada" in result["content"]
        assert "Banwee" in result["content"]  # default company_name

    async def test_uses_provided_company_name_over_default(self, tmp_path):
        (tmp_path / "t.html").write_text("{{ company_name }}")
        service = JinjaTemplateService(template_dir=str(tmp_path))

        result = await service.render_email("t.html", {"company_name": "Acme"})
        assert result["content"] == "Acme"

    async def test_unknown_template_raises(self, tmp_path):
        service = JinjaTemplateService(template_dir=str(tmp_path))
        with pytest.raises(Exception):
            await service.render_email("does-not-exist.html", {})

    async def test_currency_filter(self, tmp_path):
        (tmp_path / "price.html").write_text("{{ amount|currency }}")
        service = JinjaTemplateService(template_dir=str(tmp_path))

        result = await service.render_email("price.html", {"amount": 19.5})
        assert result["content"] == "$19.50"

    async def test_currency_filter_with_non_usd(self, tmp_path):
        (tmp_path / "price.html").write_text("{{ amount|currency('EUR') }}")
        service = JinjaTemplateService(template_dir=str(tmp_path))

        result = await service.render_email("price.html", {"amount": 19.5})
        assert result["content"] == "19.50 EUR"

    async def test_date_filter(self, tmp_path):
        from datetime import date
        (tmp_path / "d.html").write_text("{{ d|date }}")
        service = JinjaTemplateService(template_dir=str(tmp_path))

        result = await service.render_email("d.html", {"d": date(2024, 3, 5)})
        assert result["content"] == "March 05, 2024"

    async def test_datetime_filter(self, tmp_path):
        from datetime import datetime
        (tmp_path / "dt.html").write_text("{{ d|datetime }}")
        service = JinjaTemplateService(template_dir=str(tmp_path))

        result = await service.render_email("dt.html", {"d": datetime(2024, 3, 5, 14, 30)})
        assert "March 05, 2024" in result["content"]

    def test_date_filter_falls_back_to_str_for_non_datetime(self, tmp_path):
        service = JinjaTemplateService(template_dir=str(tmp_path))
        assert service._format_date("already-a-string") == "already-a-string"
        assert service._format_date(42) == "42"

    def test_datetime_filter_falls_back_to_str_for_non_datetime(self, tmp_path):
        service = JinjaTemplateService(template_dir=str(tmp_path))
        assert service._format_datetime("already-a-string") == "already-a-string"
        assert service._format_datetime(42) == "42"

    async def test_unexpected_runtime_error_is_wrapped_in_template_error(self, tmp_path):
        """A non-TemplateError exception raised during rendering (e.g. a ZeroDivisionError
        from template logic) must be caught and re-raised as a TemplateError, not leak
        the raw Python exception type."""
        from jinja2 import TemplateError
        (tmp_path / "bad.html").write_text("{{ 1 / 0 }}")
        service = JinjaTemplateService(template_dir=str(tmp_path))

        with pytest.raises(TemplateError, match="Failed to render template"):
            await service.render_email("bad.html", {})


