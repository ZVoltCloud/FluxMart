"""gradient.py: A file for handling gradient prints"""

from __future__ import annotations

import sys
from typing import Tuple, List, Any, Optional

from rich.console import Console
from rich.text import Text

console = Console()


class GradientPrinter:

    @staticmethod
    def gradient(
        start: Tuple[int, int, int], end: Tuple[int, int, int], steps: int
    ) -> List[Tuple[int, int, int]]:
        if steps < 1:
            raise ValueError("Steps must be greater than 0.")

        rs = [start[0]]
        gs = [start[1]]
        bs = [start[2]]

        for step in range(1, steps):
            rs.append(round(start[0] + (end[0] - start[0]) * step / steps))
            gs.append(round(start[1] + (end[1] - start[1]) * step / steps))
            bs.append(round(start[2] + (end[2] - start[2]) * step / steps))

        return list(zip(rs, gs, bs))

    @staticmethod
    def validate_hex_color(color: str) -> Tuple[int, int, int]:
        from .color import Color
        try:
            return Color.hex_to_rgb(color)
        except Exception as e:
            raise ValueError(f"Invalid color format '{color}': {e}") from e

    @staticmethod
    def gradient_print(
        *values: Any,
        input_text: str,
        end_text: Optional[str] = "",
        start_color: str = "#c0c0c0",
        end_color: str = "#909090",
        sep: str = " ",
        end: str = "\n",
        correct: Optional[bool] = None,
        prefix: Optional[str] = None,
        overwrite: bool = False,
        line: int | None = None
    ) -> None:
        from .color import Color, MskColor

        if line is not None:
            sys.stdout.write(f"\033[{line + 1};0H")
            sys.stdout.write("\033[2K")

        text = input_text

        start_color_rgb = GradientPrinter.validate_hex_color(start_color)
        end_color_rgb = GradientPrinter.validate_hex_color(end_color)

        steps = max(len(text) + len(end_text), 1)
        grad = GradientPrinter.gradient(start_color_rgb, end_color_rgb, steps)

        if prefix is None:
            prefix_mapping = {
                False: f"{MskColor.MSK}[{MskColor.LIGHTBLACK}ERROR{MskColor.MSK}]{MskColor.RESET} ",
                None: f"{MskColor.MSK}[{MskColor.LIGHTBLACK}MSK{MskColor.MSK}]{MskColor.RESET} ",
                True: f"{MskColor.MSK}[{MskColor.LIGHTBLACK}SUCCESS{MskColor.MSK}]{MskColor.RESET} ",
            }
            prefix = prefix_mapping.get(correct, "")

        try:
            if prefix:
                sys.stdout.write(prefix)
            for i, char in enumerate(text):
                color = grad[i]
                sys.stdout.write(f"{Color.rgb_to_ansi(*color)}{char}")
            sys.stdout.write(end_text)

            if not overwrite:
                sys.stdout.write(end)

        finally:
            sys.stdout.write(MskColor.RESET)
            sys.stdout.flush()

    @staticmethod
    def clear_line(line: int) -> None:
        sys.stdout.write(f"\033[{line + 1};0H")
        sys.stdout.write("\033[2K")
        sys.stdout.flush()
