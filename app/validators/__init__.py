"""
app/validators
───────────────
Central validation library.

Quick-start:

    from app.validators import (
        validate_email_address,
        validate_password,
        validate_message,
        validate_upload,
        validate_name,
        validate_url,
        validate_search_query,
        validate_tags,
        get_pagination_params,
        get_sort_params,
        ValidationResult,
    )
"""

from .email_validator   import validate_email_address, ValidationResult
from .password_validator import validate_password, get_strength_label
from .message_validator  import validate_message, sanitize_message
from .upload_validator   import validate_upload, sanitize_filename
from .user_input_validator import (
    validate_name,
    validate_text_field,
    validate_object_id,
    validate_url,
    validate_search_query,
    validate_tags,
)
from .api_request_validator import (
    PaginationParams, SortParams, DateRangeParams,
    get_pagination_params, get_sort_params, get_date_range_params,
    validate_enum_param, validate_batch_size,
)

__all__ = [
    # Core result type
    "ValidationResult",
    # Email
    "validate_email_address",
    # Password
    "validate_password", "get_strength_label",
    # Message / prompt injection
    "validate_message", "sanitize_message",
    # Upload
    "validate_upload", "sanitize_filename",
    # User inputs
    "validate_name", "validate_text_field", "validate_object_id",
    "validate_url", "validate_search_query", "validate_tags",
    # API request
    "PaginationParams", "SortParams", "DateRangeParams",
    "get_pagination_params", "get_sort_params", "get_date_range_params",
    "validate_enum_param", "validate_batch_size",
]
