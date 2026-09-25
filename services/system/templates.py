"""Jinja Template Service for rendering emails and exports."""
from typing import Dict, Any
from pathlib import Path
from datetime import datetime

from jinja2 import Environment, FileSystemLoader, select_autoescape, TemplateError
from core.logging import get_structured_logger
from core.config import settings

logger = get_structured_logger(__name__)


from schemas.common.service_types import RenderedTemplate
from schemas.common.service_types import RenderedTemplate


class JinjaTemplateService:
    """Service for rendering Jinja templates for emails and exports"""
    
    def __init__(self, template_dir: str = "templates"):
        """Initialize the Jinja template service with a template directory."""
        self.template_dir = Path(template_dir)
        
        # Create template directory if it doesn't exist
        self.template_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize Jinja environment with security settings
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True
        )
        
        # Add custom filters for common formatting
        self.env.filters['currency'] = self._format_currency
        self.env.filters['date'] = self._format_date
        self.env.filters['datetime'] = self._format_datetime
        
        logger.info(f"JinjaTemplateService initialized with template directory: {self.template_dir}")
    
    def _format_currency(self, value: float, currency: str = "USD") -> str:
        """Format currency values"""
        if currency == "USD":
            return f"${value:.2f}"
        return f"{value:.2f} {currency}"
    
    def _format_date(self, value) -> str:
        """Format date values"""
        if hasattr(value, 'strftime'):
            return value.strftime('%B %d, %Y')
        return str(value)
    
    def _format_datetime(self, value) -> str:
        """Format datetime values"""
        if hasattr(value, 'strftime'):
            return value.strftime('%B %d, %Y at %I:%M %p')
        return str(value)
    
    async def render_email(self, template_name: str, context: Dict[str, Any]) -> RenderedTemplate:
        """Render an email template with the provided context"""
        try:
            template = self.env.get_template(template_name)
            
            # Add common email context variables
            email_context = {
                **context,
                'company_name': context.get('company_name', 'Banwee'),
                'support_email': context.get('support_email', 'support@banwee.com'),
                'current_year': context.get('current_year', '2024'),
                'frontend_url': context.get('frontend_url', settings.FRONTEND_URL)
            }
            rendered_content = template.render(**email_context)
            
            return RenderedTemplate(
                content=rendered_content,
                template_name=template_name,
                context_used=email_context,
                rendered_at=datetime.now().isoformat()
            )
            
        except TemplateError as e:
            logger.error(f"Template rendering failed for {template_name}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error rendering template {template_name}: {e}")
            raise TemplateError(f"Failed to render template {template_name}: {e}")


    
    
    
    