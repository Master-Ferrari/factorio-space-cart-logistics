#!/usr/bin/env python3
"""
Compose base + shadow + rails layers into a single sprite and downscale it.

Usage:
    python compose.py [source_folder] [--size 80] [--out compose]

source_folder must contain three subfolders with matching filenames:
    <source_folder>/base/*.png
    <source_folder>/shadow/*.png
    <source_folder>/rails/*.png

Layers are alpha-composited in order base -> shadow -> rails (standard
Photoshop "Normal" blend mode, i.e. straight alpha-over), each keeping its
own transparency, so the background stays transparent where all layers are
empty. The result is then downscaled to <size>x<size> using bicubic
resampling plus an unsharp mask pass, emulating Photoshop's
"Bicubic Sharper" algorithm. As a final step, a Photoshop-style Exposure
adjustment (Exposure / Offset / Gamma Correction) is applied, masked by
rail_mask.png (white = full effect, black = untouched) so only the area
that mask covers is affected. Output goes to a sibling folder (default:
compose).
"""

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

LAYERS = ("base", "shadow", "rails")


def bicubic_sharper(im: Image.Image, size: int) -> Image.Image:
    resized = im.resize((size, size), Image.Resampling.BICUBIC)
    return resized.filter(ImageFilter.UnsharpMask(radius=1.0, percent=60, threshold=2))


def _srgb_to_linear(c: np.ndarray) -> np.ndarray:
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(c: np.ndarray) -> np.ndarray:
    c = np.clip(c, 0.0, None)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * (c ** (1.0 / 2.4)) - 0.055)


def load_mask(path: Path, size: int) -> np.ndarray:
    """Load a grayscale mask (white = affected, black = untouched) and
    resize it to match the output canvas if needed."""
    mask_im = Image.open(path).convert("L")
    if mask_im.size != (size, size):
        mask_im = mask_im.resize((size, size), Image.Resampling.LANCZOS)
    return np.asarray(mask_im).astype(np.float64) / 255.0


def apply_exposure(im: Image.Image, mask: np.ndarray, exposure: float, offset: float, gamma: float) -> Image.Image:
    """Photoshop-style Exposure adjustment (Image > Adjustments > Exposure),
    blended in only where `mask` (a 0..1 grayscale array, e.g. rail_mask.png)
    is non-zero."""
    arr = np.asarray(im).astype(np.float64) / 255.0
    rgb, alpha = arr[..., :3], arr[..., 3]

    linear = _srgb_to_linear(rgb)
    linear = linear * (2.0 ** exposure) + offset
    linear = np.clip(linear, 0.0, None) ** (1.0 / gamma)
    adjusted = np.clip(_linear_to_srgb(linear), 0.0, 1.0)

    m = mask[..., None]
    out_rgb = rgb * (1.0 - m) + adjusted * m
    out = np.dstack([out_rgb, alpha])
    out = np.clip(out * 255.0 + 0.5, 0, 255).astype(np.uint8)
    return Image.fromarray(out, mode="RGBA")


def compose_tile(paths: dict, size: int, exposure_args, mask: np.ndarray) -> Image.Image:
    result = None
    for layer in LAYERS:
        path = paths.get(layer)
        if path is None:
            continue
        layer_im = Image.open(path).convert("RGBA")
        if result is None:
            result = layer_im
        else:
            if layer_im.size != result.size:
                raise ValueError(f"size mismatch: {path} is {layer_im.size}, expected {result.size}")
            result = Image.alpha_composite(result, layer_im)
    if result is None:
        raise ValueError("no layers found for this tile")
    result = bicubic_sharper(result, size)
    if exposure_args is not None:
        result = apply_exposure(result, mask, *exposure_args)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", nargs="?", default="test2", help="source folder name (default: test2)")
    parser.add_argument("--size", type=int, default=80, help="output size in pixels (default: 80)")
    parser.add_argument("--out", default="compose", help="output folder name, sibling to source (default: compose)")
    parser.add_argument("--exposure", type=float, default=0.86, help="Exposure adjustment, in stops (default: 0.86)")
    parser.add_argument("--offset", type=float, default=0.0, help="Exposure adjustment offset (default: 0.0)")
    parser.add_argument("--gamma", type=float, default=0.97, help="Exposure adjustment gamma correction (default: 0.97)")
    parser.add_argument("--no-exposure", action="store_true", help="skip the final exposure adjustment step")
    parser.add_argument("--mask", default="rail_mask.png", help="grayscale mask file for the exposure step, relative to this script (default: rail_mask.png)")
    args = parser.parse_args()

    exposure_args = None if args.no_exposure else (args.exposure, args.offset, args.gamma)

    root = Path(__file__).resolve().parent
    src_root = root / args.source
    out_root = root / args.out

    if not src_root.is_dir():
        print(f"Source folder not found: {src_root}", file=sys.stderr)
        sys.exit(1)

    mask = None
    if exposure_args is not None:
        mask_path = root / args.mask
        if not mask_path.is_file():
            print(f"Mask file not found: {mask_path}", file=sys.stderr)
            sys.exit(1)
        mask = load_mask(mask_path, args.size)

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
        paths = {}
        for layer in LAYERS:
            candidate = src_root / layer / name
            if candidate.is_file():
                paths[layer] = candidate
            elif layer == "base":
                paths[layer] = candidate  # should exist, error will surface below
            else:
                print(f"  warning: {layer}/{name} missing, skipping that layer")

        try:
            tile = compose_tile(paths, args.size, exposure_args, mask)
        except Exception as e:
            print(f"  error on {name}: {e}", file=sys.stderr)
            continue

        out_path = out_root / name
        tile.save(out_path)
        print(f"  {name} -> {out_path.relative_to(root)}")
        done += 1

    print(f"Done: {done}/{len(filenames)} tiles composed into {out_root.relative_to(root)}\\")


if __name__ == "__main__":
    main()
