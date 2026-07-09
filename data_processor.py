
from collections import defaultdict
from dataclasses import asdict

import pandas as pd

from models import Repo


def build_dataframe(repos: list) -> pd.DataFrame:
    """Convert raw repo JSON into a typed, analysis-ready DataFrame."""
    if not repos:
        return pd.DataFrame()

    records = [asdict(Repo.from_api(r)) for r in repos]
    df = pd.DataFrame(records)
    df["topics"] = df["topics"].apply(lambda t: ", ".join(t) if t else "")
    for col in ("created_at", "updated_at", "pushed_at"):
        df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
    return df


def compute_summary(df: pd.DataFrame) -> dict:
    """Derive every aggregate metric the console/GUI output and dashboard need."""
    if df.empty:
        return {}

    now = pd.Timestamp.now(tz="UTC")
    stale_cutoff = now - pd.Timedelta(days=365)

    lang_counts = df["language"].value_counts()
    stars_by_lang = df.groupby("language")["stars"].sum().sort_values(ascending=False)

    by_year = (
        df.dropna(subset=["created_at"])
        .assign(year=lambda d: d["created_at"].dt.year)
        .groupby("year")
        .size()
    )

    # Month x Year grid for the contribution-style heatmap (last 24 months)
    months = pd.date_range(end=now, periods=24, freq="MS", tz="UTC")
    heat_counts = defaultdict(int)
    for ts in df["created_at"].dropna():
        heat_counts[(ts.year, ts.month)] += 1
    heatmap = [
        {"year": m.year, "month": m.month, "label": m.strftime("%b %Y"),
         "count": heat_counts.get((m.year, m.month), 0)}
        for m in months
    ]

    return {
        "total_repos": int(len(df)),
        "total_stars": int(df["stars"].sum()),
        "total_forks": int(df["forks"].sum()),
        "total_open_issues": int(df["open_issues"].sum()),
        "avg_stars": float(df["stars"].mean()),
        "median_stars": float(df["stars"].median()),
        "archived_count": int(df["is_archived"].sum()),
        "fork_count": int(df["is_fork"].sum()),
        "stale_count": int((df["pushed_at"] < stale_cutoff).sum()),
        "lang_counts": lang_counts,
        "stars_by_lang": stars_by_lang,
        "by_year": by_year,
        "heatmap": heatmap,
        "top_by_stars": df.sort_values("stars", ascending=False).head(10),
        "top_by_forks": df.sort_values("forks", ascending=False).head(10),
    }


def summary_text(username: str, stats: dict) -> str:
    """Plain-text version of the summary, used by both console and GUI log."""
    if not stats:
        return f"No repository data to summarize for '{username}'."

    lines = [
        f"SUMMARY: {username}",
        f"Public repos        : {stats['total_repos']}",
        f"Total stars         : {stats['total_stars']:,}",
        f"Total forks         : {stats['total_forks']:,}",
        f"Open issues         : {stats['total_open_issues']:,}",
        f"Avg / median stars  : {stats['avg_stars']:.2f} / {stats['median_stars']:.1f}",
        f"Forked repos        : {stats['fork_count']}",
        f"Archived repos      : {stats['archived_count']}",
        f"Stale (>1yr no push): {stats['stale_count']}",
    ]
    return "\n".join(lines)
