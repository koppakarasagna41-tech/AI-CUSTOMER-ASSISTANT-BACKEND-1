"""
app/reports/generators/csv_generator.py
──────────────────────────────────────────
CSV report generator.

generate_csv(rows, fieldnames) → bytes
  Converts a list of dicts to UTF-8 encoded CSV bytes.
  Handles datetime serialisation automatically.
"""

from __future__ import annotations
import csv
import io
from datetime import datetime
from typing import Any, Optional


def generate_csv(
    rows:       list[dict[str, Any]],
    fieldnames: Optional[list[str]] = None,
) -> bytes:
    """
    Convert rows (list of dicts) to CSV bytes.

    Args:
        rows       : data rows — each dict becomes one CSV row
        fieldnames : column order (auto-detected from first row if None)

    Returns:
        UTF-8 encoded bytes with BOM for Excel compatibility
    """
    if not rows:
        return "No data available for the selected period.\n".encode("utf-8-sig")

    fields = fieldnames or list(rows[0].keys())
    buffer = io.StringIO()

    writer = csv.DictWriter(
        buffer,
        fieldnames=fields,
        extrasaction="ignore",
        lineterminator="\r\n",
    )
    writer.writeheader()

    for row in rows:
        clean = {}
        for k, v in row.items():
            if isinstance(v, datetime):
                clean[k] = v.strftime("%Y-%m-%d %H:%M:%S UTC")
            elif isinstance(v, (list, dict)):
                clean[k] = str(v)
            elif v is None:
                clean[k] = ""
            else:
                clean[k] = v
        writer.writerow(clean)

    # UTF-8 BOM so Excel opens it correctly
    return buffer.getvalue().encode("utf-8-sig")
