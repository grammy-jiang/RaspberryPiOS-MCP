"""
Tests for metrics namespace tools.

This test module validates:
- metrics.start_sampling starts background job
- metrics.stop_sampling stops background job
- metrics.get_status returns sampling state
- metrics.query returns correct data for time ranges
- Aggregation functions work (min/max/avg)
- All JSON schemas match Doc 05 specifications
"""

from __future__ import annotations

import tempfile
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import pytest

from mcp_raspi.config import AppConfig, MetricsConfig
from mcp_raspi.context import CallerInfo, ToolContext
from mcp_raspi.errors import InvalidArgumentError
from mcp_raspi.metrics.sampler import (
    METRIC_CPU_PERCENT,
    METRIC_MEMORY_PERCENT,
)
from mcp_raspi.metrics.storage import MetricSample, MetricsStorage
from mcp_raspi.tools.metrics import (
    _parse_timestamp,
    handle_metrics_get_realtime,
    handle_metrics_get_status,
    handle_metrics_query,
    handle_metrics_start_sampling,
    handle_metrics_stop_sampling,
    reset_sampler,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def viewer_ctx() -> ToolContext:
    """Create a test context with viewer role."""
    return ToolContext(
        tool_name="metrics.get_status",
        caller=CallerInfo(user_id="viewer@example.com", role="viewer"),
        request_id="test-req-viewer",
    )


@pytest.fixture
def temp_db_path() -> Path:
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test_metrics.db"


@pytest.fixture
def test_config(temp_db_path: Path) -> AppConfig:
    """Create test config with temporary database path."""
    config = AppConfig()
    config.metrics = MetricsConfig(
        storage_path=str(temp_db_path),
        sampling_interval_seconds=30,
        max_retention_days=7,
    )
    return config


@pytest.fixture(autouse=True)
def cleanup_sampler():
    """Reset global sampler state before and after each test."""
    reset_sampler()
    yield
    reset_sampler()


@asynccontextmanager
async def sampler_context(
    ctx: ToolContext, params: dict, config: AppConfig
) -> AsyncGenerator[dict, None]:
    """
    Async context manager for proper sampler lifecycle management.

    Ensures the sampler is stopped even if the test raises an exception.
    Only attempts to stop if the sampler was successfully started.

    Args:
        ctx: Tool context for the request.
        params: Parameters for start_sampling.
        config: App configuration.

    Yields:
        Result from handle_metrics_start_sampling.
    """
    started = False
    try:
        result = await handle_metrics_start_sampling(ctx, params, config=config)
        started = True
        yield result
    finally:
        if started:
            await handle_metrics_stop_sampling(ctx, {}, config=config)


# =============================================================================
# Tests for _parse_timestamp
# =============================================================================


class TestParseTimestamp:
    """Tests for timestamp parsing helper."""

    def test_parse_none(self) -> None:
        """Test parsing None returns None."""
        assert _parse_timestamp(None) is None

    def test_parse_float(self) -> None:
        """Test parsing float timestamp."""
        timestamp = 1704067200.0
        assert _parse_timestamp(timestamp) == timestamp

    def test_parse_int(self) -> None:
        """Test parsing int timestamp."""
        timestamp = 1704067200
        assert _parse_timestamp(timestamp) == float(timestamp)

    def test_parse_iso8601(self) -> None:
        """Test parsing ISO 8601 timestamp."""
        iso_str = "2024-01-01T00:00:00+00:00"
        result = _parse_timestamp(iso_str)
        assert isinstance(result, float)
        assert result > 0

    def test_parse_iso8601_with_z(self) -> None:
        """Test parsing ISO 8601 timestamp with Z suffix."""
        iso_str = "2024-01-01T00:00:00Z"
        result = _parse_timestamp(iso_str)
        assert isinstance(result, float)
        assert result > 0

    def test_parse_numeric_string(self) -> None:
        """Test parsing numeric string."""
        result = _parse_timestamp("1704067200.0")
        assert result == 1704067200.0

    def test_parse_invalid_string(self) -> None:
        """Test parsing invalid string raises error."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            _parse_timestamp("not-a-timestamp")
        assert "Invalid timestamp" in str(exc_info.value)

    def test_parse_invalid_type(self) -> None:
        """Test parsing invalid type raises error."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            _parse_timestamp(["list"])
        assert "Invalid timestamp type" in str(exc_info.value)


# =============================================================================
# Tests for metrics.start_sampling
# =============================================================================


class TestMetricsStartSampling:
    """Tests for metrics.start_sampling tool."""

    @pytest.mark.asyncio
    async def test_returns_dict(
        self, viewer_ctx: ToolContext, test_config: AppConfig
    ) -> None:
        """Test that handler returns a dictionary."""
        async with sampler_context(
            viewer_ctx, {"interval_seconds": 5}, test_config
        ) as result:
            assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_contains_required_fields(
        self, viewer_ctx: ToolContext, test_config: AppConfig
    ) -> None:
        """Test that result contains required fields."""
        async with sampler_context(
            viewer_ctx, {"interval_seconds": 5}, test_config
        ) as result:
            assert "status" in result
            assert "job_id" in result
            assert "interval_seconds" in result
            assert "retention_days" in result
            assert "metrics_enabled" in result

    @pytest.mark.asyncio
    async def test_status_is_running(
        self, viewer_ctx: ToolContext, test_config: AppConfig
    ) -> None:
        """Test that status is 'running' after start."""
        async with sampler_context(
            viewer_ctx, {"interval_seconds": 5}, test_config
        ) as result:
            assert result["status"] == "running"

    @pytest.mark.asyncio
    async def test_custom_interval(
        self, viewer_ctx: ToolContext, test_config: AppConfig
    ) -> None:
        """Test starting with custom interval."""
        async with sampler_context(
            viewer_ctx, {"interval_seconds": 120}, test_config
        ) as result:
            assert result["interval_seconds"] == 120

    @pytest.mark.asyncio
    async def test_custom_retention(
        self, viewer_ctx: ToolContext, test_config: AppConfig
    ) -> None:
        """Test starting with custom retention."""
        async with sampler_context(
            viewer_ctx, {"retention_days": 30}, test_config
        ) as result:
            assert result["retention_days"] == 30

    @pytest.mark.asyncio
    async def test_custom_metrics(
        self, viewer_ctx: ToolContext, test_config: AppConfig
    ) -> None:
        """Test starting with custom metrics list."""
        metrics = [METRIC_CPU_PERCENT, METRIC_MEMORY_PERCENT]
        async with sampler_context(
            viewer_ctx, {"metrics": metrics}, test_config
        ) as result:
            assert result["metrics_enabled"] == metrics


# =============================================================================
# Tests for metrics.stop_sampling
# =============================================================================


class TestMetricsStopSampling:
    """Tests for metrics.stop_sampling tool."""

    @pytest.mark.asyncio
    async def test_returns_dict(
        self, viewer_ctx: ToolContext, test_config: AppConfig
    ) -> None:
        """Test that handler returns a dictionary."""
        result = await handle_metrics_stop_sampling(
            viewer_ctx, {}, config=test_config
        )
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_stops_running_sampler(
        self, viewer_ctx: ToolContext, test_config: AppConfig
    ) -> None:
        """Test that stop changes status to stopped."""
        await handle_metrics_start_sampling(
            viewer_ctx, {"interval_seconds": 5}, config=test_config
        )

        result = await handle_metrics_stop_sampling(
            viewer_ctx, {}, config=test_config
        )

        assert result["status"] == "stopped"

    @pytest.mark.asyncio
    async def test_stop_when_not_running(
        self, viewer_ctx: ToolContext, test_config: AppConfig
    ) -> None:
        """Test stop when not running returns stopped status."""
        result = await handle_metrics_stop_sampling(
            viewer_ctx, {}, config=test_config
        )
        assert result["status"] == "stopped"


# =============================================================================
# Tests for metrics.get_status
# =============================================================================


class TestMetricsGetStatus:
    """Tests for metrics.get_status tool."""

    @pytest.mark.asyncio
    async def test_returns_dict(
        self, viewer_ctx: ToolContext, test_config: AppConfig
    ) -> None:
        """Test that handler returns a dictionary."""
        result = await handle_metrics_get_status(
            viewer_ctx, {}, config=test_config
        )
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_contains_required_fields(
        self, viewer_ctx: ToolContext, test_config: AppConfig
    ) -> None:
        """Test that result contains required fields."""
        result = await handle_metrics_get_status(
            viewer_ctx, {}, config=test_config
        )

        assert "status" in result
        assert "interval_seconds" in result
        assert "retention_days" in result
        assert "metrics_enabled" in result
        assert "sample_count" in result

    @pytest.mark.asyncio
    async def test_status_when_stopped(
        self, viewer_ctx: ToolContext, test_config: AppConfig
    ) -> None:
        """Test status is 'stopped' initially."""
        result = await handle_metrics_get_status(
            viewer_ctx, {}, config=test_config
        )
        assert result["status"] == "stopped"

    @pytest.mark.asyncio
    async def test_status_when_running(
        self, viewer_ctx: ToolContext, test_config: AppConfig
    ) -> None:
        """Test status is 'running' when sampling."""
        try:
            await handle_metrics_start_sampling(
                viewer_ctx, {"interval_seconds": 5}, config=test_config
            )

            result = await handle_metrics_get_status(
                viewer_ctx, {}, config=test_config
            )

            assert result["status"] == "running"
        finally:
            await handle_metrics_stop_sampling(viewer_ctx, {}, config=test_config)

    @pytest.mark.asyncio
    async def test_includes_storage_stats(
        self, viewer_ctx: ToolContext, test_config: AppConfig
    ) -> None:
        """Test that storage statistics are included."""
        result = await handle_metrics_get_status(
            viewer_ctx, {}, config=test_config
        )

        assert "total_samples_stored" in result
        assert "metric_types_available" in result


# =============================================================================
# Tests for metrics.query
# =============================================================================


class TestMetricsQuery:
    """Tests for metrics.query tool."""

    @pytest.fixture
    async def populated_storage(self, test_config: AppConfig) -> MetricsStorage:
        """Create storage with test data."""
        storage = MetricsStorage(test_config.metrics.storage_path)
        await storage.initialize()

        # Insert test samples
        base_time = time.time()
        samples = [
            MetricSample(timestamp=base_time - 100, metric_type="cpu_percent", value=10.0),
            MetricSample(timestamp=base_time - 50, metric_type="cpu_percent", value=20.0),
            MetricSample(timestamp=base_time, metric_type="cpu_percent", value=30.0),
            MetricSample(timestamp=base_time - 100, metric_type="memory_percent", value=40.0),
            MetricSample(timestamp=base_time - 50, metric_type="memory_percent", value=50.0),
        ]
        await storage.insert_batch(samples)

        return storage

    @pytest.mark.asyncio
    async def test_returns_dict(
        self, viewer_ctx: ToolContext, test_config: AppConfig
    ) -> None:
        """Test that handler returns a dictionary."""
        result = await handle_metrics_query(
            viewer_ctx, {}, config=test_config
        )
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_contains_required_fields(
        self, viewer_ctx: ToolContext, test_config: AppConfig
    ) -> None:
        """Test that result contains required fields."""
        result = await handle_metrics_query(
            viewer_ctx, {}, config=test_config
        )

        assert "samples" in result
        assert "count" in result
        assert "query" in result
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_query_by_metric_type(
        self,
        viewer_ctx: ToolContext,
        test_config: AppConfig,
        populated_storage: MetricsStorage,  # noqa: ARG002
    ) -> None:
        """Test filtering by metric type."""
        result = await handle_metrics_query(
            viewer_ctx,
            {"metric_type": "cpu_percent"},
            config=test_config,
        )

        assert result["count"] == 3
        for sample in result["samples"]:
            assert sample["metric_type"] == "cpu_percent"

    @pytest.mark.asyncio
    async def test_query_with_time_range(
        self,
        viewer_ctx: ToolContext,
        test_config: AppConfig,
        populated_storage: MetricsStorage,  # noqa: ARG002
    ) -> None:
        """Test filtering by time range."""
        base_time = time.time()
        result = await handle_metrics_query(
            viewer_ctx,
            {
                "start_time": base_time - 75,
                "end_time": base_time + 10,
            },
            config=test_config,
        )

        # Should get 3 samples: 2 cpu + 1 memory within range
        assert result["count"] == 3

    @pytest.mark.asyncio
    async def test_query_with_limit(
        self,
        viewer_ctx: ToolContext,
        test_config: AppConfig,
        populated_storage: MetricsStorage,  # noqa: ARG002
    ) -> None:
        """Test limiting results."""
        result = await handle_metrics_query(
            viewer_ctx,
            {"limit": 2},
            config=test_config,
        )

        assert result["count"] == 2
        assert len(result["samples"]) == 2

    @pytest.mark.asyncio
    async def test_query_with_offset(
        self,
        viewer_ctx: ToolContext,
        test_config: AppConfig,
        populated_storage: MetricsStorage,  # noqa: ARG002
    ) -> None:
        """Test pagination with offset."""
        result = await handle_metrics_query(
            viewer_ctx,
            {"limit": 2, "offset": 2},
            config=test_config,
        )

        assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_query_with_aggregation(
        self,
        viewer_ctx: ToolContext,
        test_config: AppConfig,
        populated_storage: MetricsStorage,  # noqa: ARG002
    ) -> None:
        """Test query with aggregation."""
        base_time = time.time()
        result = await handle_metrics_query(
            viewer_ctx,
            {
                "metric_type": "cpu_percent",
                "start_time": base_time - 200,
                "end_time": base_time + 10,
                "aggregation": "min",
            },
            config=test_config,
        )

        assert "aggregation" in result
        assert result["aggregation"]["min_value"] == 10.0
        assert result["aggregation"]["max_value"] == 30.0
        assert result["aggregation"]["avg_value"] == 20.0
        assert result["aggregation"]["count"] == 3

    @pytest.mark.asyncio
    async def test_query_aggregation_all_includes_samples(
        self,
        viewer_ctx: ToolContext,
        test_config: AppConfig,
        populated_storage: MetricsStorage,  # noqa: ARG002
    ) -> None:
        """Test aggregation='all' includes both aggregation and samples."""
        base_time = time.time()
        result = await handle_metrics_query(
            viewer_ctx,
            {
                "metric_type": "cpu_percent",
                "start_time": base_time - 200,
                "end_time": base_time + 10,
                "aggregation": "all",
            },
            config=test_config,
        )

        assert "aggregation" in result
        assert "samples" in result
        assert len(result["samples"]) == 3

    @pytest.mark.asyncio
    async def test_query_aggregation_requires_metric_type(
        self, viewer_ctx: ToolContext, test_config: AppConfig
    ) -> None:
        """Test that aggregation requires metric_type."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_metrics_query(
                viewer_ctx,
                {"aggregation": "min"},
                config=test_config,
            )
        assert "metric_type is required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_query_aggregation_requires_time_range(
        self, viewer_ctx: ToolContext, test_config: AppConfig
    ) -> None:
        """Test that aggregation requires time range."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_metrics_query(
                viewer_ctx,
                {"metric_type": "cpu_percent", "aggregation": "min"},
                config=test_config,
            )
        assert "start_time and end_time are required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_query_invalid_limit(
        self, viewer_ctx: ToolContext, test_config: AppConfig
    ) -> None:
        """Test that invalid limit raises error."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_metrics_query(
                viewer_ctx,
                {"limit": 0},
                config=test_config,
            )
        assert "limit" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_query_invalid_offset(
        self, viewer_ctx: ToolContext, test_config: AppConfig
    ) -> None:
        """Test that invalid offset raises error."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_metrics_query(
                viewer_ctx,
                {"offset": -1},
                config=test_config,
            )
        assert "offset" in str(exc_info.value)


# =============================================================================
# Tests for metrics.get_realtime
# =============================================================================


class TestMetricsGetRealtime:
    """Tests for metrics.get_realtime tool."""

    @pytest.mark.asyncio
    async def test_returns_dict(
        self, viewer_ctx: ToolContext, test_config: AppConfig
    ) -> None:
        """Test that handler returns a dictionary."""
        result = await handle_metrics_get_realtime(
            viewer_ctx, {}, config=test_config
        )
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_contains_required_fields(
        self, viewer_ctx: ToolContext, test_config: AppConfig
    ) -> None:
        """Test that result contains required fields."""
        result = await handle_metrics_get_realtime(
            viewer_ctx, {}, config=test_config
        )

        assert "timestamp" in result
        assert "metrics" in result
        assert isinstance(result["metrics"], dict)

    @pytest.mark.asyncio
    async def test_metrics_has_cpu_percent(
        self, viewer_ctx: ToolContext, test_config: AppConfig
    ) -> None:
        """Test that metrics include cpu_percent."""
        result = await handle_metrics_get_realtime(
            viewer_ctx, {}, config=test_config
        )

        assert "cpu_percent" in result["metrics"]
        cpu = result["metrics"]["cpu_percent"]
        assert isinstance(cpu, (int, float))
        assert 0 <= cpu <= 100

    @pytest.mark.asyncio
    async def test_metrics_has_memory_percent(
        self, viewer_ctx: ToolContext, test_config: AppConfig
    ) -> None:
        """Test that metrics include memory_percent."""
        result = await handle_metrics_get_realtime(
            viewer_ctx, {}, config=test_config
        )

        assert "memory_percent" in result["metrics"]
        mem = result["metrics"]["memory_percent"]
        assert isinstance(mem, (int, float))
        assert 0 <= mem <= 100

    @pytest.mark.asyncio
    async def test_metrics_has_disk_percent(
        self, viewer_ctx: ToolContext, test_config: AppConfig
    ) -> None:
        """Test that metrics include disk_percent."""
        result = await handle_metrics_get_realtime(
            viewer_ctx, {}, config=test_config
        )

        assert "disk_percent" in result["metrics"]
        disk = result["metrics"]["disk_percent"]
        assert isinstance(disk, (int, float))
        assert 0 <= disk <= 100

    @pytest.mark.asyncio
    async def test_timestamp_is_iso8601(
        self, viewer_ctx: ToolContext, test_config: AppConfig
    ) -> None:
        """Test that timestamp is ISO 8601 format."""
        result = await handle_metrics_get_realtime(
            viewer_ctx, {}, config=test_config
        )

        assert "T" in result["timestamp"]
        # Should be parseable
        datetime.fromisoformat(result["timestamp"].replace("Z", "+00:00"))
