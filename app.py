"""
Video Converter GUI & Application
To Run:  python -m pip install opencv-python reportlab moviepy tkinterdnd2
         python app.py

         Note:
         1. tkinterdnd2 is used for drag & drop functionality: without it, drag & drop is off but click selection still works          
         2. moviepy is used for MP3 conversion: without it, MP3 conversion is off
"""
import os, queue, subprocess, sys, threading, tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import converter as cv

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    Root = TkinterDnD.Tk
except ImportError:
    DND_FILES, Root = None, tk.Tk

BG, ZONE, DARK, DARK_HOVER = "#D9D9D9", "#B3B3B3", "#2B2B2B", "#3D3D3D"
PILL, ACCENT, ACCENT_DARK, TRACK = "#4F4F4F", "#78BDD8", "#327A94", "#E6DEFA"
FONT = ("Helvetica", 11)


class Btn(tk.Label):
    """Flat button (Label-based so colours work on every OS)."""
    def __init__(self, master, text, command, width=22, bg=DARK, hover=ACCENT_DARK):
        super().__init__(master, text=text, bg=bg, fg="white", font=FONT, width=width,
                         pady=6, cursor="hand2")
        self.command, self.base, self.hover, self.enabled = command, bg, hover, True
        self.bind("<Enter>", lambda e: self.enabled and self.config(bg=self.hover))
        self.bind("<Leave>", lambda e: self.config(bg=self.base))
        self.bind("<Button-1>", lambda e: self.enabled and self.command())

    def set_enabled(self, on):
        self.enabled = on
        self.config(bg=self.base, fg="white" if on else "#8A8A8A", cursor="hand2" if on else "arrow")


class DropZone(tk.Label):
    def __init__(self, master, on_file, **kw):
        kw.setdefault("wraplength", 300)
        super().__init__(master, text="Drag to Insert a File", bg=ZONE, fg="white",
                         font=FONT, cursor="hand2", **kw)
        self.on_file = on_file
        self.bind("<Button-1>", lambda e: self.browse())
        if DND_FILES:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<DropEnter>>", lambda e: self.config(bg=ACCENT))
            self.dnd_bind("<<DropLeave>>", lambda e: self.config(bg=ZONE))
            self.dnd_bind("<<Drop>>", self._drop)

    def _drop(self, event):
        self.config(bg=ZONE)
        files = self.tk.splitlist(event.data)
        if files:
            self.on_file(files[0])

    def browse(self):
        exts = " ".join("*" + e for e in cv.VIDEO_EXTENSIONS)
        path = filedialog.askopenfilename(title="Select a video",
                                          filetypes=[("Video files", exts), ("All files", "*.*")])
        if path:
            self.on_file(path)


class Slider(tk.Canvas):
    """Three-stop slider: Low / Medium / High."""
    def __init__(self, master, on_change, width=440):
        super().__init__(master, width=width, height=46, bg=BG, highlightthickness=0, cursor="hand2")
        self.w, self.level, self.on_change = width, 1, on_change
        self.xs = [8, width // 2, width - 8]
        self.bind("<Button-1>", self._pick)
        self.bind("<B1-Motion>", self._pick)
        self.draw()

    def _pick(self, e):
        level = min(range(3), key=lambda i: abs(self.xs[i] - e.x))
        if level != self.level:
            self.level = level
            self.draw()
            self.on_change()

    def draw(self):
        self.delete("all")
        self.create_rectangle(self.xs[0], 8, self.xs[2], 16, fill=TRACK, outline="")
        for i, (x, name) in enumerate(zip(self.xs, cv.QUALITY_LEVELS)):
            self.create_line(x, 5, x, 19, fill="#6B5FA0" if i == self.level else "#9A94B8",
                             width=3 if i == self.level else 1)
            self.create_text(x, 34, text=name, font=FONT, anchor="w" if i == 0 else "e" if i == 2 else "center")


class App(Root):
    def __init__(self):
        super().__init__()
        self.title("Video Converter")
        self.geometry("760x560")
        self.minsize(640, 480)
        self.configure(bg=BG)
        self.info = self.fmt = self.q = self.cancel = None
        self.q = queue.Queue()
        self.views = {n: tk.Frame(self, bg=BG) for n in ("drop", "opts", "busy", "done")}
        self._build_drop(); self._build_opts(); self._build_busy(); self._build_done()
        self.show("drop")

    def show(self, name):
        for n, f in self.views.items():
            f.place_forget()
        self.views[name].place(relx=0, rely=0, relwidth=1, relheight=1)

    # ---------------------------------------------------------------- screen 1
    def _build_drop(self):
        f = self.views["drop"]
        zone = DropZone(f, self.load_file, wraplength=500)
        zone.place(relx=0.05, rely=0.06, relwidth=0.9, relheight=0.68)
        Btn(f, "Or click to select a file", zone.browse, width=10).place(
            relx=0.05, rely=0.79, relwidth=0.9, height=44)

    # ---------------------------------------------------------------- screen 2/3
    def _build_opts(self):
        f = self.views["opts"]
        top = tk.Frame(f, bg=BG)
        top.pack(pady=(40, 0))
        self.tile = DropZone(top, self.load_file, width=16, height=7, wraplength=150)
        self.tile.grid(row=0, column=0, padx=20)
        arrow = tk.Canvas(top, width=110, height=50, bg=BG, highlightthickness=0)
        arrow.create_line(4, 25, 104, 25, fill="#333"); arrow.create_line(84, 8, 104, 25, 84, 42, fill="#333")
        arrow.grid(row=0, column=1, padx=20)
        self.pill = tk.Canvas(top, width=190, height=30, bg=BG, highlightthickness=0, cursor="hand2")
        self.pill.grid(row=0, column=2, padx=20)
        self.pill.bind("<Button-1>", self._menu)
        self.menu = tk.Menu(self, tearoff=0)
        for name in cv.FORMATS:
            self.menu.add_command(label=name, command=lambda n=name: self.set_format(n))
        self.draw_pill("Select format")

        self.stage = tk.Frame(f, bg=BG)
        self.stage.pack(pady=30, fill="x")
        # stage A: continue
        self.stage_a = tk.Frame(self.stage, bg=BG)
        self.cont = Btn(self.stage_a, "continue", self.go_quality, width=20)
        self.cont.pack(pady=20); self.cont.set_enabled(False)
        # stage B: quality
        self.stage_b = tk.Frame(self.stage, bg=BG)
        self.slider = Slider(self.stage_b, self.update_estimate)
        self.slider.pack(pady=(10, 4))
        self.interval_row = tk.Frame(self.stage_b, bg=BG)
        tk.Label(self.interval_row, text="One frame every", bg=BG, font=FONT).pack(side="left")
        self.interval = tk.StringVar(value=f"{cv.DEFAULT_INTERVAL:g}")
        e = tk.Entry(self.interval_row, textvariable=self.interval, width=6, justify="center")
        e.pack(side="left", padx=6); tk.Label(self.interval_row, text="seconds", bg=BG, font=FONT).pack(side="left")
        self.interval.trace_add("write", lambda *a: self.update_estimate())
        self.interval_row.pack(pady=6)
        self.est = tk.Label(self.stage_b, text="Estimated size: XX", bg=BG, font=FONT)
        self.est.pack(pady=8)
        row = tk.Frame(self.stage_b, bg=BG); row.pack(pady=6)
        Btn(row, "back", self.back_to_format, width=16).pack(side="left", padx=25)
        Btn(row, "convert", self.start_convert, width=16).pack(side="left", padx=25)

    def draw_pill(self, text):
        c = self.pill; c.delete("all")
        r, w, h = 15, 190, 30
        c.create_oval(0, 0, h, h, fill=PILL, outline=""); c.create_oval(w - h, 0, w, h, fill=PILL, outline="")
        c.create_rectangle(r, 0, w - r, h, fill=PILL, outline="")
        c.create_text(w / 2, h / 2, text=f"{text}  \u2304", fill="white", font=("Helvetica", 10, "bold"))

    def _menu(self, e):
        if self.stage_a.winfo_ismapped():  # format is locked while adjusting quality
            self.menu.tk_popup(self.pill.winfo_rootx(), self.pill.winfo_rooty() + 32)

    def set_format(self, name):
        self.fmt = name
        self.draw_pill(name)
        self.cont.set_enabled(True)

    def load_file(self, path):
        path = str(path).strip("{}")
        if Path(path).suffix.lower() not in cv.VIDEO_EXTENSIONS:
            return messagebox.showerror("Unsupported file", "Please choose a video file (" + ", ".join(cv.VIDEO_EXTENSIONS) + ").")
        try:
            self.info = cv.probe_video(path)
        except Exception as exc:
            return messagebox.showerror("Can't open video", str(exc))
        i = self.info
        self.tile.config(text=f"{i.path.name}\n{cv.format_duration(i.duration)} \u00b7 {cv.human_size(i.size_bytes)}")
        self.back_to_format(); self.show("opts")

    def back_to_format(self):
        self.stage_b.pack_forget(); self.stage_a.pack()

    def go_quality(self):
        self.stage_a.pack_forget(); self.stage_b.pack()
        (self.interval_row.pack if self.fmt in cv.FRAME_FORMATS else self.interval_row.pack_forget)()
        self.update_estimate()

    def get_interval(self):
        try:
            v = float(self.interval.get()); cv.check_interval(v); return v
        except ValueError:
            return None

    def update_estimate(self):
        if not (self.info and self.fmt):
            return
        iv = self.get_interval() if self.fmt in cv.FRAME_FORMATS else cv.DEFAULT_INTERVAL
        if iv is None:
            return self.est.config(text="Estimated size: \u2014 (check the interval)")
        self.est.config(text="Estimated size: ~" + cv.human_size(cv.estimate_size(self.info, self.fmt, self.slider.level, iv)))

    # ---------------------------------------------------------------- convert
    def _build_busy(self):
        f = self.views["busy"]
        self.busy_label = tk.Label(f, text="Converting\u2026", bg=BG, font=("Helvetica", 13))
        self.busy_label.place(relx=0.5, rely=0.38, anchor="center")
        self.bar = ttk.Progressbar(f, length=420, mode="determinate", maximum=1.0)
        self.bar.place(relx=0.5, rely=0.48, anchor="center")

    def start_convert(self):
        iv = self.get_interval() if self.fmt in cv.FRAME_FORMATS else cv.DEFAULT_INTERVAL
        if iv is None:
            return messagebox.showerror("Invalid interval", f"Enter a number between {cv.MIN_INTERVAL:g} and {cv.MAX_INTERVAL:g}.")
        level, src = self.slider.level, self.info.path
        max_dim, jq = cv.FRAME_PROFILES[level]
        self.bar.config(mode="determinate", value=0); self.show("busy")

        def progress(frac):
            self.q.put(("p", frac))

        def work():
            try:
                if self.fmt == "PDF":
                    out = self._unique(src.with_suffix(".pdf"))
                    cv.convert_video_to_pdf(src, out, iv, max_dim=max_dim, jpeg_quality=jq, progress=progress)
                elif self.fmt == "MP3":
                    out = self._unique(src.with_suffix(".mp3"))
                    cv.convert_video_to_mp3(src, out, cv.MP3_BITRATES[level], progress=progress)
                else:
                    ext = ".png" if "PNG" in self.fmt else ".jpg"
                    out, _ = cv.convert_video_to_images(src, src.parent, iv, ext, max_dim, jq, progress)
                self.q.put(("done", out))
            except Exception as exc:
                self.q.put(("err", str(exc)))
        threading.Thread(target=work, daemon=True).start()
        self.after(100, self.poll)

    @staticmethod
    def _unique(p: Path):
        n, cand = 2, p
        while cand.exists():
            cand = p.with_name(f"{p.stem}_{n}{p.suffix}"); n += 1
        return cand

    def poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "p":
                    if val is None:
                        self.bar.config(mode="indeterminate"); self.bar.start(12)
                    else:
                        self.bar.config(value=val)
                elif kind == "done":
                    self.bar.stop(); self.finish(Path(val)); return
                else:
                    self.bar.stop(); self.show("opts")
                    return messagebox.showerror("Conversion failed", val)
        except queue.Empty:
            pass
        self.after(100, self.poll)

    # ---------------------------------------------------------------- done
    def _build_done(self):
        f = self.views["done"]
        self.done_path = tk.Label(f, text="file directory", bg=BG, font=FONT, wraplength=560, justify="center")
        self.done_path.place(relx=0.5, rely=0.36, anchor="center")
        self.done_size = tk.Label(f, text="", bg=BG, font=FONT, fg="#555")
        self.done_size.place(relx=0.5, rely=0.44, anchor="center")
        Btn(f, "Show in folder", self.reveal, width=24, bg=PILL).place(relx=0.5, rely=0.58, anchor="center")
        Btn(f, "Convert Another", self.reset, width=28).place(relx=0.5, rely=0.70, anchor="center")

    def finish(self, out: Path):
        self.result = out
        self.done_path.config(text=str(out))
        self.done_size.config(text="Saved \u00b7 " + cv.human_size(cv.output_size(out)))
        self.show("done")

    def reveal(self):
        folder = self.result if self.result.is_dir() else self.result.parent
        if sys.platform == "win32": os.startfile(folder)
        elif sys.platform == "darwin": subprocess.run(["open", str(folder)])
        else: subprocess.run(["xdg-open", str(folder)])

    def reset(self):
        self.info = self.fmt = None
        self.draw_pill("Select format"); self.cont.set_enabled(False)
        self.show("drop")


if __name__ == "__main__":
    App().mainloop()