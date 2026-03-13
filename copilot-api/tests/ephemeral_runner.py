from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid


def run_ephemeral_script(script_contents: str, *, command: list[str]) -> int:
    """
    Creates a dedicated temp folder, writes the script, executes it, then deletes it.
    This satisfies the V1 requirement for dynamic test scripts.
    """
    base = os.path.join(tempfile.gettempdir(), "copilot-tests", str(uuid.uuid4()))
    os.makedirs(base, exist_ok=True)
    script_path = os.path.join(base, "script.tmp")
    try:
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script_contents)
        completed = subprocess.run(command, cwd=base, check=False)
        return int(completed.returncode)
    finally:
        shutil.rmtree(base, ignore_errors=True)

