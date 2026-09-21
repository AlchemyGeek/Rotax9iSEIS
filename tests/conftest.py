import importlib.util
import sys
from pathlib import Path

import pytest

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = TOOLKIT_ROOT / "data" / "logs"
REPORTS_DIR = TOOLKIT_ROOT / "data" / "reports"
GOLDEN_DIR = Path(__file__).resolve().parent / "characterization" / "golden"

sys.path.insert(0, str(TOOLKIT_ROOT))

requires_flight_logs = pytest.mark.skipif(
    not LOGS_DIR.is_dir() or not any(LOGS_DIR.glob("*.csv")),
    reason="No flight logs in data/logs/ — these are private and gitignored, "
           "so this environment has none to characterize against.",
)

requires_golden_fixtures = pytest.mark.skipif(
    not GOLDEN_DIR.is_dir(),
    reason="No frozen golden fixtures in tests/characterization/golden/ — "
           "these are derived from private flight data and gitignored. "
           "Generate them locally before running characterization tests "
           "(see tests/characterization/README.md).",
)


def import_notebook(name: str):
    """Import a notebooks/NN_name.py module by file path.

    Notebook filenames start with digits (e.g. 04_flight_report.py) so they
    aren't valid dotted module names for a normal `import` statement.
    """
    path = TOOLKIT_ROOT / "notebooks" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
