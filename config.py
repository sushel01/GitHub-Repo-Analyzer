import logging

API_ROOT = "https://api.github.com"
USER_AGENT = "github-repo-analyzer/3.0 (+desktop-app)"

# Terminal/git-inspired accent palette, reused in the dashboard HTML.
PALETTE = [
    "#E3B341", "#3FB68B", "#A48CF2", "#F2777A",
    "#5FB3E8", "#F2A65A", "#6EE7B7", "#C792EA",
]

# Dark theme tokens shared between the desktop GUI and the generated
# HTML dashboard so the two feel like one product.
THEME = {
    "bg": "#0B0E11",
    "surface": "#12161A",
    "surface_2": "#171C21",
    "border": "#232A30",
    "text": "#E6E8EA",
    "text_dim": "#8A9199",
    "gold": "#E3B341",
    "teal": "#3FB68B",
    "red": "#F2777A",
}

LOGGER_NAME = "repo_analyzer"


def get_logger() -> logging.Logger:
    """Return the shared application logger (console handler attached once)."""
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s", "%H:%M:%S"))
        logger.addHandler(handler)
    return logger
