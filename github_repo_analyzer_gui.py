import json
import os
import queue
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import requests
import pandas as pd

GITHUB_API_URL = "https://api.github.com/users/{username}/repos"

# ---- Dashboard visual tokens -------------------------------------------
PALETTE = ["#E3B341", "#3FB68B", "#A48CF2", "#F2777A",
           "#5FB3E8", "#F2A65A", "#6EE7B7", "#C792EA"]


# =========================================================================
# Core logic (same behavior as the original script, but functions take a
# `log` callback instead of calling print() directly, and fetch_repos
# accepts an optional GitHub token for higher rate limits).
# =========================================================================

def fetch_repos(username, token=None, per_page=100, log=print, cancel_check=None):
    """Fetch all public repositories for a given GitHub username."""
    repos = []
    page = 1
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    while True:
        if cancel_check and cancel_check():
            log("Cancelled.")
            return []

        url = GITHUB_API_URL.format(username=username)
        params = {"per_page": per_page, "page": page, "type": "owner"}

        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
        except requests.exceptions.RequestException as e:
            log(f"Network error while contacting GitHub API: {e}")
            return []

        if response.status_code == 404:
            log(f"Error: GitHub user '{username}' not found.")
            return []
        elif response.status_code == 403:
            log("Error: GitHub API rate limit exceeded. Try again later, "
                "or provide a personal access token for higher limits.")
            return []
        elif response.status_code != 200:
            log(f"Error: GitHub API returned status {response.status_code}.")
            return []

        page_data = response.json()
        if not page_data:
            break

        repos.extend(page_data)
        log(f"Fetched page {page} ({len(page_data)} repos)...")
        page += 1

    return repos


def build_dataframe(repos):
    """Convert raw repo JSON data into a clean Pandas DataFrame."""
    if not repos:
        return pd.DataFrame()

    data = [{
        "name": repo.get("name"),
        "language": repo.get("language") or "Unknown",
        "stars": repo.get("stargazers_count", 0),
        "forks": repo.get("forks_count", 0),
        "open_issues": repo.get("open_issues_count", 0),
        "watchers": repo.get("watchers_count", 0),
        "created_at": repo.get("created_at"),
        "updated_at": repo.get("updated_at"),
        "url": repo.get("html_url"),
    } for repo in repos]

    return pd.DataFrame(data)


def summarize(df, username, log=print):
    """Log sorted views and summary statistics for the DataFrame."""
    if df.empty:
        log("No repository data to summarize.")
        return

    log(f"\n=== Summary for '{username}' ===")
    log(f"Total public repos : {len(df)}")
    log(f"Total stars        : {df['stars'].sum()}")
    log(f"Total forks        : {df['forks'].sum()}")
    log(f"Average stars/repo : {df['stars'].mean():.2f}")

    log("\n--- Top 5 repos by stars ---")
    top_stars = df.sort_values(by="stars", ascending=False).head(5)
    log(top_stars[["name", "stars", "forks", "language"]].to_string(index=False))

    log("\n--- Top 5 repos by forks ---")
    top_forks = df.sort_values(by="forks", ascending=False).head(5)
    log(top_forks[["name", "forks", "stars", "language"]].to_string(index=False))

    log("\n--- Repo count by language ---")
    lang_counts = df["language"].value_counts()
    log(lang_counts.to_string())

    log("\n--- Stars by language (total) ---")
    stars_by_lang = df.groupby("language")["stars"].sum().sort_values(ascending=False)
    log(stars_by_lang.to_string())


def export_to_csv(df, username, out_dir, log=print):
    """Export the DataFrame to a CSV file. Returns the file path or None."""
    if df.empty:
        return None
    filename = os.path.join(out_dir, f"{username}_repos.csv")
    df.to_csv(filename, index=False)
    log(f"\nFull repo data exported to '{filename}'.")
    return filename


# ---- Dashboard (HTML) ---------------------------------------------------

def _lang_color(lang, cache):
    if lang not in cache:
        cache[lang] = PALETTE[len(cache) % len(PALETTE)]
    return cache[lang]


def _commit_graph_svg(df, cache, width=1120, height=140):
    top = df.sort_values("stars", ascending=False).head(16).reset_index(drop=True)
    if top.empty:
        return ""

    max_stars = max(top["stars"].max(), 1)
    n = len(top)
    margin = 60
    step = (width - 2 * margin) / max(n - 1, 1)
    mid_y = height / 2

    circles, labels = [], []
    for i, row in top.iterrows():
        x = margin + i * step
        y = mid_y + (16 if i % 2 == 0 else -16)
        r = 5 + 14 * (row["stars"] / max_stars) ** 0.5
        color = _lang_color(row["language"], cache)
        circles.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{color}" '
            f'fill-opacity="0.9" stroke="#0B0E11" stroke-width="1.5"/>'
        )
        label_y = y + (26 if i % 2 == 0 else -20)
        name = row["name"] if len(row["name"]) <= 14 else row["name"][:13] + "…"
        labels.append(
            f'<text x="{x:.1f}" y="{label_y:.1f}" font-size="10" fill="#8A9199" '
            f'text-anchor="middle" font-family="IBM Plex Mono, monospace">{name}</text>'
        )

    path_pts = " L ".join(f"{margin + i*step:.1f},{mid_y:.1f}" for i in range(n))
    return f'''
    <svg viewBox="0 0 {width} {height}" width="100%" height="{height}"
         xmlns="http://www.w3.org/2000/svg">
      <path d="M {path_pts}" stroke="#232A30" stroke-width="2" fill="none"/>
      {''.join(circles)}
      {''.join(labels)}
    </svg>'''


def generate_dashboard(df, username, out_dir, log=print, auto_open=True):
    """Render an interactive, terminal-inspired HTML dashboard for the repo data."""
    if df.empty:
        log("No data available to build a dashboard.")
        return None

    lang_color_cache = {}
    filename = os.path.join(out_dir, f"{username}_dashboard.html")

    total_repos = len(df)
    total_stars = int(df["stars"].sum())
    total_forks = int(df["forks"].sum())
    avg_stars = df["stars"].mean()

    top10 = df.sort_values("stars", ascending=False).head(10)
    lang_counts = df["language"].value_counts()
    lang_colors = [_lang_color(lang, lang_color_cache) for lang in lang_counts.index]

    bar_fig = {
        "data": [{
            "type": "bar",
            "orientation": "h",
            "x": top10["stars"][::-1].tolist(),
            "y": top10["name"][::-1].tolist(),
            "marker": {"color": "#E3B341"},
            "hovertemplate": "%{y}: %{x} stars<extra></extra>",
        }],
        "layout": {
            "margin": {"l": 140, "r": 20, "t": 10, "b": 30},
            "paper_bgcolor": "rgba(0,0,0,0)",
            "plot_bgcolor": "rgba(0,0,0,0)",
            "font": {"color": "#E6E8EA", "family": "Inter, sans-serif", "size": 12},
            "xaxis": {"gridcolor": "#232A30"},
            "yaxis": {"automargin": True},
            "height": 320,
        },
    }

    pie_fig = {
        "data": [{
            "type": "pie",
            "labels": lang_counts.index.tolist(),
            "values": lang_counts.values.tolist(),
            "hole": 0.55,
            "marker": {"colors": lang_colors},
            "textfont": {"color": "#E6E8EA"},
        }],
        "layout": {
            "margin": {"l": 10, "r": 10, "t": 10, "b": 10},
            "paper_bgcolor": "rgba(0,0,0,0)",
            "font": {"color": "#E6E8EA", "family": "Inter, sans-serif", "size": 12},
            "showlegend": True,
            "legend": {"font": {"color": "#8A9199"}},
            "height": 320,
        },
    }

    scatter_fig = {
        "data": [{
            "type": "scatter",
            "mode": "markers",
            "x": df["stars"].tolist(),
            "y": df["forks"].tolist(),
            "text": df["name"].tolist(),
            "marker": {
                "color": [_lang_color(l, lang_color_cache) for l in df["language"]],
                "size": 10,
                "line": {"color": "#0B0E11", "width": 1},
            },
            "hovertemplate": "%{text}<br>%{x} stars, %{y} forks<extra></extra>",
        }],
        "layout": {
            "margin": {"l": 50, "r": 20, "t": 10, "b": 40},
            "paper_bgcolor": "rgba(0,0,0,0)",
            "plot_bgcolor": "rgba(0,0,0,0)",
            "font": {"color": "#E6E8EA", "family": "Inter, sans-serif", "size": 12},
            "xaxis": {"title": "stars", "gridcolor": "#232A30"},
            "yaxis": {"title": "forks", "gridcolor": "#232A30"},
            "height": 320,
        },
    }

    table_rows = "".join(
        f'''<tr>
              <td>{r["name"]}</td>
              <td class="num">{r["stars"]}</td>
              <td class="num">{r["forks"]}</td>
              <td><span class="chip" style="--chip:{_lang_color(r["language"], lang_color_cache)}">{r["language"]}</span></td>
            </tr>'''
        for _, r in top10.iterrows()
    )

    commit_graph = _commit_graph_svg(df, lang_color_cache)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>github-analyzer :: {username}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>
  :root {{
    --bg: #0B0E11;
    --surface: #12161A;
    --surface-2: #171C21;
    --border: #232A30;
    --text: #E6E8EA;
    --text-dim: #8A9199;
    --gold: #E3B341;
    --teal: #3FB68B;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: 'Inter', system-ui, sans-serif;
  }}
  .wrap {{ max-width: 1200px; margin: 0 auto; padding: 32px 24px 64px; }}

  .prompt {{
    font-family: 'IBM Plex Mono', monospace;
    color: var(--text-dim);
    font-size: 13px;
    margin-bottom: 6px;
  }}
  .prompt .user {{ color: var(--teal); }}
  .prompt .cmd {{ color: var(--gold); }}

  h1 {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 28px;
    font-weight: 600;
    margin: 0 0 28px;
    letter-spacing: -0.02em;
  }}

  .stats {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1px;
    background: var(--border);
    border: 1px solid var(--border);
    margin-bottom: 32px;
  }}
  .stat {{
    background: var(--surface);
    padding: 18px 20px;
  }}
  .stat .label {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    color: var(--text-dim);
    text-transform: lowercase;
  }}
  .stat .label::before {{ content: "> "; color: var(--gold); }}
  .stat .value {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 30px;
    font-weight: 600;
    margin-top: 6px;
  }}

  .section-label {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    color: var(--text-dim);
    text-transform: lowercase;
    margin: 40px 0 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
  }}

  .graph-panel {{
    background: var(--surface);
    border: 1px solid var(--border);
    padding: 16px 8px 4px;
  }}

  .charts {{
    display: grid;
    grid-template-columns: 1.2fr 1fr;
    gap: 1px;
    background: var(--border);
    border: 1px solid var(--border);
  }}
  .chart-card {{
    background: var(--surface);
    padding: 16px;
  }}
  .chart-card .title {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    color: var(--text-dim);
    margin-bottom: 4px;
  }}
  .chart-card.full {{ grid-column: 1 / -1; }}

  table {{
    width: 100%;
    border-collapse: collapse;
    background: var(--surface);
    border: 1px solid var(--border);
    font-size: 13px;
  }}
  th {{
    text-align: left;
    font-family: 'IBM Plex Mono', monospace;
    font-weight: 500;
    font-size: 11px;
    color: var(--text-dim);
    text-transform: lowercase;
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
  }}
  td {{
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
  }}
  td.num {{ font-family: 'IBM Plex Mono', monospace; color: var(--gold); }}
  tr:last-child td {{ border-bottom: none; }}

  .chip {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    color: var(--text-dim);
  }}
  .chip::before {{
    content: "";
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--chip);
  }}

  footer {{
    margin-top: 40px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    color: var(--text-dim);
  }}
</style>
</head>
<body>
<div class="wrap">
  <div class="prompt"><span class="user">guest@github-analyzer</span>:~$ <span class="cmd">analyze</span> {username}</div>
  <h1>Repo dashboard — {username}</h1>

  <div class="stats">
    <div class="stat"><div class="label">total repos</div><div class="value">{total_repos}</div></div>
    <div class="stat"><div class="label">total stars</div><div class="value">{total_stars:,}</div></div>
    <div class="stat"><div class="label">total forks</div><div class="value">{total_forks:,}</div></div>
    <div class="stat"><div class="label">avg stars/repo</div><div class="value">{avg_stars:.1f}</div></div>
  </div>

  <div class="section-label">repo timeline — sized by stars, colored by language</div>
  <div class="graph-panel">{commit_graph}</div>

  <div class="section-label">breakdown</div>
  <div class="charts">
    <div class="chart-card">
      <div class="title">top repos by stars</div>
      <div id="bar"></div>
    </div>
    <div class="chart-card">
      <div class="title">language distribution</div>
      <div id="pie"></div>
    </div>
    <div class="chart-card full">
      <div class="title">stars vs. forks</div>
      <div id="scatter"></div>
    </div>
  </div>

  <div class="section-label">top 10 repos</div>
  <table>
    <thead><tr><th>name</th><th>stars</th><th>forks</th><th>language</th></tr></thead>
    <tbody>{table_rows}</tbody>
  </table>

  <footer>generated by github_repo_analyzer_gui.py</footer>
</div>

<script>
  const cfg = {{displayModeBar: false, responsive: true}};
  Plotly.newPlot("bar", {json.dumps(bar_fig["data"])}, {json.dumps(bar_fig["layout"])}, cfg);
  Plotly.newPlot("pie", {json.dumps(pie_fig["data"])}, {json.dumps(pie_fig["layout"])}, cfg);
  Plotly.newPlot("scatter", {json.dumps(scatter_fig["data"])}, {json.dumps(scatter_fig["layout"])}, cfg);
</script>
</body>
</html>"""

    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)

    log(f"Dashboard generated: '{filename}'.")

    if auto_open:
        filepath = os.path.abspath(filename)
        webbrowser.open(f"file://{filepath}")

    return filename


# =========================================================================
# GUI
# =========================================================================

class AnalyzerApp(tk.Tk):
    BG = "#0B0E11"
    SURFACE = "#12161A"
    BORDER = "#232A30"
    TEXT = "#E6E8EA"
    TEXT_DIM = "#8A9199"
    GOLD = "#E3B341"
    TEAL = "#3FB68B"

    def __init__(self):
        super().__init__()
        self.title("GitHub Repo Analyzer")
        self.geometry("720x560")
        self.minsize(600, 460)
        self.configure(bg=self.BG)

        self.out_dir = os.getcwd()
        self.msg_queue = queue.Queue()
        self.cancel_flag = threading.Event()
        self.worker = None

        self._build_style()
        self._build_widgets()
        self.after(100, self._poll_queue)

    # ---- styling ----
    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=self.BG)
        style.configure("Surface.TFrame", background=self.SURFACE)
        style.configure("TLabel", background=self.BG, foreground=self.TEXT,
                         font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=self.BG, foreground=self.TEXT,
                         font=("Segoe UI Semibold", 18))
        style.configure("Dim.TLabel", background=self.BG, foreground=self.TEXT_DIM,
                         font=("Segoe UI", 9))
        style.configure("TEntry", fieldbackground=self.SURFACE, foreground=self.TEXT,
                         insertcolor=self.TEXT, borderwidth=1)
        style.configure("Accent.TButton", font=("Segoe UI Semibold", 10),
                         padding=8)
        style.map("Accent.TButton",
                  background=[("!disabled", self.GOLD)],
                  foreground=[("!disabled", "#0B0E11")])
        style.configure("Secondary.TButton", font=("Segoe UI", 9), padding=6)

    # ---- layout ----
    def _build_widgets(self):
        pad = {"padx": 20}

        header = ttk.Frame(self, style="TFrame")
        header.pack(fill="x", pady=(20, 4), **pad)
        ttk.Label(header, text="GitHub Repo Analyzer", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="Enter a username below — no terminal needed.",
                  style="Dim.TLabel").pack(anchor="w", pady=(2, 0))

        form = ttk.Frame(self, style="TFrame")
        form.pack(fill="x", pady=(16, 4), **pad)
        form.columnconfigure(0, weight=1)

        ttk.Label(form, text="GitHub username").grid(row=0, column=0, sticky="w")
        self.username_var = tk.StringVar()
        entry = ttk.Entry(form, textvariable=self.username_var, font=("Segoe UI", 12))
        entry.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        entry.bind("<Return>", lambda e: self.on_analyze())
        entry.focus_set()

        adv = ttk.Frame(self, style="TFrame")
        adv.pack(fill="x", pady=(10, 4), **pad)
        adv.columnconfigure(0, weight=1)
        adv.columnconfigure(1, weight=0)

        ttk.Label(adv, text="Personal access token (optional, raises rate limit)").grid(
            row=0, column=0, sticky="w")
        self.token_var = tk.StringVar()
        ttk.Entry(adv, textvariable=self.token_var, show="•").grid(
            row=1, column=0, sticky="ew", pady=(4, 0))

        self.autoopen_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(adv, text="Open dashboard automatically", variable=self.autoopen_var
                         ).grid(row=1, column=1, padx=(12, 0))

        outdir_row = ttk.Frame(self, style="TFrame")
        outdir_row.pack(fill="x", pady=(10, 4), **pad)
        outdir_row.columnconfigure(0, weight=1)
        ttk.Label(outdir_row, text="Output folder").grid(row=0, column=0, sticky="w")
        self.outdir_var = tk.StringVar(value=self.out_dir)
        ttk.Entry(outdir_row, textvariable=self.outdir_var, state="readonly").grid(
            row=1, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(outdir_row, text="Browse…", style="Secondary.TButton",
                   command=self.on_browse).grid(row=1, column=1, padx=(8, 0))

        btn_row = ttk.Frame(self, style="TFrame")
        btn_row.pack(fill="x", pady=(14, 4), **pad)
        self.analyze_btn = ttk.Button(btn_row, text="Analyze", style="Accent.TButton",
                                      command=self.on_analyze)
        self.analyze_btn.pack(side="left")
        self.cancel_btn = ttk.Button(btn_row, text="Cancel", style="Secondary.TButton",
                                     command=self.on_cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=(8, 0))

        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.pack(fill="x", pady=(8, 0), **pad)

        log_frame = ttk.Frame(self, style="TFrame")
        log_frame.pack(fill="both", expand=True, pady=(14, 20), **pad)
        ttk.Label(log_frame, text="Log", style="Dim.TLabel").pack(anchor="w")

        self.log_text = tk.Text(log_frame, bg=self.SURFACE, fg=self.TEXT,
                                insertbackground=self.TEXT, font=("Consolas", 9),
                                relief="flat", wrap="word")
        self.log_text.pack(fill="both", expand=True, pady=(4, 0))
        self.log_text.configure(state="disabled")

    # ---- actions ----
    def on_browse(self):
        chosen = filedialog.askdirectory(initialdir=self.out_dir)
        if chosen:
            self.out_dir = chosen
            self.outdir_var.set(chosen)

    def on_analyze(self):
        username = self.username_var.get().strip()
        if not username:
            messagebox.showwarning("Missing username", "Please enter a GitHub username.")
            return
        if self.worker and self.worker.is_alive():
            return

        self._clear_log()
        self.analyze_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.progress.start(12)
        self.cancel_flag.clear()

        token = self.token_var.get().strip() or None
        auto_open = self.autoopen_var.get()
        out_dir = self.out_dir

        self.worker = threading.Thread(
            target=self._run_analysis,
            args=(username, token, out_dir, auto_open),
            daemon=True,
        )
        self.worker.start()

    def on_cancel(self):
        self.cancel_flag.set()
        self._log("Cancelling after current request...")

    # ---- worker thread ----
    def _run_analysis(self, username, token, out_dir, auto_open):
        def log(msg):
            self.msg_queue.put(("log", str(msg)))

        try:
            log(f"Fetching repositories for '{username}'...")
            repos = fetch_repos(username, token=token, log=log,
                                cancel_check=self.cancel_flag.is_set)

            if self.cancel_flag.is_set():
                self.msg_queue.put(("done", None))
                return

            df = build_dataframe(repos)
            summarize(df, username, log=log)
            csv_path = export_to_csv(df, username, out_dir, log=log)
            dash_path = generate_dashboard(df, username, out_dir, log=log,
                                           auto_open=auto_open)
            self.msg_queue.put(("result", (csv_path, dash_path)))
        except Exception as e:
            log(f"Unexpected error: {e}")
        finally:
            self.msg_queue.put(("done", None))

    # ---- queue polling (keeps Tk calls on the main thread) ----
    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "result":
                    csv_path, dash_path = payload
                    if csv_path or dash_path:
                        self._log("\nDone. Files saved to: " + self.out_dir)
                elif kind == "done":
                    self.progress.stop()
                    self.analyze_btn.configure(state="normal")
                    self.cancel_btn.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _log(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", str(msg) + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")


def main():
    app = AnalyzerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
