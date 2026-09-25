"""Invoice PDF Generator using Jinja2 and WeasyPrint."""
from datetime import datetime
from typing import Dict, Optional
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML
from pathlib import Path

from core.config import settings


class InvoiceGenerator:
    """Generate PDF invoices from HTML templates using Jinja2 and WeasyPrint"""
    
    def __init__(self, template_dir: Optional[str] = None):
        """Initialize the invoice generator with a template directory."""
        if template_dir is None:
            # Default to the templates directory
            base_dir = Path(__file__).parent
            template_dir = base_dir / "messages" / "templates" / "post_purchase"
        
        self.template_dir = Path(template_dir)
        
        # Setup Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(['html', 'xml'])
        )
        
    def format_currency(self, amount, currency: str) -> str:
        """Amount with its ISO currency code, e.g. 'CAD 14.40'."""
        return f"{currency} {float(amount or 0):,.2f}"

    def format_date(self, date_obj: datetime, format_str: str = "%B %d, %Y") -> str:
        """Format datetime object to string"""
        return date_obj.strftime(format_str)

    @staticmethod
    def _address_lines(address: Optional[Dict]) -> list:
        """Address dict -> printable lines (empty parts skipped)."""
        if not address:
            return []
        city_line = " ".join(p for p in [address.get("city"), address.get("state"), address.get("post_code")] if p)
        return [line for line in [address.get("street"), city_line, address.get("country")] if line]

    def prepare_invoice_data(self, order_data: Dict) -> Dict:
        """Template fields for one order: items, totals in the order's currency and the seller/customer blocks."""
        currency = order_data["currency"]
        money = lambda amount: self.format_currency(amount, currency)
        customer = order_data.get("customer", {})
        discount = float(order_data.get("discount_amount") or 0)
        return {
            "bnw_invoice_ref": f"INV-{order_data['order_number']}",
            "bnw_invoice_issue_date": self.format_date(order_data["order_date"]),
            "bnw_order_reference_id": order_data["order_number"],
            "bnw_order_placement_date": self.format_date(order_data["order_date"]),
            "payment_status": str(order_data.get("payment_status") or "").rsplit(".", 1)[-1].replace("_", " ").title(),
            "bnw_customer_full_name": customer.get("name"),
            "bnw_customer_email_address": customer.get("email"),
            "bnw_customer_phone_number": customer.get("phone"),
            "shipping_address_lines": self._address_lines(order_data.get("shipping_address")),
            "bnw_order_subtotal_amount": money(order_data.get("subtotal")),
            "bnw_tax_rate": f"{float(order_data.get('tax_rate') or 0) * 100:g}",
            "bnw_tax_amount": money(order_data.get("tax_amount")),
            "bnw_shipping_amount": money(order_data.get("shipping_amount")),
            "bnw_discount_amount": money(discount) if discount > 0 else None,
            "bnw_grand_total_amount": money(order_data.get("total_amount")),
            "items": [
                {
                    "name": item.get("name", "Product"),
                    "description": item.get("variant_name", ""),
                    "unit_price": money(item.get("price")),
                    "quantity": item.get("quantity", 1),
                    "total_price": money(item.get("total")),
                }
                for item in order_data.get("items", [])
            ],
            "logo_url": order_data.get("logo_url"),
            "company_name": settings.STORE_NAME,
            "company_address_lines": [line.strip() for line in settings.STORE_ADDRESS.split("|") if line.strip()],
        }

    def generate_pdf_bytes(self, order_data: Dict, template_name: str = "invoice_template.html") -> bytes:
        """Render the invoice template and convert it to PDF bytes."""
        html = self.env.get_template(template_name).render(**self.prepare_invoice_data(order_data))
        return HTML(string=html).write_pdf()

    async def generate_invoice(self, order_data: Dict) -> Dict:
        """Generate the invoice PDF and return a result dict with success/pdf_bytes/message."""
        try:
            return {
                "success": True,
                "pdf_bytes": self.generate_pdf_bytes(order_data),
                "invoice_ref": f"INV-{order_data['order_number']}",
            }
        except Exception as e:
            return {"success": False, "message": f"Failed to generate invoice: {e}"}
