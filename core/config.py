"""
Application Configuration and Environment Management

This module provides:
- Environment variable management and validation
- Application settings with context-aware defaults
- Environment validation and setup utilities
- Pydantic-based configuration validation
"""

import os
import re
from typing import List, Dict, Any, Optional, Tuple, Literal
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from dotenv import load_dotenv
from pydantic import Field, field_validator, ValidationError, ConfigDict
from pydantic_settings import BaseSettings
from core.logging import get_structured_logger

# Configure logging
logger = get_structured_logger(__name__)


# =============================================================================
# ENUMS AND DATA CLASSES
# =============================================================================

class EnvironmentType(Enum):
    """Supported environment types"""
    DEVELOPMENT = "dev"
    PRODUCTION = "prod" 
    STAGING = "staging"
    LOCAL = "local"


class VariableType(Enum):
    """Types of environment variables for validation"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    URL = "url"
    EMAIL = "email"
    SECRET = "secret"
    JSON = "json"


@dataclass
class EnvironmentVariable:
    """Definition of an environment variable with validation rules"""
    name: str
    description: str
    variable_type: VariableType
    required: bool = True
    default_value: Optional[str] = None
    validation_pattern: Optional[str] = None
    sensitive: bool = False
    dev_override: Optional[str] = None
    prod_override: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of environment variable validation"""
    is_valid: bool
    missing_variables: List[str] = field(default_factory=list)
    invalid_variables: List[Tuple[str, str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error_message: Optional[str] = None


@dataclass
class EnvironmentContext:
    """Context information about the current environment"""
    is_docker: bool
    is_production: bool
    is_development: bool
    container_name: str
    env_file_path: Optional[str]


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def parse_cors(value: str) -> List[str]:
    """
    Parses CORS origins. Accepts comma-separated string or list-like string.
    """
    if not value:
        return [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://0.0.0.0:5173",
            "http://localhost:3000",
            "http://www.banwee.com",
            "https://www.banwee.com",
            "https://www.banwee.ca",
            "https://www.banwee.co.uk",
            "https://www.banwee.ng",
            "https://banwee.com"
        ]
    
    if isinstance(value, str):
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            return [i.strip().strip('"') for i in value[1:-1].split(",")]
        return [i.strip() for i in value.split(",")]
    
    raise ValueError("Invalid CORS format")


# =============================================================================
# PYDANTIC CONFIGURATION MODELS
# =============================================================================

class DatabaseConfig(BaseSettings):
    """Pydantic model for database configuration validation"""
    
    model_config = ConfigDict(extra='ignore', env_file='.env', case_sensitive=True)
    
    POSTGRES_DB_URL: str = Field(..., description="Complete PostgreSQL connection URL")
    
    DB_POOL_SIZE: int = Field(default=20, ge=1, le=100, description="Database connection pool size")
    DB_MAX_OVERFLOW: int = Field(default=30, ge=0, le=100, description="Max overflow connections")
    DB_POOL_TIMEOUT: int = Field(default=30, ge=1, description="Pool timeout in seconds")
    DB_POOL_RECYCLE: int = Field(default=3600, ge=300, description="Connection recycle time in seconds")
    
    @field_validator('POSTGRES_DB_URL')
    @classmethod
    def validate_db_url(cls, v):
        """Validate database URL format"""
        if not v.startswith(('postgresql://', 'postgresql+asyncpg://', 'postgresql+psycopg2://')):
            raise ValueError('Database URL must start with postgresql:// or postgresql+asyncpg://')
        return v


class RedisConfig(BaseSettings):
    """Pydantic model for Redis configuration validation"""
    
    model_config = ConfigDict(extra='ignore', env_file='.env', case_sensitive=True)
    
    REDIS_URL: str = Field(
        default="redis://redis:6379/0",
        description="Redis connection URL"
    )
    REDIS_CACHE_ENABLED: bool = Field(default=True, description="Enable Redis caching")
    REDIS_RATELIMIT_ENABLED: bool = Field(default=True, description="Enable Redis rate limiting")
    REDIS_CACHE_TTL: int = Field(default=3600, ge=60, description="Cache TTL in seconds")
    
    @field_validator('REDIS_URL')
    @classmethod
    def validate_redis_url(cls, v):
        """Validate Redis URL format"""
        if not v.startswith(('redis://', 'rediss://')):
            raise ValueError('Redis URL must start with redis:// or rediss://')
        return v


class SecurityConfig(BaseSettings):
    """Pydantic model for security configuration validation"""
    
    model_config = ConfigDict(extra='ignore', env_file='.env', case_sensitive=True)
    
    SECRET_KEY: str = Field(..., min_length=32, description="Application secret key")
    ALGORITHM: str = Field(default="HS256", description="JWT algorithm")
    
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, ge=5, le=1440)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, ge=1, le=90)
    
    STRIPE_SECRET_KEY: str = Field(..., description="Stripe API secret key")
    STRIPE_WEBHOOK_SECRET: str = Field(..., description="Stripe webhook secret")
    
    @field_validator('SECRET_KEY')
    @classmethod
    def validate_secret_key(cls, v):
        """Validate secret key strength"""
        env = os.getenv('ENVIRONMENT', 'local')
        if env == 'production':
            if len(v) < 64:
                raise ValueError('Production SECRET_KEY must be at least 64 characters')
            if v == 'your_secret_key_here_change_in_production':
                raise ValueError('Production SECRET_KEY must be changed from default value')
        return v
    
    @field_validator('STRIPE_SECRET_KEY')
    @classmethod
    def validate_stripe_key(cls, v):
        """Validate Stripe secret key format"""
        if not v.startswith(('sk_test_', 'sk_live_')):
            raise ValueError("STRIPE_SECRET_KEY must start with 'sk_test_' or 'sk_live_'")
        
        env = os.getenv('ENVIRONMENT', 'local')
        if env == 'production' and v.startswith('sk_test_'):
            raise ValueError('Production environment should use live Stripe keys (sk_live_)')
        
        return v
    
    @field_validator('STRIPE_WEBHOOK_SECRET')
    @classmethod
    def validate_webhook_secret(cls, v):
        """Validate Stripe webhook secret format"""
        if not v.startswith('whsec_'):
            raise ValueError("STRIPE_WEBHOOK_SECRET must start with 'whsec_'")
        return v


class ApplicationConfig(BaseSettings):
    """Pydantic model for general application configuration validation"""
    
    model_config = ConfigDict(extra='ignore', env_file='.env', case_sensitive=True)
    
    ENVIRONMENT: Literal["local", "staging", "production"] = Field(
        default="local",
        description="Application environment"
    )
    DOMAIN: str = Field(default="localhost", description="Application domain")
    
    FRONTEND_URL: str = Field(default="http://localhost:5173", description="Frontend URL")
    BACKEND_URL: str = Field(default="http://localhost:8000", description="Backend URL")
    BACKEND_CORS_ORIGINS: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        description="CORS origins"
    )
    
    # Email Configuration (optional in development)
    MAILJET_API_KEY: Optional[str] = Field(None, description="Mailjet API key")
    MAILJET_API_SECRET: Optional[str] = Field(None, description="Mailjet API secret")
    MAILJET_FROM_EMAIL: str = Field(
        default="Banwee <noreply@banwee.com>",
        description="From email address"
    )
    
    # Business Logic Configuration
    
    @field_validator('FRONTEND_URL', 'BACKEND_URL')
    @classmethod
    def validate_urls(cls, v):
        """Validate URL format"""
        if not v.startswith(('http://', 'https://')):
            raise ValueError('URLs must start with http:// or https://')
        return v
    
    @field_validator('MAILJET_API_KEY', 'MAILJET_API_SECRET')
    @classmethod
    def validate_email_config(cls, v):
        """Validate email configuration in production"""
        env = os.getenv('ENVIRONMENT', 'local')
        if env == 'production' and not v:
            logger.warning(f'Email configuration is not set in production environment')
        return v


class PydanticConfigValidator:
    """Validator that uses Pydantic models for comprehensive configuration validation"""
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def validate_all(self) -> ValidationResult:
        """Validate all configuration sections using Pydantic models"""
        try:
            # Validate each configuration section
            self._validate_database()
            self._validate_redis()
            self._validate_security()
            self._validate_application()
            
            # Check if there were any errors
            is_valid = len(self.errors) == 0
            
            return ValidationResult(
                is_valid=is_valid,
                missing_variables=[],
                invalid_variables=[(err, "") for err in self.errors],
                warnings=self.warnings,
                error_message="\n".join(self.errors) if self.errors else None
            )
            
        except Exception as e:
            logger.exception("Unexpected error during Pydantic validation")
            return ValidationResult(
                is_valid=False,
                error_message=f"Validation error: {str(e)}"
            )
    
    def _validate_database(self):
        """Validate database configuration"""
        try:
            DatabaseConfig()
            logger.info("✓ Database configuration validated successfully")
        except ValidationError as e:
            for error in e.errors():
                field = error['loc'][0]
                msg = error['msg']
                self.errors.append(f"Database config - {field}: {msg}")
            logger.error("✗ Database configuration validation failed")
    
    def _validate_redis(self):
        """Validate Redis configuration"""
        try:
            RedisConfig()
            logger.info("✓ Redis configuration validated successfully")
        except ValidationError as e:
            for error in e.errors():
                field = error['loc'][0]
                msg = error['msg']
                self.errors.append(f"Redis config - {field}: {msg}")
            logger.error("✗ Redis configuration validation failed")
    
    def _validate_security(self):
        """Validate security configuration"""
        try:
            SecurityConfig()
            logger.info("✓ Security configuration validated successfully")
        except ValidationError as e:
            for error in e.errors():
                field = error['loc'][0]
                msg = error['msg']
                self.errors.append(f"Security config - {field}: {msg}")
            logger.error("✗ Security configuration validation failed")
    
    def _validate_application(self):
        """Validate application configuration"""
        try:
            ApplicationConfig()
            logger.info("✓ Application configuration validated successfully")
        except ValidationError as e:
            for error in e.errors():
                field = error['loc'][0]
                msg = error['msg']
                # Email config warnings are not critical in development
                if field in ['MAILJET_API_KEY', 'MAILJET_API_SECRET'] and os.getenv('ENVIRONMENT') != 'production':
                    self.warnings.append(f"Application config - {field}: {msg}")
                else:
                    self.errors.append(f"Application config - {field}: {msg}")
            if not self.errors:
                logger.info("✓ Application configuration validated successfully")
            else:
                logger.error("✗ Application configuration validation failed")


# =============================================================================
# ENVIRONMENT VARIABLE DEFINITIONS
# =============================================================================

class VariableDefinitions:
    """Centralized environment variable definitions for all containers"""
    
    BACKEND_VARIABLES = [
        # Database Configuration
        EnvironmentVariable(
            name="POSTGRES_DB_URL",
            description="Complete PostgreSQL connection URL",
            variable_type=VariableType.URL,
            required=True,
            validation_pattern=r"^postgresql(\+asyncpg)?://.*"
        ),
        
        # Redis Configuration
        EnvironmentVariable(
            name="REDIS_URL",
            description="Redis connection URL",
            variable_type=VariableType.URL,
            required=True,
            default_value="redis://redis:6379/0",
            dev_override="redis://localhost:6379/0",
            prod_override="redis://redis:6379/0"
        ),
        
        # Security Configuration
        EnvironmentVariable(
            name="SECRET_KEY",
            description="Application secret key for JWT and encryption",
            variable_type=VariableType.SECRET,
            required=True,
            sensitive=True,
            validation_pattern=r"^.{32,}$"
        ),
        EnvironmentVariable(
            name="STRIPE_SECRET_KEY",
            description="Stripe API secret key",
            variable_type=VariableType.SECRET,
            required=True,
            sensitive=True,
            validation_pattern=r"^sk_(test_|live_)[a-zA-Z0-9]{99}$"
        ),
        EnvironmentVariable(
            name="STRIPE_WEBHOOK_SECRET",
            description="Stripe webhook endpoint secret",
            variable_type=VariableType.SECRET,
            required=True,
            sensitive=True,
            validation_pattern=r"^whsec_[a-zA-Z0-9_]{10,}$"
        ),
        
        # Application Settings
        EnvironmentVariable(
            name="ENVIRONMENT",
            description="Application environment (local, staging, production)",
            variable_type=VariableType.STRING,
            required=True,
            default_value="local",
            validation_pattern=r"^(local|staging|production)$"
        ),
        EnvironmentVariable(
            name="FRONTEND_URL",
            description="Frontend application URL",
            variable_type=VariableType.URL,
            required=True,
            default_value="http://localhost:5173"
        ),
        EnvironmentVariable(
            name="BACKEND_URL",
            description="Backend application URL",
            variable_type=VariableType.URL,
            required=True,
            default_value="http://localhost:8000"
        ),
        
        # Email Configuration
        EnvironmentVariable(
            name="MAILJET_API_KEY",
            description="Mailjet API key for email sending",
            variable_type=VariableType.SECRET,
            required=False,
            sensitive=True
        ),
        EnvironmentVariable(
            name="MAILJET_API_SECRET",
            description="Mailjet API secret for email sending",
            variable_type=VariableType.SECRET,
            required=False,
            sensitive=True
        ),
    ]


# =============================================================================
# MAIN SETTINGS CLASS
# =============================================================================

class Settings:
    """
    Application settings with environment validation and context awareness
    """
    
    def __init__(self):
        self._load_environment()
        self._initialize_settings()
        self._validate_configuration()
    
    def _load_environment(self):
        """Load environment variables from .env file"""
        ENVIRONMENT = os.getenv('ENVIRONMENT', 'local')
        
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        
        # Priority order for environment files
        env_files = []
        
        if ENVIRONMENT in ['local', 'dev']:
            # For local development, check these files in order
            env_files = [
                os.path.join(BASE_DIR, 'backend', '.env'),        # Backend-specific config
                os.path.join(BASE_DIR, 'backend', '.env.example') # Backend template
            ]
        else:
            env_files = [
                os.path.join(BASE_DIR, 'backend', '.env'),        # Backend config
                os.path.join(BASE_DIR, 'backend', '.env.example') # Backend template
            ]
        
        # Load the first existing file
        for env_file in env_files:
            if os.path.exists(env_file):
                load_dotenv(env_file)
                logger.info(f"Loaded environment from {env_file}")
                break
        else:
            logger.warning("No environment file found")

    def _initialize_settings(self):
        """Initialize all configuration settings."""
        
        # --- General Environment Settings ---
        self.DOMAIN: str = os.getenv('DOMAIN', 'localhost')
        self.ENVIRONMENT: Literal["local", "staging", "production"] = os.getenv('ENVIRONMENT', 'local')
        
        # --- URLs ---
        self.FRONTEND_URL: str = os.getenv('FRONTEND_URL', 'http://localhost:5173')
        self.BACKEND_URL: str = os.getenv('BACKEND_URL', 'http://localhost:8000')
        cors_origins = os.getenv('BACKEND_CORS_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173,http://0.0.0.0:5173')
        
        # --- PostgreSQL Database Configuration ---
        self.POSTGRES_DB_URL: str = os.getenv('POSTGRES_DB_URL')
        
        # Database connection pool settings
        self.DB_POOL_SIZE: int = int(os.getenv('DB_POOL_SIZE', 20))
        self.DB_MAX_OVERFLOW: int = int(os.getenv('DB_MAX_OVERFLOW', 30))
        self.DB_POOL_TIMEOUT: int = int(os.getenv('DB_POOL_TIMEOUT', 30))
        self.DB_POOL_RECYCLE: int = int(os.getenv('DB_POOL_RECYCLE', 3600))
        
        # --- Security Settings ---
        self.SECRET_KEY: str = os.getenv('SECRET_KEY')
        self.STRIPE_SECRET_KEY: str = os.getenv('STRIPE_SECRET_KEY')
        self.STRIPE_WEBHOOK_SECRET: str = os.getenv('STRIPE_WEBHOOK_SECRET')
        self.ALGORITHM: str = os.getenv('ALGORITHM', "HS256")
        
        # Session and Token Configuration
        self.ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', 30))
        self.REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv('REFRESH_TOKEN_EXPIRE_DAYS', 7))
        
        # Session Security
        self.FORCE_LOGOUT_ON_PASSWORD_CHANGE: bool = os.getenv('FORCE_LOGOUT_ON_PASSWORD_CHANGE', 'true').lower() == 'true'
        
        # --- Redis Configuration ---
        self.ENABLE_REDIS: bool = os.getenv('ENABLE_REDIS', 'true').lower() == 'true'
        self.REDIS_URL: str = os.getenv('REDIS_URL')
        self.REDIS_CACHE_ENABLED: bool = os.getenv('REDIS_CACHE_ENABLED', 'true').lower() == 'true'
        self.REDIS_RATELIMIT_ENABLED: bool = os.getenv('REDIS_RATELIMIT_ENABLED', 'true').lower() == 'true'
        self.REDIS_CACHE_TTL: int = int(os.getenv('REDIS_CACHE_TTL', '3600'))
        self.REDIS_CART_TTL_GUEST: int = int(os.getenv('REDIS_CART_TTL_GUEST', '1800'))  # 30 minutes for guests
        self.REDIS_CART_TTL_USER: int = int(os.getenv('REDIS_CART_TTL_USER', '259200'))  # 3 days for users
        self.REDIS_CART_EXTEND_ON_ADD: bool = os.getenv('REDIS_CART_EXTEND_ON_ADD', 'true').lower() == 'true'
        
        # --- Background Tasks Configuration (ARQ + FastAPI) ---
        self.ENABLE_ARQ: bool = os.getenv('ENABLE_ARQ', 'true').lower() == 'true'
        self.ARQ_REDIS_URL: str = os.getenv('ARQ_REDIS_URL', 'redis://redis:6379/0')
        
        # --- CORS Configuration ---
        self.BACKEND_CORS_ORIGINS: List[str] = parse_cors(cors_origins)
        
        # ... (rest of the settings)
        self.MAILJET_API_KEY: str = os.getenv('MAILJET_API_KEY', '')
        self.MAILJET_API_SECRET: str = os.getenv('MAILJET_API_SECRET', '')
        self.MAILJET_FROM_EMAIL: str = os.getenv('MAILJET_FROM_EMAIL', 'Banwee <noreply@banwee.com>')
        self.TELEGRAM_BOT_TOKEN: str = os.getenv('TELEGRAM_BOT_TOKEN', '')
        self.WHATSAPP_ACCESS_TOKEN: str = os.getenv('WHATSAPP_ACCESS_TOKEN', '')
        self.PHONE_NUMBER_ID: str = os.getenv('PHONE_NUMBER_ID', '')
        self.FACEBOOK_APP_ID: str = os.getenv('FACEBOOK_APP_ID')
        self.FACEBOOK_APP_SECRET: str = os.getenv('FACEBOOK_APP_SECRET')
        self.TIKTOK_CLIENT_KEY: str = os.getenv('TIKTOK_CLIENT_KEY')
        self.TIKTOK_CLIENT_SECRET: str = os.getenv('TIKTOK_CLIENT_SECRET')
        self.ADMIN_USER_ID: str = os.getenv('ADMIN_USER_ID', 'your_admin_uuid_here')
        self.NOTIFICATION_CLEANUP_DAYS: int = int(os.getenv('NOTIFICATION_CLEANUP_DAYS', 30))
        self.NOTIFICATION_CLEANUP_INTERVAL_SECONDS: int = int(os.getenv('NOTIFICATION_CLEANUP_INTERVAL_SECONDS', 86400))
        
        # --- Business Logic Configuration ---
    
    @property
    def server_host(self) -> str:
        """Determines the server host URL based on the environment."""
        return f"http://{self.DOMAIN}" if self.ENVIRONMENT == "local" else f"https://{self.DOMAIN}"
    
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        """Constructs the SQLAlchemy database URI for async operations."""
        if not self.POSTGRES_DB_URL:
            raise ValueError("POSTGRES_DB_URL is required")
        # Add asyncpg driver for async operations
        if '+asyncpg' not in self.POSTGRES_DB_URL and '+psycopg2' not in self.POSTGRES_DB_URL:
            return self.POSTGRES_DB_URL.replace('postgresql://', 'postgresql+asyncpg://')
        return self.POSTGRES_DB_URL
    
    @property
    def SQLALCHEMY_DATABASE_URI_SYNC(self) -> str:
        """Constructs the SQLAlchemy database URI for synchronous operations."""
        if not self.POSTGRES_DB_URL:
            raise ValueError("POSTGRES_DB_URL is required")
        # Add psycopg2 driver for sync operations and convert SSL parameters
        sync_uri = self.POSTGRES_DB_URL
        if '+asyncpg' not in sync_uri and '+psycopg2' not in sync_uri:
            sync_uri = sync_uri.replace('postgresql://', 'postgresql+psycopg2://')
        elif '+asyncpg' in sync_uri:
            sync_uri = sync_uri.replace('+asyncpg', '+psycopg2')
        
        # Convert SSL parameters for psycopg2
        if 'ssl=require' in sync_uri:
            sync_uri = sync_uri.replace('ssl=require', 'sslmode=require')
        
        return sync_uri
    
    def _validate_configuration(self):
        """Validate all configuration settings"""
        # Use Pydantic validator for comprehensive validation
        pydantic_validator = PydanticConfigValidator()
        pydantic_result = pydantic_validator.validate_all()
        
        if not pydantic_result.is_valid:
            logger.error("Configuration validation failed:")
            logger.error(pydantic_result.error_message)
            raise ValueError(f"Configuration validation failed:\n{pydantic_result.error_message}")
        
        if pydantic_result.warnings:
            for warning in pydantic_result.warnings:
                logger.warning(warning)
        
        # Run legacy validators for backward compatibility
        self.validate_required_settings()
        self.validate_stripe_configuration()
    
    def validate_required_settings(self) -> None:
        """Validates that all required configuration settings are present."""
        missing_settings = []
        
        if not self.SECRET_KEY:
            missing_settings.append("SECRET_KEY is required for token signing")
        
        if not self.STRIPE_SECRET_KEY:
            missing_settings.append("STRIPE_SECRET_KEY is required for Stripe API authentication")
        
        if not self.STRIPE_WEBHOOK_SECRET:
            missing_settings.append("STRIPE_WEBHOOK_SECRET is required for webhook signature verification")
        
        if self.ENABLE_REDIS and not self.REDIS_URL:
            missing_settings.append("REDIS_URL is required for Redis connection")
        
        if self.ENABLE_ARQ and not self.ARQ_REDIS_URL:
            missing_settings.append("ARQ_REDIS_URL is required for background tasks")
        
        if not self.POSTGRES_DB_URL:
            missing_settings.append("POSTGRES_DB_URL is required for database connection")
        
        if missing_settings:
            error_message = "Missing required configuration settings:\n" + "\n".join(f"- {setting}" for setting in missing_settings)
            raise ValueError(error_message)
    
    def validate_stripe_configuration(self) -> None:
        """Validates Stripe-specific configuration settings."""
        if self.STRIPE_SECRET_KEY and not self.STRIPE_SECRET_KEY.startswith(('sk_test_', 'sk_live_')):
            raise ValueError("STRIPE_SECRET_KEY must start with 'sk_test_' or 'sk_live_'")
        
        if self.STRIPE_WEBHOOK_SECRET and not self.STRIPE_WEBHOOK_SECRET.startswith('whsec_'):
            raise ValueError("STRIPE_WEBHOOK_SECRET must start with 'whsec_'")


# =============================================================================
# ENVIRONMENT VALIDATOR
# =============================================================================

class EnvironmentValidator:
    """Enhanced environment validator with context-aware validation"""
    
    def __init__(self):
        self.context = self._detect_environment_context()
    
    def _detect_environment_context(self) -> EnvironmentContext:
        """Detect the current environment context"""
        
        is_docker = (
            os.path.exists('/.dockerenv') or
            os.getenv('DOCKER_CONTAINER') == 'true' or
            os.getenv('KUBERNETES_SERVICE_HOST') is not None
        )
        
        env_type = os.getenv('ENVIRONMENT', 'local').lower()
        is_production = env_type in ['production', 'prod']
        is_development = env_type in ['development', 'dev', 'local']
        
        container_name = self._detect_container_name()
        env_file_path = self._find_env_file()
        
        return EnvironmentContext(
            is_docker=is_docker,
            is_production=is_production,
            is_development=is_development,
            container_name=container_name,
            env_file_path=env_file_path
        )
    
    def _detect_container_name(self) -> str:
        """Detect the current container name"""
        container_name = os.getenv('CONTAINER_NAME')
        if container_name:
            return container_name.lower()
        
        cwd = Path.cwd()
        if 'backend' in cwd.parts:
            return 'backend'
        elif 'frontend' in cwd.parts:
            return 'frontend'
        elif 'negotiator' in cwd.parts:
            return 'negotiator'
        elif 'scheduler' in cwd.parts:
            return 'scheduler'
        
        return 'backend'
    
    def _find_env_file(self) -> Optional[str]:
        """Find the appropriate .env file"""
        current_env = Path('.env')
        if current_env.exists():
            return str(current_env)
        
        container_paths = [
            Path('backend/.env'),
            Path('frontend/.env'),
            Path('../.env'),
        ]
        
        for path in container_paths:
            if path.exists():
                return str(path)
        
        return None
    
    def validate_startup_environment(self) -> ValidationResult:
        """Perform comprehensive startup validation with context awareness"""
        try:
            logger.info(f"Validating environment for {self.context.container_name} container")
            
            if self.context.env_file_path:
                load_dotenv(self.context.env_file_path)
                logger.info(f"Loaded environment from {self.context.env_file_path}")
            
            validation_rules = self._get_validation_rules()
            result = self._validate_with_context(validation_rules)
            self._add_context_warnings(result)
            
            return result
            
        except Exception as e:
            logger.error(f"Startup validation failed: {e}")
            return ValidationResult(
                is_valid=False,
                error_message=f"Validation error: {str(e)}"
            )
    
    def _get_validation_rules(self) -> List[EnvironmentVariable]:
        """Get validation rules appropriate for the current context"""
        if self.context.container_name == 'backend':
            rules = VariableDefinitions.BACKEND_VARIABLES.copy()
        else:
            rules = [
                EnvironmentVariable(
                    name="ENVIRONMENT",
                    description="Application environment",
                    variable_type=VariableType.STRING,
                    required=True,
                    default_value="local"
                )
            ]
        
        # Adjust rules based on context
        if self.context.is_development:
            for rule in rules:
                if rule.name in ['MAILJET_API_KEY', 'MAILJET_API_SECRET']:
                    rule.required = False
        
        return rules
    
    def _validate_with_context(self, rules: List[EnvironmentVariable]) -> ValidationResult:
        """Validate environment variables with context awareness"""
        missing_variables = []
        invalid_variables = []
        warnings = []
        
        for rule in rules:
            value = os.getenv(rule.name)
            
            # Apply environment-specific overrides
            if self.context.is_development and rule.dev_override:
                if not value or value == rule.default_value:
                    value = rule.dev_override
                    os.environ[rule.name] = value
                    warnings.append(f"Applied development override for {rule.name}")
            
            elif self.context.is_production and rule.prod_override:
                if not value or value == rule.default_value:
                    value = rule.prod_override
                    os.environ[rule.name] = value
                    warnings.append(f"Applied production override for {rule.name}")
            
            # Check required variables
            if rule.required and not value:
                if rule.default_value:
                    os.environ[rule.name] = rule.default_value
                    warnings.append(f"Using default value for {rule.name}")
                else:
                    missing_variables.append(rule.name)
                    continue
            
            # Validate variable if present
            if value:
                error = self._validate_variable_value(rule, value)
                if error:
                    invalid_variables.append((rule.name, error))
        
        # Generate error message
        error_message = None
        if missing_variables or invalid_variables:
            error_parts = []
            
            if missing_variables:
                error_parts.append(
                    f"Missing required variables for {self.context.container_name}:\n" +
                    "\n".join(f"  - {var}" for var in missing_variables)
                )
            
            if invalid_variables:
                error_parts.append(
                    f"Invalid variables for {self.context.container_name}:\n" +
                    "\n".join(f"  - {var}: {error}" for var, error in invalid_variables)
                )
            
            error_message = "\n\n".join(error_parts)
        
        return ValidationResult(
            is_valid=len(missing_variables) == 0 and len(invalid_variables) == 0,
            missing_variables=missing_variables,
            invalid_variables=invalid_variables,
            warnings=warnings,
            error_message=error_message
        )
    
    def _validate_variable_value(self, rule: EnvironmentVariable, value: str) -> Optional[str]:
        """Validate a single environment variable value"""
        try:
            # Type-specific validation
            if rule.variable_type == VariableType.INTEGER:
                try:
                    int(value)
                except ValueError:
                    return f"Must be a valid integer, got: {value}"
            
            elif rule.variable_type == VariableType.URL:
                if not value.startswith(("http://", "https://", "redis://", "postgresql://", "postgresql+asyncpg://")):
                    return f"Must be a valid URL, got: {value}"
            
            # Pattern validation
            if rule.validation_pattern:
                if not re.match(rule.validation_pattern, value):
                    return f"Does not match required pattern: {rule.validation_pattern}"
            
            # Context-specific validation
            if self.context.is_production and rule.sensitive:
                if rule.name == 'SECRET_KEY' and len(value) < 32:
                    return "SECRET_KEY must be at least 32 characters in production"
                
                if 'test' in value.lower() and rule.name.startswith('STRIPE'):
                    return f"Production environment should not use test Stripe keys"
            
            return None
            
        except Exception as e:
            return f"Validation error: {str(e)}"
    
    def _add_context_warnings(self, result: ValidationResult):
        """Add context-specific warnings to the validation result"""
        if self.context.is_development:
            result.warnings.append("Running in development mode")
        
        if self.context.is_production:
            result.warnings.append("Running in production mode")
        
        if self.context.is_docker:
            result.warnings.append("Running in Docker container")


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def validate_startup_environment() -> ValidationResult:
    """Validate environment for application startup"""
    validator = EnvironmentValidator()
    return validator.validate_startup_environment()


def get_setup_instructions() -> str:
    """Get context-specific setup instructions"""
    validator = EnvironmentValidator()
    instructions = [
        f"# Environment Setup Instructions for {validator.context.container_name.title()}",
        "",
        f"**Current Context:**",
        f"- Container: {validator.context.container_name}",
        f"- Docker: {'Yes' if validator.context.is_docker else 'No'}",
        f"- Environment: {'Production' if validator.context.is_production else 'Development'}",
        "",
    ]
    
    if not validator.context.env_file_path:
        instructions.extend([
            "## Missing .env File",
            "",
            "1. Create a .env file in the appropriate location",
            "2. Edit the .env file with your configuration values",
            "",
        ])
    
    return "\n".join(instructions)


# =============================================================================
# MAIN SETTINGS INSTANCE
# =============================================================================

# Instantiate the settings object to be used throughout the application
settings = Settings()