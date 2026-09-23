# Converter
A conversion tool to change file types.


Make sure to push everything to a separate branch BEFORE we commit to main.

## Local MP4 to PDF webpage

Install dependencies and start the demo from this folder:

```powershell
python -m pip install -r requirements.txt
python mp4_to_pdf.py
```

Open http://127.0.0.1:8765. Upload an MP4, choose the frame interval and
maximum page count, then click **Create PDF**. Stop the server with Ctrl+C.
Use `--port 8766` if the default port is occupied.

The local demo accepts MP4 files up to 200 MB and creates up to 500 pages.
Each page contains one video frame with an approximate timestamp, not a
transcript. A page limit can omit later frames. Variable-frame-rate video
may have approximate sampling times. Temporary uploads are removed after
processing, and the browser downloads the PDF.

### Website insertion area

Search `mp4_to_pdf.py` for **WEBSITE INSERTION AREA**. The marked section
contains the HTML, styles, and browser code, with blank comment space for
future integration and marked header/footer insertion points.

The Python `/convert` route accepts a multipart POST containing `video`,
`interval`, and `max_pages`, and returns a PDF (or JSON with an `error`
message). Keep the frontend and endpoint on the same origin. Python must
run on a server; a static HTML host alone cannot execute the converter.
This is a local demo. Public hosting needs a production server and suitable
access, request limits, and background processing for long videos.

Command-line conversion is still supported:

```powershell
python mp4_to_pdf.py video.mp4 result.pdf --interval 5
```
