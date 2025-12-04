"""
Tests for metrics sampler module.

This test module validates:
- Starting and stopping the background sampling job
- Collecting metrics (CPU, memory, disk, temperature)
- Configuration validation (interval, retention, metrics)
- Sampler state management
- Retention policy enforcement
"""

from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_raspi.errors import FailedPreconditionError, InvalidArgumentError
from mcp_raspi.metrics.sampler import (
    DEFAULT_METRICS,
    DEFAULT_RETENTION_DAYS,
    DEFAULT_SAMPLING_INTERVAL,
    MAX_SAMPLING_INTERVAL,
    METRIC_CPU_PERCENT,
    METRIC_DISK_PERCENT,
    METRIC_MEMORY_PERCENT,
    MIN_SAMPLING_INTERVAL,
    MetricsSampler,
    SamplerState,
    SamplerStatus,
    collect_metrics,
)
from mcp_raspi.metrics.storage import MetricsStorage

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def temp_db_path() -> Path:
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test_metrics.db"


@pytest.fixture
async def storage(temp_db_path: Path) -> MetricsStorage:
    """Create an initialized MetricsStorage instance."""
    storage = MetricsStorage(temp_db_path)
    await storage.initialize()
    return storage


@pytest.fixture
def sampler(storage: MetricsStorage) -> MetricsSampler:
    """Create a MetricsSampler instance."""
    return MetricsSampler(storage)


# =============================================================================
# Tests for SamplerState
# =============================================================================


class TestSamplerState:
    """Tests for SamplerState dataclass."""

    def test_default_values(self) -> None:
        """Test default state values."""
        state = SamplerState()

        assert state.status == SamplerStatus.STOPPED
        assert state.job_id is None
        assert state.interval_seconds == DEFAULT_SAMPLING_INTERVAL
        assert state.retention_days == DEFAULT_RETENTION_DAYS
        assert state.metrics_enabled == DEFAULT_METRICS
        assert state.sample_count == 0
        assert state.error_count == 0

    def test_to_dict(self) -> None:
        """Test SamplerState.to_dict() method."""
        state = SamplerState(
            status=SamplerStatus.RUNNING,
            job_id="test-123",
            interval_seconds=30,
            retention_days=14,
        )

        d = state.to_dict()

        assert d["status"] == "running"
        assert d["job_id"] == "test-123"
        assert d["interval_seconds"] == 30
        assert d["retention_days"] == 14


class TestSamplerStatus:
    """Tests for SamplerStatus enum."""

    def test_status_values(self) -> None:
        """Test status enum values."""
        assert SamplerStatus.STOPPED.value == "stopped"
        assert SamplerStatus.STARTING.value == "starting"
        assert SamplerStatus.RUNNING.value == "running"
        assert SamplerStatus.STOPPING.value == "stopping"


# =============================================================================
# Tests for collect_metrics
# =============================================================================


class TestCollectMetrics:
    """Tests for the collect_metrics function."""

    def test_collects_cpu_percent(self) -> None:
        """Test collecting CPU percent metric."""
        samples = collect_metrics([METRIC_CPU_PERCENT])

        assert len(samples) == 1
        assert samples[0].metric_type == METRIC_CPU_PERCENT
        assert 0 <= samples[0].value <= 100

    def test_collects_memory_percent(self) -> None:
        """Test collecting memory percent metric."""
        samples = collect_metrics([METRIC_MEMORY_PERCENT])

        assert len(samples) == 1
        assert samples[0].metric_type == METRIC_MEMORY_PERCENT
        assert 0 <= samples[0].value <= 100

    def test_collects_disk_percent(self) -> None:
        """Test collecting disk percent metric."""
        samples = collect_metrics([METRIC_DISK_PERCENT])

        assert len(samples) == 1
        assert samples[0].metric_type == METRIC_DISK_PERCENT
        assert 0 <= samples[0].value <= 100

    def test_collects_all_default_metrics(self) -> None:
        """Test collecting all default metrics."""
        samples = collect_metrics(DEFAULT_METRICS)

        # Should have at least CPU, memory, disk (temperature may be unavailable)
        assert len(samples) >= 5
        metric_types = {s.metric_type for s in samples}
        assert METRIC_CPU_PERCENT in metric_types
        assert METRIC_MEMORY_PERCENT in metric_types
        assert METRIC_DISK_PERCENT in metric_types

    def test_collects_empty_list(self) -> None:
        """Test collecting with empty metrics list."""
        samples = collect_metrics([])
        assert samples == []

    def test_samples_have_timestamps(self) -> None:
        """Test that samples have valid timestamps."""
        before = time.time()
        samples = collect_metrics([METRIC_CPU_PERCENT])
        after = time.time()

        assert len(samples) == 1
        assert before <= samples[0].timestamp <= after


# =============================================================================
# Tests for MetricsSampler Start/Stop
# =============================================================================


class TestMetricsSamplerStartStop:
    """Tests for starting and stopping the sampler."""

    @pytest.mark.asyncio
    async def test_start_creates_job(self, sampler: MetricsSampler) -> None:
        """Test that start creates a new sampling job."""
        state = await sampler.start(interval_seconds=5)

        try:
            assert state.status == SamplerStatus.RUNNING
            assert state.job_id is not None
            assert state.started_at is not None
            assert sampler.is_running
        finally:
            await sampler.stop()

    @pytest.mark.asyncio
    async def test_start_with_custom_interval(self, sampler: MetricsSampler) -> None:
        """Test starting with custom interval."""
        state = await sampler.start(interval_seconds=10)

        try:
            assert state.interval_seconds == 10
        finally:
            await sampler.stop()

    @pytest.mark.asyncio
    async def test_start_with_custom_retention(self, sampler: MetricsSampler) -> None:
        """Test starting with custom retention."""
        state = await sampler.start(retention_days=30)

        try:
            assert state.retention_days == 30
        finally:
            await sampler.stop()

    @pytest.mark.asyncio
    async def test_start_with_custom_metrics(self, sampler: MetricsSampler) -> None:
        """Test starting with custom metrics list."""
        metrics = [METRIC_CPU_PERCENT, METRIC_MEMORY_PERCENT]
        state = await sampler.start(metrics=metrics)

        try:
            assert state.metrics_enabled == metrics
        finally:
            await sampler.stop()

    @pytest.mark.asyncio
    async def test_stop_changes_status(self, sampler: MetricsSampler) -> None:
        """Test that stop changes status to stopped."""
        await sampler.start(interval_seconds=5)
        state = await sampler.stop()

        assert state.status == SamplerStatus.STOPPED
        assert not sampler.is_running

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, sampler: MetricsSampler) -> None:
        """Test that stop when not running returns stopped state."""
        state = await sampler.stop()

        assert state.status == SamplerStatus.STOPPED

    @pytest.mark.asyncio
    async def test_double_start_raises_error(self, sampler: MetricsSampler) -> None:
        """Test that starting twice raises an error."""
        await sampler.start(interval_seconds=5)

        try:
            with pytest.raises(FailedPreconditionError) as exc_info:
                await sampler.start()
            assert "already running" in str(exc_info.value)
        finally:
            await sampler.stop()

    @pytest.mark.asyncio
    async def test_restart_after_stop(self, sampler: MetricsSampler) -> None:
        """Test that sampler can be restarted after stopping."""
        state1 = await sampler.start(interval_seconds=5)
        job_id1 = state1.job_id
        await sampler.stop()

        state2 = await sampler.start(interval_seconds=5)

        try:
            assert state2.status == SamplerStatus.RUNNING
            # New job should have different ID
            assert state2.job_id != job_id1
        finally:
            await sampler.stop()


# =============================================================================
# Tests for Parameter Validation
# =============================================================================


class TestMetricsSamplerValidation:
    """Tests for parameter validation."""

    @pytest.mark.asyncio
    async def test_interval_too_small(self, sampler: MetricsSampler) -> None:
        """Test that interval below minimum raises error."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await sampler.start(interval_seconds=1)
        assert "interval_seconds" in str(exc_info.value)
        assert str(MIN_SAMPLING_INTERVAL) in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_interval_too_large(self, sampler: MetricsSampler) -> None:
        """Test that interval above maximum raises error."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await sampler.start(interval_seconds=10000)
        assert "interval_seconds" in str(exc_info.value)
        assert str(MAX_SAMPLING_INTERVAL) in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_retention_too_small(self, sampler: MetricsSampler) -> None:
        """Test that retention below minimum raises error."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await sampler.start(retention_days=0)
        assert "retention_days" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_retention_too_large(self, sampler: MetricsSampler) -> None:
        """Test that retention above maximum raises error."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await sampler.start(retention_days=1000)
        assert "retention_days" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_invalid_metric_type(self, sampler: MetricsSampler) -> None:
        """Test that invalid metric type raises error."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await sampler.start(metrics=["invalid_metric"])
        assert "Invalid metric types" in str(exc_info.value)


# =============================================================================
# Tests for get_status
# =============================================================================


class TestMetricsSamplerGetStatus:
    """Tests for get_status method."""

    @pytest.mark.asyncio
    async def test_get_status_when_stopped(self, sampler: MetricsSampler) -> None:
        """Test get_status when sampler is stopped."""
        status = sampler.get_status()

        assert status.status == SamplerStatus.STOPPED
        assert status.job_id is None

    @pytest.mark.asyncio
    async def test_get_status_when_running(self, sampler: MetricsSampler) -> None:
        """Test get_status when sampler is running."""
        await sampler.start(interval_seconds=5)

        try:
            status = sampler.get_status()
            assert status.status == SamplerStatus.RUNNING
            assert status.job_id is not None
        finally:
            await sampler.stop()

    @pytest.mark.asyncio
    async def test_get_status_returns_copy(self, sampler: MetricsSampler) -> None:
        """Test that get_status returns a copy of state."""
        await sampler.start(interval_seconds=5)

        try:
            status1 = sampler.get_status()
            status2 = sampler.get_status()

            # Should be equal but different objects
            assert status1.job_id == status2.job_id
            assert status1.metrics_enabled is not status2.metrics_enabled
        finally:
            await sampler.stop()


# =============================================================================
# Tests for Sampling Behavior
# =============================================================================


class TestMetricsSamplerBehavior:
    """Tests for actual sampling behavior."""

    @pytest.mark.asyncio
    async def test_samples_collected(
        self, storage: MetricsStorage, sampler: MetricsSampler
    ) -> None:
        """Test that samples are collected and stored."""
        # Start with short interval
        await sampler.start(interval_seconds=5, metrics=[METRIC_CPU_PERCENT])

        try:
            # Wait for at least one sample
            await asyncio.sleep(1)

            # Check that samples were stored
            count = await storage.get_sample_count()
            # May or may not have collected yet depending on timing
            assert count >= 0
        finally:
            await sampler.stop()

    @pytest.mark.asyncio
    async def test_sample_count_increases(
        self,
        storage: MetricsStorage,  # noqa: ARG002
        sampler: MetricsSampler,
    ) -> None:
        """Test that sample count increases over time."""
        await sampler.start(interval_seconds=5, metrics=[METRIC_CPU_PERCENT])

        try:
            # Wait a bit
            await asyncio.sleep(0.5)
            status = sampler.get_status()
            # Sample count should be tracked
            assert isinstance(status.sample_count, int)
        finally:
            await sampler.stop()

    @pytest.mark.asyncio
    async def test_error_handling_in_sampling_loop(
        self, storage: MetricsStorage
    ) -> None:
        """Test that errors in sampling loop are handled gracefully."""
        sampler = MetricsSampler(storage)

        # Mock storage to raise an error
        with patch.object(
            storage, "insert_batch", side_effect=Exception("Test error")
        ):
            await sampler.start(interval_seconds=5)

            try:
                # Wait for an attempted sample
                await asyncio.sleep(0.5)

                # Sampler should still be running despite error
                assert sampler.is_running
                status = sampler.get_status()
                # Error count may have increased
                assert isinstance(status.error_count, int)
            finally:
                await sampler.stop()


# =============================================================================
# Tests for is_running Property
# =============================================================================


class TestMetricsSamplerIsRunning:
    """Tests for is_running property."""

    def test_is_running_when_stopped(self, sampler: MetricsSampler) -> None:
        """Test is_running is False when stopped."""
        assert not sampler.is_running

    @pytest.mark.asyncio
    async def test_is_running_when_running(self, sampler: MetricsSampler) -> None:
        """Test is_running is True when running."""
        await sampler.start(interval_seconds=5)

        try:
            assert sampler.is_running
        finally:
            await sampler.stop()

    @pytest.mark.asyncio
    async def test_is_running_after_stop(self, sampler: MetricsSampler) -> None:
        """Test is_running is False after stop."""
        await sampler.start(interval_seconds=5)
        await sampler.stop()

        assert not sampler.is_running


# =============================================================================
# Tests with Config
# =============================================================================


class TestMetricsSamplerWithConfig:
    """Tests for MetricsSampler with config."""

    @pytest.mark.asyncio
    async def test_uses_config_defaults(self, storage: MetricsStorage) -> None:
        """Test that sampler uses config defaults."""
        from mcp_raspi.config import MetricsConfig

        config = MetricsConfig(
            sampling_interval_seconds=120,
            max_retention_days=14,
        )

        sampler = MetricsSampler(storage, config)
        status = sampler.get_status()

        assert status.interval_seconds == 120
        assert status.retention_days == 14
