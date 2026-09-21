# The default interval for mp4->pdf conversion is 10 seconds

from __future__ import annotations

import argparse
import io
import math
import os
from pathlib import Path
import sys
import tempfile


def convert_video_to_pdf(
    input_path: Path,
    output_path: Path,
    interval: float = 10.0,
    max_pages: int | None = None,
    overwrite: bool = False,
) -> int:
    # Write sampled frames to a PDF and return the number of pages created
    try:
        import cv2
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependencies. Run: "
            "python -m pip install opencv-python reportlab"
        ) from exc

    input_path = Path(input_path).expanduser().resolve()
    output_path = Path(output_path).expanduser().resolve()
    if not input_path.is_file():
        raise ValueError(f"Input file does not exist: {input_path}")
    if output_path.suffix.lower() != ".pdf":
        raise ValueError("The output filename must end in .pdf.")
    if input_path == output_path:
        raise ValueError("Input and output must be different files.")
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output_path}. Use --overwrite.")
    if not math.isfinite(interval) or interval <= 0:
        raise ValueError("Interval must be a finite number greater than zero.")
    if max_pages is not None and max_pages < 1:
        raise ValueError("Maximum pages must be at least 1.")

    capture = cv2.VideoCapture(str(input_path))
    temporary_path = None
    try:
        if not capture.isOpened():
            raise RuntimeError(f"Unable to open the video: {input_path}")
        fps = capture.get(cv2.CAP_PROP_FPS)
        if not math.isfinite(fps) or fps <= 0:
            raise RuntimeError("The video does not report a valid frame rate.")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            suffix=".pdf", dir=output_path.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)

        pdf = canvas.Canvas(str(temporary_path))
        pdf.setTitle(f"Video frames: {input_path.name}")
        pages = 0
        frame_index = 0
        next_sample = 0.0

        # Read sequentially to avoid random seeks between keyframes
        # Keep only one decoded frame in memory at a time
        while capture.grab():
            timestamp = frame_index / fps
            frame_index += 1
            if timestamp + 1e-9 < next_sample:
                continue
            success, frame = capture.retrieve()
            if not success or frame is None:
                raise RuntimeError(f"Unable to decode frame {frame_index - 1}.")

            height, width = frame.shape[:2]
            # Cap the image size to keep the resulting PDF manageable
            scale = min(1.0, 1600 / max(width, height))
            if scale < 1:
                frame = cv2.resize(
                    frame,
                    (max(1, round(width * scale)), max(1, round(height * scale))),
                    interpolation=cv2.INTER_AREA,
                )
            success, encoded = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85]
            )
            if not success:
                raise RuntimeError("Unable to encode a sampled frame.")

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
                ImageReader(io.BytesIO(encoded.tobytes())),
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
            print(f"Added page {pages} at {timestamp:.2f} seconds", flush=True)
            if max_pages is not None and pages >= max_pages:
                break
            # If the interval is smaller than a frame, sample each frame once
            next_sample = max(next_sample + interval, timestamp + interval)

        if pages == 0:
            raise RuntimeError("No readable frames were found in the video.")
        pdf.save()
        if overwrite:
            os.replace(temporary_path, output_path)
        else:
            # Exclusive creation protects a file created during conversion
            import shutil

            with output_path.open("xb") as destination:
                with temporary_path.open("rb") as source:
                    shutil.copyfileobj(source, destination)
        return pages
    finally:
        capture.release()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="Path to the MP4 video")
    parser.add_argument("output", type=Path, nargs="?", help="Output PDF (default: video filename with .pdf)")
    parser.add_argument("--interval", type=float, default=10.0, help="Seconds between sampled frames (default: 10)")
    parser.add_argument("--max-pages", type=int, help="Optional limit on PDF pages")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing output PDF")
    args = parser.parse_args()
    output_path = args.output or args.input.with_suffix(".pdf")
    try:
        pages = convert_video_to_pdf(args.input, output_path, args.interval, args.max_pages, args.overwrite)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nConversion cancelled.", file=sys.stderr)
        return 130
    print(f"Created {output_path.resolve()} ({pages} pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())