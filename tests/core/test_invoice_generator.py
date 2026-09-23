"""Tests for core/utils/invoice_generator.py - InvoiceGenerator."""

from datetime import datetime
import pytest

from core.utils.invoice_generator import InvoiceGenerator


@pytest.fixture
def generator():
    return InvoiceGenerator()


class TestFormatCurrency:

    def test_formats_with_thousands_separator(self, generator):
        assert generator.format_currency(1234.5) == "$ 1,234.50"

    def test_custom_currency_symbol(self, generator):
        assert generator.format_currency(10, "€") == "€ 10.00"


class TestGenerateInvoiceRef:

    def test_uses_first_eight_hex_chars_uppercased(self, generator):
        ref = generator.generate_invoice_ref("a7b3c2d1-4e5f-6789-0abc-def123456789")
        assert ref == "INV-A7B3C2D1"


class TestGetLogoUrl:

    def test_uses_provided_logo_url(self, generator):
        assert generator._get_logo_url({"logo_url": "https://x/logo.png"}) == "https://x/logo.png"

    def test_falls_back_to_none(self, generator):
        assert generator._get_logo_url({}) is None


class TestPrepareInvoiceData:

    def test_formats_items_and_totals(self, generator):
        order_data = {
            "order_id": "a7b3c2d1-4e5f-6789-0abc-def123456789",
            "customer": {"name": "Ada Lovelace", "email": "ada@example.com"},
            "subtotal": 100.0,
            "tax_amount": 8.0,
            "total_amount": 108.0,
            "items": [{"name": "Coffee", "price": 10.0, "quantity": 2, "total": 20.0}],
        }
        data = generator.prepare_invoice_data(order_data)
        assert data["bnw_customer_full_name"] == "Ada Lovelace"
        assert data["items"][0]["unit_price"] == "$ 10.00"
        assert data["discount_percentage"] == 0
        assert data["bnw_discount_amount"] is None

    def test_calculates_discount_percentage(self, generator):
        order_data = {"order_id": "id", "subtotal": 100.0, "discount_amount": 25.0}
        data = generator.prepare_invoice_data(order_data)
        assert data["discount_percentage"] == 25
        assert data["bnw_discount_amount"] == "$ 25.00"


class TestGenerateHtml:

    def test_renders_the_real_template_when_present(self, generator):
        """The default template_dir does have a real invoice_template.html, so a
        plain call actually exercises the successful Jinja render path, not the
        fallback - confirm that's genuinely what happens."""
        html = generator.generate_html({"order_id": "a7b3c2d1-4e5f-6789-0abc-def123456789", "customer": {"name": "Ada"}, "total_amount": 10.0})
        assert "Ada" in html

    def test_falls_back_to_simple_html_when_template_missing(self, tmp_path):
        """Use a generator pointed at an empty directory (no invoice_template.html
        at all) to force the real TemplateNotFound failure that this fallback
        branch exists to handle."""
        generator = InvoiceGenerator(template_dir=str(tmp_path))
        html = generator.generate_html({"order_id": "id-1", "customer": {"name": "Ada"}, "total_amount": 10.0})
        assert "INVOICE" in html
        assert "Ada" in html
        assert "template error" in html


class TestGeneratePdf:

    def test_writes_pdf_to_output_path(self, generator, mocker, tmp_path):
        mock_html = mocker.patch("core.utils.invoice_generator.HTML")
        output_path = str(tmp_path / "invoice.pdf")

        result = generator.generate_pdf({"order_id": "id-1", "customer": {"name": "Ada"}, "total_amount": 10.0}, output_path)

        assert result == output_path
        mock_html.return_value.write_pdf.assert_called_once_with(output_path)


class TestGeneratePdfBytes:

    def test_returns_bytes_from_weasyprint(self, generator, mocker):
        mock_html = mocker.patch("core.utils.invoice_generator.HTML")
        mock_html.return_value.write_pdf.return_value = b"%PDF-1.4"
        result = generator.generate_pdf_bytes({"order_id": "id-1", "total_amount": 10.0})
        assert result == b"%PDF-1.4"

    def test_raises_descriptive_error_when_system_library_missing(self, generator, mocker):
        mocker.patch("core.utils.invoice_generator.HTML", side_effect=OSError("cannot load library libgobject-2.0"))
        with pytest.raises(Exception, match="system libraries"):
            generator.generate_pdf_bytes({"order_id": "id-1", "total_amount": 10.0})

    def test_falls_back_to_simple_pdf_on_other_errors(self, generator, mocker):
        calls = {"count": 0}

        def html_side_effect(string):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("template render error")
            mock = mocker.Mock()
            mock.write_pdf.return_value = b"%PDF-fallback"
            return mock

        mocker.patch("core.utils.invoice_generator.HTML", side_effect=html_side_effect)
        result = generator.generate_pdf_bytes({"order_id": "id-1", "total_amount": 10.0})
        assert result == b"%PDF-fallback"

    def test_raises_combined_error_when_both_main_and_fallback_pdf_fail(self, generator, mocker):
        """When even the simplified fallback HTML fails to convert to PDF, both
        error messages must be surfaced together rather than losing the first."""
        mocker.patch("core.utils.invoice_generator.HTML", side_effect=RuntimeError("weasyprint down"))
        with pytest.raises(Exception, match="Both main template and fallback failed"):
            generator.generate_pdf_bytes({"order_id": "id-1", "total_amount": 10.0})


class TestGenerateInvoice:

    @pytest.mark.asyncio
    async def test_fails_when_template_directory_missing(self, generator, mocker):
        mocker.patch.object(type(generator.template_dir), "exists", return_value=False)
        result = await generator.generate_invoice({"order_id": "id-1"})
        assert result["success"] is False
        assert "Template directory not found" in result["error"]

    @pytest.mark.asyncio
    async def test_succeeds_with_generated_pdf_bytes(self, generator, mocker):
        mocker.patch.object(generator, "generate_pdf_bytes", return_value=b"%PDF-1.4")
        mocker.patch.object(type(generator.template_dir), "exists", return_value=True)
        result = await generator.generate_invoice({"order_id": "a7b3c2d1-4e5f-6789-0abc-def123456789"})
        assert result["success"] is True
        assert result["pdf_bytes"] == b"%PDF-1.4"
        assert result["invoice_ref"] == "INV-A7B3C2D1"

    @pytest.mark.asyncio
    async def test_fails_when_template_file_missing(self, tmp_path):
        """template_dir exists (it's a real, empty tmp dir) but invoice_template.html
        inside it doesn't - a real filesystem check, no mocking needed."""
        generator = InvoiceGenerator(template_dir=str(tmp_path))
        result = await generator.generate_invoice({"order_id": "id-1"})
        assert result["success"] is False
        assert "Template file not found" in result["error"]

    @pytest.mark.asyncio
    async def test_returns_error_dict_with_traceback_when_pdf_generation_raises(self, generator, mocker):
        mocker.patch.object(type(generator.template_dir), "exists", return_value=True)
        mocker.patch.object(generator, "generate_pdf_bytes", side_effect=RuntimeError("weasyprint exploded"))
        result = await generator.generate_invoice({"order_id": "id-1"})
        assert result["success"] is False
        assert "weasyprint exploded" in result["error"]
        assert "error_details" in result
        assert "RuntimeError" in result["error_details"]
