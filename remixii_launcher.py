import sys
import tempfile
import traceback
from pathlib import Path


def _prepare_logs() -> None:
    if sys.stdout is not None and sys.stderr is not None:
        return
    log_path = Path(tempfile.gettempdir()) / "remixii-startup.log"
    stream = log_path.open("a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


if __name__ == "__main__":
    try:
        _prepare_logs()
        from remixii.app import main

        main()
    except Exception:
        traceback.print_exc()
        raise
