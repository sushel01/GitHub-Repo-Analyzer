import os
import time
from typing import Optional

import requests

from config import API_ROOT, USER_AGENT, get_logger

log = get_logger()


class RepoAnalyzerError(Exception):
    """Raised for unrecoverable analyzer failures (bad user, auth, network)."""


class GitHubClient:
    """Thin wrapper around the GitHub REST API with auth + retry/backoff."""

    def __init__(self, token: Optional[str] = None, timeout: int = 15):
        self.session = requests.Session()
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        token = token or os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
            log.info("Using authenticated requests (higher rate limit).")
        else:
            log.info("No token provided; using unauthenticated requests (60 req/hr limit).")
        self.session.headers.update(headers)
        self.timeout = timeout

    def _get(self, url: str, params: Optional[dict] = None) -> requests.Response:
        """GET with automatic handling of GitHub's primary rate limit."""
        resp = None
        for _ in range(3):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
            except requests.exceptions.RequestException as e:
                raise RepoAnalyzerError(f"Network error contacting GitHub: {e}")

            if resp.status_code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0":
                reset = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
                wait = max(reset - time.time(), 1)
                log.warning("Rate limit hit. Waiting %.0fs for reset...", wait)
                time.sleep(min(wait, 60))
                continue
            return resp
        return resp

    def get_user(self, username: str) -> dict:
        resp = self._get(f"{API_ROOT}/users/{username}")
        if resp.status_code == 404:
            raise RepoAnalyzerError(f"GitHub user '{username}' not found.")
        if resp.status_code != 200:
            raise RepoAnalyzerError(f"GitHub API returned {resp.status_code} fetching user profile.")
        return resp.json()

    def get_repos(self, username: str, include_forks: bool = True, per_page: int = 100) -> list:
        repos = []
        page = 1
        while True:
            resp = self._get(
                f"{API_ROOT}/users/{username}/repos",
                params={"per_page": per_page, "page": page, "type": "owner", "sort": "updated"},
            )
            if resp.status_code == 404:
                raise RepoAnalyzerError(f"GitHub user '{username}' not found.")
            if resp.status_code != 200:
                raise RepoAnalyzerError(f"GitHub API returned {resp.status_code} fetching repos.")

            batch = resp.json()
            if not batch:
                break
            repos.extend(batch)
            page += 1

        if not include_forks:
            repos = [r for r in repos if not r.get("fork")]
        return repos
