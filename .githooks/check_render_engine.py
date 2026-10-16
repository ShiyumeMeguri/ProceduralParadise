"""Refuse a commit that brings another render engine into the repository: every render is EEVEE's.

Run by the pre-commit hook (``.githooks/pre-commit``; ``git config core.hooksPath .githooks`` once per clone).  It reads the
lines the commit adds to code and data (``.py``, ``.json``) and refuses any that names Cycles -- its engine, its settings,
its devices (this hook's own folder aside).  Lines already in the repository are not judged; what a commit adds is."""
import re
import subprocess
import sys

FORBIDDEN = re.compile(r"cycles", re.IGNORECASE)
CHECKED = (".py", ".json")


def added_lines():
    diff = subprocess.run(["git", "diff", "--cached", "--unified=0", "--no-color", "--diff-filter=ACMR"],
                          capture_output=True, check=True).stdout.decode("utf-8", errors="replace")
    path = None
    number = 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@"):
            number = int(re.match(r"@@ -\S+ \+(\d+)", line).group(1))
        elif line.startswith("+") and not line.startswith("+++"):
            if path is not None and path.endswith(CHECKED) and not path.startswith(".githooks/"):
                yield path, number, line[1:]
            number += 1


def main():
    found = [(path, number, text) for path, number, text in added_lines() if FORBIDDEN.search(text)]
    for path, number, text in found:
        print(f"{path}:{number}: {text.strip()[:160]}", file=sys.stderr)
    if found:
        print("commit refused: the repository renders with EEVEE alone -- its shading is written for EEVEE, and EEVEE's "
              "picture is the right one; take Cycles out of these lines.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
