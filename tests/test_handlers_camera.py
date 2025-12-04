"""
Tests for camera handlers in the Privileged Agent.

This test module validates:
- camera.get_info detects camera or returns "not detected"
- camera.capture captures photo with rate limiting
- Rate limiting works correctly
- Parameter validation works
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_raspi.ipc.protocol import IPCRequest
from mcp_raspi_ops.handlers.camera import (
    AgentPhotoRateLimiter,
    _agent_rate_limiter,
    _detect_camera_info,
    handle_camera_capture,
    handle_camera_get_info,
    register_camera_handlers,
)
from mcp_raspi_ops.handlers_core import HandlerError, HandlerRegistry


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def temp_media_dir():
    """Create a temporary media directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset the rate limiter before each test."""
    _agent_rate_limiter._timestamps.clear()
    _agent_rate_limiter._max_per_minute = 30
    yield


def make_request(
    operation: str,
    params: dict | None = None,
    request_id: str = "test-req-1",
) -> IPCRequest:
    """Create an IPC request for testing."""
    return IPCRequest(
        id=request_id,
        operation=operation,
        timestamp="2025-01-15T10:00:00Z",
        caller={"user_id": "test@example.com", "role": "admin"},
        params=params or {},
    )


# =============================================================================
# Tests for AgentPhotoRateLimiter
# =============================================================================


class TestAgentPhotoRateLimiter:
    """Tests for the agent photo rate limiter."""

    def test_allows_within_limit(self) -> None:
        """Test that captures within limit are allowed."""
        limiter = AgentPhotoRateLimiter(max_per_minute=5)

        for _ in range(5):
            allowed, retry_after = limiter.check_and_record()
            assert allowed is True
            assert retry_after is None

    def test_blocks_when_limit_exceeded(self) -> None:
        """Test that captures are blocked when limit exceeded."""
        limiter = AgentPhotoRateLimiter(max_per_minute=2)

        # Use up the limit
        for _ in range(2):
            allowed, _ = limiter.check_and_record()
            assert allowed is True

        # Next should be blocked
        allowed, retry_after = limiter.check_and_record()
        assert allowed is False
        assert retry_after is not None
        assert retry_after > 0

    def test_remaining_count(self) -> None:
        """Test remaining count calculation."""
        limiter = AgentPhotoRateLimiter(max_per_minute=5)

        assert limiter.get_remaining() == 5

        limiter.check_and_record()
        assert limiter.get_remaining() == 4

    def test_set_limit(self) -> None:
        """Test updating the rate limit."""
        limiter = AgentPhotoRateLimiter(max_per_minute=5)
        limiter.set_limit(10)

        assert limiter.get_remaining() == 10


# =============================================================================
# Tests for Camera Detection
# =============================================================================


class TestCameraDetection:
    """Tests for camera detection at agent level."""

    def test_detect_camera_info_structure(self) -> None:
        """Test detection returns expected structure."""
        result = _detect_camera_info()

        assert "detected" in result
        if result["detected"]:
            assert "model" in result
            assert "backend" in result

    def test_detect_no_camera(self) -> None:
        """Test detection when no camera available."""
        with patch.dict("sys.modules", {"picamera2": None}):
            with patch.object(Path, "glob", return_value=[]):
                result = _detect_camera_info()
                assert result["detected"] is False


# =============================================================================
# Tests for camera.get_info Handler
# =============================================================================


class TestCameraGetInfoHandler:
    """Tests for camera.get_info handler."""

    @pytest.mark.asyncio
    async def test_get_info_returns_detection_status(self) -> None:
        """Test get_info returns detection status."""
        request = make_request("camera.get_info", {"max_per_minute": 10})

        result = await handle_camera_get_info(request)

        assert "detected" in result
        assert "rate_limit" in result

    @pytest.mark.asyncio
    async def test_get_info_includes_rate_limit(self) -> None:
        """Test get_info includes rate limit info."""
        request = make_request("camera.get_info", {"max_per_minute": 15})

        result = await handle_camera_get_info(request)

        assert result["rate_limit"]["max_per_minute"] == 15
        assert "remaining" in result["rate_limit"]


# =============================================================================
# Tests for camera.capture Handler
# =============================================================================


class TestCameraCaptureHandler:
    """Tests for camera.capture handler."""

    @pytest.mark.asyncio
    async def test_capture_requires_output_path(self) -> None:
        """Test that output_path is required."""
        request = make_request(
            "camera.capture",
            {"width": 640, "height": 480, "quality": 85},
        )

        with pytest.raises(HandlerError) as exc_info:
            await handle_camera_capture(request)
        assert exc_info.value.code == "invalid_argument"
        assert "output_path" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_capture_validates_width(self, temp_media_dir: Path) -> None:
        """Test that width is validated."""
        request = make_request(
            "camera.capture",
            {
                "output_path": str(temp_media_dir / "test.jpg"),
                "width": -1,
                "height": 480,
                "quality": 85,
            },
        )

        with pytest.raises(HandlerError) as exc_info:
            await handle_camera_capture(request)
        assert exc_info.value.code == "invalid_argument"

    @pytest.mark.asyncio
    async def test_capture_validates_height(self, temp_media_dir: Path) -> None:
        """Test that height is validated."""
        request = make_request(
            "camera.capture",
            {
                "output_path": str(temp_media_dir / "test.jpg"),
                "width": 640,
                "height": -1,
                "quality": 85,
            },
        )

        with pytest.raises(HandlerError) as exc_info:
            await handle_camera_capture(request)
        assert exc_info.value.code == "invalid_argument"

    @pytest.mark.asyncio
    async def test_capture_validates_quality_low(self, temp_media_dir: Path) -> None:
        """Test that quality below 1 is rejected."""
        request = make_request(
            "camera.capture",
            {
                "output_path": str(temp_media_dir / "test.jpg"),
                "width": 640,
                "height": 480,
                "quality": 0,
            },
        )

        with pytest.raises(HandlerError) as exc_info:
            await handle_camera_capture(request)
        assert exc_info.value.code == "invalid_argument"

    @pytest.mark.asyncio
    async def test_capture_validates_quality_high(self, temp_media_dir: Path) -> None:
        """Test that quality above 100 is rejected."""
        request = make_request(
            "camera.capture",
            {
                "output_path": str(temp_media_dir / "test.jpg"),
                "width": 640,
                "height": 480,
                "quality": 101,
            },
        )

        with pytest.raises(HandlerError) as exc_info:
            await handle_camera_capture(request)
        assert exc_info.value.code == "invalid_argument"

    @pytest.mark.asyncio
    async def test_capture_mock_creates_file(self, temp_media_dir: Path) -> None:
        """Test mock capture creates a file."""
        output_path = temp_media_dir / "photos" / "test.jpg"

        request = make_request(
            "camera.capture",
            {
                "output_path": str(output_path),
                "width": 640,
                "height": 480,
                "quality": 85,
                "use_mock": True,
            },
        )

        result = await handle_camera_capture(request)

        assert result["success"] is True
        assert result["mocked"] is True
        assert Path(result["file_path"]).exists()

    @pytest.mark.asyncio
    async def test_capture_mock_file_is_jpeg(self, temp_media_dir: Path) -> None:
        """Test mock capture creates valid JPEG."""
        output_path = temp_media_dir / "photos" / "test.jpg"

        request = make_request(
            "camera.capture",
            {
                "output_path": str(output_path),
                "width": 640,
                "height": 480,
                "quality": 85,
                "use_mock": True,
            },
        )

        result = await handle_camera_capture(request)

        # Check JPEG magic bytes
        with open(result["file_path"], "rb") as f:
            magic = f.read(2)
            assert magic == b"\xff\xd8"

    @pytest.mark.asyncio
    async def test_capture_rate_limit_enforced(self, temp_media_dir: Path) -> None:
        """Test rate limiting is enforced."""
        # Reset rate limiter with low limit
        _agent_rate_limiter._timestamps.clear()
        _agent_rate_limiter.set_limit(2)

        output_path = temp_media_dir / "photos" / "test.jpg"

        # First two should succeed
        for i in range(2):
            request = make_request(
                "camera.capture",
                {
                    "output_path": str(temp_media_dir / f"photo_{i}.jpg"),
                    "width": 640,
                    "height": 480,
                    "quality": 85,
                    "use_mock": True,
                    "max_per_minute": 2,
                },
            )
            result = await handle_camera_capture(request)
            assert result["success"] is True

        # Third should fail
        request = make_request(
            "camera.capture",
            {
                "output_path": str(temp_media_dir / "photo_3.jpg"),
                "width": 640,
                "height": 480,
                "quality": 85,
                "use_mock": True,
                "max_per_minute": 2,
            },
        )

        with pytest.raises(HandlerError) as exc_info:
            await handle_camera_capture(request)
        assert exc_info.value.code == "resource_exhausted"
        assert "Rate limit exceeded" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_capture_returns_metadata(self, temp_media_dir: Path) -> None:
        """Test capture returns expected metadata."""
        request = make_request(
            "camera.capture",
            {
                "output_path": str(temp_media_dir / "test.jpg"),
                "width": 800,
                "height": 600,
                "quality": 90,
                "use_mock": True,
            },
        )

        result = await handle_camera_capture(request)

        assert result["width"] == 800
        assert result["height"] == 600
        assert result["quality"] == 90
        assert "file_size_bytes" in result
        assert "timestamp" in result
        assert "rate_limit_remaining" in result


# =============================================================================
# Tests for Handler Registration
# =============================================================================


class TestHandlerRegistration:
    """Tests for handler registration."""

    def test_register_camera_handlers(self) -> None:
        """Test that camera handlers are registered correctly."""
        registry = HandlerRegistry()
        register_camera_handlers(registry)

        operations = registry.get_operations()
        assert "camera.get_info" in operations
        assert "camera.capture" in operations
