"""
Metrics namespace tools for the Raspberry Pi MCP Server.

This module implements tools in the `metrics.*` namespace:
- metrics.start_sampling: Start background metrics sampling job
- metrics.stop_sampling: Stop background sampling job gracefully
- metrics.get_status: Return current sampling state
- metrics.query: Query metrics with time range and aggregation

Design follows Doc 05 §4 (metrics namespace specification) and
Doc 06 §4-5 (Metrics module design).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from mcp_raspi.context import ToolContext
from mcp_raspi.errors import (
    InvalidArgumentError,
)
from mcp_raspi.logging import get_logger
from mcp_raspi.metrics.sampler import (
    MetricsSampler,
)
from mcp_raspi.metrics.storage import MetricsStorage

if TYPE_CHECKING:
    from mcp_raspi.config import AppConfig

logger = get_logger(__name__)

# =============================================================================
# Module-level sampler instance
# =============================================================================

# Global sampler instance (initialized lazily)
_sampler: MetricsSampler | None = None
_storage: MetricsStorage | None = None


def _get_sampler(config: AppConfig | None = None) -> MetricsSampler:
    """
    Get or create the global sampler instance.

    Args:
        config: Optional AppConfig for configuration.

    Returns:
        The global MetricsSampler instance.
    """
    global _sampler, _storage

    if _sampler is None:
        # Get storage path from config or use default
        storage_path = "/var/lib/mcp-raspi/metrics/metrics.db"
        if config is not None:
            storage_path = config.metrics.storage_path

        _storage = MetricsStorage(storage_path)
        metrics_config = config.metrics if config else None
        _sampler = MetricsSampler(_storage, metrics_config)

    return _sampler


def _get_storage(config: AppConfig | None = None) -> MetricsStorage:
    """
    Get or create the global storage instance.

    Args:
        config: Optional AppConfig for configuration.

    Returns:
        The global MetricsStorage instance.
    """
    global _storage

    if _storage is None:
        storage_path = "/var/lib/mcp-raspi/metrics/metrics.db"
        if config is not None:
            storage_path = config.metrics.storage_path
        _storage = MetricsStorage(storage_path)

    return _storage


def reset_sampler() -> None:
    """
    Reset the global sampler instance.

    Used for testing to ensure clean state between tests.
    """
    global _sampler, _storage
    _sampler = None
    _storage = None


# =============================================================================
# Helper Functions
# =============================================================================


def _parse_timestamp(value: Any) -> float | None:
    """
    Parse a timestamp value to Unix timestamp.

    Accepts:
    - None: returns None
    - float/int: Unix timestamp (returned as-is)
    - str: ISO 8601 format (parsed to Unix timestamp)

    Args:
        value: Timestamp value to parse.

    Returns:
        Unix timestamp as float, or None if input is None.

    Raises:
        InvalidArgumentError: If the value cannot be parsed.
    """
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        try:
            # Try ISO 8601 parsing
            if "T" in value:
                # Handle timezone suffix
                if value.endswith("Z"):
                    value = value[:-1] + "+00:00"
                dt = datetime.fromisoformat(value)
                return dt.timestamp()
            else:
                # Try as numeric string
                return float(value)
        except (ValueError, OSError) as e:
            raise InvalidArgumentError(
                f"Invalid timestamp format: {value}",
                details={"value": value, "error": str(e)},
            ) from e

    raise InvalidArgumentError(
        f"Invalid timestamp type: {type(value).__name__}",
        details={"value": str(value)},
    )


# =============================================================================
# metrics.start_sampling
# =============================================================================


async def handle_metrics_start_sampling(
    ctx: ToolContext,
    params: dict[str, Any],
    *,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    """
    Handle the metrics.start_sampling tool call.

    Starts a background metrics sampling job that collects system metrics
    (CPU, memory, disk, temperature) at regular intervals and stores them
    in SQLite for later querying.

    Args:
        ctx: The ToolContext for this request.
        params: Request parameters:
            - interval_seconds: Sampling interval (5-3600, default 60)
            - retention_days: How long to keep data (1-365, default 7)
            - metrics: List of metrics to collect (default: all)
        config: Optional AppConfig for storage path.

    Returns:
        Dictionary with sampling job status:
        - job_id: Unique job identifier
        - status: Current status ('running')
        - interval_seconds: Configured interval
        - retention_days: Configured retention
        - metrics_enabled: List of metrics being collected
        - started_at: Job start timestamp (ISO 8601)

    Raises:
        InvalidArgumentError: If parameters are invalid.
        FailedPreconditionError: If sampler is already running.
    """
    sampler = _get_sampler(config)

    # Parse parameters
    interval_seconds = params.get("interval_seconds")
    retention_days = params.get("retention_days")
    metrics = params.get("metrics")

    # Start the sampler
    state = await sampler.start(
        interval_seconds=interval_seconds,
        retention_days=retention_days,
        metrics=metrics,
    )

    logger.info(
        "Metrics sampling started",
        extra={
            "user": ctx.caller.user_id,
            "job_id": state.job_id,
            "interval": state.interval_seconds,
        },
    )

    return state.to_dict()


# =============================================================================
# metrics.stop_sampling
# =============================================================================


async def handle_metrics_stop_sampling(
    ctx: ToolContext,
    _params: dict[str, Any],
    *,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    """
    Handle the metrics.stop_sampling tool call.

    Stops the background metrics sampling job gracefully.

    Args:
        ctx: The ToolContext for this request.
        _params: Request parameters (currently none required).
        config: Optional AppConfig for storage path.

    Returns:
        Dictionary with final sampling job status:
        - job_id: Job identifier
        - status: Current status ('stopped')
        - sample_count: Total samples collected
        - error_count: Number of errors encountered
    """
    sampler = _get_sampler(config)

    state = await sampler.stop()

    logger.info(
        "Metrics sampling stopped",
        extra={
            "user": ctx.caller.user_id,
            "job_id": state.job_id,
            "sample_count": state.sample_count,
        },
    )

    return state.to_dict()


# =============================================================================
# metrics.get_status
# =============================================================================


async def handle_metrics_get_status(
    _ctx: ToolContext,
    _params: dict[str, Any],
    *,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    """
    Handle the metrics.get_status tool call.

    Returns the current status of the metrics sampling system including
    whether sampling is active, configuration, and statistics.

    Args:
        _ctx: The ToolContext for this request.
        _params: Request parameters (currently none required).
        config: Optional AppConfig for storage path.

    Returns:
        Dictionary with sampling status:
        - status: Current status ('running', 'stopped', etc.)
        - job_id: Job identifier (if running)
        - interval_seconds: Configured interval
        - retention_days: Configured retention
        - metrics_enabled: List of metrics being collected
        - sample_count: Total samples collected
        - last_sample_at: Last sample timestamp
    """
    sampler = _get_sampler(config)
    storage = _get_storage(config)

    state = sampler.get_status()
    result = state.to_dict()

    # Add storage statistics
    try:
        await storage.initialize()
        result["total_samples_stored"] = await storage.get_sample_count()
        result["metric_types_available"] = await storage.get_metric_types()
    except Exception as e:
        logger.warning(
            "Could not get storage statistics",
            extra={"error": str(e)},
        )
        result["total_samples_stored"] = None
        result["metric_types_available"] = []

    return result


# =============================================================================
# metrics.query
# =============================================================================


async def handle_metrics_query(
    _ctx: ToolContext,
    params: dict[str, Any],
    *,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    """
    Handle the metrics.query tool call.

    Queries stored metrics with time range filtering and optional aggregation.

    Args:
        _ctx: The ToolContext for this request.
        params: Request parameters:
            - metric_type: Type of metric to query (e.g., 'cpu_percent')
            - start_time: Start of time range (Unix timestamp or ISO 8601)
            - end_time: End of time range (Unix timestamp or ISO 8601)
            - aggregation: Optional aggregation ('min', 'max', 'avg', 'all')
            - limit: Max samples to return (default 1000)
            - offset: Pagination offset (default 0)
            - order: Sort order ('asc' or 'desc', default 'desc')
        config: Optional AppConfig for storage path.

    Returns:
        Dictionary with query results:
        - samples: List of metric samples (if not aggregating)
        - aggregation: Aggregation results (if aggregation specified)
        - count: Number of samples returned
        - query: Query parameters used

    Raises:
        InvalidArgumentError: If parameters are invalid.
    """
    storage = _get_storage(config)
    await storage.initialize()

    # Parse parameters
    metric_type = params.get("metric_type")
    start_time = _parse_timestamp(params.get("start_time"))
    end_time = _parse_timestamp(params.get("end_time"))
    aggregation = params.get("aggregation")
    limit = params.get("limit", 1000)
    offset = params.get("offset", 0)
    order = params.get("order", "desc")

    # Validate limit
    if not isinstance(limit, int) or limit < 1 or limit > 10000:
        raise InvalidArgumentError(
            "limit must be an integer between 1 and 10000",
            details={"limit": limit},
        )

    # Validate offset
    if not isinstance(offset, int) or offset < 0:
        raise InvalidArgumentError(
            "offset must be a non-negative integer",
            details={"offset": offset},
        )

    # Build query info
    query_info = {
        "metric_type": metric_type,
        "start_time": start_time,
        "end_time": end_time,
        "aggregation": aggregation,
        "limit": limit,
        "offset": offset,
        "order": order,
    }

    result: dict[str, Any] = {
        "query": query_info,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    # Handle aggregation
    if aggregation:
        if not metric_type:
            raise InvalidArgumentError(
                "metric_type is required for aggregation",
                details={"aggregation": aggregation},
            )
        if start_time is None or end_time is None:
            raise InvalidArgumentError(
                "start_time and end_time are required for aggregation",
                details={"aggregation": aggregation},
            )

        agg_result = await storage.aggregate(
            metric_type=metric_type,
            start_time=start_time,
            end_time=end_time,
        )
        result["aggregation"] = agg_result.to_dict()
        result["count"] = agg_result.count

        # If aggregation is 'all', also return raw samples
        if aggregation == "all":
            samples = await storage.query(
                metric_type=metric_type,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
                offset=offset,
                order=order,
            )
            result["samples"] = [s.to_dict() for s in samples]
    else:
        # Return raw samples
        samples = await storage.query(
            metric_type=metric_type,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
            order=order,
        )
        result["samples"] = [s.to_dict() for s in samples]
        result["count"] = len(samples)

    return result


# =============================================================================
# metrics.get_realtime
# =============================================================================


async def handle_metrics_get_realtime(
    _ctx: ToolContext,
    _params: dict[str, Any],
    *,
    config: AppConfig | None = None,  # noqa: ARG001
) -> dict[str, Any]:
    """
    Handle the metrics.get_realtime tool call.

    Returns real-time metrics snapshot (same as system.get_health_snapshot
    but in the metrics namespace for consistency).

    Args:
        _ctx: The ToolContext for this request.
        _params: Request parameters (currently none required).
        config: Optional AppConfig (not used).

    Returns:
        Dictionary with current metrics:
        - timestamp: Current timestamp (ISO 8601)
        - metrics: Dictionary of metric_type -> value
    """
    import psutil

    from mcp_raspi.metrics.sampler import (
        METRIC_CPU_PERCENT,
        METRIC_DISK_PERCENT,
        METRIC_DISK_USED_BYTES,
        METRIC_MEMORY_PERCENT,
        METRIC_MEMORY_USED_BYTES,
        METRIC_TEMPERATURE,
        _get_cpu_temperature,
    )

    timestamp = datetime.now(UTC).isoformat()
    metrics: dict[str, Any] = {}

    # CPU
    metrics[METRIC_CPU_PERCENT] = psutil.cpu_percent(interval=0.1)

    # Memory
    memory = psutil.virtual_memory()
    metrics[METRIC_MEMORY_PERCENT] = memory.percent
    metrics[METRIC_MEMORY_USED_BYTES] = memory.used

    # Disk
    try:
        disk = psutil.disk_usage("/")
        metrics[METRIC_DISK_PERCENT] = disk.percent
        metrics[METRIC_DISK_USED_BYTES] = disk.used
    except OSError:
        pass

    # Temperature
    temp = _get_cpu_temperature()
    metrics[METRIC_TEMPERATURE] = round(temp, 1) if temp else None

    return {
        "timestamp": timestamp,
        "metrics": metrics,
    }
