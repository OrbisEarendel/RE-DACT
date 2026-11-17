"""Command line entry point. Owner: P4 (replace/extend with the UI).

    python -m app.cli samples/test.txt --level 1
"""
import argparse
import json

from core.pipeline import redact


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("path")
    p.add_argument("--level", type=int, default=1, choices=[1, 2, 3])
    args = p.parse_args()
    result = redact(args.path, level=args.level)
    print("Wrote:", result.out_path)
    print(json.dumps(result.log, indent=2))


if __name__ == "__main__":
    main()
