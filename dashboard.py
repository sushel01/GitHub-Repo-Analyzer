import json
import os
import webbrowser
from typing import Optional

import pandas as pd

from config import PALETTE, get_logger

log = get_logger()


def _lang_color_map(languages) -> dict:
    return {lang: PALETTE[i % len(PALETTE)] for i, lang in enumerate(languages)}


def _heatmap_svg(heatmap: list, width: int = 1040) -> str:
    """GitHub-contribution-style heatmap of repo creation activity (24 months)."""
    if not heatmap:
        return ""
    cell, gap = 26, 6
    max_count = max((h["count"] for h in heatmap), default=0) or 1
    height = cell + 40

    def color(count: int) -> str:
        if count == 0:
            return "#171C21"
        ratio = count / max_count
        if ratio > 0.75:
            return "#3FB68B"
        if ratio > 0.5:
            return "#2E8B63"
        if ratio > 0.25:
            return "#1F5C42"
        return "#173C2E"

    cells, labels = [], []
    for i, h in enumerate(heatmap):
        x = i * (cell + gap)
        cells.append(
            f'<rect x="{x}" y="0" width="{cell}" height="{cell}" rx="4" '
            f'fill="{color(h["count"])}" stroke="#0B0E11" stroke-width="1">'
            f'<title>{h["label"]}: {h["count"]} repo(s) created</title></rect>'
        )
        if i % 3 == 0:
            labels.append(
                f'<text x="{x}" y="{cell + 18}" font-size="10" fill="#8A9199" '
                f'font-family="IBM Plex Mono, monospace">{h["label"]}</text>'
            )

    svg_width = len(heatmap) * (cell + gap)
    return (
        f'<svg viewBox="0 0 {max(svg_width, width)} {height}" width="100%" '
        f'height="{height}" xmlns="http://www.w3.org/2000/svg">'
        f'{"".join(cells)}{"".join(labels)}</svg>'
    )


def _commit_graph_svg(df: pd.DataFrame, lang_colors: dict, width: int = 1040, height: int = 140) -> str:
    """Repos plotted as dots along a git-log-style line, sized by stars."""
    top = df.sort_values("stars", ascending=False).head(14).reset_index(drop=True)
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
        color = lang_colors.get(row["language"], "#8A9199")
        circles.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{color}" '
            f'fill-opacity="0.9" stroke="#0B0E11" stroke-width="1.5">'
            f'<title>{row["name"]}: {row["stars"]} stars</title></circle>'
        )
        label_y = y + (26 if i % 2 == 0 else -20)
        name = row["name"] if len(row["name"]) <= 14 else row["name"][:13] + "…"
        labels.append(
            f'<text x="{x:.1f}" y="{label_y:.1f}" font-size="10" fill="#8A9199" '
            f'text-anchor="middle" font-family="IBM Plex Mono, monospace">{name}</text>'
        )

    path_pts = " L ".join(f"{margin + i * step:.1f},{mid_y:.1f}" for i in range(n))
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<path d="M {path_pts}" stroke="#232A30" stroke-width="2" fill="none"/>'
        f'{"".join(circles)}{"".join(labels)}</svg>'
    )


CSS = """
:root {
  --bg: #0B0E11; --surface: #12161A; --surface-2: #171C21;
  --border: #232A30; --text: #E6E8EA; --text-dim: #8A9199;
  --gold: #E3B341; --teal: #3FB68B; --red: #F2777A;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font-family: 'Inter', system-ui, sans-serif; }
.wrap { max-width: 1200px; margin: 0 auto; padding: 32px 24px 64px; }
.profile { display: flex; align-items: center; gap: 18px; margin-bottom: 24px; }
.profile img { width: 64px; height: 64px; border-radius: 8px; border: 1px solid var(--border); }
.profile .name { font-size: 20px; font-weight: 700; }
.profile .handle { color: var(--text-dim); font-family: 'IBM Plex Mono', monospace; font-size: 13px; }
.profile .bio { color: var(--text-dim); font-size: 13px; margin-top: 4px; max-width: 640px; }
.prompt { font-family: 'IBM Plex Mono', monospace; color: var(--text-dim); font-size: 13px; margin-bottom: 6px; }
.prompt .user { color: var(--teal); } .prompt .cmd { color: var(--gold); }
h1 { font-family: 'IBM Plex Mono', monospace; font-size: 26px; font-weight: 600; margin: 0 0 24px; letter-spacing: -0.02em; }
.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px; background: var(--border); border: 1px solid var(--border); margin-bottom: 24px; }
.stat { background: var(--surface); padding: 18px 20px; }
.stat .label { font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: var(--text-dim); text-transform: lowercase; }
.stat .label::before { content: "> "; color: var(--gold); }
.stat .value { font-family: 'IBM Plex Mono', monospace; font-size: 28px; font-weight: 600; margin-top: 6px; }
.stat .sub { font-size: 11px; color: var(--text-dim); margin-top: 4px; }
.section-label { font-family: 'IBM Plex Mono', monospace; font-size: 12px; color: var(--text-dim); text-transform: lowercase; margin: 36px 0 12px; padding-bottom: 8px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; }
.graph-panel { background: var(--surface); border: 1px solid var(--border); padding: 16px 8px 4px; overflow-x: auto; }
.charts { display: grid; grid-template-columns: 1.2fr 1fr; gap: 1px; background: var(--border); border: 1px solid var(--border); }
.chart-card { background: var(--surface); padding: 16px; }
.chart-card .title { font-family: 'IBM Plex Mono', monospace; font-size: 12px; color: var(--text-dim); margin-bottom: 4px; }
.chart-card.full { grid-column: 1 / -1; }
.table-toolbar { display: flex; gap: 8px; margin-bottom: 8px; }
.table-toolbar input { flex: 1; background: var(--surface); border: 1px solid var(--border); color: var(--text); padding: 8px 12px; font-family: 'IBM Plex Mono', monospace; font-size: 12px; border-radius: 4px; }
.table-toolbar input:focus { outline: 1px solid var(--gold); }
table { width: 100%; border-collapse: collapse; background: var(--surface); border: 1px solid var(--border); font-size: 13px; }
th { text-align: left; font-family: 'IBM Plex Mono', monospace; font-weight: 500; font-size: 11px; color: var(--text-dim); text-transform: lowercase; padding: 10px 14px; border-bottom: 1px solid var(--border); cursor: pointer; user-select: none; white-space: nowrap; }
th:hover { color: var(--text); }
td { padding: 10px 14px; border-bottom: 1px solid var(--border); }
td.num { font-family: 'IBM Plex Mono', monospace; color: var(--gold); }
tr:last-child td { border-bottom: none; }
tr:hover td { background: var(--surface-2); }
a.repo-link { color: var(--text); text-decoration: none; }
a.repo-link:hover { color: var(--teal); text-decoration: underline; }
.chip { display: inline-flex; align-items: center; gap: 6px; font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: var(--text-dim); }
.chip::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--chip); }
.badge { display: inline-block; font-size: 10px; padding: 2px 6px; border-radius: 3px; font-family: 'IBM Plex Mono', monospace; margin-left: 6px; }
.badge.archived { background: rgba(242,119,122,0.15); color: var(--red); }
.badge.fork { background: rgba(95,179,232,0.15); color: #5FB3E8; }
footer { margin-top: 40px; font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: var(--text-dim); }
@media (max-width: 720px) {
  .stats { grid-template-columns: repeat(2, 1fr); }
  .charts { grid-template-columns: 1fr; }
}
"""

JS_TEMPLATE = """
const cfg = {displayModeBar: false, responsive: true};
Plotly.newPlot("bar", ##BAR_DATA##.data, ##BAR_DATA##.layout, cfg);
Plotly.newPlot("pie", ##PIE_DATA##.data, ##PIE_DATA##.layout, cfg);
Plotly.newPlot("scatter", ##SCATTER_DATA##.data, ##SCATTER_DATA##.layout, cfg);
Plotly.newPlot("yearline", ##YEAR_DATA##.data, ##YEAR_DATA##.layout, cfg);

// --- table search filter ---
const searchInput = document.getElementById("repo-search");
const rows = Array.from(document.querySelectorAll("#repo-table tbody tr"));
searchInput.addEventListener("input", () => {
  const q = searchInput.value.toLowerCase();
  rows.forEach(r => {
    r.style.display = r.dataset.search.includes(q) ? "" : "none";
  });
});

// --- table sort ---
document.querySelectorAll("#repo-table th[data-key]").forEach(th => {
  th.addEventListener("click", () => {
    const key = th.dataset.key;
    const numeric = th.dataset.numeric === "1";
    const asc = th.dataset.asc !== "true";
    document.querySelectorAll("#repo-table th").forEach(h => h.removeAttribute("data-asc"));
    th.dataset.asc = asc;
    const tbody = document.querySelector("#repo-table tbody");
    const sorted = rows.slice().sort((a, b) => {
      let va = a.dataset[key], vb = b.dataset[key];
      if (numeric) { va = parseFloat(va); vb = parseFloat(vb); }
      if (va < vb) return asc ? -1 : 1;
      if (va > vb) return asc ? 1 : -1;
      return 0;
    });
    sorted.forEach(r => tbody.appendChild(r));
  });
});
"""


def generate_dashboard(df: pd.DataFrame, stats: dict, user: dict, username: str,
                        out_dir: str, open_browser: bool = True) -> Optional[str]:
    """Render a polished, self-contained HTML dashboard. Returns the file path."""
    if df.empty:
        log.warning("No data available to build a dashboard.")
        return None

    lang_colors = _lang_color_map(stats["lang_counts"].index)
    top10 = stats["top_by_stars"]

    bar_fig = {
        "data": [{
            "type": "bar", "orientation": "h",
            "x": top10["stars"][::-1].tolist(),
            "y": top10["name"][::-1].tolist(),
            "marker": {"color": "#E3B341"},
            "hovertemplate": "%{y}: %{x} stars<extra></extra>",
        }],
        "layout": {
            "margin": {"l": 140, "r": 20, "t": 10, "b": 30},
            "paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)",
            "font": {"color": "#E6E8EA", "family": "Inter, sans-serif", "size": 12},
            "xaxis": {"gridcolor": "#232A30"}, "yaxis": {"automargin": True},
            "height": 300,
        },
    }

    pie_fig = {
        "data": [{
            "type": "pie",
            "labels": stats["lang_counts"].index.tolist(),
            "values": stats["lang_counts"].values.tolist(),
            "hole": 0.55,
            "marker": {"colors": [lang_colors[l] for l in stats["lang_counts"].index]},
            "textfont": {"color": "#E6E8EA"},
        }],
        "layout": {
            "margin": {"l": 10, "r": 10, "t": 10, "b": 10},
            "paper_bgcolor": "rgba(0,0,0,0)",
            "font": {"color": "#E6E8EA", "family": "Inter, sans-serif", "size": 12},
            "showlegend": True, "legend": {"font": {"color": "#8A9199"}},
            "height": 300,
        },
    }

    scatter_fig = {
        "data": [{
            "type": "scatter", "mode": "markers",
            "x": df["stars"].tolist(), "y": df["forks"].tolist(),
            "text": df["name"].tolist(),
            "marker": {
                "color": [lang_colors.get(l, "#8A9199") for l in df["language"]],
                "size": 10, "line": {"color": "#0B0E11", "width": 1},
            },
            "hovertemplate": "%{text}<br>%{x} stars, %{y} forks<extra></extra>",
        }],
        "layout": {
            "margin": {"l": 50, "r": 20, "t": 10, "b": 40},
            "paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)",
            "font": {"color": "#E6E8EA", "family": "Inter, sans-serif", "size": 12},
            "xaxis": {"title": "stars", "gridcolor": "#232A30"},
            "yaxis": {"title": "forks", "gridcolor": "#232A30"},
            "height": 300,
        },
    }

    year_series = stats["by_year"]
    year_fig = {
        "data": [{
            "type": "scatter", "mode": "lines+markers",
            "x": [str(y) for y in year_series.index.tolist()],
            "y": year_series.values.tolist(),
            "line": {"color": "#3FB68B", "width": 2},
            "marker": {"color": "#3FB68B", "size": 7},
            "fill": "tozeroy", "fillcolor": "rgba(63,182,139,0.1)",
        }],
        "layout": {
            "margin": {"l": 40, "r": 20, "t": 10, "b": 30},
            "paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)",
            "font": {"color": "#E6E8EA", "family": "Inter, sans-serif", "size": 12},
            "xaxis": {"gridcolor": "#232A30"}, "yaxis": {"gridcolor": "#232A30", "title": "repos created"},
            "height": 260,
        },
    }

    def table_row(r) -> str:
        badges = ""
        if r["is_archived"]:
            badges += '<span class="badge archived">archived</span>'
        if r["is_fork"]:
            badges += '<span class="badge fork">fork</span>'
        search_blob = f'{r["name"]} {r["language"]}'.lower()
        created = r["created_at"].strftime("%Y-%m-%d") if pd.notna(r["created_at"]) else ""
        return (
            f'<tr data-search="{search_blob}" data-name="{r["name"]}" '
            f'data-stars="{r["stars"]}" data-forks="{r["forks"]}" data-created="{created}">'
            f'<td><a class="repo-link" href="{r["url"]}" target="_blank" rel="noopener">{r["name"]}</a>{badges}</td>'
            f'<td class="num">{r["stars"]}</td>'
            f'<td class="num">{r["forks"]}</td>'
            f'<td><span class="chip" style="--chip:{lang_colors.get(r["language"], "#8A9199")}">{r["language"]}</span></td>'
            f'<td>{r["license"]}</td>'
            f'<td>{created}</td>'
            f"</tr>"
        )

    table_rows = "".join(table_row(r) for _, r in df.sort_values("stars", ascending=False).iterrows())

    commit_graph = _commit_graph_svg(df, lang_colors)
    heatmap_svg = _heatmap_svg(stats["heatmap"])

    avatar = user.get("avatar_url", "")
    display_name = user.get("name") or username
    bio = user.get("bio") or ""
    followers = user.get("followers", 0)
    following = user.get("following", 0)

    js = (
        JS_TEMPLATE
        .replace("##BAR_DATA##", json.dumps(bar_fig))
        .replace("##PIE_DATA##", json.dumps(pie_fig))
        .replace("##SCATTER_DATA##", json.dumps(scatter_fig))
        .replace("##YEAR_DATA##", json.dumps(year_fig))
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>github-analyzer :: {username}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <div class="prompt"><span class="user">guest@github-analyzer</span>:~$ <span class="cmd">analyze</span> {username}</div>

  <div class="profile">
    {f'<img src="{avatar}" alt="{username} avatar">' if avatar else ''}
    <div>
      <div class="name">{display_name}</div>
      <div class="handle">@{username} · {followers} followers · {following} following</div>
      {f'<div class="bio">{bio}</div>' if bio else ''}
    </div>
  </div>

  <h1>Repository dashboard</h1>

  <div class="stats">
    <div class="stat"><div class="label">total repos</div><div class="value">{stats['total_repos']}</div>
      <div class="sub">{stats['fork_count']} forked · {stats['archived_count']} archived</div></div>
    <div class="stat"><div class="label">total stars</div><div class="value">{stats['total_stars']:,}</div>
      <div class="sub">avg {stats['avg_stars']:.1f} / repo</div></div>
    <div class="stat"><div class="label">total forks</div><div class="value">{stats['total_forks']:,}</div>
      <div class="sub">{stats['total_open_issues']:,} open issues</div></div>
    <div class="stat"><div class="label">stale repos</div><div class="value">{stats['stale_count']}</div>
      <div class="sub">no push in 365+ days</div></div>
  </div>

  <div class="section-label"><span>repo creation activity — last 24 months</span></div>
  <div class="graph-panel">{heatmap_svg}</div>

  <div class="section-label"><span>repo timeline — sized by stars, colored by language</span></div>
  <div class="graph-panel">{commit_graph}</div>

  <div class="section-label"><span>breakdown</span></div>
  <div class="charts">
    <div class="chart-card">
      <div class="title">top repos by stars</div>
      <div id="bar"></div>
    </div>
    <div class="chart-card">
      <div class="title">language distribution</div>
      <div id="pie"></div>
    </div>
    <div class="chart-card">
      <div class="title">stars vs. forks</div>
      <div id="scatter"></div>
    </div>
    <div class="chart-card">
      <div class="title">repos created per year</div>
      <div id="yearline"></div>
    </div>
  </div>

  <div class="section-label"><span>all repositories ({stats['total_repos']})</span></div>
  <div class="table-toolbar">
    <input id="repo-search" type="text" placeholder="Filter by name or language...">
  </div>
  <table id="repo-table">
    <thead>
      <tr>
        <th data-key="name">name</th>
        <th data-key="stars" data-numeric="1">stars</th>
        <th data-key="forks" data-numeric="1">forks</th>
        <th>language</th>
        <th>license</th>
        <th data-key="created" data-numeric="0">created</th>
      </tr>
    </thead>
    <tbody>{table_rows}</tbody>
  </table>

  <footer>generated by GitHub Repo Analyzer</footer>
</div>

<script>{js}</script>
</body>
</html>"""

    path = os.path.join(out_dir, f"{username}_dashboard.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    log.info("Dashboard generated -> %s", path)

    if open_browser:
        webbrowser.open(f"file://{os.path.abspath(path)}")
    return path
