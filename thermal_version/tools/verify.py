"""Complete configured code checks. Install requirements-dev.txt first."""

import ast
import compileall
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main() -> int:
    for args in (["format", "--check"], ["check"]):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "ruff",
                *args,
                "main.py",
                "base_main.py",
                "thermal_main.py",
                "thermo",
                "milu",
                "tests",
                "tools",
            ],
            cwd=ROOT,
        )
        if result.returncode:
            return result.returncode
    paths = [ROOT / name for name in ("main.py", "base_main.py", "thermal_main.py")] + sorted(
        p for folder in ("thermo", "milu", "tests", "tools") for p in (ROOT / folder).rglob("*.py")
    )
    for path in paths:
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(path))
        for number, line in enumerate(source.splitlines(), 1):
            if "\t" in line or line.rstrip() != line or line.startswith(("<<<<<<< ", ">>>>>>> ")):
                raise ValueError(f"whitespace/conflict check: {path}:{number}")
        if not source.endswith("\n"):
            raise ValueError(f"missing final newline: {path}")
    for folder in ("thermo", "milu", "tests", "tools"):
        if not compileall.compile_dir(ROOT / folder, quiet=1):
            return 1
    print(
        f"PASS: syntax, bytecode build and basic source hygiene ({len(paths)} files)",
        flush=True,
    )
    return subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
