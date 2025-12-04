"""
Tests for metrics storage layer.

This test module validates:
- SQLite schema creation and initialization
- Inserting individual and batch samples
- Querying with filters and pagination
- Aggregation functions (min, max, avg)
- Retention policy (delete old data)
- Concurrent access handling
"""

from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path

import pytest

from mcp_raspi.errors import InvalidArgumentError
from mcp_raspi.metrics.storage import (
    AggregationResult,
    MetricSample,
    MetricsStorage,
)

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


# =============================================================================
# Tests for Initialization
# =============================================================================


class TestMetricsStorageInit:
    """Tests for MetricsStorage initialization."""

    @pytest.mark.asyncio
    async def test_initialize_creates_database(self, temp_db_path: Path) -> None:
        """Test that initialize creates the database file."""
        storage = MetricsStorage(temp_db_path)
        assert not temp_db_path.exists()

        await storage.initialize()

        assert temp_db_path.exists()

    @pytest.mark.asyncio
    async def test_initialize_creates_parent_dirs(self) -> None:
        """Test that initialize creates parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "nested" / "path" / "metrics.db"
            storage = MetricsStorage(db_path)

            await storage.initialize()

            assert db_path.exists()

    @pytest.mark.asyncio
    async def test_initialize_is_idempotent(self, temp_db_path: Path) -> None:
        """Test that initialize can be called multiple times safely."""
        storage = MetricsStorage(temp_db_path)

        await storage.initialize()
        await storage.initialize()  # Should not raise

        assert temp_db_path.exists()

    @pytest.mark.asyncio
    async def test_initialize_creates_tables(self, storage: MetricsStorage) -> None:
        """Test that initialize creates the metrics table."""
        # Insert a sample to verify table exists
        sample = MetricSample(
            timestamp=time.time(),
            metric_type="test",
            value=1.0,
        )
        sample_id = await storage.insert(sample)
        assert sample_id > 0


# =============================================================================
# Tests for Insert Operations
# =============================================================================


class TestMetricsStorageInsert:
    """Tests for inserting metric samples."""

    @pytest.mark.asyncio
    async def test_insert_single_sample(self, storage: MetricsStorage) -> None:
        """Test inserting a single sample."""
        sample = MetricSample(
            timestamp=time.time(),
            metric_type="cpu_percent",
            value=45.5,
        )

        sample_id = await storage.insert(sample)

        assert sample_id > 0
        assert sample.id == sample_id

    @pytest.mark.asyncio
    async def test_insert_with_metadata(self, storage: MetricsStorage) -> None:
        """Test inserting a sample with metadata."""
        sample = MetricSample(
            timestamp=time.time(),
            metric_type="memory_used_bytes",
            value=1024.0,
            metadata={"total_bytes": 2048},
        )

        await storage.insert(sample)

        # Query and verify metadata
        samples = await storage.query(metric_type="memory_used_bytes", limit=1)
        assert len(samples) == 1
        assert samples[0].metadata == {"total_bytes": 2048}

    @pytest.mark.asyncio
    async def test_insert_batch_samples(self, storage: MetricsStorage) -> None:
        """Test inserting multiple samples in a batch."""
        timestamp = time.time()
        samples = [
            MetricSample(timestamp=timestamp, metric_type="cpu_percent", value=10.0),
            MetricSample(timestamp=timestamp, metric_type="memory_percent", value=20.0),
            MetricSample(timestamp=timestamp, metric_type="disk_percent", value=30.0),
        ]

        count = await storage.insert_batch(samples)

        assert count == 3

    @pytest.mark.asyncio
    async def test_insert_batch_empty_list(self, storage: MetricsStorage) -> None:
        """Test inserting an empty list of samples."""
        count = await storage.insert_batch([])
        assert count == 0

    @pytest.mark.asyncio
    async def test_insert_auto_initializes(self, temp_db_path: Path) -> None:
        """Test that insert auto-initializes the database."""
        storage = MetricsStorage(temp_db_path)
        sample = MetricSample(
            timestamp=time.time(),
            metric_type="test",
            value=1.0,
        )

        # Should not raise, should auto-initialize
        sample_id = await storage.insert(sample)
        assert sample_id > 0


# =============================================================================
# Tests for Query Operations
# =============================================================================


class TestMetricsStorageQuery:
    """Tests for querying metric samples."""

    @pytest.mark.asyncio
    async def test_query_empty_database(self, storage: MetricsStorage) -> None:
        """Test querying an empty database."""
        samples = await storage.query()
        assert samples == []

    @pytest.mark.asyncio
    async def test_query_by_metric_type(self, storage: MetricsStorage) -> None:
        """Test filtering by metric type."""
        timestamp = time.time()
        await storage.insert_batch(
            [
                MetricSample(timestamp=timestamp, metric_type="cpu", value=10.0),
                MetricSample(timestamp=timestamp, metric_type="memory", value=20.0),
                MetricSample(timestamp=timestamp, metric_type="cpu", value=15.0),
            ]
        )

        samples = await storage.query(metric_type="cpu")

        assert len(samples) == 2
        assert all(s.metric_type == "cpu" for s in samples)

    @pytest.mark.asyncio
    async def test_query_by_time_range(self, storage: MetricsStorage) -> None:
        """Test filtering by time range."""
        base_time = time.time()
        await storage.insert_batch(
            [
                MetricSample(timestamp=base_time - 100, metric_type="test", value=1.0),
                MetricSample(timestamp=base_time, metric_type="test", value=2.0),
                MetricSample(timestamp=base_time + 100, metric_type="test", value=3.0),
            ]
        )

        samples = await storage.query(
            start_time=base_time - 50,
            end_time=base_time + 50,
        )

        assert len(samples) == 1
        assert samples[0].value == 2.0

    @pytest.mark.asyncio
    async def test_query_with_limit(self, storage: MetricsStorage) -> None:
        """Test limiting results."""
        timestamp = time.time()
        await storage.insert_batch(
            [
                MetricSample(timestamp=timestamp + i, metric_type="test", value=float(i))
                for i in range(10)
            ]
        )

        samples = await storage.query(limit=5)

        assert len(samples) == 5

    @pytest.mark.asyncio
    async def test_query_with_offset(self, storage: MetricsStorage) -> None:
        """Test pagination with offset."""
        timestamp = time.time()
        await storage.insert_batch(
            [
                MetricSample(timestamp=timestamp + i, metric_type="test", value=float(i))
                for i in range(10)
            ]
        )

        # Get first page
        page1 = await storage.query(limit=5, offset=0, order="asc")
        # Get second page
        page2 = await storage.query(limit=5, offset=5, order="asc")

        assert len(page1) == 5
        assert len(page2) == 5
        # Values should not overlap
        page1_values = {s.value for s in page1}
        page2_values = {s.value for s in page2}
        assert page1_values.isdisjoint(page2_values)

    @pytest.mark.asyncio
    async def test_query_order_ascending(self, storage: MetricsStorage) -> None:
        """Test ascending order."""
        timestamp = time.time()
        await storage.insert_batch(
            [
                MetricSample(timestamp=timestamp + i, metric_type="test", value=float(i))
                for i in range(5)
            ]
        )

        samples = await storage.query(order="asc")

        values = [s.value for s in samples]
        assert values == sorted(values)

    @pytest.mark.asyncio
    async def test_query_order_descending(self, storage: MetricsStorage) -> None:
        """Test descending order (default)."""
        timestamp = time.time()
        await storage.insert_batch(
            [
                MetricSample(timestamp=timestamp + i, metric_type="test", value=float(i))
                for i in range(5)
            ]
        )

        samples = await storage.query(order="desc")

        values = [s.value for s in samples]
        assert values == sorted(values, reverse=True)

    @pytest.mark.asyncio
    async def test_query_invalid_limit(self, storage: MetricsStorage) -> None:
        """Test that invalid limit raises error."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await storage.query(limit=0)
        assert "limit" in str(exc_info.value)

        with pytest.raises(InvalidArgumentError):
            await storage.query(limit=100000)

    @pytest.mark.asyncio
    async def test_query_invalid_offset(self, storage: MetricsStorage) -> None:
        """Test that negative offset raises error."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await storage.query(offset=-1)
        assert "offset" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_query_invalid_order(self, storage: MetricsStorage) -> None:
        """Test that invalid order raises error."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await storage.query(order="random")
        assert "order" in str(exc_info.value)


# =============================================================================
# Tests for Aggregation
# =============================================================================


class TestMetricsStorageAggregation:
    """Tests for aggregation functions."""

    @pytest.mark.asyncio
    async def test_aggregate_min_max_avg(self, storage: MetricsStorage) -> None:
        """Test min, max, avg aggregation."""
        base_time = time.time()
        await storage.insert_batch(
            [
                MetricSample(timestamp=base_time, metric_type="cpu", value=10.0),
                MetricSample(timestamp=base_time + 1, metric_type="cpu", value=20.0),
                MetricSample(timestamp=base_time + 2, metric_type="cpu", value=30.0),
            ]
        )

        result = await storage.aggregate(
            metric_type="cpu",
            start_time=base_time - 1,
            end_time=base_time + 10,
        )

        assert result.min_value == 10.0
        assert result.max_value == 30.0
        assert result.avg_value == 20.0
        assert result.count == 3

    @pytest.mark.asyncio
    async def test_aggregate_empty_range(self, storage: MetricsStorage) -> None:
        """Test aggregation on empty range."""
        result = await storage.aggregate(
            metric_type="nonexistent",
            start_time=0,
            end_time=time.time(),
        )

        assert result.min_value is None
        assert result.max_value is None
        assert result.avg_value is None
        assert result.count == 0

    @pytest.mark.asyncio
    async def test_aggregate_single_sample(self, storage: MetricsStorage) -> None:
        """Test aggregation with single sample."""
        timestamp = time.time()
        await storage.insert(
            MetricSample(timestamp=timestamp, metric_type="test", value=42.0)
        )

        result = await storage.aggregate(
            metric_type="test",
            start_time=timestamp - 1,
            end_time=timestamp + 1,
        )

        assert result.min_value == 42.0
        assert result.max_value == 42.0
        assert result.avg_value == 42.0
        assert result.count == 1

    @pytest.mark.asyncio
    async def test_aggregate_requires_metric_type(self, storage: MetricsStorage) -> None:
        """Test that metric_type is required."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await storage.aggregate(
                metric_type="",
                start_time=0,
                end_time=time.time(),
            )
        assert "metric_type" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_aggregate_time_range_validation(
        self, storage: MetricsStorage
    ) -> None:
        """Test that start_time must be less than end_time."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await storage.aggregate(
                metric_type="test",
                start_time=100,
                end_time=50,
            )
        assert "start_time" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_aggregation_result_to_dict(
        self, storage: MetricsStorage  # noqa: ARG002
    ) -> None:
        """Test AggregationResult.to_dict() method."""
        result = AggregationResult(
            metric_type="cpu",
            min_value=10.0,
            max_value=90.0,
            avg_value=50.0,
            count=100,
            start_time=1000.0,
            end_time=2000.0,
        )

        d = result.to_dict()

        assert d["metric_type"] == "cpu"
        assert d["min_value"] == 10.0
        assert d["max_value"] == 90.0
        assert d["avg_value"] == 50.0
        assert d["count"] == 100


# =============================================================================
# Tests for Retention Policy
# =============================================================================


class TestMetricsStorageRetention:
    """Tests for retention policy (delete old data)."""

    @pytest.mark.asyncio
    async def test_delete_older_than(self, storage: MetricsStorage) -> None:
        """Test deleting samples older than cutoff."""
        old_time = time.time() - 1000
        new_time = time.time()

        await storage.insert_batch(
            [
                MetricSample(timestamp=old_time, metric_type="test", value=1.0),
                MetricSample(timestamp=old_time + 1, metric_type="test", value=2.0),
                MetricSample(timestamp=new_time, metric_type="test", value=3.0),
            ]
        )

        # Delete samples older than 500 seconds ago
        cutoff = time.time() - 500
        deleted = await storage.delete_older_than(cutoff)

        assert deleted == 2

        # Verify remaining sample
        samples = await storage.query()
        assert len(samples) == 1
        assert samples[0].value == 3.0

    @pytest.mark.asyncio
    async def test_delete_older_than_none_to_delete(
        self, storage: MetricsStorage
    ) -> None:
        """Test when no samples are old enough to delete."""
        timestamp = time.time()
        await storage.insert(
            MetricSample(timestamp=timestamp, metric_type="test", value=1.0)
        )

        # Cutoff is in the past, but sample is newer
        deleted = await storage.delete_older_than(timestamp - 1000)

        assert deleted == 0


# =============================================================================
# Tests for Utility Methods
# =============================================================================


class TestMetricsStorageUtilities:
    """Tests for utility methods."""

    @pytest.mark.asyncio
    async def test_get_metric_types(self, storage: MetricsStorage) -> None:
        """Test getting distinct metric types."""
        timestamp = time.time()
        await storage.insert_batch(
            [
                MetricSample(timestamp=timestamp, metric_type="cpu", value=10.0),
                MetricSample(timestamp=timestamp, metric_type="memory", value=20.0),
                MetricSample(timestamp=timestamp, metric_type="cpu", value=15.0),
            ]
        )

        types = await storage.get_metric_types()

        assert set(types) == {"cpu", "memory"}

    @pytest.mark.asyncio
    async def test_get_metric_types_empty(self, storage: MetricsStorage) -> None:
        """Test getting metric types from empty database."""
        types = await storage.get_metric_types()
        assert types == []

    @pytest.mark.asyncio
    async def test_get_sample_count(self, storage: MetricsStorage) -> None:
        """Test getting total sample count."""
        timestamp = time.time()
        await storage.insert_batch(
            [
                MetricSample(timestamp=timestamp, metric_type="cpu", value=10.0),
                MetricSample(timestamp=timestamp, metric_type="memory", value=20.0),
                MetricSample(timestamp=timestamp, metric_type="cpu", value=15.0),
            ]
        )

        count = await storage.get_sample_count()
        assert count == 3

        # Filter by type
        cpu_count = await storage.get_sample_count(metric_type="cpu")
        assert cpu_count == 2

    @pytest.mark.asyncio
    async def test_get_sample_count_empty(self, storage: MetricsStorage) -> None:
        """Test getting sample count from empty database."""
        count = await storage.get_sample_count()
        assert count == 0

    @pytest.mark.asyncio
    async def test_close(self, storage: MetricsStorage) -> None:
        """Test closing the storage."""
        await storage.close()
        # After close, _initialized should be False
        assert storage._initialized is False


# =============================================================================
# Tests for MetricSample
# =============================================================================


class TestMetricSample:
    """Tests for MetricSample dataclass."""

    def test_to_dict(self) -> None:
        """Test MetricSample.to_dict() method."""
        sample = MetricSample(
            id=123,
            timestamp=1000.0,
            metric_type="cpu_percent",
            value=45.5,
            metadata={"core": 0},
        )

        d = sample.to_dict()

        assert d["id"] == 123
        assert d["timestamp"] == 1000.0
        assert d["metric_type"] == "cpu_percent"
        assert d["value"] == 45.5
        assert d["metadata"] == {"core": 0}

    def test_to_dict_no_metadata(self) -> None:
        """Test to_dict with empty metadata."""
        sample = MetricSample(
            timestamp=1000.0,
            metric_type="test",
            value=1.0,
        )

        d = sample.to_dict()

        assert d["metadata"] == {}
        assert d["id"] is None


# =============================================================================
# Tests for Concurrent Access
# =============================================================================


class TestMetricsStorageConcurrency:
    """Tests for concurrent access handling."""

    @pytest.mark.asyncio
    async def test_concurrent_inserts(self, storage: MetricsStorage) -> None:
        """Test concurrent insert operations."""

        async def insert_samples(prefix: str) -> None:
            for i in range(10):
                sample = MetricSample(
                    timestamp=time.time(),
                    metric_type=f"{prefix}_{i}",
                    value=float(i),
                )
                await storage.insert(sample)

        # Run concurrent inserts
        await asyncio.gather(
            insert_samples("task1"),
            insert_samples("task2"),
            insert_samples("task3"),
        )

        # Verify all samples were inserted
        count = await storage.get_sample_count()
        assert count == 30

    @pytest.mark.asyncio
    async def test_concurrent_reads_and_writes(self, storage: MetricsStorage) -> None:
        """Test concurrent read and write operations."""
        # Pre-populate
        timestamp = time.time()
        await storage.insert_batch(
            [
                MetricSample(timestamp=timestamp + i, metric_type="test", value=float(i))
                for i in range(50)
            ]
        )

        async def read_samples() -> list[MetricSample]:
            return await storage.query(limit=10)

        async def write_samples() -> None:
            for i in range(10):
                sample = MetricSample(
                    timestamp=time.time(),
                    metric_type="concurrent",
                    value=float(i),
                )
                await storage.insert(sample)

        # Run concurrent reads and writes
        results = await asyncio.gather(
            read_samples(),
            write_samples(),
            read_samples(),
            write_samples(),
        )

        # First and third results should be lists of samples
        assert len(results[0]) == 10
        assert len(results[2]) == 10

        # Total count should include original + new samples
        count = await storage.get_sample_count()
        assert count == 70  # 50 original + 20 new
