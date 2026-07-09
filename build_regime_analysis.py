from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parent
    sys.path.insert(0, str(project_root / "src"))

    from price_action.regime_analysis import main as regime_analysis_main

    regime_analysis_main()


if __name__ == "__main__":
    main()
