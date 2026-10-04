"""
Mutation check: proves each safety property is actually pinned by a test.

tests/mutations.txt lists deliberate breakages of the contract - each one
removes or weakens exactly one safety property (market-status parsing, the delisting-category check,
quote grounding, the scan cap, fail-closed fetches, the validator's
comparisons, ...).
For every mutation this script patches the contract, runs the full test
suite, and restores the original. A mutation the suite still passes is a
safety property no test protects; the script exits non-zero if any
survive.

Format of tests/mutations.txt: blocks separated by a line "===", each
    <name>
    ---
    <exact original text>
    ---
    <replacement text>

Usage (from the repo root):  python3 scripts/mutation_check.py
"""

import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
CONTRACT = REPO / "contracts" / "delist_watch.py"
PYTEST = REPO / ".venv" / "bin" / "pytest"


def main() -> int:
    original = CONTRACT.read_text()
    mutations = []
    for block in (REPO / "tests" / "mutations.txt").read_text().split("\n===\n"):
        name, old, new = block.split("\n---\n")
        assert old in original, f"mutation target not found in {CONTRACT.name}: {name.strip()}"
        mutations.append((name.strip(), old, new))

    survivors = []
    try:
        for name, old, new in mutations:
            CONTRACT.write_text(original.replace(old, new, 1))
            result = subprocess.run([str(PYTEST), "tests", "-q", "-x", "-p", "no:cacheprovider"],
                                    cwd=REPO, capture_output=True, text=True)
            killed = result.returncode != 0
            print(("KILLED    " if killed else "SURVIVED  ") + name)
            if not killed:
                survivors.append(name)
    finally:
        CONTRACT.write_text(original)

    print(f"\n{len(mutations) - len(survivors)}/{len(mutations)} mutations killed")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
