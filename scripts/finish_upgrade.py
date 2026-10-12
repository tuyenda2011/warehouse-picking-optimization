"""Run the authorized validation/holdout sequence with durable progress across chat interruptions."""
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "tmp/upgrade-pipeline-status.json"


def status(stage, state, **extra):
    value = {"stage": stage, "state": state, "updated_utc": datetime.now(timezone.utc).isoformat(), **extra}
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2)+"\n", encoding="utf-8")
    temporary.replace(STATE)


def main():
    commands = [
        ("tests", ["-m", "pytest", "-q", "--disable-warnings", "--basetemp", "tmp/upgrade-durable-suite"]),
        ("historical", ["-X", "utf8", "report/verify_historical.py", "--workspace", "tmp/historical-upgrade-verification-v2"]),
        ("tiny_exact", ["-X", "utf8", "report/upgrade_exact.py"]),
        ("holdout", ["-X", "utf8", "scripts/upgrade_study_driver.py", "holdout"]),
        ("study_verify", ["-X", "utf8", "scripts/upgrade_study_driver.py", "verify"]),
        ("analysis", ["-X", "utf8", "report/analyze_upgrade.py"]),
    ]
    for stage, args in commands:
        logfile = ROOT / "tmp" / f"upgrade-durable-{stage}.log"
        if logfile.exists():
            raise RuntimeError("Refusing to replace pipeline stage log: " + stage)
        status(stage, "running", log=str(logfile))
        with logfile.open("x", encoding="utf-8") as stream:
            child = subprocess.Popen([sys.executable, *args], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
            status(stage, "running", log=str(logfile), child_pid=child.pid)
            code = child.wait()
        if code:
            status(stage, "failed", exit_code=code, log=str(logfile))
            return code
        status(stage, "passed", log=str(logfile))
    status("analysis", "complete")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        status("pipeline", "failed", error=str(exc))
        raise
