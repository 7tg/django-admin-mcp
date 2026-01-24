"""
Error handling utilities for django-admin-mcp handlers.

Provides secure error responses that don't leak internal information
while logging detailed errors for debugging.
"""

import logging
from typing import Any

from django.core.exceptions import (
    FieldDoesNotExist,
    ObjectDoesNotExist,
    PermissionDenied,
    ValidationError as DjangoValidationError,
)
from django.db import DatabaseError, IntegrityError, OperationalError
from pydantic import ValidationError as PydanticValidationError

logger = logging.getLogger(__name__)


def handle_database_error(e: Exception, operation: str = "database operation") -> dict[str, Any]:
    """
    Handle database-related exceptions with generic error messages.

    Args:
        e: The database exception that occurred.
        operation: Description of the operation that failed.

    Returns:
        Dictionary with generic error message and code.
    """
    if isinstance(e, IntegrityError):
        logger.error(f"Integrity error during {operation}: {e}")
        return {
            "error": "A database constraint was violated",
            "code": "integrity_error",
        }
    elif isinstance(e, OperationalError):
        logger.error(f"Database error during {operation}: {e}")
        return {
            "error": "A database error occurred",
            "code": "database_error",
        }
    elif isinstance(e, DatabaseError):
        logger.error(f"Database error during {operation}: {e}")
        return {
            "error": "A database error occurred",
            "code": "database_error",
        }
    else:
        logger.exception(f"Unexpected error during {operation}")
        return {
            "error": "An unexpected error occurred",
            "code": "internal_error",
        }


def handle_validation_error(e: Exception, operation: str = "validation") -> dict[str, Any]:
    """
    Handle validation exceptions.

    Args:
        e: The validation exception that occurred.
        operation: Description of the operation that failed.

    Returns:
        Dictionary with validation error message and code.
    """
    logger.warning(f"Validation error during {operation}: {e}")
    return {
        "error": "Validation failed",
        "code": "validation_error",
    }


def handle_not_found_error(model_name: str, obj_id: Any = None) -> dict[str, Any]:
    """
    Handle object not found exceptions.

    Args:
        model_name: Name of the model that wasn't found.
        obj_id: Optional ID that wasn't found.

    Returns:
        Dictionary with not found error message and code.
    """
    if obj_id:
        logger.info(f"Object not found: {model_name} with id {obj_id}")
    else:
        logger.info(f"Model not found: {model_name}")
    return {
        "error": f"{model_name.capitalize()} not found",
        "code": "not_found",
    }


def handle_permission_error(operation: str, model_name: str) -> dict[str, Any]:
    """
    Handle permission denied exceptions.

    Args:
        operation: The operation that was denied.
        model_name: The model name the operation was attempted on.

    Returns:
        Dictionary with permission denied error message and code.
    """
    logger.warning(f"Permission denied: cannot {operation} {model_name}")
    return {
        "error": f"Permission denied: cannot {operation} {model_name}",
        "code": "permission_denied",
    }


def handle_generic_error(e: Exception, operation: str = "operation") -> dict[str, Any]:
    """
    Handle any exception with a generic error message.

    This is the fallback handler that should be used for unexpected exceptions
    to prevent information disclosure.

    Args:
        e: The exception that occurred.
        operation: Description of the operation that failed.

    Returns:
        Dictionary with generic error message and code.
    """
    # Check for common Django exceptions that we can handle more specifically
    if isinstance(e, ObjectDoesNotExist):
        logger.info(f"Object not found during {operation}: {e}")
        return {
            "error": "Object not found",
            "code": "not_found",
        }
    elif isinstance(e, FieldDoesNotExist):
        logger.warning(f"Invalid field during {operation}: {e}")
        return {
            "error": "Invalid field specified",
            "code": "invalid_field",
        }
    elif isinstance(e, PermissionDenied):
        logger.warning(f"Permission denied during {operation}: {e}")
        return {
            "error": "Permission denied",
            "code": "permission_denied",
        }
    elif isinstance(e, (DjangoValidationError, PydanticValidationError)):
        return handle_validation_error(e, operation)
    elif isinstance(e, (IntegrityError, OperationalError, DatabaseError)):
        return handle_database_error(e, operation)
    elif isinstance(e, (ValueError, TypeError)):
        logger.warning(f"Invalid input during {operation}: {e}")
        return {
            "error": "Invalid input provided",
            "code": "invalid_input",
        }
    else:
        # For any other unexpected exception, log with full traceback
        logger.exception(f"Unexpected error during {operation}")
        return {
            "error": "An unexpected error occurred",
            "code": "internal_error",
        }
