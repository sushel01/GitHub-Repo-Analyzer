# GitHub Repo Analyzer

A desktop app that analyzes any GitHub user's public repositories and
generates an interactive HTML dashboard.
Enter a username in the window, click **Analyze**, and the dashboard
opens in your browser automatically.

## Running it

1. Install the two dependencies (one time only):
   ```bash
   pip install -r requirements.txt
   ```
2. Launch the app:
   ```bash
   python main.py
   ```

   *(Windows tip: rename `main.py` to `main.pyw` and double-click it
   directly — no console window will appear at all.)*

# Project structure

| File               | Responsibility                                              |
|---------------------|---------------------------------------------------------------|
| `main.py`           | Entry point — launches the window                            |
| `gui.py`            | The tkinter desktop UI (the only file that imports tkinter)  |
| `analyzer.py`       | Orchestrates fetch → process → export → dashboard             |
| `github_client.py`  | GitHub REST API calls, auth, rate-limit retry                |
| `models.py`         | The `Repo` data model                                        |
| `data_processor.py` | Builds the DataFrame and computes summary statistics          |
| `dashboard.py`      | Renders the self-contained HTML dashboard                    |
| `exporters.py`      | Writes CSV / JSON files                                      |
| `config.py`         | Shared constants, color palette, logging setup                |

