"""A small, closed copy of the registry for tests that write into a temporary project.

Copying all of `registry/` (thousands of files) into every temporary root made the suite take
minutes. Tests that register or replay objects need the sources, revisions, migration manifests and
the claims everything else hangs from - not the statements filed inside manuscripts or the formal
targets, which nothing in those tests refers to. What is left out refers to what is kept, never the
other way round, so the copy still validates as a whole.
"""
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATEMENT = re.compile(r"^amvo-clm-.+-ms\d+-")


def small_registry(destination: Path) -> Path:
    source = ROOT / "registry"
    destination.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        if entry.is_file():
            shutil.copyfile(entry, destination / entry.name)
        elif entry.name == "formal_targets":
            continue
        elif entry.name == "claims":
            (destination / "claims").mkdir(exist_ok=True)
            for f in entry.iterdir():
                if not STATEMENT.match(f.stem):
                    shutil.copyfile(f, destination / "claims" / f.name)
        else:
            shutil.copytree(entry, destination / entry.name)
    return destination
