"""
Camera namespace tools for the Raspberry Pi MCP Server.

This module implements tools in the `camera.*` namespace:
- camera.get_info: Detect camera and return capabilities
- camera.take_photo: Capture JPEG with resolution/quality parameters

Design follows Doc 05 §7 (camera namespace) and Doc 08 §6 (Camera).

Features:
- Camera detection using picamera2 (with graceful fallback)
- JPEG capture with configurable resolution and quality
- Rate limiting (max photos per minute)
- Photos saved to configured media directory
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any

from mcp_raspi.constants import MINIMAL_JPEG_BYTES
from mcp_raspi.context import ToolContext
from mcp_raspi.errors import (
    FailedPreconditionError,
    InvalidArgumentError,
)
from mcp_raspi.logging import get_logger
from mcp_raspi.security.audit_logger import get_audit_logger
from mcp_raspi.security.rbac import require_role

if TYPE_CHECKING:
    from mcp_raspi.config import AppConfig

logger = get_logger(__name__)

# =============================================================================
# Constants
# =============================================================================

# Supported resolutions
SUPPORTED_RESOLUTIONS = {
    "640x480": (640, 480),
    "1280x720": (1280, 720),
    "1920x1080": (1920, 1080),
}
DEFAULT_RESOLUTION = "1280x720"

# Quality constraints
MIN_QUALITY = 1
MAX_QUALITY = 100
DEFAULT_QUALITY = 85

# Rate limiting defaults
DEFAULT_MAX_PHOTOS_PER_MINUTE = 10

# Default media directory
DEFAULT_MEDIA_ROOT = "/var/lib/mcp-raspi/media"


# =============================================================================
# Rate Limiting
# =============================================================================


class PhotoRateLimiter:
    """
    Rate limiter for photo captures.

    Tracks capture timestamps and enforces max photos per minute limit.
    Thread-safe implementation.
    """

    def __init__(self, max_per_minute: int = DEFAULT_MAX_PHOTOS_PER_MINUTE) -> None:
        """
        Initialize the rate limiter.

        Args:
            max_per_minute: Maximum photos allowed per minute.
        """
        self._max_per_minute = max_per_minute
        self._timestamps: list[float] = []
        self._lock = Lock()

    def set_limit(self, max_per_minute: int) -> None:
        """Update the rate limit."""
        with self._lock:
            self._max_per_minute = max_per_minute

    def check_and_record(self) -> tuple[bool, float | None]:
        """
        Check if a capture is allowed and record it.

        Returns:
            Tuple of (is_allowed, retry_after_seconds).
            If not allowed, retry_after_seconds indicates when to retry.
        """
        with self._lock:
            now = time.time()
            cutoff = now - 60.0  # One minute window

            # Remove old timestamps
            self._timestamps = [ts for ts in self._timestamps if ts > cutoff]

            # Check limit
            if len(self._timestamps) >= self._max_per_minute:
                # Calculate when oldest capture will expire
                oldest = min(self._timestamps)
                retry_after = oldest + 60.0 - now
                return False, max(retry_after, 0.1)

            # Record this capture
            self._timestamps.append(now)
            return True, None

    def get_remaining(self) -> int:
        """Get remaining captures allowed in the current window."""
        with self._lock:
            now = time.time()
            cutoff = now - 60.0
            self._timestamps = [ts for ts in self._timestamps if ts > cutoff]
            return max(0, self._max_per_minute - len(self._timestamps))


# Global rate limiter instance
_rate_limiter = PhotoRateLimiter()


def get_rate_limiter() -> PhotoRateLimiter:
    """Get the global photo rate limiter."""
    return _rate_limiter


# =============================================================================
# Camera Detection
# =============================================================================


def _detect_camera() -> dict[str, Any]:
    """
    Detect available camera and return its capabilities.

    Attempts to use picamera2 for detection, falls back to other methods.

    Returns:
        Dictionary with camera info or {"detected": False}.
    """
    # Try picamera2 first (Raspberry Pi camera)
    try:
        from picamera2 import Picamera2

        # Get camera info without starting it
        cameras = Picamera2.global_camera_info()

        if not cameras:
            return {"detected": False, "reason": "No cameras found"}

        # Use the first camera
        camera_info = cameras[0]
        model = camera_info.get("Model", "Unknown")

        # Get supported resolutions
        resolutions = list(SUPPORTED_RESOLUTIONS.keys())

        return {
            "detected": True,
            "model": model,
            "num_cameras": len(cameras),
            "resolutions": resolutions,
            "formats": ["jpeg", "png"],
            "backend": "picamera2",
        }

    except ImportError:
        logger.debug("picamera2 not available")
    except Exception as e:
        logger.debug(f"picamera2 detection failed: {e}")

    # Try v4l2 device detection as fallback
    try:
        v4l2_devices = list(Path("/dev").glob("video*"))
        if v4l2_devices:
            return {
                "detected": True,
                "model": "V4L2 Camera",
                "num_cameras": len(v4l2_devices),
                "resolutions": list(SUPPORTED_RESOLUTIONS.keys()),
                "formats": ["jpeg"],
                "backend": "v4l2",
                "devices": [str(d) for d in v4l2_devices[:4]],
            }
    except Exception as e:
        logger.debug(f"V4L2 detection failed: {e}")

    return {"detected": False, "reason": "No camera detected"}


# =============================================================================
# Photo Capture
# =============================================================================


def _capture_photo_picamera2(
    width: int,
    height: int,
    quality: int,
    output_path: Path,
) -> dict[str, Any]:
    """
    Capture a photo using picamera2.

    Args:
        width: Image width in pixels.
        height: Image height in pixels.
        quality: JPEG quality (1-100).
        output_path: Path to save the image.

    Returns:
        Dictionary with capture result.

    Raises:
        FailedPreconditionError: If capture fails.
    """
    try:
        from picamera2 import Picamera2

        # Create camera instance
        picam2 = Picamera2()

        try:
            # Configure for still capture
            config = picam2.create_still_configuration(
                main={"size": (width, height), "format": "RGB888"}
            )
            picam2.configure(config)

            # Start camera
            picam2.start()

            # Capture to file
            picam2.capture_file(str(output_path), format="jpeg")

            # Get file size
            file_size = output_path.stat().st_size

            return {
                "success": True,
                "file_path": str(output_path),
                "file_size_bytes": file_size,
                "width": width,
                "height": height,
                "quality": quality,
            }

        finally:
            picam2.stop()
            picam2.close()

    except ImportError as e:
        raise FailedPreconditionError(
            "picamera2 library not available",
            details={"error": str(e)},
        ) from e
    except Exception as e:
        raise FailedPreconditionError(
            f"Failed to capture photo: {e}",
            details={"error": str(e), "width": width, "height": height},
        ) from e


def _capture_photo_mock(
    width: int,
    height: int,
    quality: int,
    output_path: Path,
) -> dict[str, Any]:
    """
    Create a mock photo capture result for testing/sandbox mode.

    Args:
        width: Image width in pixels.
        height: Image height in pixels.
        quality: JPEG quality (1-100).
        output_path: Path where image would be saved.

    Returns:
        Dictionary with mock capture result.
    """
    # Create parent directory if it doesn't exist
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Use the shared minimal JPEG constant for testing
    with open(output_path, "wb") as f:
        f.write(MINIMAL_JPEG_BYTES)

    return {
        "success": True,
        "file_path": str(output_path),
        "file_size_bytes": len(MINIMAL_JPEG_BYTES),
        "width": width,
        "height": height,
        "quality": quality,
        "mocked": True,
    }


# =============================================================================
# Validation Helpers
# =============================================================================


def _validate_resolution(resolution: Any) -> tuple[int, int]:
    """
    Validate and parse resolution parameter.

    Args:
        resolution: Resolution string (e.g., "1280x720").

    Returns:
        Tuple of (width, height).

    Raises:
        InvalidArgumentError: If resolution is invalid.
    """
    if resolution is None:
        return SUPPORTED_RESOLUTIONS[DEFAULT_RESOLUTION]

    res_str = str(resolution)
    if res_str not in SUPPORTED_RESOLUTIONS:
        raise InvalidArgumentError(
            f"Invalid resolution: {resolution}. Must be one of: {', '.join(SUPPORTED_RESOLUTIONS.keys())}",
            details={
                "parameter": "resolution",
                "value": resolution,
                "valid_values": list(SUPPORTED_RESOLUTIONS.keys()),
            },
        )

    return SUPPORTED_RESOLUTIONS[res_str]


def _validate_quality(quality: Any) -> int:
    """
    Validate quality parameter.

    Args:
        quality: JPEG quality (1-100).

    Returns:
        Validated quality as integer.

    Raises:
        InvalidArgumentError: If quality is invalid.
    """
    if quality is None:
        return DEFAULT_QUALITY

    if not isinstance(quality, int):
        try:
            quality = int(quality)
        except (ValueError, TypeError) as e:
            raise InvalidArgumentError(
                f"Invalid quality: {quality}",
                details={"parameter": "quality", "value": quality},
            ) from e

    if quality < MIN_QUALITY or quality > MAX_QUALITY:
        raise InvalidArgumentError(
            f"quality must be between {MIN_QUALITY} and {MAX_QUALITY}",
            details={
                "parameter": "quality",
                "value": quality,
                "min": MIN_QUALITY,
                "max": MAX_QUALITY,
            },
        )

    return quality


def _get_media_root(config: AppConfig | None) -> str:
    """Get media root directory from configuration."""
    if config is None:
        return DEFAULT_MEDIA_ROOT
    return config.camera.media_root


def _get_max_photos_per_minute(config: AppConfig | None) -> int:
    """Get max photos per minute from configuration."""
    if config is None:
        return DEFAULT_MAX_PHOTOS_PER_MINUTE
    return config.camera.max_photos_per_minute


def _get_sandbox_mode(config: AppConfig | None) -> str:
    """Get sandbox mode from configuration."""
    if config is None:
        return "partial"
    return config.testing.sandbox_mode


# =============================================================================
# camera.get_info
# =============================================================================


@require_role("viewer")
async def handle_camera_get_info(
    ctx: ToolContext,
    _params: dict[str, Any],
    *,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    """
    Handle the camera.get_info tool call.

    Detects available camera and returns its capabilities.

    Args:
        ctx: The ToolContext for this request.
        _params: Request parameters (none required).
        config: Optional AppConfig for settings.

    Returns:
        Dictionary with:
        - detected: Boolean indicating if camera is present
        - model: Camera model if detected
        - resolutions: Supported resolutions
        - formats: Supported image formats
        - rate_limit: Current rate limit settings

    Raises:
        PermissionDeniedError: If caller lacks viewer role.
    """
    audit = get_audit_logger()
    audit.log_tool_call(ctx=ctx, status="initiated", params={})

    logger.info(
        "camera.get_info requested",
        extra={"user": ctx.caller.user_id},
    )

    sandbox_mode = _get_sandbox_mode(config)
    max_photos = _get_max_photos_per_minute(config)
    media_root = _get_media_root(config)

    # Update rate limiter with config
    _rate_limiter.set_limit(max_photos)

    # Get camera info
    if sandbox_mode == "full":
        # Mock camera info in full sandbox mode
        camera_info = {
            "detected": True,
            "model": "Mock Camera (sandbox mode)",
            "num_cameras": 1,
            "resolutions": list(SUPPORTED_RESOLUTIONS.keys()),
            "formats": ["jpeg", "png"],
            "backend": "mock",
            "mocked": True,
        }
    else:
        camera_info = _detect_camera()

    return {
        **camera_info,
        "rate_limit": {
            "max_per_minute": max_photos,
            "remaining": _rate_limiter.get_remaining(),
        },
        "media_root": media_root,
        "timestamp": datetime.now(UTC).isoformat(),
    }


# =============================================================================
# camera.take_photo
# =============================================================================


@require_role("operator")
async def handle_camera_take_photo(
    ctx: ToolContext,
    params: dict[str, Any],
    *,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    """
    Handle the camera.take_photo tool call.

    Captures a photo using the camera and saves it to the media directory.

    Args:
        ctx: The ToolContext for this request.
        params: Request parameters:
            - resolution: Resolution string (e.g., "1280x720")
            - quality: JPEG quality (1-100)
            - filename: Optional custom filename
        config: Optional AppConfig for settings.

    Returns:
        Dictionary with:
        - file_path: Path to the saved image
        - file_size_bytes: Size of the image file
        - width: Image width
        - height: Image height
        - quality: JPEG quality used
        - timestamp: Capture timestamp

    Raises:
        PermissionDeniedError: If caller lacks operator role.
        InvalidArgumentError: If parameters are invalid.
        FailedPreconditionError: If camera is not available or rate limited.
    """
    # Validate parameters
    width, height = _validate_resolution(params.get("resolution"))
    quality = _validate_quality(params.get("quality"))
    custom_filename = params.get("filename")

    # Get configuration
    sandbox_mode = _get_sandbox_mode(config)
    max_photos = _get_max_photos_per_minute(config)
    media_root = _get_media_root(config)

    # Update rate limiter
    _rate_limiter.set_limit(max_photos)

    audit = get_audit_logger()
    audit.log_tool_call(
        ctx=ctx,
        status="initiated",
        params={
            "resolution": f"{width}x{height}",
            "quality": quality,
        },
    )

    logger.info(
        "camera.take_photo requested",
        extra={
            "user": ctx.caller.user_id,
            "width": width,
            "height": height,
            "quality": quality,
            "sandbox_mode": sandbox_mode,
        },
    )

    # Check rate limit
    allowed, retry_after = _rate_limiter.check_and_record()
    if not allowed:
        raise FailedPreconditionError(
            f"Rate limit exceeded. Max {max_photos} photos per minute.",
            details={
                "max_per_minute": max_photos,
                "retry_after_seconds": round(retry_after, 1) if retry_after else None,
            },
        )

    # Generate filename
    timestamp = datetime.now(UTC)
    if custom_filename:
        # Sanitize custom filename
        safe_filename = "".join(
            c for c in custom_filename if c.isalnum() or c in "._-"
        )
        if not safe_filename.lower().endswith(".jpg"):
            safe_filename += ".jpg"
    else:
        safe_filename = f"photo_{timestamp.strftime('%Y%m%d_%H%M%S')}.jpg"

    # Build output path
    output_dir = Path(media_root) / "photos" / timestamp.strftime("%Y-%m-%d")
    output_path = output_dir / safe_filename

    # Handle based on sandbox mode
    if sandbox_mode == "full":
        logger.info("Sandbox mode 'full': Creating mock photo")
        result = _capture_photo_mock(width, height, quality, output_path)
    elif sandbox_mode == "partial":
        logger.warning("Sandbox mode 'partial': Logging photo request (not executing)")
        # Create mock file for testing but mark as logged_only
        result = _capture_photo_mock(width, height, quality, output_path)
        result["logged_only"] = True
        result["mocked"] = True
    else:
        # Check camera availability first
        camera_info = _detect_camera()
        if not camera_info.get("detected"):
            raise FailedPreconditionError(
                "No camera detected",
                details={"camera_info": camera_info},
            )

        # Capture based on backend
        backend = camera_info.get("backend", "picamera2")
        if backend == "picamera2":
            result = _capture_photo_picamera2(width, height, quality, output_path)
        else:
            # V4L2 or other - use mock for now
            result = _capture_photo_mock(width, height, quality, output_path)
            result["backend"] = backend

    return {
        **result,
        "timestamp": timestamp.isoformat(),
        "rate_limit_remaining": _rate_limiter.get_remaining(),
    }
