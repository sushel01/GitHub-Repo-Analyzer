from dataclasses import dataclass, field
from typing import Optional

from config import get_logger
from github_client import GitHubClient, RepoAnalyzerError
from data_processor import build_dataframe, compute_summary, summary_text
from exporters import export_csv, export_json
from dashboard import generate_dashboard

log = get_logger()


@dataclass
class AnalysisOptions:
    username: str
    token: Optional[str] = None
    output_dir: str = "."
    min_stars: int = 0
    exclude_forks: bool = False
    exclude_archived: bool = False
    export_csv_file: bool = True
    export_json_file: bool = True
    export_html: bool = True
    open_browser: bool = True


@dataclass
class AnalysisResult:
    username: str
    stats: dict = field(default_factory=dict)
    summary: str = ""
    csv_path: Optional[str] = None
    json_path: Optional[str] = None
    html_path: Optional[str] = None


def run_analysis(opts: AnalysisOptions) -> AnalysisResult:
    """Run one full analysis pass. Raises RepoAnalyzerError on failure."""
    username = opts.username.strip()
    if not username:
        raise RepoAnalyzerError("Username cannot be empty.")

    client = GitHubClient(token=opts.token)

    log.info("Fetching profile for '%s'...", username)
    user = client.get_user(username)

    log.info("Fetching repositories for '%s'...", username)
    raw_repos = client.get_repos(username, include_forks=not opts.exclude_forks)

    df = build_dataframe(raw_repos)
    if not df.empty:
        if opts.min_stars:
            df = df[df["stars"] >= opts.min_stars]
        if opts.exclude_archived:
            df = df[~df["is_archived"]]

    if df.empty:
        raise RepoAnalyzerError(
            f"No repositories found for '{username}' matching the given filters."
        )

    stats = compute_summary(df)
    result = AnalysisResult(username=username, stats=stats, summary=summary_text(username, stats))

    if opts.export_csv_file:
        result.csv_path = export_csv(df, username, opts.output_dir)
    if opts.export_json_file:
        result.json_path = export_json(df, username, opts.output_dir)
    if opts.export_html:
        result.html_path = generate_dashboard(
            df, stats, user, username, opts.output_dir, open_browser=opts.open_browser
        )

    return result
