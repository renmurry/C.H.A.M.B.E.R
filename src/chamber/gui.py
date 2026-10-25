"""The clicky app (tkinter, nothing extra to install).

Folder pickers, CRS dropdown, options, progress bar, live log, open-folder
button. The actual work runs on a background thread so the window doesn't freeze;
it talks back to the UI through a queue.
"""
from __future__ import annotations
import os, sys, queue, threading, traceback
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import random
import time

from . import __version__
from .batch import run_batch
from . import achievements as A
from .pixeldog import DogProgress

PAD = {"padx": 8, "pady": 4}


def _resource(rel):
    """Locate a bundled asset whether running from source or a PyInstaller exe."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, rel)
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", rel))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"C.H.A.M.B.E.R  v{__version__}")
        self.geometry("700x680")
        self.minsize(640, 620)
        self._set_icons()
        self.q = queue.Queue()
        self.worker = None
        self._build()
        self.after(100, self._drain)

    def _set_icons(self):
        try:
            ico = _resource("assets/app.ico")
            if os.path.exists(ico):
                self.iconbitmap(ico)            # title bar + taskbar (Windows)
        except Exception:
            pass
        try:
            png = _resource("assets/logo_64.png")
            if os.path.exists(png):
                self._winicon = tk.PhotoImage(file=png)
                self.iconphoto(True, self._winicon)
        except Exception:
            pass

    # ---------- layout ----------
    def _build(self):
        st = ttk.Style()
        try:
            st.theme_use("vista")               # nicer on Windows; ignored elsewhere
        except Exception:
            pass
        st.configure("Run.TButton", font=("Segoe UI", 10, "bold"), padding=(18, 4))

        frm = ttk.Frame(self); frm.pack(fill="x", **PAD)
        try:
            self._logo48 = tk.PhotoImage(file=_resource("assets/logo_48.png"))
            ttk.Label(frm, image=self._logo48).grid(row=0, column=0, rowspan=2,
                                                    sticky="w", padx=(0, 10))
        except Exception:
            self._logo48 = None
        ttk.Label(frm, text="C.H.A.M.B.E.R", font=("Segoe UI", 16, "bold")).grid(
            row=0, column=1, sticky="w")
        ttk.Label(frm, text="Extract block boundaries from georeferenced PDF map sheets.",
                  foreground="#777").grid(row=1, column=1, sticky="w", pady=(0, 8))

        self.in_var = tk.StringVar()
        self.out_var = tk.StringVar()
        ttk.Label(frm, text="PDF folder:").grid(row=2, column=0, sticky="e", **PAD)
        ttk.Entry(frm, textvariable=self.in_var, width=58).grid(row=2, column=1, sticky="we", **PAD)
        ttk.Button(frm, text="Browse…", command=self._pick_in).grid(row=2, column=2, **PAD)

        ttk.Label(frm, text="Output folder:").grid(row=3, column=0, sticky="e", **PAD)
        ttk.Entry(frm, textvariable=self.out_var, width=58).grid(row=3, column=1, sticky="we", **PAD)
        ttk.Button(frm, text="Browse…", command=self._pick_out).grid(row=3, column=2, **PAD)
        frm.columnconfigure(1, weight=1)

        opt = ttk.LabelFrame(self, text="Options"); opt.pack(fill="x", **PAD)
        ttk.Label(opt, text="Target CRS:").grid(row=0, column=0, sticky="e", **PAD)
        self.crs_var = tk.StringVar(value="Auto (detect UTM zone per sheet)")
        self.crs_box = ttk.Combobox(opt, textvariable=self.crs_var, width=28, values=[
            "Auto (detect UTM zone per sheet)",
            "EPSG:4326 (lat/lon)", "EPSG:3857 (Web Mercator)", "Custom…"])
        self.crs_box.grid(row=0, column=1, sticky="w", **PAD)
        self.crs_box.bind("<<ComboboxSelected>>", self._crs_changed)
        self.custom_epsg = tk.StringVar(value="")
        self.custom_entry = ttk.Entry(opt, textvariable=self.custom_epsg, width=10)
        # checkboxes
        self.tif_var = tk.BooleanVar(value=True)
        self.vec_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="Also export GeoTIFF", variable=self.tif_var).grid(
            row=0, column=2, sticky="w", **PAD)
        ttk.Checkbutton(opt, text="Use vector boundary if present", variable=self.vec_var).grid(
            row=1, column=2, sticky="w", **PAD)
        ttk.Label(opt, text="Parallel jobs:").grid(row=1, column=0, sticky="e", **PAD)
        self.jobs_var = tk.IntVar(value=1)
        ttk.Spinbox(opt, from_=1, to=16, textvariable=self.jobs_var, width=5).grid(
            row=1, column=1, sticky="w", **PAD)

        # export-format checkboxes
        ttk.Label(opt, text="Export formats:").grid(row=2, column=0, sticky="e", **PAD)
        fmtbar = ttk.Frame(opt); fmtbar.grid(row=2, column=1, columnspan=2, sticky="w", **PAD)
        self.fmt_vars = {
            "geojson": tk.BooleanVar(value=True),
            "kml":     tk.BooleanVar(value=True),
            "shp":     tk.BooleanVar(value=False),
            "gpkg":    tk.BooleanVar(value=False),
            "dxf":     tk.BooleanVar(value=False),
        }
        for label, key in [("GeoJSON", "geojson"), ("KML", "kml"), ("Shapefile", "shp"),
                           ("GeoPackage", "gpkg"), ("DXF", "dxf")]:
            ttk.Checkbutton(fmtbar, text=label, variable=self.fmt_vars[key]).pack(side="left", padx=4)

        self.merge_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="Merge and zip shapefiles",
                        variable=self.merge_var).grid(row=3, column=1, columnspan=2,
                                                      sticky="w", **PAD)
        self.ocr_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="Read block IDs from the map (OCR)",
                        variable=self.ocr_var).grid(row=4, column=1, columnspan=2,
                                                    sticky="w", **PAD)

        bar = ttk.Frame(self); bar.pack(fill="x", **PAD)
        self.run_btn = ttk.Button(bar, text="Run", style="Run.TButton", command=self._run)
        self.run_btn.pack(side="left", **PAD)
        self.open_btn = ttk.Button(bar, text="Open output folder",
                                   command=self._open_out, state="disabled")
        self.open_btn.pack(side="left", **PAD)
        self.clear_btn = ttk.Button(bar, text="Clear", command=self._clear)
        self.clear_btn.pack(side="left", **PAD)
        self.badges_btn = ttk.Button(bar, text="Badges", command=self._show_badges)
        self.badges_btn.pack(side="left", **PAD)
        # the progress bar: a pixel dog running to its bone, status line above it
        self.status = ttk.Label(self, text="Ready when you are.", foreground="#666")
        self.status.pack(fill="x", padx=14, pady=(4, 0))
        self.dog = DogProgress(self)
        self.dog.pack(fill="x", padx=12, pady=(0, 4))

        logf = ttk.LabelFrame(self, text="Log"); logf.pack(fill="both", expand=True, **PAD)
        self.log = tk.Text(logf, height=12, wrap="word", state="disabled",
                           font=("Consolas", 9), relief="flat", padx=6, pady=4)
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(logf, command=self.log.yview); sb.pack(side="right", fill="y")
        self.log.config(yscrollcommand=sb.set)
        self.log.tag_configure("ok", foreground="#1d7a3f")
        self.log.tag_configure("flag", foreground="#a86400")
        self.log.tag_configure("fail", foreground="#c0392b")
        self.log.tag_configure("head", font=("Consolas", 9, "bold"))

    # ---------- helpers ----------
    def _crs_changed(self, _=None):
        if self.crs_var.get().startswith("Custom"):
            self.custom_entry.grid(row=0, column=2, sticky="w", **PAD)
        else:
            self.custom_entry.grid_remove()

    def _pick_in(self):
        d = filedialog.askdirectory(title="Select the folder containing your PDFs")
        if d:
            self.in_var.set(d)
            if not self.out_var.get():
                self.out_var.set(str(Path(d) / "converted"))

    def _pick_out(self):
        d = filedialog.askdirectory(title="Select an output folder")
        if d: self.out_var.set(d)

    def _epsg_value(self):
        s = self.crs_var.get()
        if s.startswith("Auto"): return "auto"
        if s.startswith("Custom"): return self.custom_epsg.get().strip()
        return s.split(":")[1].split(" ")[0]    # "EPSG:4326 (...)" -> "4326"

    def _log(self, msg, tag=None):
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n", (tag,) if tag else ())
        self.log.see("end"); self.log.config(state="disabled")

    @staticmethod
    def _eta(done, total, started):
        if done < 2:
            return "sniffing around..."
        left = (time.time() - started) / done * (total - done)
        if left < 60:
            return "under a minute left"
        return f"~{int(left // 60) + 1} min left"

    def _open_out(self):
        out = self.out_var.get()
        if out and os.path.isdir(out):
            try: os.startfile(out)            # Windows
            except AttributeError: pass

    def _clear(self):
        # wipe the log
        self.log.config(state="normal"); self.log.delete("1.0", "end")
        self.log.config(state="disabled")
        # reset progress + status
        self.dog.reset(); self.status.config(text="Ready when you are.")
        # clear the folder selections (format + CRS choices are left as-is)
        self.in_var.set(""); self.out_var.set("")
        self.open_btn.config(state="disabled")

    # ---------- completion celebration + badges ----------
    def _completion_dialog(self, s, newly):
        try:
            self._build_completion(s, newly)
        except Exception:
            messagebox.showinfo("C.H.A.M.B.E.R",
                f"Finished.\n\n{s['ok']} ok, {s['flagged']} flagged, {s['failed']} failed.\n\n"
                f"Results in:\n{s['output_dir']}")

    def _build_completion(self, s, newly):
        clean = s["failed"] == 0 and s["flagged"] == 0 and s["ok"] > 0
        if s["failed"]:
            head, color = "Run complete", "#b35900"
        elif s["flagged"]:
            head, color = "Done - a few to review", "#7a6a00"
        else:
            head, color = "All done!", "#1d7a3f"

        win = tk.Toplevel(self); win.title("C.H.A.M.B.E.R")
        win.transient(self); win.resizable(False, False)
        ttk.Label(win, text=head, font=("Segoe UI", 16, "bold"),
                  foreground=color).pack(padx=24, pady=(16, 2))
        ttk.Label(win, text=f"{s['ok']} ok     {s['flagged']} flagged     {s['failed']} failed",
                  font=("Segoe UI", 11)).pack(padx=24)
        ttk.Label(win, text=f"Saved in:\n{s['output_dir']}",
                  foreground="#666", justify="center").pack(padx=24, pady=(2, 6))

        cv = tk.Canvas(win, width=380, height=88, highlightthickness=0)
        cv.pack(padx=10)
        cv.create_text(190, 46, text=f"+{s['ok']} blocks", fill=color,
                       font=("Segoe UI", 20, "bold"))
        if clean:
            items = []
            for _ in range(26):
                x = random.randint(8, 372); sz = random.randint(4, 8)
                col = random.choice(["#e24b4a", "#378add", "#639922", "#ef9f27", "#d4537e"])
                items.append(cv.create_rectangle(x, -10, x + sz, -10 + sz, fill=col, outline=""))
            self._confetti(cv, items, 0)

        if newly:
            bf = ttk.LabelFrame(win, text="Achievement unlocked!")
            bf.pack(fill="x", padx=14, pady=6)
            for _bid, name, desc in newly:
                row = ttk.Frame(bf); row.pack(fill="x", padx=8, pady=3)
                ttk.Label(row, text="[+]", foreground=color,
                          font=("Segoe UI", 11, "bold")).pack(side="left")
                ttk.Label(row, text=f"  {name}",
                          font=("Segoe UI", 11, "bold")).pack(side="left")
                ttk.Label(row, text=f"  -  {desc}", foreground="#666").pack(side="left")

        btns = ttk.Frame(win); btns.pack(pady=(6, 14))
        ttk.Button(btns, text="Open output folder", command=self._open_out).pack(side="left", padx=6)
        ttk.Button(btns, text="Close", command=win.destroy).pack(side="left", padx=6)

        win.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - win.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - win.winfo_height()) // 3
        win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        try:
            win.attributes("-alpha", 0.0); self._fade(win, 0.0)
        except Exception:
            pass
        win.grab_set()

    def _fade(self, win, a):
        a = min(1.0, a + 0.12)
        try:
            win.attributes("-alpha", a)
        except Exception:
            return
        if a < 1.0:
            win.after(20, lambda: self._fade(win, a))

    def _confetti(self, cv, items, frame):
        if frame > 40:
            return
        for it in items:
            cv.move(it, random.randint(-1, 1), random.randint(4, 9))
        cv.after(40, lambda: self._confetti(cv, items, frame + 1))

    def _show_badges(self):
        try:
            unlocked = set(A.load_stats().get("unlocked", []))
        except Exception:
            unlocked = set()
        win = tk.Toplevel(self); win.title("Badges")
        win.transient(self); win.resizable(False, False)
        ttk.Label(win, text="Achievements", font=("Segoe UI", 14, "bold")).pack(
            padx=16, pady=(12, 2))
        ttk.Label(win, text=f"{len(unlocked)} of {len(A.BADGES)} unlocked",
                  foreground="#666").pack(pady=(0, 8))
        for bid, name, desc, _test in A.BADGES:
            got = bid in unlocked
            row = ttk.Frame(win); row.pack(fill="x", padx=16, pady=2)
            ttk.Label(row, text=("[*]" if got else "[ ]"),
                      foreground=("#1d7a3f" if got else "#999"),
                      font=("Segoe UI", 11, "bold")).pack(side="left")
            ttk.Label(row, text=f"  {name}", font=("Segoe UI", 11, "bold"),
                      foreground=("#000" if got else "#999")).pack(side="left")
            ttk.Label(row, text=f"  -  {desc}", foreground="#888").pack(side="left")
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=12)
        win.grab_set()

    # ---------- run ----------
    def _run(self):
        indir = self.in_var.get().strip()
        outdir = self.out_var.get().strip()
        if not indir or not Path(indir).is_dir():
            messagebox.showerror("C.H.A.M.B.E.R", "Please choose a valid PDF folder."); return
        if not outdir:
            outdir = str(Path(indir) / "converted"); self.out_var.set(outdir)
        pdfs = list(Path(indir).rglob("*.pdf"))
        if not pdfs:
            messagebox.showwarning("C.H.A.M.B.E.R", "No PDF files found in that folder."); return

        formats = [k for k, v in self.fmt_vars.items() if v.get()]
        if not formats:
            messagebox.showwarning("C.H.A.M.B.E.R",
                "Pick at least one export format (GeoJSON, KML, Shapefile, GeoPackage or DXF)."); return
        self._last_formats = formats
        epsg = self._epsg_value()
        if epsg != "auto" and not epsg.isdigit():
            messagebox.showwarning("C.H.A.M.B.E.R",
                "Type a numeric EPSG code (for example 32643), or pick Auto."); return
        params = {"epsg": epsg, "dpi": 300, "simplify": 0.0010,
                  "white_min": 175, "vector": self.vec_var.get(), "tif": self.tif_var.get(),
                  "formats": formats, "merge_zip": self.merge_var.get(),
                  "ocr": self.ocr_var.get(), "output_dir": outdir}
        self.run_btn.config(state="disabled"); self.open_btn.config(state="disabled")
        self.clear_btn.config(state="disabled")
        self.dog.start(len(pdfs)); self._started = time.time()
        self.status.config(text=f"0/{len(pdfs)}  ·  off we go!")
        self._log(f"Processing {len(pdfs)} PDF(s)  ->  {outdir}   (CRS {params['epsg']})", "head")

        def work():
            try:
                summary = run_batch(indir, outdir, params, jobs=self.jobs_var.get(),
                                    on_progress=lambda d, t: self.q.put(("prog", d, t)),
                                    on_log=lambda r: self.q.put(("log", r)))
                self.q.put(("done", summary))
            except Exception:
                self.q.put(("error", traceback.format_exc()))

        self.worker = threading.Thread(target=work, daemon=True); self.worker.start()

    def _drain(self):
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                if kind == "prog":
                    _, d, t = item
                    self.dog.set_progress(d, t)
                    self.status.config(text=f"{d}/{t}  ·  "
                                       f"{self._eta(d, t, getattr(self, '_started', time.time()))}")
                elif kind == "log":
                    r = item[1]
                    if r["error"]:
                        self._log(f"  FAIL  {r['file']}: {r['error']}", "fail")
                    else:
                        p = r["props"]
                        self._log(f"  ok    {r['file']}   {p['area_ha']} ha  [{p['qc']}]",
                                  "ok" if p["qc"] == "ok" else "flag")
                elif kind == "done":
                    s = item[1]
                    clean = s["failed"] == 0 and s["flagged"] == 0
                    self._log(f"\nDone: {s['ok']} ok, {s['flagged']} flagged, {s['failed']} failed.",
                              "head")
                    self.dog.finish(clean=clean)
                    self.status.config(text="Good dog! All done." if clean
                                       else "Done. A few sheets to review.")
                    self.run_btn.config(state="normal"); self.open_btn.config(state="normal")
                    self.clear_btn.config(state="normal")
                    try:
                        _, newly = A.record_run(s, getattr(self, "_last_formats", []))
                    except Exception:
                        newly = []
                    self._completion_dialog(s, newly)
                elif kind == "error":
                    self._log("\nERROR:\n" + item[1], "fail")
                    self.dog.reset()
                    self.status.config(text="Error"); self.run_btn.config(state="normal")
                    self.clear_btn.config(state="normal")
                    messagebox.showerror("C.H.A.M.B.E.R", "Something went wrong. See the log.")
        except queue.Empty:
            pass
        self.after(100, self._drain)


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
