"""Loads the component catalog and the reference list from editable YAML files."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Component:
    id: str
    name: str
    category: str
    power_w: float
    cost_usd: float
    specs: dict[str, Any] = field(default_factory=dict)
    refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Media:
    id: str
    name: str
    kind: str
    max_reach_m: float
    end_power_w: float
    end_cost_usd: float
    fiber: str
    refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Catalog:
    components: dict[str, Component]
    media: dict[str, Media]
    fiber: dict[str, dict[str, Any]]
    facility: dict[str, Any]
    labor: dict[str, float]
    references: dict[str, dict[str, str]]

    def component(self, cid: str) -> Component:
        try:
            return self.components[cid]
        except KeyError:
            raise KeyError(f"unknown catalog component '{cid}'") from None


def _read_yaml(path: Path | None, default_name: str) -> dict[str, Any]:
    if path is not None:
        return yaml.safe_load(Path(path).read_text())
    text = resources.files("dcdesigner.data").joinpath(default_name).read_text()
    return yaml.safe_load(text)


def load_catalog(catalog_path: Path | None = None, references_path: Path | None = None) -> Catalog:
    raw = _read_yaml(catalog_path, "catalog.yaml")
    refs = _read_yaml(references_path, "references.yaml")
    components = {
        cid: Component(
            id=cid,
            name=c["name"],
            category=c["category"],
            power_w=float(c["power_w"]),
            cost_usd=float(c["cost_usd"]),
            specs=dict(c.get("specs") or {}),
            refs=tuple(c.get("refs") or ()),
        )
        for cid, c in raw["components"].items()
    }
    media = {
        mid: Media(
            id=mid,
            name=m["name"],
            kind=m["kind"],
            max_reach_m=float(m["max_reach_m"]),
            end_power_w=float(m["end_power_w"]),
            end_cost_usd=float(m["end_cost_usd"]),
            fiber=m["fiber"],
            refs=tuple(m.get("refs") or ()),
        )
        for mid, m in raw["media"].items()
    }
    cat = Catalog(
        components=components,
        media=media,
        fiber=raw["fiber"],
        facility=raw["facility"],
        labor={k: float(v) for k, v in raw["labor"].items()},
        references=refs,
    )
    missing = sorted(
        {r for c in components.values() for r in c.refs}
        | {r for m in media.values() for r in m.refs}
        | set(raw["facility"].get("refs", []))
    )
    missing = [r for r in missing if r not in refs]
    if missing:
        raise ValueError(f"catalog cites unknown references: {missing}")
    return cat
