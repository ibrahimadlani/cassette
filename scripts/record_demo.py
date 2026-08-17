"""Render the README's demo GIF from real command output.

Nothing here is staged. The script runs `cassette fuzz`, `cassette fuzz
--buggy` and `cassette shrink`, captures what they actually print, and types it
out frame by frame into an animated GIF. If the tool stops finding the bug, the
GIF stops showing it being found.

Run it with `make gif` after anything that changes what those commands print.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT = Path("/System/Library/Fonts/Menlo.ttc")
FALLBACK = Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")

SIZE = 15
COLUMNS = 92
PADDING = 22
LINE_HEIGHT = 21
SCALE = 2

BACKGROUND = (14, 17, 22)
CHROME = (22, 27, 34)
DEFAULT = (230, 237, 243)
DIM = (139, 148, 158)
PROMPT = (88, 166, 255)
GOOD = (63, 185, 80)
BAD = (248, 81, 73)
WARN = (210, 153, 34)
ACCENT = (163, 113, 247)

ANSI = re.compile(r"\x1b\[[0-9;]*m")


@dataclass(frozen=True, slots=True)
class Step:
    """One command, and how long to hold on its output."""

    command: list[str]
    caption: str
    hold_frames: int = 26
    type_speed: int = 3


STEPS = [
    Step(
        ["cassette", "fuzz", "--seeds", "2000", "--workers", "8", "--all", "--no-record"],
        "2000 scenarios against the current store",
        hold_frames=20,
    ),
    Step(
        ["cassette", "fuzz", "--seeds", "2000", "--workers", "8", "--buggy", "--no-record"],
        "the same fuzzer, with the fixed defects switched back on",
        hold_frames=24,
    ),
    Step(
        ["cassette", "shrink", "--seed", "6", "--buggy"],
        "reduce it to something a person can read",
        hold_frames=64,
    ),
]


def load_font() -> ImageFont.FreeTypeFont:
    """A monospace face, or fail loudly rather than draw something ugly."""
    for candidate in (FONT, FALLBACK):
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), SIZE * SCALE)
    raise SystemExit("no monospace font found; set FONT in this script")


def run(step: Step) -> list[str]:
    """Run the command and return its output, stripped of colour codes."""
    print(f"  $ {' '.join(step.command)}", file=sys.stderr)
    result = subprocess.run(step.command, capture_output=True, text=True, check=False, timeout=300)
    body = (result.stdout + result.stderr).rstrip("\n")
    return [ANSI.sub("", line)[:COLUMNS] for line in body.split("\n")]


def colour(line: str) -> tuple[int, int, int]:
    """Colour a line the way the terminal would have."""
    stripped = line.strip()
    if stripped.startswith("$"):
        return PROMPT
    if stripped.startswith("#"):
        return DIM
    if "NEW" in line or "VIOLATION" in line or "<--" in line:
        return BAD
    if "no violations" in line or stripped.startswith("ok"):
        return GOOD
    if "known failure" in line or "reduced" in stripped[:8]:
        return WARN
    if "x fewer events" in line:
        return ACCENT
    return DEFAULT


def frame(lines: list[str], font: ImageFont.FreeTypeFont, height: int) -> Image.Image:
    """One frame: a terminal window with `lines` in it."""
    width = (COLUMNS * (SIZE * SCALE) * 6) // 10 + PADDING * SCALE * 2
    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)

    bar = 30 * SCALE
    draw.rectangle([(0, 0), (width, bar)], fill=CHROME)
    for index, dot in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        centre = PADDING * SCALE + index * 20 * SCALE
        radius = 6 * SCALE
        draw.ellipse(
            [(centre - radius, bar // 2 - radius), (centre + radius, bar // 2 + radius)], fill=dot
        )
    draw.text((width // 2, bar // 2), "cassette", font=font, fill=DIM, anchor="mm")

    y = bar + PADDING * SCALE
    for line in lines:
        draw.text((PADDING * SCALE, y), line, font=font, fill=colour(line))
        y += LINE_HEIGHT * SCALE

    return image


def build(output: Path, keep_last: int) -> None:
    """Run every step and write the GIF."""
    font = load_font()
    transcript: list[str] = []
    frames: list[Image.Image] = []
    durations: list[int] = []

    captured = [(step, run(step)) for step in STEPS]

    tallest = 0
    for _, lines in captured:
        tallest = max(tallest, len(lines) + 4)
    height = (30 + PADDING * 2 + min(tallest, keep_last) * LINE_HEIGHT + 8) * SCALE

    def push(image: Image.Image, hold: int) -> None:
        frames.append(image)
        durations.append(hold)

    for step, lines in captured:
        transcript.clear()
        transcript.append(f"# {step.caption}")
        transcript.append("")

        prompt = f"$ {' '.join(step.command)}"
        for cut in range(2, len(prompt) + 1, step.type_speed):
            push(frame([*transcript, prompt[:cut]], font, height), 30)
        transcript.append(prompt)
        transcript.append("")
        push(frame(transcript, font, height), 220)

        for line in lines:
            transcript.append(line)
            push(frame(transcript[-keep_last:], font, height), 55)

        push(frame(transcript[-keep_last:], font, height), step.hold_frames * 40)

    output.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        output,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    size_kb = output.stat().st_size / 1024
    print(f"wrote {output} — {len(frames)} frames, {size_kb:.0f} KiB", file=sys.stderr)


def main() -> None:
    """Record the demo."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", type=Path, default=Path("docs/demo.gif"))
    parser.add_argument("--lines", type=int, default=22, help="Visible terminal lines.")
    arguments = parser.parse_args()
    build(arguments.output, arguments.lines)


if __name__ == "__main__":
    main()
