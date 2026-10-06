"""Physical reach estimation and link-media classification.

Cable lengths come from a simple, documented floor-plan model:

* Host links run in-row from a compute rack to the SU's network racks, which
  sit in the middle of the SU row. Length = racks away x rack width
  + 2 x vertical rise + in-row slack.
* Leaf-to-spine links run between SU rows and the SuperPod's spine row in the
  middle of the SuperPod. Length = rows away x row pitch + half a row
  + 2 x vertical rise + tray slack.
* Spine-to-super-spine links leave the hall for the campus core room in the
  middle of the campus. Length = halls away x hall spacing + hall-to-core run
  + 2 x vertical rise + tray slack.

Each link takes the cheapest allowed medium whose reach covers it
(DAC -> AEC -> LPO -> DR -> FR).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import ceil

from .catalog import Catalog
from .schema import DesignSpec

MEDIA_ORDER = ("dac", "aec", "lpo", "dr", "fr")


class ReachError(ValueError):
    pass


@dataclass(frozen=True)
class LinkGroup:
    """Links of one medium within one assembly."""

    media: str
    links: int
    length_m_total: float
    max_m: float

    @property
    def avg_m(self) -> float:
        return self.length_m_total / self.links if self.links else 0.0


def classify(spec: DesignSpec, catalog: Catalog, length_m: float) -> str:
    for mid in MEDIA_ORDER:
        if mid in spec.scale_out.allowed_media and catalog.media[mid].max_reach_m >= length_m:
            return mid
    raise ReachError(f"no allowed medium reaches {length_m:.1f} m")


def group(spec: DesignSpec, catalog: Catalog, runs: list[tuple[float, int]]) -> list[LinkGroup]:
    """Folds (length, link count) runs into one LinkGroup per medium."""
    acc: dict[str, list[float]] = defaultdict(lambda: [0, 0.0, 0.0])
    for length, n in runs:
        if n <= 0:
            continue
        mid = classify(spec, catalog, length)
        a = acc[mid]
        a[0] += n
        a[1] += length * n
        a[2] = max(a[2], length)
    return [
        LinkGroup(mid, int(acc[mid][0]), round(acc[mid][1], 3), round(acc[mid][2], 3))
        for mid in MEDIA_ORDER
        if mid in acc
    ]


def network_racks(switches: int, switch_ru: int, rack_ru: int) -> int:
    return ceil(switches * switch_ru / rack_ru) if switches else 0


def host_runs(spec: DesignSpec, su_racks: int, gpus_per_rack: int, planes: int) -> list[tuple[float, int]]:
    """In-row host link lengths for one SU, as (length, links across all planes)."""
    lay = spec.layout
    left = su_racks // 2
    right = su_racks - left
    runs = []
    for side in (left, right):
        for j in range(1, side + 1):
            length = j * lay.rack_width_m + 2 * lay.vertical_m + lay.row_slack_m
            runs.append((round(length, 3), gpus_per_rack * planes))
    return runs


def leaf_spine_runs(
    spec: DesignSpec, su_racks: tuple[int, ...], su_leaves: tuple[int, ...], leaf_up: int, planes: int
) -> list[tuple[float, int]]:
    """Leaf-to-spine lengths for one SuperPod: one SU per row, spine row in the middle."""
    lay = spec.layout
    rows = len(su_racks)
    center = (rows - 1) / 2
    runs = []
    for i, (racks, leaves) in enumerate(zip(su_racks, su_leaves, strict=True)):
        rows_away = abs(i - center) + 0.5
        length = rows_away * lay.row_pitch_m + racks * lay.rack_width_m / 2 + 2 * lay.vertical_m + lay.tray_slack_m
        runs.append((round(length, 3), leaves * leaf_up * planes))
    return runs


def hall_to_core_m(spec: DesignSpec, hall_index: int, halls: int) -> float:
    lay = spec.layout
    halls_away = abs(hall_index - (halls - 1) / 2)
    return round(halls_away * lay.hall_spacing_m + lay.hall_to_core_m + 2 * lay.vertical_m + lay.tray_slack_m, 3)


def core_local_m(spec: DesignSpec) -> float:
    lay = spec.layout
    return round(20 + 2 * lay.vertical_m + lay.tray_slack_m, 3)
