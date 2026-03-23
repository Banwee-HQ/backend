"""
Invoice PDF Generator using Jinja2 and WeasyPrint
"""
from datetime import datetime, timedelta
from typing import Dict, Optional
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML
from pathlib import Path


class InvoiceGenerator:
    """Generate PDF invoices from HTML templates using Jinja2 and WeasyPrint"""
    
    def __init__(self, template_dir: Optional[str] = None):
        """
        Initialize the invoice generator
        
        Args:
            template_dir: Directory containing invoice templates
        """
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
        
    def format_currency(self, amount: float, currency: str = "$") -> str:
        """Format amount as currency"""
        return f"{currency} {amount:,.2f}"
    
    def format_date(self, date_obj: datetime, format_str: str = "%B %d, %Y") -> str:
        """Format datetime object to string"""
        return date_obj.strftime(format_str)
    
    def generate_invoice_ref(self, order_id: str) -> str:
        """Generate invoice reference from order ID"""
        # Take first 8 characters of order ID and format
        short_id = order_id.replace("-", "")[:8].upper()
        return f"INV-{short_id}"
    
    def _get_logo_url(self, order_data: Dict) -> str:
        """Get logo URL with fallback handling"""
        # If logo_url is provided in order_data, use it
        if order_data.get('logo_url'):
            return order_data['logo_url']
        
        # For now, return None to use the text fallback in the template
        # In production, you would configure a proper logo URL or base64 encoded image
        return None
    
    def prepare_invoice_data(self, order_data: Dict) -> Dict:
        """
        Prepare invoice data from order information
        
        Args:
            order_data: Dictionary containing order information
            
        Returns:
            Dictionary with formatted invoice data
        """
        current_date = datetime.now()
        
        # Format items
        items = []
        for item in order_data.get('items', []):
            items.append({
                'name': item.get('name', 'Product'),
                'description': item.get('variant_name', ''),
                'unit_price': self.format_currency(item.get('price', 0)),
                'quantity': item.get('quantity', 1),
                'total_price': self.format_currency(item.get('total', 0))
            })
        
        # Calculate discount percentage if applicable
        discount_percentage = 0
        if order_data.get('discount_amount', 0) > 0 and order_data.get('subtotal', 0) > 0:
            discount_percentage = round(
                (order_data['discount_amount'] / order_data['subtotal']) * 100
            )
        
        # Prepare invoice data
        invoice_data = {
            # Invoice metadata
            'bnw_invoice_ref': self.generate_invoice_ref(order_data.get('order_id', '')),
            'bnw_invoice_issue_date': self.format_date(current_date),
            'bnw_payment_due_date': self.format_date(current_date + timedelta(days=30)),
            'bnw_order_reference_id': order_data.get('order_id', ''),
            'bnw_order_placement_date': self.format_date(
                order_data.get('order_date', current_date)
            ),
            
            # Customer information
            'bnw_customer_full_name': order_data.get('customer', {}).get('name', 'N/A'),
            'bnw_customer_email_address': order_data.get('customer', {}).get('email', 'N/A'),
            'bnw_customer_phone_number': order_data.get('customer', {}).get('phone', 'N/A'),
            
            # Financial data
            'bnw_order_subtotal_amount': self.format_currency(
                order_data.get('subtotal', 0)
            ),
            'bnw_tax_rate': order_data.get('tax_rate', 10),
            'bnw_tax_amount': self.format_currency(order_data.get('tax_amount', 0)),
            'bnw_shipping_amount': self.format_currency(order_data.get('shipping_amount', 0)),
            'bnw_discount_amount': self.format_currency(
                order_data.get('discount_amount', 0)
            ) if order_data.get('discount_amount', 0) > 0 else None,
            'discount_percentage': discount_percentage,
            'bnw_grand_total_amount': self.format_currency(
                order_data.get('total_amount', 0)
            ),
            
            # Items
            'items': items,
            
            # Company information
            'logo_url': self._get_logo_url(order_data),
            'company_address_line1': order_data.get(
                'company_address_line1', 
                'Main Street, Number 66/B'
            ),
            'company_address_line2': order_data.get(
                'company_address_line2',
                'South Winbond, YK'
            ),
        }
        
        return invoice_data
    
    def generate_html(
        self, 
        order_data: Dict, 
        template_name: str = "invoice_template.html"
    ) -> str:
        """
        Generate HTML invoice from template
        
        Args:
            order_data: Order information dictionary
            template_name: Name of the Jinja2 template file
            
        Returns:
            Rendered HTML string
        """
        try:
            # Prepare data
            invoice_data = self.prepare_invoice_data(order_data)
            
            # Load and render template
            template = self.env.get_template(template_name)
            html_content = template.render(**invoice_data)
            
            return html_content
        except Exception as e:
            # If template loading fails, create a simple HTML invoice
            invoice_ref = self.generate_invoice_ref(order_data.get('order_id', ''))
            customer_name = order_data.get('customer', {}).get('name', 'N/A')
            total_amount = order_data.get('total_amount', 0)
            
            simple_html = f"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <title>Invoice - {invoice_ref}</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 40px; }}
                    .header {{ border-bottom: 2px solid #333; padding-bottom: 20px; margin-bottom: 20px; }}
                    .invoice-title {{ font-size: 24px; font-weight: bold; color: #333; }}
                    .invoice-details {{ margin: 20px 0; }}
                    .total {{ font-size: 18px; font-weight: bold; margin-top: 20px; }}
                </style>
            </head>
            <body>
                <div class="header">
                    <div class="invoice-title">INVOICE</div>
                    <div>Invoice #: {invoice_ref}</div>
                    <div>Date: {self.format_date(datetime.now())}</div>
                </div>
                
                <div class="invoice-details">
                    <h3>Bill To:</h3>
                    <p>{customer_name}</p>
                    
                    <h3>Order Details:</h3>
                    <p>Order ID: {order_data.get('order_id', 'N/A')}</p>
                    <p>Subtotal: ${order_data.get('subtotal', 0):.2f}</p>
                    <p>Tax: ${order_data.get('tax_amount', 0):.2f}</p>
                    <p>Shipping: ${order_data.get('shipping_amount', 0):.2f}</p>
                    
                    <div class="total">
                        Total: ${total_amount:.2f}
                    </div>
                </div>
                
                <p><em>Note: Simplified invoice due to template error: {str(e)}</em></p>
            </body>
            </html>
            """
            return simple_html
    
    def generate_pdf(
        self,
        order_data: Dict,
        output_path: str,
        template_name: str = "invoice_template.html"
    ) -> str:
        """
        Generate PDF invoice from template
        
        Args:
            order_data: Order information dictionary
            output_path: Path where PDF should be saved
            template_name: Name of the Jinja2 template file
            
        Returns:
            Path to generated PDF file
        """
        # Generate HTML
        html_content = self.generate_html(order_data, template_name)
        
        # Convert to PDF using WeasyPrint
        HTML(string=html_content).write_pdf(output_path)
        
        return output_path
    
    def generate_pdf_bytes(
        self,
        order_data: Dict,
        template_name: str = "invoice_template.html"
    ) -> bytes:
        """
        Generate PDF invoice as bytes (useful for email attachments)
        
        Args:
            order_data: Order information dictionary
            template_name: Name of the Jinja2 template file
            
        Returns:
            PDF content as bytes
        """
        try:
            # Generate HTML
            html_content = self.generate_html(order_data, template_name)
            
            # Convert to PDF bytes
            pdf_bytes = HTML(string=html_content).write_pdf()
            
            return pdf_bytes
        except Exception as e:
            # If WeasyPrint fails, create a simple HTML fallback
            fallback_html = f"""
            <!DOCTYPE html>
            <html>
            <head><title>Invoice - {self.generate_invoice_ref(order_data.get('order_id', ''))}</title></head>
            <body>
                <h1>Invoice</h1>
                <p><strong>Order ID:</strong> {order_data.get('order_id', 'N/A')}</p>
                <p><strong>Customer:</strong> {order_data.get('customer', {}).get('name', 'N/A')}</p>
                <p><strong>Total:</strong> ${order_data.get('total_amount', 0):.2f}</p>
                <p><em>Note: Full invoice template could not be loaded. Error: {str(e)}</em></p>
            </body>
            </html>
            """
            try:
                return HTML(string=fallback_html).write_pdf()
            except Exception as fallback_error:
                raise Exception(f"Both main template and fallback failed. Main error: {str(e)}, Fallback error: {str(fallback_error)}")
    
    async def generate_invoice(self, order_data: Dict) -> Dict:
        """
        Generate invoice and return result with file path or bytes
        
        Args:
            order_data: Order information dictionary
            
        Returns:
            Dictionary with invoice result
        """
        try:
            # Validate template directory exists
            if not self.template_dir.exists():
                return {
                    "success": False,
                    "error": f"Template directory not found: {self.template_dir}",
                    "message": "Invoice template directory is missing"
                }
            
            # Check if template file exists
            template_file = self.template_dir / "invoice_template.html"
            if not template_file.exists():
                return {
                    "success": False,
                    "error": f"Template file not found: {template_file}",
                    "message": "Invoice template file is missing"
                }
            
            # Generate PDF bytes
            pdf_bytes = self.generate_pdf_bytes(order_data)
            
            # For now, return the PDF bytes directly
            # In production, you might want to save to file and return path
            return {
                "success": True,
                "pdf_bytes": pdf_bytes,
                "invoice_ref": self.generate_invoice_ref(order_data.get('order_id', '')),
                "message": "Invoice generated successfully"
            }
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            return {
                "success": False,
                "error": str(e),
                "error_details": error_details,
                "message": f"Failed to generate invoice: {str(e)}"
            }


# Example usage
if __name__ == "__main__":
    # Sample order data
    sample_order = {
        'order_id': 'a7b3c2d1-4e5f-6789-0abc-def123456789',
        'created_at': datetime.now(),
        'customer_name': 'Alisa Lumbert',
        'customer_email': 'alisa.lumbert@email.com',
        'customer_phone': '+1 (231) 321 4232',
        'subtotal': 210.00,
        'tax_rate': 10,
        'tax_amount': 21.00,
        'discount_amount': 11.55,
        'total_amount': 219.45,
        'items': [
            {
                'product_name': 'Items Name',
                'variant_name': 'Sample item product description',
                'price_per_unit': 20.00,
                'quantity': 3,
                'total_price': 60.00
            },
            {
                'product_name': 'Items Name',
                'variant_name': 'Another Sample item product description',
                'price_per_unit': 5.00,
                'quantity': 1,
                'total_price': 5.00
            },
            {
                'product_name': 'Items Name',
                'variant_name': 'Sample item product description',
                'price_per_unit': 40.00,
                'quantity': 2,
                'total_price': 80.00
            },
            {
                'product_name': 'Items Name',
                'variant_name': 'Another Sample item product description',
                'price_per_unit': 20.00,
                'quantity': 1,
                'total_price': 20.00
            },
            {
                'product_name': 'Items Name',
                'variant_name': 'Another Sample item product description',
                'price_per_unit': 15.00,
                'quantity': 3,
                'total_price': 45.00
            },
        ]
    }
    
    # Generate invoice
    generator = InvoiceGenerator()
    
    # Generate HTML (for preview)
    html = generator.generate_html(sample_order)
    print("HTML generated successfully")
    
    # Generate PDF
    output_file = "sample_invoice.pdf"
    generator.generate_pdf(sample_order, output_file)
    print(f"PDF generated: {output_file}")
