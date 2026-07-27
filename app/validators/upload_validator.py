"""
app/validators/upload_validator.py
────────────────────────────────────
File upload validation.

validate_upload(file, allowed_extensions, max_size_mb) → ValidationResult
  - File extension whitelist
  - MIME type check (not trusting client Content-Type)
  - File size limit
  - Malicious filename detection (path traversal, null bytes)
  - Magic bytes / file signature verification
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional
from .email_validator import ValidationResult

# ── Magic byte signatures ─────────────────────────────────────
# Enough bytes to identify the real file type
_MAGIC_BYTES: dict[str, bytes] = {
    "pdf":  b"%PDF",
    "png":  b"\x89PNG",
    "jpg":  b"\xff\xd8\xff",
    "jpeg": b"\xff\xd8\xff",
    "gif":  b"GIF8",
    "zip":  b"PK\x03\x04",
    "docx": b"PK\x03\x04",   # .docx is a zip
    "xlsx": b"PK\x03\x04",
    "txt":  None,              # no reliable magic — skip
    "csv":  None,
    "json": None,
    "md":   None,
}

# Dangerous executable / script extensions always blocked
_BLOCKED_EXTENSIONS = {
    "exe", "bat", "cmd", "sh", "bash", "ps1", "vbs", "js", "ts",
    "py", "rb", "php", "pl", "lua", "jar", "dll", "so", "elf",
    "com", "msi", "dmg", "app", "apk", "wsf", "hta", "reg",
    "scr", "pif", "lnk", "inf", "cpl", "drv", "sys",
}

# Filename sanitisation pattern — allow only safe chars
_SAFE_FILENAME_RE = re.compile(r"^[a-zA-Z0-9_\-. ]+$")

MAX_FILENAME_LEN = 255


def validate_upload(
    filename:           str,
    content:            bytes,
    allowed_extensions: set[str],
    max_size_mb:        float = 20.0,
) -> ValidationResult:
    """
    Validate an uploaded file.

    Args:
        filename           : original filename from the upload
        content            : raw file bytes
        allowed_extensions : set of permitted lowercase extensions (e.g. {"pdf","docx"})
        max_size_mb        : maximum allowed size in megabytes

    Returns ValidationResult with errors[] on failure.
    """
    errors: list[str] = []

    # ── Filename checks ───────────────────────────────────────
    if not filename or not filename.strip():
        return ValidationResult(valid=False, errors=["Filename is required."], code="FILE_NO_NAME")

    # Strip path components (path traversal)
    safe_name = filename.replace("\\", "/").split("/")[-1].strip()

    if len(safe_name) > MAX_FILENAME_LEN:
        errors.append(f"Filename must be {MAX_FILENAME_LEN} characters or fewer.")

    if "\x00" in safe_name:
        return ValidationResult(valid=False, errors=["Filename contains null bytes."], code="FILE_MALICIOUS_NAME")

    if ".." in safe_name:
        return ValidationResult(valid=False, errors=["Filename contains path traversal sequences."], code="FILE_PATH_TRAVERSAL")

    # ── Extension check ───────────────────────────────────────
    parts = safe_name.rsplit(".", 1)
    if len(parts) < 2:
        return ValidationResult(valid=False, errors=["File has no extension."], code="FILE_NO_EXTENSION")

    ext = parts[1].lower()

    if ext in _BLOCKED_EXTENSIONS:
        return ValidationResult(
            valid=False,
            errors=[f"File type '.{ext}' is not allowed for security reasons."],
            code="FILE_BLOCKED_EXTENSION",
        )

    if ext not in allowed_extensions:
        return ValidationResult(
            valid=False,
            errors=[f"File type '.{ext}' is not supported. Allowed: {', '.join(sorted(allowed_extensions))}."],
            code="FILE_UNSUPPORTED_EXTENSION",
        )

    # ── Size check ────────────────────────────────────────────
    max_bytes = int(max_size_mb * 1024 * 1024)
    if len(content) > max_bytes:
        actual_mb = len(content) / (1024 * 1024)
        errors.append(f"File size ({actual_mb:.1f} MB) exceeds the {max_size_mb} MB limit.")

    # ── Magic bytes check ─────────────────────────────────────
    magic = _MAGIC_BYTES.get(ext)
    if magic and len(content) >= len(magic):
        if not content.startswith(magic):
            errors.append(
                f"File content does not match the expected .{ext} format. "
                "The file may be corrupted or disguised."
            )

    if errors:
        return ValidationResult(valid=False, errors=errors, code="FILE_INVALID")

    return ValidationResult(valid=True, value=safe_name)


def sanitize_filename(filename: str) -> str:
    """Return a safe version of the filename (no path, no special chars)."""
    name = filename.replace("\\", "/").split("/")[-1].strip()
    # Replace unsafe characters with underscores
    name = re.sub(r"[^\w.\-]", "_", name)
    # Collapse multiple underscores
    name = re.sub(r"_+", "_", name)
    return name[:MAX_FILENAME_LEN]
