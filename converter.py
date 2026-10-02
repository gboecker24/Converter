"""Conversion backend for the video converter (video -> PDF, MP3, or image frames).

No UI code lives here, so the same functions can be reused by a website route
(see the WEBSITE INTEGRATION notes in the original mp4_to_pdf.py).

Install: python -m pip install opencv-python reportlab moviepy
"""

from __future__ import annotations

import io
import math
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, Optional

# progress(fraction) where fraction is 0..1, or None when the total is unknown
Progress = Callable[[Optional[float]], None]

VIDEO_EXTENSIONS = (".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm")

FORMATS = ("PDF", "MP3", "Images (JPG)", "Images (PNG)")
FRAME_FORMATS = ("PDF", "Images (JPG)", "Images (PNG)")  # formats that sample frames

QUALITY_LEVELS = ("Low", "Medium", "High")  # index 0, 1, 2 on the slider
MP3_BITRATES = ("96k", "192k", "320k")
# (longest side in pixels, JPEG quality) for each quality level
FRAME_PROFILES = ((1000, 60), (1600, 85), (2400, 95))

DEFAULT_INTERVAL = 10.0  # seconds between frames (same default as mp4_to_pdf.py)
MIN_INTERVAL, MAX_INTERVAL = 0.1, 3600.0
PDF_PAGE_OVERHEAD = 1200  # rough bytes of PDF structure per page, for estimates


# ----------------------------------------------------------------- helpers

def _cv2():
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency. Run: python -m pip install opencv-python"
        ) from exc
    return cv2


def human_size(num_bytes: float) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def format_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def expected_frames(duration: float, interval: float) -> int:
    """How many frames a sampling interval produces (frame at t=0, then every interval)."""
    if duration <= 0:
        return 1
    return max(1, math.ceil(duration / interval - 1e-9))


def check_interval(interval: float) -> None:
    if not math.isfinite(interval) or not MIN_INTERVAL <= interval <= MAX_INTERVAL:
        raise ValueError(
            f"Interval must be between {MIN_INTERVAL:g} and {MAX_INTERVAL:g} seconds."
        )


def _resize(frame, max_dim: int):
    cv2 = _cv2()
    height, width = frame.shape[:2]
    scale = min(1.0, max_dim / max(width, height))
    if scale < 1:
        frame = cv2.resize(
            frame,
            (max(1, round(width * scale)), max(1, round(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
    return frame


def _encode(frame, ext: str, jpeg_quality: int) -> bytes:
    cv2 = _cv2()
    if ext == ".png":
        success, encoded = cv2.imencode(".png", frame, [cv2.IMWRITE_PNG_COMPRESSION, 6])
    else:
        success, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
    if not success:
        raise RuntimeError("Unable to encode a sampled frame.")
    return encoded.tobytes()


def _sampled_frames(capture, fps: float, interval: float) -> Iterator[tuple[float, object]]:
    """Yield (timestamp, frame) roughly every `interval` seconds.

    Reads sequentially to avoid random seeks between keyframes and keeps only
    one decoded frame in memory at a time (same approach as mp4_to_pdf.py).
    """
    frame_index = 0
    next_sample = 0.0
    while capture.grab():
        timestamp = frame_index / fps
        frame_index += 1
        if timestamp + 1e-9 < next_sample:
            continue
        success, frame = capture.retrieve()
        if not success or frame is None:
            raise RuntimeError(f"Unable to decode frame {frame_index - 1}.")
        yield timestamp, frame
        next_sample = max(next_sample + interval, timestamp + interval)


def _open_capture(input_path: Path):
    cv2 = _cv2()
    input_path = Path(input_path).expanduser().resolve()
    if not input_path.is_file():
        raise ValueError(f"Input file does not exist: {input_path}")
    capture = cv2.VideoCapture(str(input_path))
    if not capture.isOpened():
        capture.release()
        raise RuntimeError(f"Unable to open the video: {input_path}")
    fps = capture.get(cv2.CAP_PROP_FPS)
    if not math.isfinite(fps) or fps <= 0:
        capture.release()
        raise RuntimeError("The video does not report a valid frame rate.")
    frame_count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
    duration = frame_count / fps if frame_count and frame_count > 0 else 0.0
    return input_path, capture, fps, duration


# -------------------------------------------------------------- video info

@dataclass
class VideoInfo:
    path: Path
    size_bytes: int
    duration: float  # seconds (0 if the container doesn't report it)
    fps: float
    width: int
    height: int
    sample_frame: object  # BGR frame from mid-video, used to estimate output sizes
    _frame_bytes: dict = field(default_factory=dict)


def probe_video(path) -> VideoInfo:
    cv2 = _cv2()
    path, capture, fps, duration = _open_capture(Path(path))
    try:
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        if total and total > 1:
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(total // 2))
        success, frame = capture.read()
        if not success or frame is None:
            capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            success, frame = capture.read()
        if not success or frame is None:
            raise RuntimeError("No readable frames were found in the video.")
    finally:
        capture.release()
    return VideoInfo(path, path.stat().st_size, duration, fps, width, height, frame)


def estimate_size(info: VideoInfo, fmt: str, level: int, interval: float = DEFAULT_INTERVAL) -> int:
    """Estimated output size in bytes for the chosen format and quality level."""
    if fmt == "MP3":
        bits_per_second = int(MP3_BITRATES[level][:-1]) * 1000
        return int(bits_per_second / 8 * info.duration)
    max_dim, jpeg_quality = FRAME_PROFILES[level]
    ext = ".png" if fmt == "Images (PNG)" else ".jpg"
    key = (ext, level)
    if key not in info._frame_bytes:
        info._frame_bytes[key] = len(_encode(_resize(info.sample_frame, max_dim), ext, jpeg_quality))
    per_frame = info._frame_bytes[key] + (PDF_PAGE_OVERHEAD if fmt == "PDF" else 0)
    return per_frame * expected_frames(info.duration, interval)


def output_size(path) -> int:
    path = Path(path)
    if path.is_dir():
        return sum(f.stat().st_size for f in path.iterdir() if f.is_file())
    return path.stat().st_size


# ------------------------------------------------------------------- PDF

def convert_video_to_pdf(
    input_path: Path,
    output_path: Path,
    interval: float = DEFAULT_INTERVAL,
    max_pages: int | None = None,
    overwrite: bool = False,
    max_dim: int = 1600,
    jpeg_quality: int = 85,
    progress: Progress | None = None,
) -> int:
    """Write sampled frames to a PDF (one per page) and return the page count."""
    try:
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependencies. Run: python -m pip install opencv-python reportlab"
        ) from exc

    output_path = Path(output_path).expanduser().resolve()
    if output_path.suffix.lower() != ".pdf":
        raise ValueError("The output filename must end in .pdf.")
    if Path(input_path).expanduser().resolve() == output_path:
        raise ValueError("Input and output must be different files.")
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output_path}. Use --overwrite.")
    check_interval(interval)
    if max_pages is not None and max_pages < 1:
        raise ValueError("Maximum pages must be at least 1.")

    input_path, capture, fps, duration = _open_capture(input_path)
    total = expected_frames(duration, interval)
    if max_pages is not None:
        total = min(total, max_pages)
    temporary_path = None
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            suffix=".pdf", dir=output_path.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)

        pdf = canvas.Canvas(str(temporary_path))
        pdf.setTitle(f"Video frames: {input_path.name}")
        pages = 0
        for timestamp, frame in _sampled_frames(capture, fps, interval):
            frame = _resize(frame, max_dim)
            height, width = frame.shape[:2]
            encoded = _encode(frame, ".jpg", jpeg_quality)

            page_width, page_height = (842, 595) if width >= height else (595, 842)
            margin = 24
            footer = 24
            image_scale = min(
                (page_width - 2 * margin) / width,
                (page_height - 2 * margin - footer) / height,
            )
            draw_width = width * image_scale
            draw_height = height * image_scale
            pdf.setPageSize((page_width, page_height))
            pdf.drawImage(
                ImageReader(io.BytesIO(encoded)),
                (page_width - draw_width) / 2,
                margin + footer + (page_height - 2 * margin - footer - draw_height) / 2,
                width=draw_width,
                height=draw_height,
            )
            hours = int(timestamp // 3600)
            minutes = int(timestamp % 3600 // 60)
            seconds = timestamp % 60
            pdf.setFont("Helvetica", 10)
            pdf.drawCentredString(
                page_width / 2,
                margin,
                f"Page {pages + 1} | Approx. time {hours:02d}:{minutes:02d}:{seconds:05.2f}",
            )
            pdf.showPage()
            pages += 1
            if progress:
                progress(min(1.0, pages / total))
            if max_pages is not None and pages >= max_pages:
                break

        if pages == 0:
            raise RuntimeError("No readable frames were found in the video.")
        pdf.save()
        if overwrite:
            os.replace(temporary_path, output_path)
        else:
            # Exclusive creation protects a file created during conversion
            with output_path.open("xb") as destination:
                with temporary_path.open("rb") as source:
                    shutil.copyfileobj(source, destination)
        return pages
    finally:
        capture.release()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


# ---------------------------------------------------------------- images

def convert_video_to_images(
    input_path: Path,
    output_dir: Path,
    interval: float = DEFAULT_INTERVAL,
    ext: str = ".jpg",
    max_dim: int = 1600,
    jpeg_quality: int = 85,
    progress: Progress | None = None,
) -> tuple[Path, int]:
    """Save sampled frames into a new folder inside output_dir.

    Returns (folder, number_of_images).
    """
    check_interval(interval)
    ext = ".png" if ext.lower() == ".png" else ".jpg"
    input_path, capture, fps, duration = _open_capture(input_path)
    total = expected_frames(duration, interval)
    try:
        base = Path(output_dir).expanduser().resolve() / f"{input_path.stem}_frames"
        folder, counter = base, 2
        while folder.exists():  # never write into (or overwrite) an existing folder
            folder = base.with_name(f"{base.name}_{counter}")
            counter += 1
        folder.mkdir(parents=True)

        count = 0
        for timestamp, frame in _sampled_frames(capture, fps, interval):
            data = _encode(_resize(frame, max_dim), ext, jpeg_quality)
            hours, rest = divmod(int(timestamp), 3600)
            minutes, seconds = divmod(rest, 60)
            name = f"{input_path.stem}_{count + 1:04d}_{hours:02d}h{minutes:02d}m{seconds:02d}s{ext}"
            (folder / name).write_bytes(data)  # write_bytes handles non-ASCII paths on Windows
            count += 1
            if progress:
                progress(min(1.0, count / total))
        if count == 0:
            shutil.rmtree(folder, ignore_errors=True)
            raise RuntimeError("No readable frames were found in the video.")
        return folder, count
    finally:
        capture.release()


# ------------------------------------------------------------------- MP3

def convert_video_to_mp3(
    input_path: Path,
    output_path: Path,
    bitrate: str = "192k",
    progress: Progress | None = None,
) -> None:
    """Rip the audio track of a video to an MP3 (moviepy, as in MP4toMP3.py)."""
    try:
        from moviepy import VideoFileClip  # needed to open the video and access its audio
    except ImportError as exc:
        raise RuntimeError("Missing dependency. Run: python -m pip install moviepy") from exc

    input_path = Path(input_path).expanduser().resolve()
    output_path = Path(output_path).expanduser().resolve()
    if not input_path.is_file():
        raise ValueError(f"Input file does not exist: {input_path}")
    if output_path.suffix.lower() != ".mp3":
        raise ValueError("The output filename must end in .mp3.")
    if progress:
        progress(None)  # moviepy doesn't report progress, so the UI shows a busy bar

    clip = VideoFileClip(str(input_path))
    try:
        if clip.audio is None:
            raise RuntimeError("This video has no audio track to convert.")
        # logger=None stops moviepy from printing to the terminal
        clip.audio.write_audiofile(str(output_path), bitrate=bitrate, logger=None)
    finally:
        clip.close()