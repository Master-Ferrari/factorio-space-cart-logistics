#!/usr/bin/env python3
"""
Compose base + shadow + rails_off + rails_on passes into a single sprite and downscale it.

Usage:
    python compose_passes.py [source_folder] [--size 80] [--out compose]

source_folder contains subfolders with matching filenames:
    <source_folder>/base/*.png        required
    <source_folder>/shadow/*.png      optional
    <source_folder>/rails_off/*.png   optional
    <source_folder>/rails_on/*.png    optional (falls back to rails/ for older renders)

Pipeline per tile:
  1. Photoshop-style Exposure adjustment (Exposure / Offset / Gamma Correction)
     applied to the rails_on layer only.
  2. Straight alpha-over (Photoshop "Normal"): base -> shadow -> rails_off -> rails_on.
     The background stays transparent where all layers are empty.
  3. Downscale to <size>x<size>: bicubic resampling plus an unsharp mask,
     emulating Photoshop's "Bicubic Sharper".

Output goes to a sibling folder (default: compose).
"""

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

LAYERS = ("base", "shadow", "rails_off", "rails_on")
FALLBACK = {"rails_on": "rails"}          # старые рендеры с одной папкой rails
EXPOSED = {"rails_on"}


def bicubic_sharper(im: Image.Image, size: int) -> Image.Image:
    resized = im.resize((size, size), Image.Resampling.BICUBIC)
    return resized.filter(ImageFilter.UnsharpMask(radius=1.0, percent=60, threshold=2))


def _srgb_to_linear(c: np.ndarray) -> np.ndarray:
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(c: np.ndarray) -> np.ndarray:
    c = np.clip(c, 0.0, None)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * (c ** (1.0 / 2.4)) - 0.055)


def apply_exposure(im: Image.Image, exposure: float, offset: float, gamma: float) -> Image.Image:
    """Photoshop-style Exposure adjustment on RGB; alpha is left untouched."""
    arr = np.asarray(im.convert("RGBA")).astype(np.float64) / 255.0
    rgb, alpha = arr[..., :3], arr[..., 3]

    linear = _srgb_to_linear(rgb)
    linear = linear * (2.0 ** exposure) + offset
    linear = np.clip(linear, 0.0, None) ** (1.0 / gamma)
    adjusted = np.clip(_linear_to_srgb(linear), 0.0, 1.0)

    out = np.dstack([adjusted, alpha])
    out = np.clip(out * 255.0 + 0.5, 0, 255).astype(np.uint8)
    return Image.fromarray(out, mode="RGBA")


def find_layer(src_root: Path, layer: str, name: str):
    for folder in (layer, FALLBACK.get(layer)):
        if folder:
            p = src_root / folder / name
            if p.is_file():
                return p
    return None


def compose_tile(paths: dict, size: int, exposure_args) -> Image.Image:
    result = None
    for layer in LAYERS:
        path = paths.get(layer)
        if path is None:
            continue
        layer_im = Image.open(path).convert("RGBA")
        if layer in EXPOSED and exposure_args is not None:
            layer_im = apply_exposure(layer_im, *exposure_args)
        if result is None:
            result = layer_im
        else:
            if layer_im.size != result.size:
                raise ValueError(f"size mismatch: {path} is {layer_im.size}, expected {result.size}")
            result = Image.alpha_composite(result, layer_im)
    if result is None:
        raise ValueError("no layers found for this tile")
    return bicubic_sharper(result, size)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", nargs="?", default="test2", help="source folder name, relative to this script (default: test2)")
    parser.add_argument("--size", type=int, default=80, help="output size in pixels (default: 80)")
    parser.add_argument("--out", default="compose", help="output folder name, sibling to source (default: compose)")
    parser.add_argument("--exposure", type=float, default=0.86, help="rails_on exposure, in stops (default: 0.86)")
    parser.add_argument("--offset", type=float, default=0.0, help="rails_on exposure offset (default: 0.0)")
    parser.add_argument("--gamma", type=float, default=0.97, help="rails_on exposure gamma correction (default: 0.97)")
    parser.add_argument("--no-exposure", action="store_true", help="skip the rails_on exposure step")
    args = parser.parse_args()

    exposure_args = None if args.no_exposure else (args.exposure, args.offset, args.gamma)

    root = Path(__file__).resolve().parent
    src_root = root / args.source
    out_root = root / args.out

    if not src_root.is_dir():
        print(f"Source folder not found: {src_root}", file=sys.stderr)
        sys.exit(1)

    base_dir = src_root / "base"
    if not base_dir.is_dir():
        print(f"Missing base layer folder: {base_dir}", file=sys.stderr)
        sys.exit(1)

    out_root.mkdir(parents=True, exist_ok=True)

    filenames = sorted(p.name for p in base_dir.glob("*.png"))
    if not filenames:
        print(f"No .png files found in {base_dir}", file=sys.stderr)
        sys.exit(1)

    done = 0
    for name in filenames:
        paths = {"base": base_dir / name}
        for layer in LAYERS[1:]:
            p = find_layer(src_root, layer, name)
            if p is not None:
                paths[layer] = p
            else:
                print(f"  note: {layer}/{name} missing, skipping that layer")

        try:
            tile = compose_tile(paths, args.size, exposure_args)
        except Exception as e:
            print(f"  error on {name}: {e}", file=sys.stderr)
            continue

        out_path = out_root / name
        tile.save(out_path)
        print(f"  {name} -> {out_path.relative_to(root)}")
        done += 1

    print(f"Done: {done}/{len(filenames)} tiles composed into {out_root.relative_to(root)}")


if __name__ == "__main__":
    main()