import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from logging import Handler
from tkinter import filedialog, messagebox, ttk

from analyzer import AnalysisOptions, run_analysis
from config import THEME, get_logger
from github_client import RepoAnalyzerError

log = get_logger()


class _QueueLogHandler(Handler):
    """Pushes formatted log records into a queue so the GUI thread can
    display them without touching widgets from a background thread."""

    def __init__(self, msg_queue: queue.Queue):
        super().__init__()
        self.msg_queue = msg_queue

    def emit(self, record):
        self.msg_queue.put(("log", self.format(record)))


class RepoAnalyzerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GitHub Repo Analyzer")
        self.geometry("640x680")
        self.minsize(560, 620)
        self.configure(bg=THEME["bg"])

        self.msg_queue: queue.Queue = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.last_result = None

        self._build_style()
        self._build_widgets()
        self._attach_log_handler()
        self.after(100, self._poll_queue)

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------
    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        bg, surface, border = THEME["bg"], THEME["surface"], THEME["border"]
        text, dim, gold = THEME["text"], THEME["text_dim"], THEME["gold"]

        style.configure(".", background=bg, foreground=text, font=("Segoe UI", 10))
        style.configure("TFrame", background=bg)
        style.configure("Card.TFrame", background=surface)
        style.configure("TLabel", background=bg, foreground=text)
        style.configure("Dim.TLabel", background=bg, foreground=dim, font=("Segoe UI", 9))
        style.configure("Header.TLabel", background=bg, foreground=text, font=("Segoe UI", 15, "bold"))
        style.configure("TCheckbutton", background=bg, foreground=text)
        style.map("TCheckbutton", background=[("active", bg)])
        style.configure("TEntry", fieldbackground=surface, foreground=text, insertcolor=text)
        style.configure("TSpinbox", fieldbackground=surface, foreground=text)
        style.configure(
            "Accent.TButton",
            background=gold, foreground="#0B0E11",
            font=("Segoe UI", 10, "bold"), padding=8, borderwidth=0,
        )
        style.map("Accent.TButton", background=[("active", "#f0c869"), ("disabled", border)])
        style.configure("Secondary.TButton", background=surface, foreground=text, padding=6, borderwidth=1)
        style.map("Secondary.TButton", background=[("active", border)])

    # ------------------------------------------------------------------
    # Widget layout
    # ------------------------------------------------------------------
    def _build_widgets(self):
        pad = {"padx": 16, "pady": 6}

        header = ttk.Label(self, text="GitHub Repo Analyzer", style="Header.TLabel")
        header.pack(anchor="w", padx=16, pady=(16, 0))
        ttk.Label(
            self, text="Enter a GitHub username and generate a full analytics dashboard.",
            style="Dim.TLabel",
        ).pack(anchor="w", padx=16, pady=(0, 12))

        form = ttk.Frame(self)
        form.pack(fill="x", **pad)
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="GitHub username").grid(row=0, column=0, sticky="w", pady=4)
        self.username_var = tk.StringVar()
        username_entry = ttk.Entry(form, textvariable=self.username_var)
        username_entry.grid(row=0, column=1, sticky="ew", pady=4)
        username_entry.focus_set()
        username_entry.bind("<Return>", lambda e: self._on_analyze())

        ttk.Label(form, text="Access token (optional)").grid(row=1, column=0, sticky="w", pady=4)
        self.token_var = tk.StringVar(value=os.environ.get("GITHUB_TOKEN", ""))
        ttk.Entry(form, textvariable=self.token_var, show="*").grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(form, text="Output folder").grid(row=2, column=0, sticky="w", pady=4)
        out_frame = ttk.Frame(form)
        out_frame.grid(row=2, column=1, sticky="ew", pady=4)
        out_frame.columnconfigure(0, weight=1)
        self.output_dir_var = tk.StringVar(value=os.path.abspath("."))
        ttk.Entry(out_frame, textvariable=self.output_dir_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(out_frame, text="Browse...", style="Secondary.TButton",
                   command=self._browse_output_dir).grid(row=0, column=1, padx=(6, 0))

        ttk.Label(form, text="Minimum stars").grid(row=3, column=0, sticky="w", pady=4)
        self.min_stars_var = tk.IntVar(value=0)
        ttk.Spinbox(form, from_=0, to=100000, textvariable=self.min_stars_var, width=10)\
            .grid(row=3, column=1, sticky="w", pady=4)

        # Filters
        filters = ttk.Frame(self)
        filters.pack(fill="x", padx=16, pady=(4, 0))
        self.exclude_forks_var = tk.BooleanVar(value=False)
        self.exclude_archived_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(filters, text="Exclude forked repos", variable=self.exclude_forks_var)\
            .pack(side="left", padx=(0, 16))
        ttk.Checkbutton(filters, text="Exclude archived repos", variable=self.exclude_archived_var)\
            .pack(side="left")

        # Outputs
        outputs = ttk.Frame(self)
        outputs.pack(fill="x", padx=16, pady=(8, 0))
        ttk.Label(outputs, text="Generate:", style="Dim.TLabel").pack(side="left", padx=(0, 8))
        self.want_html_var = tk.BooleanVar(value=True)
        self.want_csv_var = tk.BooleanVar(value=True)
        self.want_json_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(outputs, text="HTML dashboard", variable=self.want_html_var).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(outputs, text="CSV", variable=self.want_csv_var).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(outputs, text="JSON", variable=self.want_json_var).pack(side="left")

        self.open_browser_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self, text="Open dashboard automatically when done",
                         variable=self.open_browser_var).pack(anchor="w", padx=16, pady=(6, 10))

        # Action button + progress bar
        action_frame = ttk.Frame(self)
        action_frame.pack(fill="x", padx=16, pady=(0, 8))
        self.analyze_btn = ttk.Button(action_frame, text="Analyze", style="Accent.TButton",
                                       command=self._on_analyze)
        self.analyze_btn.pack(side="left")
        self.progress = ttk.Progressbar(action_frame, mode="indeterminate")
        self.progress.pack(side="left", fill="x", expand=True, padx=(12, 0))

        # Log output
        ttk.Label(self, text="Activity log", style="Dim.TLabel").pack(anchor="w", padx=16, pady=(6, 0))
        log_frame = ttk.Frame(self, style="Card.TFrame")
        log_frame.pack(fill="both", expand=True, padx=16, pady=(4, 8))
        self.log_text = tk.Text(
            log_frame, height=10, bg=THEME["surface"], fg=THEME["text_dim"],
            insertbackground=THEME["text"], relief="flat", wrap="word",
            font=("Consolas", 9),
        )
        self.log_text.pack(fill="both", expand=True, side="left", padx=6, pady=6)
        scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scroll.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scroll.set, state="disabled")

        # Result actions
        result_frame = ttk.Frame(self)
        result_frame.pack(fill="x", padx=16, pady=(0, 16))
        self.open_dashboard_btn = ttk.Button(
            result_frame, text="Open Dashboard", style="Secondary.TButton",
            command=self._open_dashboard, state="disabled",
        )
        self.open_dashboard_btn.pack(side="left")
        self.open_folder_btn = ttk.Button(
            result_frame, text="Open Output Folder", style="Secondary.TButton",
            command=self._open_output_folder,
        )
        self.open_folder_btn.pack(side="left", padx=(8, 0))

    # ------------------------------------------------------------------
    # Logging bridge
    # ------------------------------------------------------------------
    def _attach_log_handler(self):
        handler = _QueueLogHandler(self.msg_queue)
        handler.setFormatter(__import__("logging").Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
        log.addHandler(handler)

    def _append_log(self, line: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _browse_output_dir(self):
        chosen = filedialog.askdirectory(initialdir=self.output_dir_var.get() or ".")
        if chosen:
            self.output_dir_var.set(chosen)

    def _on_analyze(self):
        username = self.username_var.get().strip()
        if not username:
            messagebox.showwarning("Missing username", "Please enter a GitHub username first.")
            return
        if self.worker_thread and self.worker_thread.is_alive():
            return  # already running

        out_dir = self.output_dir_var.get().strip() or "."
        os.makedirs(out_dir, exist_ok=True)

        opts = AnalysisOptions(
            username=username,
            token=self.token_var.get().strip() or None,
            output_dir=out_dir,
            min_stars=int(self.min_stars_var.get() or 0),
            exclude_forks=self.exclude_forks_var.get(),
            exclude_archived=self.exclude_archived_var.get(),
            export_csv_file=self.want_csv_var.get(),
            export_json_file=self.want_json_var.get(),
            export_html=self.want_html_var.get(),
            open_browser=self.open_browser_var.get(),
        )

        self.analyze_btn.configure(state="disabled")
        self.open_dashboard_btn.configure(state="disabled")
        self.progress.start(12)
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

        self.worker_thread = threading.Thread(target=self._worker, args=(opts,), daemon=True)
        self.worker_thread.start()

    def _worker(self, opts: AnalysisOptions):
        try:
            result = run_analysis(opts)
            self.msg_queue.put(("done", result))
        except RepoAnalyzerError as e:
            self.msg_queue.put(("error", str(e)))
        except Exception as e:  # noqa: BLE001 - surface anything unexpected to the user
            self.msg_queue.put(("error", f"Unexpected error: {e}"))

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "done":
                    self._on_done(payload)
                elif kind == "error":
                    self._on_error(payload)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _on_done(self, result):
        self.progress.stop()
        self.analyze_btn.configure(state="normal")
        self.last_result = result
        if result.html_path:
            self.open_dashboard_btn.configure(state="normal")
        self._append_log("── Done ──")
        self._append_log(result.summary)
        paths = [p for p in (result.csv_path, result.json_path, result.html_path) if p]
        if paths:
            self._append_log("Files written:")
            for p in paths:
                self._append_log(f"  {p}")
        messagebox.showinfo("Analysis complete", f"Finished analyzing '{result.username}'.")

    def _on_error(self, message: str):
        self.progress.stop()
        self.analyze_btn.configure(state="normal")
        self._append_log(f"ERROR: {message}")
        messagebox.showerror("Analysis failed", message)

    def _open_dashboard(self):
        if self.last_result and self.last_result.html_path:
            webbrowser.open(f"file://{os.path.abspath(self.last_result.html_path)}")

    def _open_output_folder(self):
        folder = os.path.abspath(self.output_dir_var.get() or ".")
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as e:
            messagebox.showerror("Could not open folder", str(e))


def launch():
    app = RepoAnalyzerApp()
    app.mainloop()
