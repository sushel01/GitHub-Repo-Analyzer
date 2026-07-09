
import os
from typing import Optional

import pandas as pd

from config import get_logger

log = get_logger()


def export_csv(df: pd.DataFrame, username: str, out_dir: str) -> Optional[str]:
    if df.empty:
        return None
    path = os.path.join(out_dir, f"{username}_repos.csv")
    df.to_csv(path, index=False)
    log.info("CSV exported -> %s", path)
    return path


def export_json(df: pd.DataFrame, username: str, out_dir: str) -> Optional[str]:
    if df.empty:
        return None
    path = os.path.join(out_dir, f"{username}_repos.json")
    df.to_json(path, orient="records", date_format="iso", indent=2)
    log.info("JSON exported -> %s", path)
    return path
