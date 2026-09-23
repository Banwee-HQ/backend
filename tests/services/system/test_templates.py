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


class TestRenderExport:

    async def test_renders_export_with_format_type(self, tmp_path):
        (tmp_path / "export.html").write_text("{{ format_type }} report by {{ company_name }}")
        service = JinjaTemplateService(template_dir=str(tmp_path))

        result = await service.render_export("export.html", {"format_type": "csv"})
        assert result["format_type"] == "csv"
        assert "csv report by Banwee" in result["content"]

    async def test_default_format_type_is_html(self, tmp_path):
        (tmp_path / "export.html").write_text("{{ format_type }}")
        service = JinjaTemplateService(template_dir=str(tmp_path))

        result = await service.render_export("export.html", {})
        assert result["format_type"] == "html"

    async def test_unknown_template_raises_template_error(self, tmp_path):
        from jinja2 import TemplateError
        service = JinjaTemplateService(template_dir=str(tmp_path))
        with pytest.raises(TemplateError):
            await service.render_export("does-not-exist.html", {})

    async def test_unexpected_runtime_error_is_wrapped_in_template_error(self, tmp_path):
        from jinja2 import TemplateError
        (tmp_path / "bad.html").write_text("{{ 1 / 0 }}")
        service = JinjaTemplateService(template_dir=str(tmp_path))

        with pytest.raises(TemplateError, match="Failed to render template"):
            await service.render_export("bad.html", {})


class TestValidateTemplate:

    async def test_valid_template_has_no_errors(self, tmp_path):
        service = JinjaTemplateService(template_dir=str(tmp_path))
        result = await service.validate_template("Hello {{ name }}")
        assert result["is_valid"] is True
        assert result["errors"] == []

    async def test_syntax_error_is_reported(self, tmp_path):
        service = JinjaTemplateService(template_dir=str(tmp_path))
        result = await service.validate_template("{% if %}")
        assert result["is_valid"] is False
        assert len(result["errors"]) > 0

    async def test_undefined_variable_used_at_render_time_is_a_warning_not_an_error(self, tmp_path):
        """Accessing an attribute of an undefined variable raises Jinja's UndefinedError
        at render time (not a syntax/TemplateError), which the service should treat as
        a warning since the template might just need real context, not be broken."""
        service = JinjaTemplateService(template_dir=str(tmp_path))
        result = await service.validate_template("{{ undefined_var.attr }}")
        assert result["is_valid"] is True
        assert len(result["warnings"]) > 0
        assert "undefined" in result["warnings"][0].lower()

    async def test_render_time_error_unrelated_to_undefined_is_an_error(self, tmp_path):
        """A render-time error whose message doesn't mention 'undefined' (e.g. a
        ZeroDivisionError from template logic) must be reported as an error."""
        service = JinjaTemplateService(template_dir=str(tmp_path))
        result = await service.validate_template("{{ 1 / 0 }}")
        assert result["is_valid"] is False
        assert any("rendering error" in e.lower() for e in result["errors"])

    async def test_non_string_content_is_an_unexpected_validation_error(self, tmp_path):
        """Anything raised by from_string() itself that isn't a TemplateError (e.g. a
        TypeError from passing a non-string) falls through to the generic handler."""
        service = JinjaTemplateService(template_dir=str(tmp_path))
        result = await service.validate_template(None)
        assert result["is_valid"] is False
        assert any("unexpected validation error" in e.lower() for e in result["errors"])


class TestTemplateFileOperations:

    def test_create_and_check_existence(self, tmp_path):
        service = JinjaTemplateService(template_dir=str(tmp_path))
        assert service.template_exists("new.html") is False

        assert service.create_template_file("new.html", "<p>hi</p>") is True
        assert service.template_exists("new.html") is True
        assert (tmp_path / "new.html").read_text() == "<p>hi</p>"

    def test_create_template_file_in_subdirectory(self, tmp_path):
        service = JinjaTemplateService(template_dir=str(tmp_path))
        assert service.create_template_file("emails/welcome.html", "hi") is True
        assert (tmp_path / "emails" / "welcome.html").exists()

    def test_create_template_file_returns_false_on_write_failure(self, tmp_path):
        """An embedded NUL byte is rejected by the OS when opening the file - a
        genuine OSError/ValueError, not a mocked one."""
        service = JinjaTemplateService(template_dir=str(tmp_path))
        assert service.create_template_file("bad\x00name.html", "content") is False

    def test_list_templates_returns_empty_list_on_filesystem_error(self, tmp_path, mocker):
        """rglob() on a path that vanishes mid-scan (e.g. concurrent deletion) or hits
        a permissions/IO error raises - list_templates should degrade to [] rather
        than propagate. Python's pathlib.rglob() doesn't itself raise for a merely
        missing directory (it just yields nothing), so the underlying OSError is
        simulated directly to exercise this defensive branch."""
        service = JinjaTemplateService(template_dir=str(tmp_path))
        mocker.patch.object(type(service.template_dir), "rglob", side_effect=OSError("disk error"))
        assert service.list_templates() == []

    def test_list_templates_returns_html_files(self, tmp_path):
        service = JinjaTemplateService(template_dir=str(tmp_path))
        service.create_template_file("a.html", "a")
        service.create_template_file("nested/b.html", "b")
        (tmp_path / "not_a_template.txt").write_text("skip me")

        templates = service.list_templates()
        assert "a.html" in templates
        assert any("b.html" in t for t in templates)
        assert not any(t.endswith(".txt") for t in templates)

    def test_template_exists_false_for_missing_file(self, tmp_path):
        service = JinjaTemplateService(template_dir=str(tmp_path))
        assert service.template_exists("nope.html") is False
