"""
Jinja Template Service for rendering emails and exports
"""
import os
from typing import Dict, Any, Optional
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape, Template, TemplateError
from pydantic import BaseModel
from core.logging import get_structured_logger
from core.config import settings

logger = get_structured_logger(__name__)


class RenderedTemplate(BaseModel):
    """Result of template rendering"""
    content: str
    template_name: str
    context_used: Dict[str, Any]
    rendered_at: str


class RenderedExport(BaseModel):
    """Result of export template rendering"""
    content: str
    format_type: str
    template_name: str
    data_used: Dict[str, Any]
    rendered_at: str


class TemplateValidationResult(BaseModel):
    """Result of template validation"""
    is_valid: bool
    errors: list[str]
    warnings: list[str]


class JinjaTemplateService:
    """Service for rendering Jinja templates for emails and exports"""
    
    def __init__(self, template_dir: str = "templates"):
        """
        Initialize the Jinja template service
        
        Args:
            template_dir: Directory containing template files
        """
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
    
    async def render_email_template(
        self,
        template_name: str,
        context: Dict[str, Any]
    ) -> RenderedTemplate:
        """
        Render an email template with the provided context
        
        Args:
            template_name: Name of the template file (e.g., 'welcome_email.html')
            context: Dictionary containing template variables
            
        Returns:
            RenderedTemplate with the rendered content
            
        Raises:
            TemplateError: If template rendering fails
        """
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
            
            from datetime import datetime
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
    
    async def render_export_template(
        self,
        template_name: str,
        data: Dict[str, Any],
        format_type: str  # "html", "csv", "json"
    ) -> RenderedExport:
        """
        Render an export template with the provided data
        
        Args:
            template_name: Name of the template file
            data: Dictionary containing export data
            format_type: Output format type
            
        Returns:
            RenderedExport with the rendered content
            
        Raises:
            TemplateError: If template rendering fails
        """
        try:
            template = self.env.get_template(template_name)
            
            # Add common export context variables
            export_context = {
                **data,
                'format_type': format_type,
                'generated_at': data.get('generated_at'),
                'company_name': data.get('company_name', 'Banwee')
            }
            
            rendered_content = template.render(**export_context)
            
            from datetime import datetime
            return RenderedExport(
                content=rendered_content,
                format_type=format_type,
                template_name=template_name,
                data_used=export_context,
                rendered_at=datetime.now().isoformat()
            )
            
        except TemplateError as e:
            logger.error(f"Export template rendering failed for {template_name}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error rendering export template {template_name}: {e}")
            raise TemplateError(f"Failed to render export template {template_name}: {e}")
    
    async def validate_template(
        self,
        template_content: str
    ) -> TemplateValidationResult:
        """
        Validate a template string for syntax errors
        
        Args:
            template_content: The template content as a string
            
        Returns:
            TemplateValidationResult with validation status and any errors
        """
        errors = []
        warnings = []
        
        try:
            # Parse the template to check for syntax errors
            template = self.env.from_string(template_content)
            
            # Try to render with empty context to catch basic issues
            try:
                template.render()
            except Exception as e:
                # This might be expected if template requires specific variables
                # Only warn about undefined variables, not error
                if "undefined" in str(e).lower():
                    warnings.append(f"Template contains undefined variables: {e}")
                else:
                    errors.append(f"Template rendering error: {e}")
            
        except TemplateError as e:
            errors.append(f"Template syntax error: {e}")
        except Exception as e:
            errors.append(f"Unexpected validation error: {e}")
        
        return TemplateValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    def create_template_file(self, template_name: str, content: str) -> bool:
        """
        Create a new template file
        
        Args:
            template_name: Name of the template file
            content: Template content
            
        Returns:
            True if successful, False otherwise
        """
        try:
            template_path = self.template_dir / template_name
            template_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(template_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"Template file created: {template_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create template file {template_name}: {e}")
            return False
    
    def list_templates(self) -> list[str]:
        """
        List all available template files
        
        Returns:
            List of template file names
        """
        try:
            templates = []
            for file_path in self.template_dir.rglob("*.html"):
                relative_path = file_path.relative_to(self.template_dir)
                templates.append(str(relative_path))
            return templates
        except Exception as e:
            logger.error(f"Failed to list templates: {e}")
            return []
    
    def template_exists(self, template_name: str) -> bool:
        """
        Check if a template file exists
        
        Args:
            template_name: Name of the template file
            
        Returns:
            True if template exists, False otherwise
        """
        template_path = self.template_dir / template_name
        return template_path.exists()