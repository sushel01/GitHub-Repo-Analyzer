from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Repo:
    name: str
    full_name: str
    language: str
    stars: int
    forks: int
    open_issues: int
    watchers: int
    size_kb: int
    is_fork: bool
    is_archived: bool
    license: str
    topics: list = field(default_factory=list)
    default_branch: str = "main"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    pushed_at: Optional[str] = None
    url: str = ""

    @classmethod
    def from_api(cls, raw: dict) -> "Repo":
        lic = raw.get("license") or {}
        return cls(
            name=raw.get("name", ""),
            full_name=raw.get("full_name", ""),
            language=raw.get("language") or "Unknown",
            stars=raw.get("stargazers_count", 0) or 0,
            forks=raw.get("forks_count", 0) or 0,
            open_issues=raw.get("open_issues_count", 0) or 0,
            watchers=raw.get("watchers_count", 0) or 0,
            size_kb=raw.get("size", 0) or 0,
            is_fork=bool(raw.get("fork", False)),
            is_archived=bool(raw.get("archived", False)),
            license=lic.get("spdx_id") or "None",
            topics=raw.get("topics", []) or [],
            default_branch=raw.get("default_branch", "main"),
            created_at=raw.get("created_at"),
            updated_at=raw.get("updated_at"),
            pushed_at=raw.get("pushed_at"),
            url=raw.get("html_url", ""),
        )
