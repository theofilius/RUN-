"""Start the dashboard here, on your computer or online:

    streamlit run app/main.py

It runs app/dashboard.py one visitor at a time (the runner's settings are shared
by the whole server process, see src/athlete.py), and with DATA_STORE=supabase
keeps data/ in Supabase: pulled when the server starts, changes uploaded after
every page run (src/cloud.py).
"""

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import cloud  # noqa: E402  (needs the project root on the path)

DASHBOARD = Path(__file__).resolve().parent / "dashboard.py"

with cloud.LOCK:
    store = cloud.storage() if cloud.active() else None
    if store:
        cloud.pull_once(store)
    before = cloud.snapshot() if store else None
    try:
        runpy.run_path(str(DASHBOARD), run_name="__main__")
    finally:
        # also after st.stop() and st.rerun(), which end a run with an exception
        if store:
            cloud.push(store, before)
