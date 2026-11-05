"""Command line: python -m synth --out ../data [--seed 7] [--scale 1] [--photos 0]

Run from eval/generate. Writes files, ground truth JSON and manifest.json.
"""

import argparse
from pathlib import Path

from synth.dataset import build


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the synthetic invoice dataset.")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--scale", type=int, default=1)
    parser.add_argument("--photos", type=int, default=0, help="phone photos to add")
    args = parser.parse_args()
    manifest = build(args.out, seed=args.seed, scale=args.scale, photos=args.photos)
    print(f"wrote {len(manifest)} files to {args.out}")


if __name__ == "__main__":
    main()
