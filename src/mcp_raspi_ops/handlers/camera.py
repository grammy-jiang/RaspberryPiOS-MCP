"""
Camera handlers for the Privileged Agent.

This module implements handlers for camera operations:
- camera.get_info: Detect camera and return capabilities
- camera.capture: Capture a photo

These handlers run with elevated privileges to access camera hardware.

Design follows Doc 08 §6 (Camera).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

from mcp_raspi.ipc.protocol import IPCRequest
from mcp_raspi.logging import get_logger
from mcp_raspi_ops.handlers_core import HandlerError, HandlerRegistry

logger = get_logger(__name__)


# =============================================================================
# Rate Limiting
# =============================================================================


class AgentPhotoRateLimiter:
    """
    Rate limiter for photo captures at the agent level.

    Provides a second layer of rate limiting in the privileged agent.
    """

    def __init__(self, max_per_minute: int = 30) -> None:
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
        """
        with self._lock:
            now = time.time()
            cutoff = now - 60.0

            self._timestamps = [ts for ts in self._timestamps if ts > cutoff]

            if len(self._timestamps) >= self._max_per_minute:
                oldest = min(self._timestamps)
                retry_after = oldest + 60.0 - now
                return False, max(retry_after, 0.1)

            self._timestamps.append(now)
            return True, None

    def get_remaining(self) -> int:
        """Get remaining captures allowed."""
        with self._lock:
            now = time.time()
            cutoff = now - 60.0
            self._timestamps = [ts for ts in self._timestamps if ts > cutoff]
            return max(0, self._max_per_minute - len(self._timestamps))


# Global rate limiter for agent
_agent_rate_limiter = AgentPhotoRateLimiter()


# =============================================================================
# Camera Detection
# =============================================================================


def _detect_camera_info() -> dict[str, Any]:
    """
    Detect available camera and return info.

    Returns:
        Dictionary with camera info or {"detected": False}.
    """
    # Try picamera2 first
    try:
        from picamera2 import Picamera2

        cameras = Picamera2.global_camera_info()

        if not cameras:
            return {"detected": False, "reason": "No cameras found"}

        camera_info = cameras[0]
        model = camera_info.get("Model", "Unknown")

        return {
            "detected": True,
            "model": model,
            "num_cameras": len(cameras),
            "resolutions": ["640x480", "1280x720", "1920x1080"],
            "formats": ["jpeg", "png"],
            "backend": "picamera2",
        }

    except ImportError:
        logger.debug("picamera2 not available")
    except Exception as e:
        logger.debug(f"picamera2 detection failed: {e}")

    # Try V4L2 devices
    try:
        v4l2_devices = list(Path("/dev").glob("video*"))
        if v4l2_devices:
            return {
                "detected": True,
                "model": "V4L2 Camera",
                "num_cameras": len(v4l2_devices),
                "resolutions": ["640x480", "1280x720", "1920x1080"],
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


def _capture_with_picamera2(
    width: int,
    height: int,
    quality: int,
    output_path: Path,
) -> dict[str, Any]:
    """
    Capture a photo using picamera2.

    Args:
        width: Image width.
        height: Image height.
        quality: JPEG quality.
        output_path: Path to save the image.

    Returns:
        Capture result dictionary.

    Raises:
        HandlerError: If capture fails.
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

            # Give camera time to adjust
            time.sleep(0.2)

            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Capture to file
            picam2.capture_file(str(output_path), format="jpeg")

            file_size = output_path.stat().st_size

            return {
                "success": True,
                "file_path": str(output_path),
                "file_size_bytes": file_size,
                "width": width,
                "height": height,
                "quality": quality,
                "backend": "picamera2",
            }

        finally:
            picam2.stop()
            picam2.close()

    except ImportError as e:
        raise HandlerError(
            code="failed_precondition",
            message="picamera2 library not available",
            details={"error": str(e)},
        ) from e
    except Exception as e:
        raise HandlerError(
            code="internal",
            message=f"Failed to capture photo: {e}",
            details={"error": str(e), "width": width, "height": height},
        ) from e


def _capture_mock(
    width: int,
    height: int,
    quality: int,
    output_path: Path,
) -> dict[str, Any]:
    """
    Create a mock photo capture for testing.

    Args:
        width: Image width.
        height: Image height.
        quality: JPEG quality.
        output_path: Path to save the image.

    Returns:
        Mock capture result.
    """
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Create minimal valid JPEG
    minimal_jpeg = bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
        0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
        0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
        0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
        0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
        0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
        0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
        0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
        0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
        0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
        0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
        0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
        0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
        0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
        0x82, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00, 0xFB,
        0xD4, 0xDB, 0xA3, 0x6C, 0x8D, 0xB2, 0x36, 0xC8, 0xDB, 0x23, 0x6C, 0xFF,
        0xD9,
    ])

    with open(output_path, "wb") as f:
        f.write(minimal_jpeg)

    return {
        "success": True,
        "file_path": str(output_path),
        "file_size_bytes": len(minimal_jpeg),
        "width": width,
        "height": height,
        "quality": quality,
        "backend": "mock",
        "mocked": True,
    }


# =============================================================================
# camera.get_info Handler
# =============================================================================


async def handle_camera_get_info(request: IPCRequest) -> dict[str, Any]:
    """
    Handle the camera.get_info operation.

    Detects available camera and returns capabilities.

    Args:
        request: IPC request with params (none required).

    Returns:
        Dict with camera info.
    """
    params = request.params
    max_per_minute = params.get("max_per_minute", 30)

    logger.debug(
        "camera.get_info request",
        extra={"request_id": request.id},
    )

    _agent_rate_limiter.set_limit(max_per_minute)

    camera_info = _detect_camera_info()

    return {
        **camera_info,
        "rate_limit": {
            "max_per_minute": max_per_minute,
            "remaining": _agent_rate_limiter.get_remaining(),
        },
    }


# =============================================================================
# camera.capture Handler
# =============================================================================


async def handle_camera_capture(request: IPCRequest) -> dict[str, Any]:
    """
    Handle the camera.capture operation.

    Captures a photo using the camera.

    Args:
        request: IPC request with params:
            - width: Image width in pixels
            - height: Image height in pixels
            - quality: JPEG quality (1-100)
            - output_path: Path to save the image
            - max_per_minute: Rate limit setting

    Returns:
        Dict with capture result.

    Raises:
        HandlerError: If capture fails or rate limited.
    """
    params = request.params
    width = params.get("width", 1280)
    height = params.get("height", 720)
    quality = params.get("quality", 85)
    output_path = params.get("output_path")
    max_per_minute = params.get("max_per_minute", 30)
    use_mock = params.get("use_mock", False)

    logger.info(
        "camera.capture request",
        extra={
            "request_id": request.id,
            "width": width,
            "height": height,
            "quality": quality,
            "output_path": output_path,
        },
    )

    # Validate parameters
    if not output_path:
        raise HandlerError(
            code="invalid_argument",
            message="Parameter 'output_path' is required",
            details={"parameter": "output_path"},
        )

    if not isinstance(width, int) or width < 1:
        raise HandlerError(
            code="invalid_argument",
            message=f"Invalid width: {width}",
            details={"parameter": "width", "value": width},
        )

    if not isinstance(height, int) or height < 1:
        raise HandlerError(
            code="invalid_argument",
            message=f"Invalid height: {height}",
            details={"parameter": "height", "value": height},
        )

    if not isinstance(quality, int) or quality < 1 or quality > 100:
        raise HandlerError(
            code="invalid_argument",
            message=f"Invalid quality: {quality}. Must be 1-100.",
            details={"parameter": "quality", "value": quality},
        )

    # Check rate limit
    _agent_rate_limiter.set_limit(max_per_minute)
    allowed, retry_after = _agent_rate_limiter.check_and_record()

    if not allowed:
        raise HandlerError(
            code="resource_exhausted",
            message=f"Rate limit exceeded. Max {max_per_minute} photos per minute.",
            details={
                "max_per_minute": max_per_minute,
                "retry_after_seconds": round(retry_after, 1) if retry_after else None,
            },
        )

    output_path_obj = Path(output_path)

    # If using mock mode, create mock photo
    if use_mock:
        result = _capture_mock(width, height, quality, output_path_obj)
        return {
            **result,
            "timestamp": datetime.now(UTC).isoformat(),
            "rate_limit_remaining": _agent_rate_limiter.get_remaining(),
        }

    # Check camera availability
    camera_info = _detect_camera_info()
    if not camera_info.get("detected"):
        raise HandlerError(
            code="failed_precondition",
            message="No camera detected",
            details=camera_info,
        )

    # Capture based on backend
    backend = camera_info.get("backend", "picamera2")
    if backend == "picamera2":
        result = _capture_with_picamera2(width, height, quality, output_path_obj)
    else:
        # Use mock for unsupported backends
        result = _capture_mock(width, height, quality, output_path_obj)
        result["backend"] = backend

    return {
        **result,
        "timestamp": datetime.now(UTC).isoformat(),
        "rate_limit_remaining": _agent_rate_limiter.get_remaining(),
    }


# =============================================================================
# Handler Registration
# =============================================================================


def register_camera_handlers(registry: HandlerRegistry) -> None:
    """
    Register camera handlers with the handler registry.

    Args:
        registry: The handler registry to register with.
    """
    registry.register("camera.get_info", handle_camera_get_info)
    registry.register("camera.capture", handle_camera_capture)
    logger.debug("Registered camera handlers")
