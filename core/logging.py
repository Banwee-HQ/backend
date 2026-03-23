"""
Enhanced logging configuration for the application.
Provides structured logging with JSON output, contextual information, and multiple handlers.
"""
import logging
import json
import sys
import os
from datetime import datetime
from typing import Any, Dict, Optional, Union
from pathlib import Path
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from enum import Enum


class LogLevel(Enum):
    """Log level enumeration"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogFormat(Enum):
    """Log format enumeration"""
    SIMPLE = "simple"
    DETAILED = "detailed"
    JSON = "json"


class StructuredLogger:
    """
    Enhanced structured logger with JSON output, file rotation, and contextual information
    """

    def __init__(
        self, 
        name: str = "banwee",
        level: Union[str, LogLevel] = LogLevel.INFO,
        log_format: LogFormat = LogFormat.JSON,
        enable_file_logging: bool = True,
        log_dir: Optional[str] = None
    ):
        self.name = name
        self.logger = logging.getLogger(name)
        self.log_format = log_format
        self.enable_file_logging = enable_file_logging
        
        # Set log level
        if isinstance(level, LogLevel):
            self.logger.setLevel(getattr(logging, level.value))
        else:
            self.logger.setLevel(getattr(logging, level.upper()))

        # Clear existing handlers to avoid duplicates
        self.logger.handlers.clear()
        
        # Setup handlers
        self._setup_console_handler()
        
        if enable_file_logging:
            self._setup_file_handlers(log_dir)

    def _setup_console_handler(self):
        """Setup console handler with appropriate formatter"""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        if self.log_format == LogFormat.JSON:
            formatter = logging.Formatter('%(message)s')
        elif self.log_format == LogFormat.DETAILED:
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
            )
        else:  # SIMPLE
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

    def _setup_file_handlers(self, log_dir: Optional[str] = None):
        """Setup file handlers with rotation"""
        if log_dir is None:
            log_dir = os.getenv('LOG_DIR', 'logs')
        
        log_path = Path(log_dir)
        log_path.mkdir(exist_ok=True)
        
        # General application log with rotation (INFO, WARNING, ERROR only)
        app_log_file = log_path / f"{self.name}.log"
        file_handler = RotatingFileHandler(
            app_log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5
        )
        file_handler.setLevel(logging.INFO)  # Only INFO, WARNING, ERROR
        
        # Error log with daily rotation (ERROR only for critical failures)
        error_log_file = log_path / f"{self.name}_error.log"
        error_handler = TimedRotatingFileHandler(
            error_log_file,
            when='midnight',
            interval=1,
            backupCount=30
        )
        error_handler.setLevel(logging.ERROR)  # ERROR only
        
        # JSON formatter for file logs
        json_formatter = logging.Formatter('%(message)s')
        file_handler.setFormatter(json_formatter)
        error_handler.setFormatter(json_formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(error_handler)

    def _create_log_entry(
        self,
        level: str,
        message: str,
        user_id: Optional[str] = None,
        endpoint: Optional[str] = None,
        request_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        exception: Optional[Exception] = None,
        extra_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a structured log entry with enhanced context
        """
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": level.upper(),
            "message": message,
            "service": "banwee-api",
            "logger": self.name,
        }

        if user_id:
            log_entry["user_id"] = user_id

        if endpoint:
            log_entry["endpoint"] = endpoint
            
        if request_id:
            log_entry["request_id"] = request_id

        if metadata:
            log_entry["metadata"] = metadata
            
        if extra_context:
            log_entry["context"] = extra_context

        if exception:
            log_entry["exception"] = {
                "type": type(exception).__name__,
                "message": str(exception),
                "module": getattr(exception, '__module__', None),
            }
            
            # Add stack trace for debugging
            import traceback
            log_entry["exception"]["traceback"] = traceback.format_exc()

        return log_entry

    def _log(
        self,
        level: str,
        message: str,
        user_id: Optional[str] = None,
        endpoint: Optional[str] = None,
        request_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        exception: Optional[Exception] = None,
        extra_context: Optional[Dict[str, Any]] = None
    ):
        """Internal logging method"""
        if self.log_format == LogFormat.JSON:
            log_entry = self._create_log_entry(
                level, message, user_id, endpoint, request_id, 
                metadata, exception, extra_context
            )
            log_message = json.dumps(log_entry, default=str)
        else:
            # For non-JSON formats, create a readable message
            log_message = message
            if metadata:
                log_message += f" | Metadata: {metadata}"
            if user_id:
                log_message += f" | User: {user_id}"
            if endpoint:
                log_message += f" | Endpoint: {endpoint}"
        
        # Log using the appropriate level
        getattr(self.logger, level.lower())(log_message)

    def debug(
        self,
        message: str,
        user_id: Optional[str] = None,
        endpoint: Optional[str] = None,
        request_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        extra_context: Optional[Dict[str, Any]] = None
    ):
        """Log debug message"""
        self._log("debug", message, user_id, endpoint, request_id, metadata, None, extra_context)

    def info(
        self,
        message: str,
        user_id: Optional[str] = None,
        endpoint: Optional[str] = None,
        request_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        extra_context: Optional[Dict[str, Any]] = None
    ):
        """Log info message"""
        self._log("info", message, user_id, endpoint, request_id, metadata, None, extra_context)

    def warning(
        self,
        message: str,
        user_id: Optional[str] = None,
        endpoint: Optional[str] = None,
        request_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        exception: Optional[Exception] = None,
        extra_context: Optional[Dict[str, Any]] = None
    ):
        """Log warning message"""
        self._log("warning", message, user_id, endpoint, request_id, metadata, exception, extra_context)

    def error(
        self,
        message: str,
        user_id: Optional[str] = None,
        endpoint: Optional[str] = None,
        request_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        exception: Optional[Exception] = None,
        extra_context: Optional[Dict[str, Any]] = None
    ):
        """Log error message"""
        self._log("error", message, user_id, endpoint, request_id, metadata, exception, extra_context)

    def critical(
        self,
        message: str,
        user_id: Optional[str] = None,
        endpoint: Optional[str] = None,
        request_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        exception: Optional[Exception] = None,
        extra_context: Optional[Dict[str, Any]] = None
    ):
        """Log critical message"""
        self._log("critical", message, user_id, endpoint, request_id, metadata, exception, extra_context)

    def log_request(
        self,
        method: str,
        endpoint: str,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
        duration_ms: Optional[float] = None,
        status_code: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log HTTP request with structured data"""
        request_data = {
            "method": method,
            "endpoint": endpoint,
            "duration_ms": duration_ms,
            "status_code": status_code
        }
        
        if metadata:
            request_data.update(metadata)
        
        self.info(
            f"{method} {endpoint}",
            user_id=user_id,
            endpoint=endpoint,
            request_id=request_id,
            metadata=request_data
        )

    def log_database_operation(
        self,
        operation: str,
        table: str,
        duration_ms: Optional[float] = None,
        affected_rows: Optional[int] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log database operations"""
        db_data = {
            "operation": operation,
            "table": table,
            "duration_ms": duration_ms,
            "affected_rows": affected_rows
        }
        
        if metadata:
            db_data.update(metadata)
        
        self.info(
            f"DB {operation} on {table}",
            user_id=user_id,
            metadata=db_data,
            extra_context={"component": "database"}
        )

    def log_business_event(
        self,
        event_type: str,
        event_data: Dict[str, Any],
        user_id: Optional[str] = None,
        request_id: Optional[str] = None
    ):
        """Log business events for analytics"""
        self.info(
            f"Business Event: {event_type}",
            user_id=user_id,
            request_id=request_id,
            metadata=event_data,
            extra_context={"component": "business_logic", "event_type": event_type}
        )


class LoggerManager:
    """
    Manager for creating and configuring loggers across the application
    """
    
    _loggers: Dict[str, StructuredLogger] = {}
    _default_config = {
        "level": LogLevel.INFO,
        "log_format": LogFormat.JSON,
        "enable_file_logging": True
    }
    
    @classmethod
    def configure_defaults(
        cls,
        level: Union[str, LogLevel] = LogLevel.INFO,
        log_format: LogFormat = LogFormat.JSON,
        enable_file_logging: bool = True,
        log_dir: Optional[str] = None
    ):
        """Configure default settings for all loggers"""
        cls._default_config = {
            "level": level,
            "log_format": log_format,
            "enable_file_logging": enable_file_logging,
            "log_dir": log_dir
        }
    
    @classmethod
    def get_logger(cls, name: str) -> StructuredLogger:
        """Get or create a structured logger instance"""
        if name not in cls._loggers:
            cls._loggers[name] = StructuredLogger(
                name=name,
                **cls._default_config
            )
        return cls._loggers[name]
    
    @classmethod
    def get_standard_logger(cls, name: str) -> logging.Logger:
        """Get a standard Python logger (for backward compatibility)"""
        return logging.getLogger(name)


def setup_logging(
    level: Union[str, LogLevel] = LogLevel.INFO,
    log_format: LogFormat = LogFormat.JSON,
    enable_file_logging: bool = True,
    log_dir: Optional[str] = None
) -> None:
    """
    Configure application-wide logging.
    
    Args:
        level: Logging level
        log_format: Log format (simple, detailed, json)
        enable_file_logging: Whether to enable file logging
        log_dir: Directory for log files
    """
    # Configure the logger manager defaults
    LoggerManager.configure_defaults(
        level=level,
        log_format=log_format,
        enable_file_logging=enable_file_logging,
        log_dir=log_dir
    )
    
    # Configure root logger for backward compatibility
    if isinstance(level, LogLevel):
        log_level = getattr(logging, level.value)
    else:
        log_level = getattr(logging, level.upper())
    
    if log_format == LogFormat.JSON:
        format_str = '%(message)s'
    elif log_format == LogFormat.DETAILED:
        format_str = '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    else:
        format_str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    logging.basicConfig(
        level=log_level,
        format=format_str,
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    
    # Set specific log levels for noisy libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a standard logger instance for a module (backward compatibility).
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        Configured logger instance
    """
    return LoggerManager.get_standard_logger(name)


def get_structured_logger(name: str) -> StructuredLogger:
    """
    Get a structured logger instance for a module.
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        Configured structured logger instance
    """
    return LoggerManager.get_logger(name)


# Create global structured logger instance for backward compatibility
structured_logger = LoggerManager.get_logger("banwee")

# For backward compatibility, also export a standard logger
logger = logging.getLogger(__name__)

# Export commonly used items
__all__ = [
    'StructuredLogger',
    'LoggerManager', 
    'LogLevel',
    'LogFormat',
    'setup_logging',
    'get_logger',
    'get_structured_logger',
    'structured_logger',
    'logger'
]