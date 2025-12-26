"""
Helper Functions - دوال مساعدة
==============================

Common helper functions for data formatting, validation, and processing.

Author: NebulaCompute Team
License: MIT
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Awaitable, Callable, Dict, List, Optional, TypeVar, Union

T = TypeVar("T")


# =============================================================================
# Size and Duration Formatting
# =============================================================================


def format_bytes(size_bytes: Union[int, float], precision: int = 2) -> str:
    """
    تنسيق حجم البايتات لصيغة مقروءة
    Format bytes to human-readable format

    Args:
        size_bytes: Size in bytes
        precision: Decimal precision

    Returns:
        Formatted string (e.g., "1.5 GB")

    Examples:
        >>> format_bytes(1024)
        '1.00 KB'
        >>> format_bytes(1073741824)
        '1.00 GB'
    """
    if size_bytes < 0:
        return f"-{format_bytes(abs(size_bytes), precision)}"

    if size_bytes == 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB", "PB", "EB"]
    unit_index = 0
    size = float(size_bytes)

    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    return f"{size:.{precision}f} {units[unit_index]}"


def format_duration(seconds: Union[int, float], short: bool = False) -> str:
    """
    تنسيق المدة الزمنية لصيغة مقروءة
    Format duration to human-readable format

    Args:
        seconds: Duration in seconds
        short: Use short format (e.g., "1h 30m" vs "1 hour, 30 minutes")

    Returns:
        Formatted string

    Examples:
        >>> format_duration(3661)
        '1 hour, 1 minute, 1 second'
        >>> format_duration(3661, short=True)
        '1h 1m 1s'
    """
    if seconds < 0:
        return f"-{format_duration(abs(seconds), short)}"

    if seconds < 1:
        return "< 1 second" if not short else "< 1s"

    seconds = int(seconds)
    parts = []

    units = [
        (86400, "day", "d"),
        (3600, "hour", "h"),
        (60, "minute", "m"),
        (1, "second", "s"),
    ]

    for divisor, long_name, short_name in units:
        if seconds >= divisor:
            count = seconds // divisor
            seconds %= divisor

            if short:
                parts.append(f"{count}{short_name}")
            else:
                unit = long_name if count == 1 else f"{long_name}s"
                parts.append(f"{count} {unit}")

    if short:
        return " ".join(parts)
    return ", ".join(parts)


def parse_duration(duration_str: str) -> int:
    """
    تحليل نص المدة الزمنية إلى ثوانٍ
    Parse duration string to seconds

    Args:
        duration_str: Duration string (e.g., "1h30m", "2 hours", "90s")

    Returns:
        Duration in seconds

    Examples:
        >>> parse_duration("1h30m")
        5400
        >>> parse_duration("2 hours")
        7200
    """
    duration_str = duration_str.strip().lower()

    # Handle simple numeric (assume seconds)
    if duration_str.isdigit():
        return int(duration_str)

    # Parse patterns like "1h", "30m", "1h30m", "2 hours 30 minutes"
    total_seconds = 0

    patterns = [
        (r"(\d+)\s*d(?:ays?)?", 86400),
        (r"(\d+)\s*h(?:ours?)?", 3600),
        (r"(\d+)\s*m(?:in(?:utes?)?)?", 60),
        (r"(\d+)\s*s(?:ec(?:onds?)?)?", 1),
    ]

    for pattern, multiplier in patterns:
        match = re.search(pattern, duration_str)
        if match:
            total_seconds += int(match.group(1)) * multiplier

    return total_seconds


def parse_size(size_str: str) -> int:
    """
    تحليل نص الحجم إلى بايتات
    Parse size string to bytes

    Args:
        size_str: Size string (e.g., "1GB", "500 MB", "1024")

    Returns:
        Size in bytes

    Examples:
        >>> parse_size("1GB")
        1073741824
        >>> parse_size("500 MB")
        524288000
    """
    size_str = size_str.strip().upper()

    # Handle simple numeric (assume bytes)
    if size_str.isdigit():
        return int(size_str)

    # Parse patterns like "1GB", "500 MB"
    match = re.match(r"(\d+(?:\.\d+)?)\s*(B|KB|MB|GB|TB|PB|EB)?", size_str)
    if not match:
        raise ValueError(f"Invalid size format: {size_str}")

    value = float(match.group(1))
    unit = match.group(2) or "B"

    multipliers = {
        "B": 1,
        "KB": 1024,
        "MB": 1024**2,
        "GB": 1024**3,
        "TB": 1024**4,
        "PB": 1024**5,
        "EB": 1024**6,
    }

    return int(value * multipliers[unit])


# =============================================================================
# ID Generation
# =============================================================================


def generate_id() -> str:
    """
    توليد معرف فريد UUID
    Generate unique UUID

    Returns:
        UUID string
    """
    return str(uuid.uuid4())


def generate_short_id(length: int = 8) -> str:
    """
    توليد معرف قصير
    Generate short ID

    Args:
        length: ID length (default 8)

    Returns:
        Short ID string
    """
    return uuid.uuid4().hex[:length]


# =============================================================================
# Async Helpers
# =============================================================================


def retry_async(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
) -> Callable:
    """
    مزخرف لإعادة المحاولة للدوال غير المتزامنة
    Retry decorator for async functions

    Args:
        max_retries: Maximum retry attempts
        delay: Initial delay between retries
        backoff: Backoff multiplier
        exceptions: Exception types to retry

    Returns:
        Decorated function
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            current_delay = delay

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff

            raise last_exception

        return wrapper

    return decorator


def timeout_async(seconds: float) -> Callable:
    """
    مزخرف لتحديد مهلة للدوال غير المتزامنة
    Timeout decorator for async functions

    Args:
        seconds: Timeout in seconds

    Returns:
        Decorated function
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)

        return wrapper

    return decorator


# =============================================================================
# Collection Helpers
# =============================================================================


async def batch_process(
    items: List[T],
    processor: Callable[[T], Awaitable[Any]],
    batch_size: int = 10,
    delay: float = 0.0,
) -> List[Any]:
    """
    معالجة العناصر على دفعات
    Process items in batches

    Args:
        items: Items to process
        processor: Async processor function
        batch_size: Batch size
        delay: Delay between batches

    Returns:
        List of results
    """
    results = []

    for i in range(0, len(items), batch_size):
        batch = items[i : i + batch_size]
        batch_results = await asyncio.gather(
            *[processor(item) for item in batch],
            return_exceptions=True,
        )
        results.extend(batch_results)

        if delay > 0 and i + batch_size < len(items):
            await asyncio.sleep(delay)

    return results


def chunk_list(items: List[T], chunk_size: int) -> List[List[T]]:
    """
    تقسيم القائمة إلى أجزاء
    Split list into chunks

    Args:
        items: Items to split
        chunk_size: Chunk size

    Returns:
        List of chunks
    """
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]


def deep_merge(base: Dict, override: Dict) -> Dict:
    """
    دمج القواميس بشكل عميق
    Deep merge dictionaries

    Args:
        base: Base dictionary
        override: Override dictionary

    Returns:
        Merged dictionary
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value

    return result


def flatten_dict(
    d: Dict[str, Any],
    parent_key: str = "",
    separator: str = ".",
) -> Dict[str, Any]:
    """
    تسطيح القاموس المتداخل
    Flatten nested dictionary

    Args:
        d: Dictionary to flatten
        parent_key: Parent key prefix
        separator: Key separator

    Returns:
        Flattened dictionary
    """
    items = []

    for key, value in d.items():
        new_key = f"{parent_key}{separator}{key}" if parent_key else key

        if isinstance(value, dict):
            items.extend(flatten_dict(value, new_key, separator).items())
        else:
            items.append((new_key, value))

    return dict(items)


def safe_get(
    d: Dict[str, Any],
    path: str,
    default: Any = None,
    separator: str = ".",
) -> Any:
    """
    الحصول على قيمة من قاموس متداخل بأمان
    Safely get value from nested dictionary

    Args:
        d: Dictionary
        path: Dot-separated path (e.g., "a.b.c")
        default: Default value if not found
        separator: Path separator

    Returns:
        Value or default
    """
    keys = path.split(separator)
    current = d

    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default

    return current


# =============================================================================
# Validation
# =============================================================================


def validate_email(email: str) -> bool:
    """
    التحقق من صحة البريد الإلكتروني
    Validate email address

    Args:
        email: Email address

    Returns:
        True if valid
    """
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def validate_hostname(hostname: str) -> bool:
    """
    التحقق من صحة اسم المضيف
    Validate hostname

    Args:
        hostname: Hostname

    Returns:
        True if valid
    """
    if not hostname or len(hostname) > 255:
        return False

    pattern = r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$"
    return bool(re.match(pattern, hostname))


# =============================================================================
# String Helpers
# =============================================================================


def sanitize_string(
    s: str,
    allowed_chars: str = "",
    replace_with: str = "_",
) -> str:
    """
    تنظيف النص من الأحرف غير المسموحة
    Sanitize string by removing disallowed characters

    Args:
        s: Input string
        allowed_chars: Additional allowed characters
        replace_with: Replacement character

    Returns:
        Sanitized string
    """
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" + allowed_chars)
    return "".join(c if c in allowed else replace_with for c in s)


def truncate_string(s: str, max_length: int, suffix: str = "...") -> str:
    """
    اقتطاع النص إذا تجاوز الطول المحدد
    Truncate string if it exceeds max length

    Args:
        s: Input string
        max_length: Maximum length
        suffix: Suffix to append if truncated

    Returns:
        Truncated string
    """
    if len(s) <= max_length:
        return s
    return s[: max_length - len(suffix)] + suffix


def hash_string(s: str, algorithm: str = "sha256") -> str:
    """
    حساب تجزئة النص
    Compute hash of string

    Args:
        s: Input string
        algorithm: Hash algorithm (md5, sha1, sha256, sha512)

    Returns:
        Hex digest
    """
    hasher = hashlib.new(algorithm)
    hasher.update(s.encode("utf-8"))
    return hasher.hexdigest()


# =============================================================================
# Timestamp Helpers
# =============================================================================


def get_timestamp() -> str:
    """
    الحصول على الطابع الزمني الحالي بصيغة ISO
    Get current timestamp in ISO format

    Returns:
        ISO formatted timestamp
    """
    return datetime.now(timezone.utc).isoformat()


def parse_timestamp(timestamp_str: str) -> datetime:
    """
    تحليل الطابع الزمني من نص
    Parse timestamp from string

    Args:
        timestamp_str: ISO formatted timestamp

    Returns:
        Datetime object
    """
    # Handle various ISO formats
    formats = [
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ]

    # Replace Z with +00:00 for parsing
    timestamp_str = timestamp_str.replace("Z", "+00:00")

    for fmt in formats:
        try:
            return datetime.strptime(timestamp_str, fmt)
        except ValueError:
            continue

    raise ValueError(f"Unable to parse timestamp: {timestamp_str}")
