"""Tests for services/analytics/export.py - ExportService.

export_subscription_data() and its private helpers (_export_subscriptions_csv/
_json/_html, _json_serializer, _generate_basic_html_export) were removed:
confirmed via grep that nothing in the app calls export_subscription_data(),
and two of the three format helpers were broken (filters.dict() on an
ExportFilters TypedDict, which has no such method - TypedDict instances are
plain dicts at runtime). Only the three static order-export methods below are
actually reachable, from api/analytics/analytics.py.
"""

import csv
import io
import pytest
from openpyxl import load_workbook

from services.analytics.export import ExportService


def sample_order(**overrides) -> dict:
    # Matches OrderService._format_order_response()'s real shape, as passed
    # through OrderService.list() -> ExportService.export_orders_to_*().
    order = {
        "id": "order-123",
        "user": {"firstname": "Ada", "lastname": "Lovelace", "email": "ada@example.com"},
        "status": "delivered",
        "payment_status": "paid",
        "total_amount": 49.98,
        "items": [
            {
                "variant": {"product_name": "Widget", "name": "Default"},
                "quantity": 2, "price_per_unit": 19.99, "total_price": 39.98,
            },
        ],
        "created_at": "2026-01-01T00:00:00Z",
    }
    order.update(overrides)
    return order


class TestExportOrdersToCsv:

    def test_empty_list_returns_placeholder_message(self):
        output = ExportService.export_orders_to_csv([])
        assert output.read() == b"No orders to export"

    def test_writes_expected_header_and_row(self):
        output = ExportService.export_orders_to_csv([sample_order()])
        text = output.read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["Customer Name"] == "Ada Lovelace"
        assert rows[0]["Customer Email"] == "ada@example.com"
        assert rows[0]["Total Amount"] == "$49.98"
        assert rows[0]["Items Count"] == "1"

    def test_handles_missing_user_gracefully(self):
        output = ExportService.export_orders_to_csv([sample_order(user={})])
        text = output.read().decode("utf-8")
        rows = list(csv.DictReader(io.StringIO(text)))
        assert rows[0]["Customer Name"] == ""
        assert rows[0]["Customer Email"] == ""


class TestExportOrdersToExcel:

    def test_writes_header_and_row(self):
        output = ExportService.export_orders_to_excel([sample_order()])
        wb = load_workbook(output)
        ws = wb.active
        assert ws.title == "Orders"
        assert ws.cell(row=1, column=1).value == "Order ID"
        assert ws.cell(row=2, column=1).value == "order-123"
        assert ws.cell(row=2, column=2).value == "Ada Lovelace"
        assert ws.cell(row=2, column=6).value == 49.98
        assert ws.cell(row=2, column=7).value == 1

    def test_empty_list_still_produces_a_valid_workbook(self):
        output = ExportService.export_orders_to_excel([])
        wb = load_workbook(output)
        assert wb.active.cell(row=1, column=1).value == "Order ID"


class TestExportOrdersToPdf:

    def test_raises_when_weasyprint_unavailable(self, mocker):
        mocker.patch("services.analytics.export._WEASYPRINT_AVAILABLE", False)
        with pytest.raises(RuntimeError):
            ExportService.export_orders_to_pdf([sample_order()])

    def test_renders_pdf_bytes_when_available(self, mocker):
        mocker.patch("services.analytics.export._WEASYPRINT_AVAILABLE", True)
        mock_html = mocker.patch("services.analytics.export.HTML")
        mock_html.return_value.write_pdf.return_value = b"%PDF-1.4 fake pdf bytes"

        output = ExportService.export_orders_to_pdf([sample_order()])
        assert output.read() == b"%PDF-1.4 fake pdf bytes"

    def test_empty_orders_renders_without_error(self, mocker):
        mocker.patch("services.analytics.export._WEASYPRINT_AVAILABLE", True)
        mock_html = mocker.patch("services.analytics.export.HTML")
        mock_html.return_value.write_pdf.return_value = b"%PDF-1.4"

        output = ExportService.export_orders_to_pdf([])
        assert output.read() == b"%PDF-1.4"
        # The "no orders" branch of the template must have rendered without
        # a Jinja error (order.id[:8] etc. would KeyError on an empty list).
        rendered_html = mock_html.call_args.kwargs.get("string") or mock_html.call_args.args[0]
        assert "No orders to export" in rendered_html
