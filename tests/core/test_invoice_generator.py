"""Tests for core/utils/invoice_generator.py - InvoiceGenerator."""

from datetime import datetime
import pytest

from core.utils.invoice_generator import InvoiceGenerator


@pytest.fixture
def generator():
    return InvoiceGenerator()


@pytest.fixture
def order_data():
    return {
        "order_id": "a7b3c2d1-4e5f-6789-0abc-def123456789",
        "order_number": "ORD-20260924-ABC",
        "order_date": datetime(2026, 9, 24, 12, 0),
        "currency": "CAD",
        "customer": {"name": "Ada Obi", "email": "ada@example.com", "phone": None},
        "shipping_address": {"street": "100 King St W", "city": "Toronto", "state": "ON", "post_code": "M5X 1A9", "country": "Canada"},
        "items": [{"name": "Palm Oil", "variant_name": "1 litre", "quantity": 2, "price": 8.5, "total": 17.0}],
        "subtotal": 17.0, "discount_amount": 2.0, "tax_rate": 0.13, "tax_amount": 2.6,
        "shipping_amount": 4.99, "total_amount": 22.59, "payment_status": "PaymentStatus.PAID",
    }


class TestFormatCurrency:

    def test_uses_iso_code_and_thousands_separator(self, generator):
        assert generator.format_currency(1234.5, "CAD") == "CAD 1,234.50"


class TestPrepareInvoiceData:

    def test_uses_order_number_rate_and_currency(self, generator, order_data):
        data = generator.prepare_invoice_data(order_data)
        assert data["bnw_invoice_ref"] == "INV-ORD-20260924-ABC"
        assert data["bnw_tax_rate"] == "13"
        assert data["bnw_grand_total_amount"] == "CAD 22.59"
        assert data["items"][0]["unit_price"] == "CAD 8.50"
        assert data["payment_status"] == "Paid"

    def test_discount_line_only_when_discounted(self, generator, order_data):
        assert generator.prepare_invoice_data(order_data)["bnw_discount_amount"] == "CAD 2.00"
        order_data["discount_amount"] = 0
        assert generator.prepare_invoice_data(order_data)["bnw_discount_amount"] is None

    def test_shipping_address_lines_skip_empty_parts(self, generator, order_data):
        order_data["shipping_address"]["state"] = None
        assert generator.prepare_invoice_data(order_data)["shipping_address_lines"] == ["100 King St W", "Toronto M5X 1A9", "Canada"]


class TestGenerateInvoice:

    async def test_returns_pdf_bytes(self, generator, order_data):
        result = await generator.generate_invoice(order_data)
        assert result["success"] is True
        assert result["pdf_bytes"].startswith(b"%PDF")
        assert result["invoice_ref"] == "INV-ORD-20260924-ABC"

    async def test_reports_failure_instead_of_raising(self, generator, order_data, mocker):
        mocker.patch.object(generator, "generate_pdf_bytes", side_effect=RuntimeError("no fonts"))
        result = await generator.generate_invoice(order_data)
        assert result == {"success": False, "message": "Failed to generate invoice: no fonts"}
