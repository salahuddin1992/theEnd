"""
Utility Functions - أدوات مساعدة
================================

Common utility functions for NebulaCompute.

Author: NebulaCompute Team
License: MIT
"""

from distributed_cluster.utils.async_utils import (
    async_retry,
    cancel_tasks,
    create_task_with_name,
    gather_with_concurrency,
    run_with_timeout,
    wait_for_first,
)
from distributed_cluster.utils.helpers import (
    batch_process,
    chunk_list,
    deep_merge,
    flatten_dict,
    format_bytes,
    format_duration,
    generate_id,
    generate_short_id,
    get_timestamp,
    hash_string,
    parse_duration,
    parse_size,
    parse_timestamp,
    retry_async,
    safe_get,
    sanitize_string,
    timeout_async,
    truncate_string,
    validate_email,
    validate_hostname,
)
from distributed_cluster.utils.system import (
    find_available_port,
    get_cpu_count,
    get_disk_usage,
    get_memory_info,
    get_network_interfaces,
    get_process_info,
    is_port_available,
)

__all__ = [
    # Helpers
    "format_bytes",
    "format_duration",
    "parse_duration",
    "parse_size",
    "generate_id",
    "generate_short_id",
    "retry_async",
    "timeout_async",
    "batch_process",
    "chunk_list",
    "deep_merge",
    "flatten_dict",
    "safe_get",
    "validate_email",
    "validate_hostname",
    "sanitize_string",
    "truncate_string",
    "hash_string",
    "get_timestamp",
    "parse_timestamp",
    # Async utils
    "run_with_timeout",
    "gather_with_concurrency",
    "async_retry",
    "create_task_with_name",
    "cancel_tasks",
    "wait_for_first",
    # System utils
    "get_cpu_count",
    "get_memory_info",
    "get_disk_usage",
    "get_network_interfaces",
    "get_process_info",
    "is_port_available",
    "find_available_port",
]
