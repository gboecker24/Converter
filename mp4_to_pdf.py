"""MP4 to PDF with a local webpage demo.

Install: python -m pip install flask opencv-python reportlab
Web demo: python mp4_to_pdf.py
Open: http://127.0.0.1:8765
CLI: python mp4_to_pdf.py video.mp4 result.pdf --interval 5

Search for WEBSITE INSERTION AREA to customize the webpage.
"""

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

# ============================================================================
# WEBSITE INSERTION AREA — START
# ============================================================================
# Replace the HTML below with your own website layout, navigation, or branding.
# For an existing Flask website, move this HTML to a template and register the
# /convert route below on that application. Keep the form names "video",
# "interval", and "max_pages". The endpoint returns a downloadable PDF.
# Keep the frontend and endpoint on the same origin; change the form action if
# the endpoint lives at another path. A static HTML host cannot run Python.
#
# Insert your future website integration notes here:
#
#
#
# ============================================================================

PAGE_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Framebook · MP4 to PDF</title>
  <style>
    :root { color-scheme: light; --ink: #253629; --muted: #59675d; --green: #245b40; }
    * { box-sizing: border-box; }
    body { margin: 0; background: #f5f3ed; color: var(--ink); font-family: system-ui, sans-serif; }
    header { max-width: 1100px; margin: auto; padding: 28px 32px; display: flex; justify-content: space-between; border-bottom: 1px solid #d8dcd2; }
    .brand { font-weight: 750; letter-spacing: -.6px; font-size: 22px; }
    .tag { font-size: 13px; color: var(--muted); align-self: center; }
    main { max-width: 1100px; margin: 0 auto; padding: 64px 32px 40px; display: grid; grid-template-columns: 1fr 1fr; gap: 68px; align-items: start; }
    .eyebrow { text-transform: uppercase; letter-spacing: 2px; font-size: 12px; font-weight: 700; color: var(--green); }
    h1 { font-family: Georgia, serif; font-weight: 400; font-size: clamp(40px, 5vw, 62px); line-height: 1.07; letter-spacing: -2px; margin: 20px 0 24px; }
    .intro { line-height: 1.7; color: var(--muted); max-width: 390px; font-size: 16px; }
    .steps { padding: 22px 0 0; list-style: none; counter-reset: step; }
    .steps li { border-top: 1px solid #d8dcd2; padding: 16px 0; font-size: 14px; counter-increment: step; }
    .steps li::before { content: "0" counter(step); color: var(--green); margin-right: 18px; font-size: 12px; }
    form { background: #fffefb; border: 1px solid #d8dcd2; padding: 28px; }
    h2 { margin: 0 0 24px; font-size: 21px; letter-spacing: -.5px; }
    label { display: block; font-size: 14px; font-weight: 650; margin-bottom: 8px; }
    .upload { padding: 24px 18px; border: 1px dashed #94aa97; background: #f1f5ee; }
    input[type=file] { max-width: 100%; font: inherit; font-size: 13px; }
    input::file-selector-button { padding: 10px 12px; background: #fff; border: 1px solid #a8b5a7; border-radius: 4px; margin: 8px 10px 8px 0; cursor: pointer; }
    .hint { color: var(--muted); font-size: 12px; line-height: 1.6; margin: 8px 0 0; }
    .fields { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin: 24px 0; }
    input[type=number] { width: 100%; border: 1px solid #a8b5a7; background: white; padding: 12px; font: inherit; border-radius: 4px; }
    button { width: 100%; padding: 15px; border: 0; border-radius: 4px; background: var(--green); color: white; font: inherit; font-weight: 650; cursor: pointer; }
    button:hover { background: #19462f; }
    button:disabled { opacity: .65; cursor: wait; }
    :focus-visible { outline: 3px solid #9b642a; outline-offset: 4px; }
    #status { min-height: 42px; font-size: 13px; line-height: 1.6; margin: 16px 0 0; color: var(--muted); overflow-wrap: anywhere; }
    #status.error { color: #9c2828; }
    #download { display: inline-block; color: var(--green); margin-top: 8px; font-size: 14px; }
    #download[hidden] { display: none; }
    footer { max-width: 1100px; margin: 0 auto; padding: 20px 32px; border-top: 1px solid #d8dcd2; color: var(--muted); font-size: 12px; line-height: 1.7; }
    @media (max-width: 760px) { main { grid-template-columns: 1fr; gap: 30px; padding-top: 32px; } h1 { max-width: 460px; } .steps { display: none; } }
    @media (max-width: 380px) { header, main, footer { padding-left: 18px; padding-right: 18px; } form { padding: 18px; } .fields { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <!-- WEBSITE INSERTION AREA: add your website header or navigation here. -->


  <header><span class="brand">Framebook<span aria-hidden="true">.</span></span><span class="tag">Local demo / MP4 → PDF</span></header>
  <main>
    <section>
      <div class="eyebrow">From motion to pages</div>
      <h1>Your video.<br>A page at a time.</h1>
      <p class="intro">Turn moments from an MP4 into a PDF you can browse, share, or print. Choose how often to capture a frame; we’ll put each one on its own page.</p>
      <ol class="steps"><li>Choose a video from your computer</li><li>Set the spacing between frames</li><li>Download your illustrated PDF</li></ol>
    </section>
    <form id="converter" action="/convert" method="post" enctype="multipart/form-data">
      <h2>Make a framebook</h2>
      <div class="upload">
        <label for="video">MP4 video</label>
        <input id="video" name="video" type="file" accept=".mp4,video/mp4" required aria-describedby="file-hint">
        <p class="hint" id="file-hint">Up to 200 MB. Your video is processed on this computer.</p>
      </div>
      <div class="fields">
        <div><label for="interval">Frame interval (seconds)</label><input id="interval" name="interval" type="number" min="0.1" max="3600" step="0.1" value="10" required aria-describedby="interval-hint"><p class="hint" id="interval-hint">Lower values capture more frames.</p></div>
        <div><label for="max-pages">Maximum pages</label><input id="max-pages" name="max_pages" type="number" min="1" max="500" step="1" value="100" required aria-describedby="limit-hint"><p class="hint" id="limit-hint">Stops at this limit or the video’s end.</p></div>
      </div>
      <button id="convert" type="submit">Create PDF →</button>
      <p id="status" role="status" aria-live="polite">Ready when you are. Longer videos take more time.</p>
      <a id="download" hidden>Download PDF again</a>
    </form>
  </main>
  <footer>One frame per page, with an approximate timestamp. Audio and transcripts are not included. Temporary uploads are removed after processing.</footer>

  <!-- WEBSITE INSERTION AREA: add your website footer or other content here. -->


  <script>
    const form = document.querySelector('#converter');
    const button = document.querySelector('#convert');
    const status = document.querySelector('#status');
    const download = document.querySelector('#download');
    let downloadUrl;
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const file = document.querySelector('#video').files[0];
      status.className = '';
      if (!file || !file.name.toLowerCase().endsWith('.mp4')) {
        status.className = 'error'; status.textContent = 'Choose an MP4 video.'; return;
      }
      if (file.size > 200 * 1024 * 1024) {
        status.className = 'error'; status.textContent = 'Please choose a video smaller than 200 MB.'; return;
      }
      if (downloadUrl) URL.revokeObjectURL(downloadUrl);
      download.hidden = true;
      button.disabled = true;
      button.textContent = 'Creating your PDF…';
      form.setAttribute('aria-busy', 'true');
      status.textContent = 'Uploading and extracting frames. Keep this page open until the PDF is ready.';
      try {
        const response = await fetch(form.action, { method: 'POST', body: new FormData(form) });
        if (!response.ok) {
          const error = await response.json().catch(() => ({}));
          throw new Error(error.error || 'Conversion failed. Please try again.');
        }
        downloadUrl = URL.createObjectURL(await response.blob());
        download.href = downloadUrl;
        download.download = file.name.replace(/\.mp4$/i, '') + '.pdf';
        download.hidden = false;
        download.click();
        const pages = response.headers.get('X-Page-Count');
        const capped = response.headers.get('X-Page-Limit-Reached') === 'true';
        status.textContent = `Your PDF is ready (${pages} pages).` + (capped ? ' Page limit reached; later frames may be omitted.' : '') + ' If the download did not start, use the link below.';
      } catch (error) {
        status.className = 'error';
        status.textContent = error.message || 'Could not connect. Make sure the local Python server is running.';
      } finally {
        button.disabled = false;
        button.textContent = 'Create PDF →';
        form.removeAttribute('aria-busy');
      }
    });
  </script>
</body>
</html>"""

# ============================================================================
# WEBSITE INSERTION AREA — END
# ============================================================================


def create_app():
    try:
        from flask import Flask, jsonify, render_template_string, request, send_file
        from werkzeug.utils import secure_filename
    except ImportError as exc:
        raise RuntimeError(
            "Missing web dependency. Run: python -m pip install flask"
        ) from exc
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 201 * 1024 * 1024  # Includes form overhead.
    # This is a local demo. Before public hosting, add authentication/rate limits,
    # a production server, and a job queue for long conversions.

    @app.get("/")
    def index():
        return render_template_string(PAGE_HTML)

    @app.errorhandler(413)
    def too_large(_error):
        return jsonify(error="Please choose a video smaller than 200 MB."), 413

    # WEBSITE INTEGRATION: POST a multipart form here with the video file,
    # interval (seconds), and max_pages. Success returns application/pdf;
    # validation failures return JSON containing an "error" message.
    @app.post("/convert")
    def convert():
        upload = request.files.get("video")
        if upload is None or not upload.filename:
            return jsonify(error="Choose an MP4 video."), 400
        if Path(upload.filename).suffix.lower() != ".mp4":
            return jsonify(error="Only .mp4 files are accepted."), 400
        try:
            interval = float(request.form.get("interval", "10"))
            max_pages = int(request.form.get("max_pages", "100"))
            if not math.isfinite(interval) or not 0.1 <= interval <= 3600:
                raise ValueError("Interval must be between 0.1 and 3600 seconds.")
            if not 1 <= max_pages <= 500:
                raise ValueError("Page limit must be a whole number from 1 to 500.")
        except ValueError:
            return jsonify(error="Use an interval from 0.1 to 3600 seconds and a whole-number page limit from 1 to 500."), 400
        name = Path(secure_filename(upload.filename) or "video.mp4").stem
        try:
            # Each request gets its own folder, which is removed after conversion.
            with tempfile.TemporaryDirectory(prefix="framebook-") as folder:
                input_path = Path(folder) / "video.mp4"
                output_path = Path(folder) / "frames.pdf"
                upload.save(input_path)
                if input_path.stat().st_size > 200 * 1024 * 1024:
                    return jsonify(error="Please choose a video smaller than 200 MB."), 413
                pages = convert_video_to_pdf(input_path, output_path, interval, max_pages)
                result = io.BytesIO(output_path.read_bytes())
            response = send_file(result, mimetype="application/pdf", as_attachment=True,
                                 download_name=f"{name}.pdf", max_age=0)
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Page-Count"] = str(pages)
            response.headers["X-Page-Limit-Reached"] = str(pages == max_pages).lower()
            return response
        except (ValueError, RuntimeError) as exc:
            return jsonify(error=str(exc)), 400
        except Exception:
            app.logger.exception("Video conversion failed")
            return jsonify(error="Conversion failed. Try another MP4 or check the server log."), 500

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, nargs="?", help="Path to the MP4 video; omit to start the webpage")
    parser.add_argument("output", type=Path, nargs="?", help="Output PDF (default: video filename with .pdf)")
    parser.add_argument("--interval", type=float, default=10.0, help="Seconds between sampled frames (default: 10)")
    parser.add_argument("--max-pages", type=int, help="Optional limit on PDF pages")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing output PDF")
    parser.add_argument("--port", type=int, default=8765, help="Local webpage port (default: 8765)")
    args = parser.parse_args()
    if args.input is None:
        try:
            create_app().run(host="127.0.0.1", port=args.port, debug=False)
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        return 0
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