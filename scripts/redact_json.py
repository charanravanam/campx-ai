"""Replace every VALUE in a JSON file with a type placeholder, keeping the structure.

Safe-to-share output for troubleshooting (still look at it before pasting!):
    python scripts/redact_json.py response.json
    python scripts/redact_json.py response.json > shape.json

Strings -> "<str>", numbers -> 0, booleans stay, null stays, lists keep at most 2 items.
Keys are kept (they are what we need to extend the normalizers).
"""
import json
import sys


def shape(v, depth=0):
    if depth > 12:
        return "<too deep>"
    if isinstance(v, dict):
        return {k: shape(x, depth + 1) for k, x in v.items()}
    if isinstance(v, list):
        return [shape(x, depth + 1) for x in v[:2]]
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return 0
    if isinstance(v, str):
        return "<str>"
    return "<?>"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python scripts/redact_json.py <file.json>")
    with open(sys.argv[1], encoding="utf-8") as f:
        print(json.dumps(shape(json.load(f)), indent=2))
