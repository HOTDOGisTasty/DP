"""Deterministic rectangular building candidates in Unreal centimeters."""

import math
import random
from typing import NamedTuple


MAX_CELLS = 10_000


class Preset(NamedTuple):
    spacing_cm: float
    width_cm: tuple[float, float]
    depth_cm: tuple[float, float]
    height_cm: tuple[float, float]
    jitter_cm: float
    yaw_degrees: float


PRESETS = {
    "european_center": Preset(
        spacing_cm=2600, width_cm=(1300, 1900), depth_cm=(800, 1300),
        height_cm=(1200, 2200), jitter_cm=70, yaw_degrees=4,
    ),
    "american_suburb": Preset(
        spacing_cm=2350, width_cm=(900, 1400), depth_cm=(800, 1200),
        height_cm=(450, 850), jitter_cm=175, yaw_degrees=11,
    ),
    "highrise": Preset(
        spacing_cm=3900, width_cm=(1700, 2700), depth_cm=(1400, 2300),
        height_cm=(3800, 9500), jitter_cm=130, yaw_degrees=7,
    ),
}


def _normalize_preset(preset):
    try:
        spacing = float(preset.spacing_cm)
        jitter = float(preset.jitter_cm) or 0.0
        yaw = float(preset.yaw_degrees) or 0.0
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("Preset spacing, jitter and yaw must be numbers") from error
    if not math.isfinite(spacing) or not math.isfinite(jitter) or jitter < 0:
        raise ValueError("Preset spacing must be finite and jitter must be finite and non-negative")
    if not 0 <= yaw <= 180:
        raise ValueError("Preset yaw must be between 0 and 180 degrees")

    ranges = []
    for name, limits in (
        ("width", preset.width_cm), ("depth", preset.depth_cm), ("height", preset.height_cm),
    ):
        try:
            if isinstance(limits, (str, bytes)):
                raise TypeError
            minimum, maximum = map(float, limits)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError(f"Preset {name} must specify two dimension limits") from error
        if not 0 < minimum <= maximum or not math.isfinite(maximum):
            raise ValueError(f"Preset {name} limits must be finite, positive and ordered")
        ranges.append((minimum, maximum))

    width, depth, height = ranges
    if spacing <= math.hypot(width[1], depth[1]) + 2 * jitter:
        raise ValueError("Preset spacing must exceed the maximum footprint diagonal plus twice the jitter")
    return Preset(spacing, width, depth, height, jitter, yaw)


def candidates(bounds, preset, seed):
    """Return one candidate per full grid cell within min x/y and max x/y bounds.

    Slot IDs refer to cells counted from the minimum bounds corner. A preset's
    spacing covers its maximum footprint diagonal plus jitter on both sides, so
    each footprint remains inside its cell at every generated rotation. Pass a
    preset ID or a Preset with custom dimensions.
    """
    if isinstance(preset, Preset):
        style = _normalize_preset(preset)
        style_key = repr(style)
    elif isinstance(preset, str) and preset in PRESETS:
        style = PRESETS[preset]
        style_key = preset
    else:
        raise ValueError(f"Unknown district preset: {preset!r}")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("District seed must be an integer")

    try:
        if isinstance(bounds, (str, bytes)):
            raise TypeError
        min_x, min_y, max_x, max_y = map(float, bounds)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("District bounds must contain four finite coordinates") from error
    span_x = max_x - min_x
    span_y = max_y - min_y
    if not all(math.isfinite(span) and span > 0 for span in (span_x, span_y)):
        raise ValueError("District bounds must have finite positive width and depth")

    spacing = style.spacing_cm
    # Cap ratios before converting them to integers, including float overflow.
    columns = math.floor(min(span_x / spacing, MAX_CELLS + 1))
    rows = math.floor(min(span_y / spacing, MAX_CELLS + 1))
    if columns * rows > MAX_CELLS:
        raise ValueError("District layout exceeds 10,000 grid cells")
    if not columns or not rows:
        return []

    # Large coordinates must retain the clearance between footprint and cell edge.
    clearance = (spacing - math.hypot(style.width_cm[1], style.depth_cm[1])) / 2
    if max(map(math.ulp, (min_x, min_y, max_x, max_y))) >= clearance - style.jitter_cm:
        raise ValueError("District bounds exceed the coordinate precision of this layout")

    layout = []
    for row in range(rows):
        for column in range(columns):
            slot_id = f"{column}:{row}"
            rng = random.Random(f"{seed:x}:{style_key}:{slot_id}")
            jitter_x = rng.uniform(-style.jitter_cm, style.jitter_cm)
            jitter_y = rng.uniform(-style.jitter_cm, style.jitter_cm)
            layout.append({
                "slot_id": slot_id,
                "center_cm": [
                    min_x + ((column + 0.5) * spacing + jitter_x),
                    min_y + ((row + 0.5) * spacing + jitter_y),
                ],
                "size_cm": [
                    rng.uniform(*style.width_cm),
                    rng.uniform(*style.depth_cm),
                    rng.uniform(*style.height_cm),
                ],
                "yaw_degrees": rng.uniform(-style.yaw_degrees, style.yaw_degrees),
            })
    return layout
