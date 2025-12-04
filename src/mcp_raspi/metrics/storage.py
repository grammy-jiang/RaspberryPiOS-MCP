"""
SQLite storage layer for metrics persistence.

This module implements the MetricsStorage class that handles:
- SQLite database initialization with proper schema
- Inserting metrics samples
- Querying metrics by time range and type
- Aggregation functions (min, max, avg)
- Retention policy (deleting old data)

Design follows Doc 06 §5 (Sampling & Storage Design) and Doc 09 §3 (Metrics Storage).

SQLite Schema:
    CREATE TABLE metrics (
        id INTEGER PRIMARY KEY,
        timestamp REAL,          -- Unix timestamp
        metric_type TEXT,        -- 'cpu_percent', 'memory_percent', etc.
        value REAL,
        metadata TEXT            -- JSON metadata
    );
    CREATE INDEX idx_timestamp ON metrics(timestamp);
    CREATE INDEX idx_type_timestamp ON metrics(metric_type, timestamp);
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp_raspi.errors import FailedPreconditionError, InvalidArgumentError
from mcp_raspi.logging import get_logger

logger = get_logger(__name__)

# =============================================================================
# Data Models
# =============================================================================


@dataclass
class MetricSample:
    """A single metric sample.

    Attributes:
        timestamp: Unix timestamp when the sample was recorded.
        metric_type: Type of metric (e.g., 'cpu_percent', 'memory_percent').
        value: The metric value.
        metadata: Optional JSON-serializable metadata.
        id: Database ID (set after insertion).
    """

    timestamp: float
    metric_type: str
    value: float
    metadata: dict[str, Any] = field(default_factory=dict)
    id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "metric_type": self.metric_type,
            "value": self.value,
            "metadata": self.metadata,
        }


@dataclass
class AggregationResult:
    """Result of an aggregation query.

    Attributes:
        metric_type: The metric type aggregated.
        min_value: Minimum value in the range.
        max_value: Maximum value in the range.
        avg_value: Average value in the range.
        count: Number of samples in the range.
        start_time: Start of the time range.
        end_time: End of the time range.
    """

    metric_type: str
    min_value: float | None
    max_value: float | None
    avg_value: float | None
    count: int
    start_time: float
    end_time: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "metric_type": self.metric_type,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "avg_value": self.avg_value,
            "count": self.count,
            "start_time": self.start_time,
            "end_time": self.end_time,
        }


# =============================================================================
# Constants
# =============================================================================

# Precision for aggregation average values (number of decimal places)
AGGREGATION_PRECISION = 4


# =============================================================================
# SQLite Schema
# =============================================================================

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    metric_type TEXT NOT NULL,
    value REAL NOT NULL,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_timestamp ON metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_type_timestamp ON metrics(metric_type, timestamp);
"""


# =============================================================================
# MetricsStorage Class
# =============================================================================


class MetricsStorage:
    """
    SQLite-based storage for metrics samples.

    This class provides thread-safe access to the metrics SQLite database
    with support for:
    - Inserting individual and batch samples
    - Querying by time range and metric type
    - Aggregation functions (min, max, avg)
    - Retention policy enforcement

    Thread Safety:
    - Uses WAL mode for better concurrent read/write performance
    - Each operation acquires and releases its own connection
    - Batch inserts use transactions for atomicity

    Example:
        >>> storage = MetricsStorage("/var/lib/mcp-raspi/metrics/metrics.db")
        >>> await storage.initialize()
        >>> sample = MetricSample(timestamp=time.time(), metric_type="cpu_percent", value=45.5)
        >>> await storage.insert(sample)
        >>> samples = await storage.query(metric_type="cpu_percent", limit=10)
    """

    def __init__(self, db_path: str | Path) -> None:
        """
        Initialize the MetricsStorage.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = Path(db_path)
        self._initialized = False
        self._lock = asyncio.Lock()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Get a database connection with proper settings.

        Yields:
            SQLite connection configured for optimal performance.
        """
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            # Enable WAL mode for better concurrent access
            conn.execute("PRAGMA journal_mode=WAL")
            # Enable foreign keys
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
        finally:
            conn.close()

    async def initialize(self) -> None:
        """
        Initialize the database schema.

        Creates the metrics table and indices if they don't exist.
        This method is idempotent and safe to call multiple times.

        Raises:
            FailedPreconditionError: If the database cannot be initialized.
        """
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            try:
                # Ensure parent directory exists
                self.db_path.parent.mkdir(parents=True, exist_ok=True)

                # Create schema
                def _init_db() -> None:
                    with self._get_connection() as conn:
                        conn.executescript(SCHEMA_SQL)
                        conn.commit()

                await asyncio.get_event_loop().run_in_executor(None, _init_db)
                self._initialized = True
                logger.info(
                    "Metrics database initialized",
                    extra={"db_path": str(self.db_path)},
                )
            except Exception as e:
                logger.error(
                    "Failed to initialize metrics database",
                    extra={"db_path": str(self.db_path), "error": str(e)},
                )
                raise FailedPreconditionError(
                    f"Failed to initialize metrics database: {e}",
                    details={"db_path": str(self.db_path)},
                ) from e

    async def _ensure_initialized(self) -> None:
        """
        Ensure the database is initialized in a thread-safe manner.

        This method checks the flag and calls initialize() which handles
        its own locking for thread safety.
        """
        if not self._initialized:
            await self.initialize()

    async def insert(self, sample: MetricSample) -> int:
        """
        Insert a single metric sample.

        Args:
            sample: The MetricSample to insert.

        Returns:
            The database ID of the inserted sample.

        Raises:
            FailedPreconditionError: If the database is not initialized or write fails.
        """
        await self._ensure_initialized()

        def _insert() -> int:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO metrics (timestamp, metric_type, value, metadata)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        sample.timestamp,
                        sample.metric_type,
                        sample.value,
                        json.dumps(sample.metadata) if sample.metadata else None,
                    ),
                )
                conn.commit()
                return cursor.lastrowid or 0

        try:
            sample_id = await asyncio.get_event_loop().run_in_executor(None, _insert)
            sample.id = sample_id
            return sample_id
        except Exception as e:
            logger.error(
                "Failed to insert metric sample",
                extra={"metric_type": sample.metric_type, "error": str(e)},
            )
            raise FailedPreconditionError(
                f"Failed to insert metric sample: {e}",
                details={"metric_type": sample.metric_type},
            ) from e

    async def insert_batch(self, samples: list[MetricSample]) -> int:
        """
        Insert multiple metric samples in a single transaction.

        This is more efficient than inserting samples one at a time
        as it reduces the number of fsync operations.

        Args:
            samples: List of MetricSample objects to insert.

        Returns:
            Number of samples inserted.

        Raises:
            FailedPreconditionError: If the database is not initialized or write fails.
        """
        if not samples:
            return 0

        await self._ensure_initialized()

        def _insert_batch() -> int:
            with self._get_connection() as conn:
                cursor = conn.executemany(
                    """
                    INSERT INTO metrics (timestamp, metric_type, value, metadata)
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        (
                            s.timestamp,
                            s.metric_type,
                            s.value,
                            json.dumps(s.metadata) if s.metadata else None,
                        )
                        for s in samples
                    ],
                )
                conn.commit()
                return cursor.rowcount

        try:
            count = await asyncio.get_event_loop().run_in_executor(None, _insert_batch)
            logger.debug(
                "Inserted batch of metric samples",
                extra={"count": count},
            )
            return count
        except Exception as e:
            logger.error(
                "Failed to insert metric samples batch",
                extra={"count": len(samples), "error": str(e)},
            )
            raise FailedPreconditionError(
                f"Failed to insert metric samples: {e}",
                details={"count": len(samples)},
            ) from e

    async def query(
        self,
        *,
        metric_type: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
        limit: int = 1000,
        offset: int = 0,
        order: str = "desc",
    ) -> list[MetricSample]:
        """
        Query metrics samples with filtering and pagination.

        Args:
            metric_type: Filter by metric type (e.g., 'cpu_percent').
            start_time: Filter samples after this Unix timestamp.
            end_time: Filter samples before this Unix timestamp.
            limit: Maximum number of samples to return (default 1000).
            offset: Number of samples to skip (for pagination).
            order: Sort order ('asc' or 'desc', default 'desc').

        Returns:
            List of MetricSample objects matching the criteria.

        Raises:
            InvalidArgumentError: If parameters are invalid.
            FailedPreconditionError: If the query fails.
        """
        await self._ensure_initialized()

        # Validate parameters
        if limit < 1 or limit > 10000:
            raise InvalidArgumentError(
                "limit must be between 1 and 10000",
                details={"limit": limit},
            )
        if offset < 0:
            raise InvalidArgumentError(
                "offset must be non-negative",
                details={"offset": offset},
            )
        if order not in ("asc", "desc"):
            raise InvalidArgumentError(
                "order must be 'asc' or 'desc'",
                details={"order": order},
            )

        def _query() -> list[MetricSample]:
            with self._get_connection() as conn:
                # Build query with conditions
                conditions = []
                params: list[Any] = []

                if metric_type is not None:
                    conditions.append("metric_type = ?")
                    params.append(metric_type)

                if start_time is not None:
                    conditions.append("timestamp >= ?")
                    params.append(start_time)

                if end_time is not None:
                    conditions.append("timestamp <= ?")
                    params.append(end_time)

                where_clause = (
                    " WHERE " + " AND ".join(conditions) if conditions else ""
                )
                order_clause = f" ORDER BY timestamp {order.upper()}"
                limit_clause = " LIMIT ? OFFSET ?"
                params.extend([limit, offset])

                query = f"""
                    SELECT id, timestamp, metric_type, value, metadata
                    FROM metrics
                    {where_clause}
                    {order_clause}
                    {limit_clause}
                """

                cursor = conn.execute(query, params)
                rows = cursor.fetchall()

                samples = []
                for row in rows:
                    metadata = {}
                    if row["metadata"]:
                        with contextlib.suppress(json.JSONDecodeError):
                            metadata = json.loads(row["metadata"])
                    samples.append(
                        MetricSample(
                            id=row["id"],
                            timestamp=row["timestamp"],
                            metric_type=row["metric_type"],
                            value=row["value"],
                            metadata=metadata,
                        )
                    )
                return samples

        try:
            return await asyncio.get_event_loop().run_in_executor(None, _query)
        except Exception as e:
            logger.error(
                "Failed to query metrics",
                extra={"metric_type": metric_type, "error": str(e)},
            )
            raise FailedPreconditionError(
                f"Failed to query metrics: {e}",
                details={"metric_type": metric_type},
            ) from e

    async def aggregate(
        self,
        metric_type: str,
        start_time: float,
        end_time: float,
    ) -> AggregationResult:
        """
        Compute aggregation statistics for a metric type over a time range.

        Computes min, max, avg, and count in a single efficient SQL query.

        Note: The time range is inclusive on both ends (start_time <= timestamp <= end_time).
        This differs from Python's typical half-open range convention [start, end).

        Args:
            metric_type: The metric type to aggregate.
            start_time: Start of the time range (Unix timestamp, inclusive).
            end_time: End of the time range (Unix timestamp, inclusive).

        Returns:
            AggregationResult with min, max, avg, count.

        Raises:
            InvalidArgumentError: If parameters are invalid.
            FailedPreconditionError: If the query fails.
        """
        await self._ensure_initialized()

        if not metric_type:
            raise InvalidArgumentError(
                "metric_type is required for aggregation",
                details={},
            )
        if start_time >= end_time:
            raise InvalidArgumentError(
                "start_time must be less than end_time",
                details={"start_time": start_time, "end_time": end_time},
            )

        def _aggregate() -> AggregationResult:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT
                        MIN(value) as min_value,
                        MAX(value) as max_value,
                        AVG(value) as avg_value,
                        COUNT(*) as count
                    FROM metrics
                    WHERE metric_type = ?
                      AND timestamp >= ?
                      AND timestamp <= ?
                    """,
                    (metric_type, start_time, end_time),
                )
                row = cursor.fetchone()
                return AggregationResult(
                    metric_type=metric_type,
                    min_value=row["min_value"],
                    max_value=row["max_value"],
                    avg_value=(
                        round(row["avg_value"], AGGREGATION_PRECISION)
                        if row["avg_value"]
                        else None
                    ),
                    count=row["count"],
                    start_time=start_time,
                    end_time=end_time,
                )

        try:
            return await asyncio.get_event_loop().run_in_executor(None, _aggregate)
        except Exception as e:
            logger.error(
                "Failed to aggregate metrics",
                extra={"metric_type": metric_type, "error": str(e)},
            )
            raise FailedPreconditionError(
                f"Failed to aggregate metrics: {e}",
                details={"metric_type": metric_type},
            ) from e

    async def delete_older_than(self, cutoff_time: float) -> int:
        """
        Delete metrics samples older than the specified time.

        Used to enforce retention policy.

        Args:
            cutoff_time: Unix timestamp. Samples older than this are deleted.

        Returns:
            Number of samples deleted.

        Raises:
            FailedPreconditionError: If the deletion fails.
        """
        await self._ensure_initialized()

        def _delete() -> int:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM metrics WHERE timestamp < ?",
                    (cutoff_time,),
                )
                conn.commit()
                return cursor.rowcount

        try:
            count = await asyncio.get_event_loop().run_in_executor(None, _delete)
            if count > 0:
                logger.info(
                    "Deleted old metrics samples",
                    extra={
                        "count": count,
                        "cutoff_time": datetime.fromtimestamp(cutoff_time).isoformat(),
                    },
                )
            return count
        except Exception as e:
            logger.error(
                "Failed to delete old metrics",
                extra={"error": str(e)},
            )
            raise FailedPreconditionError(
                f"Failed to delete old metrics: {e}",
                details={"cutoff_time": cutoff_time},
            ) from e

    async def get_metric_types(self) -> list[str]:
        """
        Get a list of all distinct metric types in the database.

        Returns:
            List of metric type strings.
        """
        await self._ensure_initialized()

        def _get_types() -> list[str]:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT DISTINCT metric_type FROM metrics ORDER BY metric_type"
                )
                return [row["metric_type"] for row in cursor.fetchall()]

        try:
            return await asyncio.get_event_loop().run_in_executor(None, _get_types)
        except Exception as e:
            logger.error(
                "Failed to get metric types",
                extra={"error": str(e)},
            )
            return []

    async def get_sample_count(
        self,
        metric_type: str | None = None,
    ) -> int:
        """
        Get the total count of samples.

        Args:
            metric_type: Optional filter by metric type.

        Returns:
            Total number of samples.
        """
        await self._ensure_initialized()

        def _count() -> int:
            with self._get_connection() as conn:
                if metric_type:
                    cursor = conn.execute(
                        "SELECT COUNT(*) as count FROM metrics WHERE metric_type = ?",
                        (metric_type,),
                    )
                else:
                    cursor = conn.execute("SELECT COUNT(*) as count FROM metrics")
                return cursor.fetchone()["count"]

        try:
            return await asyncio.get_event_loop().run_in_executor(None, _count)
        except Exception as e:
            logger.error(
                "Failed to get sample count",
                extra={"error": str(e)},
            )
            return 0

    async def close(self) -> None:
        """
        Close the storage (no-op for connection-per-operation model).

        This method exists for API consistency and potential future
        connection pooling implementations.
        """
        self._initialized = False
        logger.debug("Metrics storage closed")
