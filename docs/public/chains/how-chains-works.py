#!/usr/bin/env python3
"""Render the logo-free Chains diagram using only text and geometric primitives.

Requires Pillow==10.4.0 (including its bundled default font); no external assets.
Run this file to regenerate the adjacent PNG, or pass --check to detect drift.
Namespace names are intentionally generic because deployment settings vary.
"""

import argparse
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont


OUTPUT = Path(__file__).with_suffix(".png")
SIZE = (1440, 720)
SCALE = 2
INK = "#202830"
MUTED = "#53616B"
BORDER = "#B8C3CA"
BLUE = "#225C86"
GREEN = "#236A52"


def render():
    image = Image.new("RGB", tuple(value * SCALE for value in SIZE), "white")
    draw = ImageDraw.Draw(image)

    def box(bounds, fill, outline=BORDER, width=2):
        draw.rounded_rectangle(
            tuple(value * SCALE for value in bounds),
            radius=6 * SCALE,
            fill=fill,
            outline=outline,
            width=width * SCALE,
        )

    def text(value, position, size=26, fill=INK, anchor="lt"):
        font = ImageFont.load_default(size=size * SCALE)
        xy = tuple(value * SCALE for value in position)
        bounds = draw.textbbox(xy, value, font=font, anchor=anchor)
        assert 0 <= bounds[0] < bounds[2] <= image.width, value
        assert 0 <= bounds[1] < bounds[3] <= image.height, value
        draw.text(xy, value, font=font, fill=fill, anchor=anchor)

    def arrow(points, fill):
        points = [(x * SCALE, y * SCALE) for x, y in points]
        draw.line(points, fill=fill, width=3 * SCALE, joint="curve")
        end, previous = points[-1], points[-2]
        angle = math.atan2(end[1] - previous[1], end[0] - previous[0])
        length, half_width = 12 * SCALE, 6 * SCALE
        base = (
            end[0] - length * math.cos(angle),
            end[1] - length * math.sin(angle),
        )
        draw.polygon(
            [
                end,
                (
                    base[0] - half_width * math.sin(angle),
                    base[1] + half_width * math.cos(angle),
                ),
                (
                    base[0] + half_width * math.sin(angle),
                    base[1] - half_width * math.cos(angle),
                ),
            ],
            fill=fill,
        )

    box((16, 16, 1424, 704), "#FAFBFC")
    text("Kubernetes cluster", (48, 44), size=32)

    box((390, 104, 1050, 332), "#F0F4F6")
    text("Workload namespace", (416, 124), size=28)
    box((414, 181, 642, 306), "white")
    text("Standalone", (528, 221), anchor="mm")
    text("TaskRun", (528, 264), anchor="mm")

    # Enclosure expresses ownership without inventing sequential task execution.
    box((666, 163, 1026, 306), "#EAF4EE", outline="#97BDA7")
    text("PipelineRun", (846, 194), anchor="mm")
    box((682, 227, 839, 282), "white", outline="#97BDA7")
    box((853, 227, 1010, 282), "white", outline="#97BDA7")
    text("TaskRun", (760, 255), anchor="mm")
    text("TaskRun", (931, 255), anchor="mm")

    # Both arrows point at run resources, as in the original observation model.
    arrow([(312, 444), (312, 260), (390, 260)], BLUE)
    text("1. Run", (184, 363), size=28, fill=BLUE)
    arrow([(1128, 444), (1128, 260), (1050, 260)], GREEN)
    text("2. Observe", (1152, 363), size=28, fill=GREEN)

    box((48, 444, 632, 650), "#EFF5FA", outline="#91AEC5")
    text("Pipelines namespace", (76, 468), size=24, fill=MUTED)
    text("Tekton Pipelines Controller", (76, 520), size=32, fill=BLUE)
    text("TaskRun / PipelineRun execution", (76, 588), size=24)

    box((808, 444, 1392, 650), "#EEF6F1", outline="#97BDA7")
    text("Chains namespace", (836, 468), size=24, fill=MUTED)
    text("Tekton Chains Controller", (836, 520), size=32, fill=GREEN)
    text("3. Format", (836, 599), size=26, anchor="lm")
    arrow([(974, 599), (1006, 599)], GREEN)
    text("4. Sign", (1022, 599), size=26, anchor="lm")
    arrow([(1124, 599), (1156, 599)], GREEN)
    text("5. Upload", (1172, 599), size=26, anchor="lm")

    return image.resize(SIZE, Image.Resampling.LANCZOS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the PNG differs from this logo-free rendering; do not write.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT,
        help="Alternate PNG path, also supported with --check.",
    )
    args = parser.parse_args()
    expected = render()
    if args.check:
        try:
            with Image.open(args.output) as actual:
                actual.load()
                matches = (
                    actual.format == "PNG"
                    and actual.mode == expected.mode
                    and actual.size == expected.size
                    and ImageChops.difference(actual, expected).getbbox() is None
                )
        except (OSError, ValueError):
            matches = False
        if not matches:
            parser.exit(1, "Diagram differs from the generator; regenerate the PNG.\n")
        print("PASS: PNG matches the logo-free diagram generator.")
    else:
        expected.save(args.output, format="PNG", optimize=True)
        print(f"Rendered {args.output.name}: {SIZE[0]} x {SIZE[1]}")


if __name__ == "__main__":
    main()
