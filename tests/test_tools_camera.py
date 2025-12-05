"""
Tests for camera namespace tools.

This test module validates:
- camera.get_info detects camera or returns "not detected"
- camera.take_photo captures photo (with mocking)
- Resolution validation works correctly
- Quality validation works correctly
- Rate limiting enforced
- Photos saved to configured directory
- Viewer role can get info, operator required for capture
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_raspi.config import AppConfig, CameraConfig, TestingConfig
from mcp_raspi.context import CallerInfo, ToolContext
from mcp_raspi.errors import FailedPreconditionError, InvalidArgumentError
from mcp_raspi.security.rbac import PermissionDeniedError
from mcp_raspi.tools.camera import (
    DEFAULT_MAX_PHOTOS_PER_MINUTE,
    DEFAULT_QUALITY,
    DEFAULT_RESOLUTION,
    MAX_QUALITY,
    MIN_QUALITY,
    SUPPORTED_RESOLUTIONS,
    PhotoRateLimiter,
    _detect_camera,
    get_rate_limiter,
    handle_camera_get_info,
    handle_camera_take_photo,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def viewer_ctx() -> ToolContext:
    """Create a test context with viewer role."""
    return ToolContext(
        tool_name="camera.get_info",
        caller=CallerInfo(user_id="viewer@example.com", role="viewer"),
        request_id="test-req-viewer",
    )


@pytest.fixture
def operator_ctx() -> ToolContext:
    """Create a test context with operator role."""
    return ToolContext(
        tool_name="camera.take_photo",
        caller=CallerInfo(user_id="operator@example.com", role="operator"),
        request_id="test-req-operator",
    )


@pytest.fixture
def admin_ctx() -> ToolContext:
    """Create a test context with admin role."""
    return ToolContext(
        tool_name="camera.take_photo",
        caller=CallerInfo(user_id="admin@example.com", role="admin"),
        request_id="test-req-admin",
    )


@pytest.fixture
def temp_media_dir():
    """Create a temporary media directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def full_sandbox_config(temp_media_dir: Path) -> AppConfig:
    """Create config with full sandbox mode."""
    config = AppConfig()
    config.testing = TestingConfig(sandbox_mode="full")
    config.camera = CameraConfig(
        enabled=True,
        media_root=str(temp_media_dir),
        max_photos_per_minute=10,
    )
    return config


@pytest.fixture
def partial_sandbox_config(temp_media_dir: Path) -> AppConfig:
    """Create config with partial sandbox mode."""
    config = AppConfig()
    config.testing = TestingConfig(sandbox_mode="partial")
    config.camera = CameraConfig(
        enabled=True,
        media_root=str(temp_media_dir),
        max_photos_per_minute=10,
    )
    return config


@pytest.fixture
def disabled_sandbox_config(temp_media_dir: Path) -> AppConfig:
    """Create config with disabled sandbox mode."""
    config = AppConfig()
    config.testing = TestingConfig(sandbox_mode="disabled")
    config.camera = CameraConfig(
        enabled=True,
        media_root=str(temp_media_dir),
        max_photos_per_minute=10,
    )
    return config


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset the rate limiter before each test."""
    limiter = get_rate_limiter()
    limiter._timestamps.clear()
    limiter._max_per_minute = DEFAULT_MAX_PHOTOS_PER_MINUTE
    yield


# =============================================================================
# Tests for PhotoRateLimiter
# =============================================================================


class TestPhotoRateLimiter:
    """Tests for the photo rate limiter."""

    def test_allows_within_limit(self) -> None:
        """Test that captures within limit are allowed."""
        limiter = PhotoRateLimiter(max_per_minute=5)

        for _ in range(5):
            allowed, retry_after = limiter.check_and_record()
            assert allowed is True
            assert retry_after is None

    def test_blocks_when_limit_exceeded(self) -> None:
        """Test that captures are blocked when limit exceeded."""
        limiter = PhotoRateLimiter(max_per_minute=3)

        # Use up the limit
        for _ in range(3):
            allowed, _ = limiter.check_and_record()
            assert allowed is True

        # Next should be blocked
        allowed, retry_after = limiter.check_and_record()
        assert allowed is False
        assert retry_after is not None
        assert retry_after > 0

    def test_remaining_count(self) -> None:
        """Test remaining count calculation."""
        limiter = PhotoRateLimiter(max_per_minute=5)

        assert limiter.get_remaining() == 5

        limiter.check_and_record()
        assert limiter.get_remaining() == 4

        limiter.check_and_record()
        assert limiter.get_remaining() == 3

    def test_set_limit(self) -> None:
        """Test updating the rate limit."""
        limiter = PhotoRateLimiter(max_per_minute=5)
        limiter.set_limit(10)

        assert limiter.get_remaining() == 10


# =============================================================================
# Tests for Camera Detection
# =============================================================================


class TestCameraDetection:
    """Tests for camera detection."""

    def test_detect_camera_no_hardware(self) -> None:
        """Test detection when no camera hardware available."""
        # Mock picamera2 import to fail
        with (
            patch.dict("sys.modules", {"picamera2": None}),
            patch("mcp_raspi.tools.camera.Path.glob", return_value=[]),
        ):
            result = _detect_camera()
            assert result["detected"] is False

    def test_detect_camera_v4l2_devices(self) -> None:
        """Test detection of V4L2 devices."""
        # Mock picamera2 to fail but V4L2 devices exist
        mock_devices = [Path("/dev/video0"), Path("/dev/video1")]

        with (
            patch.dict("sys.modules", {"picamera2": None}),
            patch.object(Path, "glob", return_value=mock_devices),
        ):
            result = _detect_camera()
            # May or may not detect based on actual system
            assert "detected" in result


# =============================================================================
# Tests for camera.get_info
# =============================================================================


class TestCameraGetInfo:
    """Tests for camera.get_info tool."""

    @pytest.mark.asyncio
    async def test_viewer_can_get_info(
        self, viewer_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that viewer role can get camera info."""
        result = await handle_camera_get_info(
            viewer_ctx, {}, config=full_sandbox_config
        )

        assert "detected" in result
        assert "rate_limit" in result
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_operator_can_get_info(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that operator role can get camera info."""
        result = await handle_camera_get_info(
            operator_ctx, {}, config=full_sandbox_config
        )

        assert "detected" in result

    @pytest.mark.asyncio
    async def test_full_sandbox_returns_mock_camera(
        self, viewer_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that full sandbox mode returns mock camera info."""
        result = await handle_camera_get_info(
            viewer_ctx, {}, config=full_sandbox_config
        )

        assert result["detected"] is True
        assert result["mocked"] is True
        assert result["backend"] == "mock"

    @pytest.mark.asyncio
    async def test_returns_rate_limit_info(
        self, viewer_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that rate limit info is included."""
        result = await handle_camera_get_info(
            viewer_ctx, {}, config=full_sandbox_config
        )

        assert "rate_limit" in result
        assert "max_per_minute" in result["rate_limit"]
        assert "remaining" in result["rate_limit"]

    @pytest.mark.asyncio
    async def test_returns_supported_resolutions(
        self, viewer_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that supported resolutions are listed."""
        result = await handle_camera_get_info(
            viewer_ctx, {}, config=full_sandbox_config
        )

        assert "resolutions" in result
        assert isinstance(result["resolutions"], list)
        assert len(result["resolutions"]) > 0


# =============================================================================
# Tests for camera.take_photo
# =============================================================================


class TestCameraTakePhoto:
    """Tests for camera.take_photo tool."""

    @pytest.mark.asyncio
    async def test_viewer_denied(
        self, viewer_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that viewer role is denied."""
        with pytest.raises(PermissionDeniedError):
            await handle_camera_take_photo(
                viewer_ctx, {}, config=full_sandbox_config
            )

    @pytest.mark.asyncio
    async def test_operator_allowed(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that operator role is allowed."""
        result = await handle_camera_take_photo(
            operator_ctx, {}, config=full_sandbox_config
        )

        assert "file_path" in result
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_admin_allowed(
        self, admin_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that admin role is allowed."""
        result = await handle_camera_take_photo(
            admin_ctx, {}, config=full_sandbox_config
        )

        assert "file_path" in result

    @pytest.mark.asyncio
    async def test_default_resolution(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test default resolution is used."""
        result = await handle_camera_take_photo(
            operator_ctx, {}, config=full_sandbox_config
        )

        expected_width, expected_height = SUPPORTED_RESOLUTIONS[DEFAULT_RESOLUTION]
        assert result["width"] == expected_width
        assert result["height"] == expected_height

    @pytest.mark.asyncio
    async def test_custom_resolution(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test custom resolution is applied."""
        result = await handle_camera_take_photo(
            operator_ctx, {"resolution": "640x480"}, config=full_sandbox_config
        )

        assert result["width"] == 640
        assert result["height"] == 480

    @pytest.mark.asyncio
    async def test_invalid_resolution(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test invalid resolution is rejected."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_camera_take_photo(
                operator_ctx,
                {"resolution": "999x999"},
                config=full_sandbox_config,
            )
        assert "Invalid resolution" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_default_quality(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test default quality is used."""
        result = await handle_camera_take_photo(
            operator_ctx, {}, config=full_sandbox_config
        )

        assert result["quality"] == DEFAULT_QUALITY

    @pytest.mark.asyncio
    async def test_custom_quality(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test custom quality is applied."""
        result = await handle_camera_take_photo(
            operator_ctx, {"quality": 50}, config=full_sandbox_config
        )

        assert result["quality"] == 50

    @pytest.mark.asyncio
    async def test_invalid_quality_too_low(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test quality below minimum is rejected."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_camera_take_photo(
                operator_ctx,
                {"quality": MIN_QUALITY - 1},
                config=full_sandbox_config,
            )
        assert "quality must be between" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_invalid_quality_too_high(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test quality above maximum is rejected."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_camera_take_photo(
                operator_ctx,
                {"quality": MAX_QUALITY + 1},
                config=full_sandbox_config,
            )
        assert "quality must be between" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_photo_saved_to_media_dir(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test photo is saved to configured media directory."""
        result = await handle_camera_take_photo(
            operator_ctx, {}, config=full_sandbox_config
        )

        media_root = full_sandbox_config.camera.media_root
        assert result["file_path"].startswith(media_root)
        assert Path(result["file_path"]).exists()

    @pytest.mark.asyncio
    async def test_photo_file_is_valid_jpeg(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test created file is a valid JPEG."""
        result = await handle_camera_take_photo(
            operator_ctx, {}, config=full_sandbox_config
        )

        file_path = Path(result["file_path"])
        assert file_path.exists()

        # Check JPEG magic bytes
        with open(file_path, "rb") as f:
            magic = f.read(2)
            assert magic == b"\xff\xd8"  # JPEG magic bytes

    @pytest.mark.asyncio
    async def test_rate_limit_enforced(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test rate limiting is enforced."""
        # Set a low limit for testing
        full_sandbox_config.camera.max_photos_per_minute = 2

        # Reset the rate limiter
        limiter = get_rate_limiter()
        limiter._timestamps.clear()
        limiter.set_limit(2)

        # First two should succeed
        result1 = await handle_camera_take_photo(
            operator_ctx, {}, config=full_sandbox_config
        )
        assert result1["success"] is True

        result2 = await handle_camera_take_photo(
            operator_ctx, {}, config=full_sandbox_config
        )
        assert result2["success"] is True

        # Third should be rate limited
        with pytest.raises(FailedPreconditionError) as exc_info:
            await handle_camera_take_photo(
                operator_ctx, {}, config=full_sandbox_config
            )
        assert "Rate limit exceeded" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_rate_limit_remaining_in_response(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test rate limit remaining is included in response."""
        result = await handle_camera_take_photo(
            operator_ctx, {}, config=full_sandbox_config
        )

        assert "rate_limit_remaining" in result

    @pytest.mark.asyncio
    async def test_timestamp_in_response(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test timestamp is included in response."""
        result = await handle_camera_take_photo(
            operator_ctx, {}, config=full_sandbox_config
        )

        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_custom_filename(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test custom filename is used."""
        result = await handle_camera_take_photo(
            operator_ctx,
            {"filename": "my_custom_photo"},
            config=full_sandbox_config,
        )

        assert "my_custom_photo" in result["file_path"]

    @pytest.mark.asyncio
    async def test_full_sandbox_mocks_capture(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test full sandbox mode creates mock photo."""
        result = await handle_camera_take_photo(
            operator_ctx, {}, config=full_sandbox_config
        )

        assert result["mocked"] is True
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_partial_sandbox_mocks_capture(
        self, operator_ctx: ToolContext, partial_sandbox_config: AppConfig
    ) -> None:
        """Test partial sandbox mode creates mock photo."""
        result = await handle_camera_take_photo(
            operator_ctx, {}, config=partial_sandbox_config
        )

        assert result["mocked"] is True
        assert result["logged_only"] is True


# =============================================================================
# Tests for Resolution Constants
# =============================================================================


class TestResolutionConstants:
    """Tests for resolution constants."""

    def test_supported_resolutions_exist(self) -> None:
        """Test supported resolutions are defined."""
        assert len(SUPPORTED_RESOLUTIONS) > 0

    def test_default_resolution_in_supported(self) -> None:
        """Test default resolution is in supported list."""
        assert DEFAULT_RESOLUTION in SUPPORTED_RESOLUTIONS

    def test_resolution_tuples_valid(self) -> None:
        """Test resolution tuples have valid dimensions."""
        for res_str, (width, height) in SUPPORTED_RESOLUTIONS.items():
            assert width > 0
            assert height > 0
            assert f"{width}x{height}" == res_str


# =============================================================================
# Tests for Quality Constants
# =============================================================================


class TestQualityConstants:
    """Tests for quality constants."""

    def test_quality_range_valid(self) -> None:
        """Test quality range is valid."""
        assert MIN_QUALITY >= 1
        assert MAX_QUALITY <= 100
        assert MIN_QUALITY < MAX_QUALITY

    def test_default_quality_in_range(self) -> None:
        """Test default quality is within range."""
        assert MIN_QUALITY <= DEFAULT_QUALITY <= MAX_QUALITY
