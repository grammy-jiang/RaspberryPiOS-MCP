"""
Background metrics sampling job using asyncio.

This module implements the MetricsSampler class that:
- Runs a background asyncio task to collect metrics at configurable intervals
- Samples CPU, memory, disk, and temperature metrics
- Writes samples to the MetricsStorage
- Enforces retention policy by deleting old samples

Design follows Doc 06 §4-5 (Metrics module and Sampling Design).
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

import psutil

from mcp_raspi.errors import FailedPreconditionError, InvalidArgumentError
from mcp_raspi.logging import get_logger
from mcp_raspi.metrics.storage import MetricSample, MetricsStorage

if TYPE_CHECKING:
    from mcp_raspi.config import MetricsConfig

logger = get_logger(__name__)

# =============================================================================
# Constants
# =============================================================================

# Default sampling configuration
DEFAULT_SAMPLING_INTERVAL = 60  # seconds
MIN_SAMPLING_INTERVAL = 5  # seconds
MAX_SAMPLING_INTERVAL = 3600  # seconds (1 hour)

DEFAULT_RETENTION_DAYS = 7
MIN_RETENTION_DAYS = 1
MAX_RETENTION_DAYS = 365

# Metric type names
METRIC_CPU_PERCENT = "cpu_percent"
METRIC_MEMORY_PERCENT = "memory_percent"
METRIC_MEMORY_USED_BYTES = "memory_used_bytes"
METRIC_DISK_PERCENT = "disk_percent"
METRIC_DISK_USED_BYTES = "disk_used_bytes"
METRIC_TEMPERATURE = "temperature_celsius"

# All metric types collected by default
DEFAULT_METRICS = [
    METRIC_CPU_PERCENT,
    METRIC_MEMORY_PERCENT,
    METRIC_MEMORY_USED_BYTES,
    METRIC_DISK_PERCENT,
    METRIC_DISK_USED_BYTES,
    METRIC_TEMPERATURE,
]


# =============================================================================
# Enums and Data Models
# =============================================================================


class SamplerStatus(str, Enum):
    """Status of the metrics sampler."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"


@dataclass
class SamplerState:
    """
    Current state of the metrics sampler.

    Attributes:
        status: Current sampler status.
        job_id: Unique identifier for the sampling job.
        interval_seconds: Sampling interval.
        retention_days: Data retention period.
        metrics_enabled: List of metrics being collected.
        started_at: When the sampler was started.
        last_sample_at: When the last sample was collected.
        sample_count: Total number of samples collected.
        error_count: Number of sampling errors.
        last_error: Last error message if any.
    """

    status: SamplerStatus = SamplerStatus.STOPPED
    job_id: str | None = None
    interval_seconds: int = DEFAULT_SAMPLING_INTERVAL
    retention_days: int = DEFAULT_RETENTION_DAYS
    metrics_enabled: list[str] = field(default_factory=lambda: DEFAULT_METRICS.copy())
    started_at: datetime | None = None
    last_sample_at: datetime | None = None
    sample_count: int = 0
    error_count: int = 0
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "status": self.status.value,
            "job_id": self.job_id,
            "interval_seconds": self.interval_seconds,
            "retention_days": self.retention_days,
            "metrics_enabled": self.metrics_enabled,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_sample_at": (
                self.last_sample_at.isoformat() if self.last_sample_at else None
            ),
            "sample_count": self.sample_count,
            "error_count": self.error_count,
            "last_error": self.last_error,
        }


# =============================================================================
# Metrics Collection
# =============================================================================


def _get_cpu_temperature() -> float | None:
    """
    Get CPU temperature in Celsius.

    Reads from /sys/class/thermal/thermal_zone*/temp (Linux).
    Falls back to psutil sensors_temperatures if available.

    Returns:
        Temperature in Celsius, or None if unavailable.
    """
    from pathlib import Path

    # Try thermal zone first (most common on Raspberry Pi)
    thermal_zones = sorted(Path("/sys/class/thermal").glob("thermal_zone*/temp"))
    for temp_path in thermal_zones:
        try:
            temp_milli_c = int(temp_path.read_text().strip())
            return temp_milli_c / 1000.0
        except (OSError, ValueError, PermissionError):
            continue

    # Fallback to psutil
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            # Try common sensor names
            for sensor_name in ["cpu_thermal", "coretemp", "k10temp", "acpitz"]:
                if sensor_name in temps and temps[sensor_name]:
                    return temps[sensor_name][0].current
            # Return first available sensor
            first_sensor = list(temps.values())[0]
            if first_sensor:
                return first_sensor[0].current
    except (AttributeError, KeyError):
        pass

    return None


def collect_metrics(metrics_enabled: list[str]) -> list[MetricSample]:
    """
    Collect current system metrics.

    Args:
        metrics_enabled: List of metric types to collect.

    Returns:
        List of MetricSample objects with current values.
    """
    samples = []
    timestamp = time.time()

    # CPU percent (non-blocking, interval=0.1 for more accuracy)
    if METRIC_CPU_PERCENT in metrics_enabled:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        samples.append(
            MetricSample(
                timestamp=timestamp,
                metric_type=METRIC_CPU_PERCENT,
                value=cpu_percent,
            )
        )

    # Memory
    if METRIC_MEMORY_PERCENT in metrics_enabled or METRIC_MEMORY_USED_BYTES in metrics_enabled:
        memory = psutil.virtual_memory()
        if METRIC_MEMORY_PERCENT in metrics_enabled:
            samples.append(
                MetricSample(
                    timestamp=timestamp,
                    metric_type=METRIC_MEMORY_PERCENT,
                    value=memory.percent,
                )
            )
        if METRIC_MEMORY_USED_BYTES in metrics_enabled:
            samples.append(
                MetricSample(
                    timestamp=timestamp,
                    metric_type=METRIC_MEMORY_USED_BYTES,
                    value=float(memory.used),
                    metadata={"total_bytes": memory.total},
                )
            )

    # Disk
    if METRIC_DISK_PERCENT in metrics_enabled or METRIC_DISK_USED_BYTES in metrics_enabled:
        try:
            disk = psutil.disk_usage("/")
            if METRIC_DISK_PERCENT in metrics_enabled:
                samples.append(
                    MetricSample(
                        timestamp=timestamp,
                        metric_type=METRIC_DISK_PERCENT,
                        value=disk.percent,
                    )
                )
            if METRIC_DISK_USED_BYTES in metrics_enabled:
                samples.append(
                    MetricSample(
                        timestamp=timestamp,
                        metric_type=METRIC_DISK_USED_BYTES,
                        value=float(disk.used),
                        metadata={"total_bytes": disk.total},
                    )
                )
        except OSError:
            pass

    # Temperature
    if METRIC_TEMPERATURE in metrics_enabled:
        temp = _get_cpu_temperature()
        if temp is not None:
            samples.append(
                MetricSample(
                    timestamp=timestamp,
                    metric_type=METRIC_TEMPERATURE,
                    value=round(temp, 1),
                )
            )

    return samples


# =============================================================================
# MetricsSampler Class
# =============================================================================


class MetricsSampler:
    """
    Background metrics sampler using asyncio.

    This class manages a background task that periodically:
    - Collects system metrics (CPU, memory, disk, temperature)
    - Writes samples to the MetricsStorage
    - Enforces retention policy by deleting old data

    The sampler can be started, stopped, and reconfigured dynamically.
    Only one sampling job can be active at a time.

    Example:
        >>> storage = MetricsStorage("/var/lib/mcp-raspi/metrics/metrics.db")
        >>> sampler = MetricsSampler(storage)
        >>> await sampler.start(interval_seconds=60)
        >>> status = sampler.get_status()
        >>> await sampler.stop()
    """

    def __init__(
        self,
        storage: MetricsStorage,
        config: MetricsConfig | None = None,
    ) -> None:
        """
        Initialize the MetricsSampler.

        Args:
            storage: MetricsStorage instance for persisting samples.
            config: Optional MetricsConfig for default settings.
        """
        self._storage = storage
        self._config = config
        self._state = SamplerState()
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._lock = asyncio.Lock()

        # Apply config defaults if provided
        if config:
            self._state.interval_seconds = config.sampling_interval_seconds
            self._state.retention_days = config.max_retention_days

    @property
    def is_running(self) -> bool:
        """Check if the sampler is currently running."""
        return self._state.status == SamplerStatus.RUNNING

    def get_status(self) -> SamplerState:
        """
        Get the current sampler state.

        Returns:
            Copy of the current SamplerState.
        """
        return SamplerState(
            status=self._state.status,
            job_id=self._state.job_id,
            interval_seconds=self._state.interval_seconds,
            retention_days=self._state.retention_days,
            metrics_enabled=self._state.metrics_enabled.copy(),
            started_at=self._state.started_at,
            last_sample_at=self._state.last_sample_at,
            sample_count=self._state.sample_count,
            error_count=self._state.error_count,
            last_error=self._state.last_error,
        )

    async def start(
        self,
        *,
        interval_seconds: int | None = None,
        retention_days: int | None = None,
        metrics: list[str] | None = None,
    ) -> SamplerState:
        """
        Start the background sampling job.

        Args:
            interval_seconds: Sampling interval (5-3600 seconds).
            retention_days: How long to keep samples (1-365 days).
            metrics: List of metric types to collect (defaults to all).

        Returns:
            Current SamplerState after starting.

        Raises:
            InvalidArgumentError: If parameters are invalid.
            FailedPreconditionError: If sampler is already running.
        """
        async with self._lock:
            if self._state.status in (SamplerStatus.RUNNING, SamplerStatus.STARTING):
                raise FailedPreconditionError(
                    "Sampler is already running",
                    details={"job_id": self._state.job_id},
                )

            # Validate and apply parameters
            if interval_seconds is not None:
                if interval_seconds < MIN_SAMPLING_INTERVAL:
                    raise InvalidArgumentError(
                        f"interval_seconds must be at least {MIN_SAMPLING_INTERVAL}",
                        details={"interval_seconds": interval_seconds},
                    )
                if interval_seconds > MAX_SAMPLING_INTERVAL:
                    raise InvalidArgumentError(
                        f"interval_seconds must be at most {MAX_SAMPLING_INTERVAL}",
                        details={"interval_seconds": interval_seconds},
                    )
                self._state.interval_seconds = interval_seconds

            if retention_days is not None:
                if retention_days < MIN_RETENTION_DAYS:
                    raise InvalidArgumentError(
                        f"retention_days must be at least {MIN_RETENTION_DAYS}",
                        details={"retention_days": retention_days},
                    )
                if retention_days > MAX_RETENTION_DAYS:
                    raise InvalidArgumentError(
                        f"retention_days must be at most {MAX_RETENTION_DAYS}",
                        details={"retention_days": retention_days},
                    )
                self._state.retention_days = retention_days

            if metrics is not None:
                # Validate metric names
                valid_metrics = set(DEFAULT_METRICS)
                invalid_metrics = set(metrics) - valid_metrics
                if invalid_metrics:
                    raise InvalidArgumentError(
                        f"Invalid metric types: {invalid_metrics}",
                        details={
                            "invalid": list(invalid_metrics),
                            "valid": list(valid_metrics),
                        },
                    )
                self._state.metrics_enabled = list(metrics)

            # Initialize storage
            await self._storage.initialize()

            # Create new job
            self._state.status = SamplerStatus.STARTING
            self._state.job_id = str(uuid.uuid4())[:8]
            self._state.started_at = datetime.now()
            self._state.sample_count = 0
            self._state.error_count = 0
            self._state.last_error = None
            self._stop_event.clear()

            # Start background task
            self._task = asyncio.create_task(self._sampling_loop())
            self._state.status = SamplerStatus.RUNNING

            logger.info(
                "Metrics sampler started",
                extra={
                    "job_id": self._state.job_id,
                    "interval_seconds": self._state.interval_seconds,
                    "retention_days": self._state.retention_days,
                    "metrics": self._state.metrics_enabled,
                },
            )

            return self.get_status()

    async def stop(self) -> SamplerState:
        """
        Stop the background sampling job gracefully.

        Waits for any in-progress sampling to complete before returning.

        Returns:
            Current SamplerState after stopping.
        """
        async with self._lock:
            if self._state.status not in (SamplerStatus.RUNNING, SamplerStatus.STARTING):
                # Already stopped or stopping
                return self.get_status()

            self._state.status = SamplerStatus.STOPPING
            self._stop_event.set()

            if self._task:
                try:
                    # Wait for the task to complete with timeout
                    await asyncio.wait_for(self._task, timeout=10.0)
                except TimeoutError:
                    logger.warning("Sampler task did not stop gracefully, cancelling")
                    self._task.cancel()
                    try:
                        await self._task
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        logger.error(
                            "Exception during sampler task cancellation",
                            extra={"error": str(e), "job_id": self._state.job_id},
                        )
                except asyncio.CancelledError:
                    pass
                self._task = None

            self._state.status = SamplerStatus.STOPPED

            logger.info(
                "Metrics sampler stopped",
                extra={
                    "job_id": self._state.job_id,
                    "sample_count": self._state.sample_count,
                },
            )

            return self.get_status()

    async def _sampling_loop(self) -> None:
        """
        Main sampling loop that runs in the background.

        Collects metrics at the configured interval and handles errors gracefully.
        """
        retention_check_interval = 3600  # Check retention every hour
        last_retention_check = 0.0

        while not self._stop_event.is_set():
            try:
                # Collect metrics
                samples = await asyncio.get_event_loop().run_in_executor(
                    None, collect_metrics, self._state.metrics_enabled
                )

                if samples:
                    await self._storage.insert_batch(samples)
                    self._state.sample_count += len(samples)
                    self._state.last_sample_at = datetime.now()

                # Periodic retention check
                current_time = time.time()
                if current_time - last_retention_check > retention_check_interval:
                    await self._enforce_retention()
                    last_retention_check = current_time

            except Exception as e:
                self._state.error_count += 1
                self._state.last_error = str(e)
                logger.error(
                    "Error during metrics sampling",
                    extra={"error": str(e), "job_id": self._state.job_id},
                )

            # Wait for next sample interval or stop signal
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=float(self._state.interval_seconds),
                )
                # Stop event was set
                break
            except TimeoutError:
                # Normal timeout, continue sampling
                pass

    async def _enforce_retention(self) -> None:
        """
        Delete samples older than the retention period.
        """
        try:
            cutoff_time = time.time() - (self._state.retention_days * 24 * 3600)
            deleted = await self._storage.delete_older_than(cutoff_time)
            if deleted > 0:
                logger.debug(
                    "Retention policy enforced",
                    extra={
                        "deleted_count": deleted,
                        "retention_days": self._state.retention_days,
                    },
                )
        except Exception as e:
            logger.error(
                "Error enforcing retention policy",
                extra={"error": str(e)},
            )
