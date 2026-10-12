"""Preserve the pre-upgrade code and report without touching historical results."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "tmp/high-score-before-20261010"

if __name__ == "__main__":
    DEST.mkdir(exist_ok=False)
    entries = []
    for directory in ("src", "scripts", "tests", "demo", "configs"):
        for source in sorted((ROOT / directory).rglob("*")):
            if source.is_file() and "__pycache__" not in source.parts:
                entries.append(source)
    entries += [ROOT / "report.zip", ROOT / "report/main.pdf", ROOT / "report/main.tex",
                ROOT / "report/QUALITY_REVIEW.md", ROOT / "report/DEFENSE_GUIDE.md",
                ROOT / "report/README.md", ROOT / "README.md", ROOT / "pyproject.toml"]
    entries += list((ROOT / "report/section").rglob("*.tex"))
    manifest = {}
    for source in entries:
        target = DEST / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        manifest[source.relative_to(ROOT).as_posix()] = hashlib.sha256(source.read_bytes()).hexdigest()
    (DEST / "backup_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    print(f"Preserved {len(manifest)} files in {DEST.name}")
