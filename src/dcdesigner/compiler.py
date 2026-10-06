"""The six-tier compiler: DesignSpec -> deterministic design document.

Every tier is a list of assemblies. An assembly's bill of materials holds the
items introduced at that tier plus its child assemblies as opaque lines, so a
reader at the rack tier sees "18 x compute tray", not GPUs, and a reader at the
data-hall tier sees "12 x SuperPod", not racks. Power and cost roll up through
the tree. Tier 1 is the flattened list of indivisible parts across the build.

Partial units are exact: a cluster that does not divide into whole SuperPods
gets a smaller final SuperPod (and SU, and hall) as its own assembly variant.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from math import ceil

from . import physical, roce
from .catalog import Catalog
from .fabric import FabricPlan, alternatives, max_endpoints, plan_fabric
from .physical import LinkGroup
from .schema import DesignSpec
from .wiring import Wiring

FORMAT_VERSION = 1

TIERS = [
    (1, "silicon", "Indivisible units", "Compute silicon, NICs, switch ASICs, memory, storage and link media"),
    (2, "node", "Node", "Host or compute tray with its scale-up mesh"),
    (3, "rack", "Rack", "Mechanical, thermal and electrical boundary"),
    (4, "pod", "Pod / SuperPod", "Rail-optimized leaves (SU) and the non-blocking leaf/spine block (SuperPod)"),
    (5, "hall", "Data hall", "SuperPods, structured cabling and the facility envelope"),
    (6, "campus", "Campus / DC", "Halls joined by the super-spine core, WAN edge and utility power"),
]


@dataclass
class Line:
    ref: str
    name: str
    category: str
    qty: float
    unit_power_w: float
    unit_cost_usd: float
    kind: str = "component"  # component | assembly | media | fiber | facility
    note: str = ""

    @property
    def power_w(self) -> float:
        return self.qty * self.unit_power_w

    @property
    def cost_usd(self) -> float:
        return self.qty * self.unit_cost_usd


@dataclass
class Assembly:
    id: str
    tier: int
    name: str
    lines: list[Line]
    qty_total: int = 0
    attrs: dict = field(default_factory=dict)
    diagram: dict = field(default_factory=dict)

    @property
    def power_w(self) -> float:
        return sum(ln.power_w for ln in self.lines)

    @property
    def cost_usd(self) -> float:
        return sum(ln.cost_usd for ln in self.lines)


def _r(x: float, nd: int = 3) -> float | int:
    """Rounds for stable output; integral values become ints."""
    v = round(float(x), nd)
    return int(v) if v == int(v) else v


class Compiler:
    def __init__(self, spec: DesignSpec, catalog: Catalog):
        self.spec = spec
        self.cat = catalog
        self.asm: dict[str, Assembly] = {}
        self.fabric: FabricPlan = plan_fabric(spec, catalog)
        self.switch = catalog.component(self.fabric.switch_id)
        self.switch_ru = int(self.switch.specs.get("ru", 1))
        self.link_groups: dict[str, list[LinkGroup]] = {}

    # ----------------------------------------------------------- helpers
    def comp(self, cid: str, qty: float, note: str = "") -> Line:
        c = self.cat.component(cid)
        return Line(cid, c.name, c.category, qty, c.power_w, c.cost_usd, "component", note)

    def child(self, a: Assembly, qty: int) -> Line:
        return Line(a.id, a.name, f"tier{a.tier}", qty, a.power_w, a.cost_usd, "assembly")

    def add(self, a: Assembly) -> Assembly:
        self.asm.setdefault(a.id, a)
        return self.asm[a.id]

    def media_lines(self, groups: list[LinkGroup], label: str) -> list[Line]:
        """BOM lines for link groups: optics or cables plus fiber, per medium."""
        lines = []
        share = self.fabric.port_gbps / 800  # 800G-equivalents per link end
        for g in groups:
            m = self.cat.media[g.media]
            if m.kind == "optical":
                units = ceil(2 * g.links * share)
                lines.append(
                    Line(
                        f"media:{m.id}",
                        m.name,
                        "optics",
                        units,
                        m.end_power_w,
                        m.end_cost_usd,
                        "media",
                        f"{label}: {g.links:,} x {self.fabric.port_gbps}G links, both ends, 800G-equivalent modules",
                    )
                )
                f = self.cat.fiber[m.fiber]
                unit = f["cost_per_link_usd"] + f["cost_per_m_usd"] * g.avg_m
                lines.append(
                    Line(
                        f"fiber:{m.fiber}",
                        f["name"],
                        "fiber",
                        g.links,
                        0,
                        round(unit, 2),
                        "fiber",
                        f"{label}: avg {g.avg_m:.1f} m, max {g.max_m:.1f} m",
                    )
                )
            else:
                units = ceil(g.links * share)
                lines.append(
                    Line(
                        f"media:{m.id}",
                        m.name,
                        "copper",
                        units,
                        2 * m.end_power_w,
                        2 * m.end_cost_usd,
                        "media",
                        f"{label}: {g.links:,} x {self.fabric.port_gbps}G links, 800G-equivalent cables, "
                        f"avg {g.avg_m:.1f} m",
                    )
                )
        return lines

    # ------------------------------------------------------------ tiers
    def build_nodes(self) -> tuple[Assembly, Assembly | None]:
        s = self.spec
        n = s.node
        lines = [self.comp(n.accelerator, n.accelerators), self.comp(n.nic, n.nics)]
        lines += [self.comp(cid, q) for cid, q in n.components.items()]
        accel = self.cat.component(n.accelerator)
        node = Assembly(
            "node",
            2,
            n.name,
            lines,
            attrs={
                "form": n.form,
                "accelerators": n.accelerators,
                "rack_units": n.rack_units,
                "scale_up": s.scale_up.technology,
                "scale_up_domain": s.scale_up.domain,
                "scale_up_gbytes_s_per_gpu": s.scale_up.gbytes_s_per_gpu,
                "scale_up_medium": s.scale_up.medium,
                "scale_out_gbps_per_gpu": s.scale_out.nic_gbps,
                "scale_out_planes": s.scale_out.planes,
                "hbm_gb_per_gpu": accel.specs.get("hbm_gb"),
            },
            diagram={
                "kind": "node",
                "gpus": n.accelerators,
                "cpus": sum(q for cid, q in n.components.items() if self.cat.component(cid).category == "cpu"),
                "nics": n.nics,
                "scale_up_switches": sum(
                    q for cid, q in n.components.items() if self.cat.component(cid).category == "scale_up_switch"
                ),
                "pcie_switches": sum(
                    q for cid, q in n.components.items() if self.cat.component(cid).category == "pcie"
                ),
                "scale_up": s.scale_up.technology,
                "domain": s.scale_up.domain,
                "planes": s.scale_out.planes,
            },
        )
        tray = None
        st = s.scale_up.switch_tray
        if st:
            tray = Assembly(
                "switch-tray",
                2,
                st.name,
                [self.comp(cid, q) for cid, q in st.components.items()],
                attrs={"rack_units": st.rack_units, "per_domain": st.per_domain},
                diagram={
                    "kind": "switch-tray",
                    "asics": sum(
                        q for cid, q in st.components.items() if self.cat.component(cid).category == "scale_up_switch"
                    ),
                },
            )
        return self.add(node), (self.add(tray) if tray else None)

    def build_rack(self, node: Assembly, tray: Assembly | None) -> Assembly:
        s = self.spec
        r = s.rack
        lines = [self.child(node, r.nodes)]
        trays = s.scale_up.switch_tray.per_domain if tray else 0
        if tray:
            lines.append(self.child(tray, trays))
        lines.append(self.comp(r.frame, 1))
        lines += [self.comp(cid, q) for cid, q in r.components.items()]
        load_kw = sum(ln.power_w for ln in lines) / 1000
        shelf = self.cat.component(r.power_shelf)
        shelves = ceil(load_kw / shelf.specs["capacity_kw"]) + r.power_shelf_spares
        lines.append(self.comp(r.power_shelf, shelves, f"N+{r.power_shelf_spares}"))
        if load_kw > r.power_budget_kw:
            raise ValueError(f"rack load {load_kw:.1f} kW exceeds the {r.power_budget_kw} kW budget")
        ru_used = (
            r.nodes * s.node.rack_units
            + trays * (tray.attrs["rack_units"] if tray else 0)
            + shelves
            + sum(q for cid, q in r.components.items() if self.cat.component(cid).category == "network_mgmt")
        )
        if ru_used > r.rack_units:
            raise ValueError(f"rack needs {ru_used} RU but has {r.rack_units}")
        top = (r.nodes + 1) // 2 + (1 if tray and r.nodes > 2 else 0)
        slots = [{"kind": "mgmt", "ru": 1, "label": "OOB mgmt switch"}]
        slots += [{"kind": "power", "ru": 1, "label": "Power shelf"}] * ((shelves + 1) // 2)
        slots += [{"kind": "node", "ru": s.node.rack_units, "label": s.node.name}] * (top if tray else r.nodes)
        if tray:
            slots += [{"kind": "switch", "ru": tray.attrs["rack_units"], "label": tray.name}] * trays
            slots += [{"kind": "node", "ru": s.node.rack_units, "label": s.node.name}] * (r.nodes - top)
        slots += [{"kind": "power", "ru": 1, "label": "Power shelf"}] * (shelves // 2)
        rack = Assembly(
            "rack",
            3,
            r.name,
            lines,
            attrs={
                "gpus": s.gpus_per_rack,
                "power_kw": _r(load_kw),
                "power_budget_kw": r.power_budget_kw,
                "budget_used": _r(load_kw / r.power_budget_kw, 4),
                "cooling": r.cooling,
                "liquid_kw": _r(load_kw * r.liquid_fraction),
                "air_kw": _r(load_kw * (1 - r.liquid_fraction)),
                "rack_units": r.rack_units,
                "rack_units_used": ru_used,
                "scale_up_domain_gpus": s.scale_up.gpus_per_domain,
                "scale_up_domains": s.gpus_per_rack // s.scale_up.gpus_per_domain,
                "scale_out_ports": s.gpus_per_rack * s.scale_out.planes,
            },
            diagram={"kind": "rack", "rack_units": r.rack_units, "slots": slots, "cooling": r.cooling},
        )
        return self.add(rack)

    def build_su(self, rack: Assembly, racks: int, leaves: int) -> Assembly:
        s, f = self.spec, self.fabric
        aid = f"su-{racks}r"
        if aid in self.asm:
            return self.asm[aid]
        switches = leaves * f.planes
        nracks = physical.network_racks(switches, self.switch_ru, s.layout.network_rack_ru)
        groups = physical.group(s, self.cat, physical.host_runs(s, racks, s.gpus_per_rack, f.planes))
        self.link_groups[aid] = groups
        lines = [
            self.child(rack, racks),
            self.comp(f.switch_id, switches, f"leaf: {leaves} per plane x {f.planes} planes"),
            self.comp("rack-48u-orv3", nracks, "network racks, middle of row"),
            *self.media_lines(groups, "GPU to leaf"),
        ]
        gpus = racks * s.gpus_per_rack
        return self.add(
            Assembly(
                aid,
                4,
                f"Scalable unit ({racks} racks, {gpus:,} GPUs)",
                lines,
                attrs={
                    "role": "su",
                    "racks": racks,
                    "gpus": gpus,
                    "leaves_per_plane": leaves,
                    "rails": f.rails,
                    "leaf_ports_down": f.leaf_down,
                    "leaf_ports_up": f.leaf_up,
                    "leaf_port_fill": _r(gpus / (leaves * f.leaf_down), 4),
                    "network_racks": nracks,
                    "host_links": gpus * f.planes,
                    "host_media": {g.media: g.links for g in groups},
                },
                diagram={
                    "kind": "su",
                    "racks": racks,
                    "network_racks": nracks,
                    "leaves": leaves,
                    "planes": f.planes,
                    "rails": f.rails,
                    "media": {g.media: g.links for g in groups},
                },
            )
        )

    def build_superpod(self, rack: Assembly, sp) -> Assembly:
        s, f = self.spec, self.fabric
        aid = f"superpod-{sp.racks}r"
        if aid in self.asm:
            return self.asm[aid]
        lines: list[Line] = []
        su_counts = Counter(zip(sp.su_racks, sp.su_leaves, strict=True))
        for (racks, leaves), n in sorted(su_counts.items(), reverse=True):
            lines.append(self.child(self.build_su(rack, racks, leaves), n))
        spines = sp.spines * f.planes
        runs = physical.leaf_spine_runs(s, sp.su_racks, sp.su_leaves, f.leaf_up, f.planes)
        groups = physical.group(s, self.cat, runs)
        self.link_groups[aid] = groups
        nracks = physical.network_racks(spines, self.switch_ru, s.layout.network_rack_ru)
        if spines:
            lines += [
                self.comp(f.switch_id, spines, f"spine: {sp.spines} per plane x {f.planes} planes"),
                self.comp("rack-48u-orv3", nracks, "spine racks"),
                *self.media_lines(groups, "leaf to spine"),
            ]
        return self.add(
            Assembly(
                aid,
                4,
                f"SuperPod ({sp.racks} racks, {sp.gpus:,} GPUs)",
                lines,
                attrs={
                    "role": "superpod",
                    "racks": sp.racks,
                    "gpus": sp.gpus,
                    "sus": len(sp.su_racks),
                    "leaves_per_plane": sp.leaves,
                    "spines_per_plane": sp.spines,
                    "spine_ports_down": f.spine_down,
                    "leaf_spine_links": sp.leaves * f.leaf_up * f.planes,
                    "fabric_media": {g.media: g.links for g in groups},
                    "non_blocking": s.scale_out.oversubscription == 1.0,
                },
                diagram={
                    "kind": "superpod",
                    "sus": list(sp.su_racks),
                    "leaves": sp.leaves,
                    "spines": sp.spines,
                    "planes": f.planes,
                    "media": {g.media: g.links for g in groups},
                },
            )
        )

    def build_halls(self, rack: Assembly) -> list[tuple[Assembly, list]]:
        s, f = self.spec, self.fabric
        sps = [(sp, self.build_superpod(rack, sp)) for sp in f.superpods]
        biggest_kw = max(a.power_w for _, a in sps) / 1000
        per_hall = int(s.facility.hall_it_mw_max * 1000 // biggest_kw)
        if per_hall < 1:
            raise ValueError(f"a SuperPod draws {biggest_kw / 1000:.1f} MW, more than the hall limit")
        chunks = [sps[i : i + per_hall] for i in range(0, len(sps), per_hall)]
        halls = []
        for chunk in chunks:
            members = Counter(a.id for _, a in chunk)
            aid = "hall-" + "-".join(f"{n}x{k.removeprefix('superpod-')}" for k, n in sorted(members.items()))
            halls.append((aid, chunk))
        out = []
        for aid, chunk in halls:
            if aid not in self.asm:
                self.asm[aid] = self._hall_assembly(aid, chunk)
            out.append((self.asm[aid], chunk))
        return out

    def _hall_assembly(self, aid: str, chunk: list) -> Assembly:
        s, f = self.spec, self.fabric
        lines = []
        for sp_id, n in sorted(Counter(a.id for _, a in chunk).items()):
            lines.append(self.child(self.asm[sp_id], n))
        it_kw = sum(a.power_w for _, a in chunk) / 1000
        racks = sum(sp.racks for sp, _ in chunk)
        gpus = sum(sp.gpus for sp, _ in chunk)
        rack_kw = self.asm["rack"].power_w / 1000
        liquid_kw = racks * rack_kw * s.rack.liquid_fraction
        cdus = ceil(liquid_kw / self.cat.component("cdu-1500kw").specs["capacity_kw"]) + s.facility.cdu_spares_per_hall
        ls_links = sum(sp.leaves * f.leaf_up for sp, _ in chunk) * f.planes
        uplinks = ls_links if f.tiers >= 3 else 0
        panel_ports = 2 * ls_links + uplinks
        panels = ceil(panel_ports / self.cat.component("mpo-patch-panel").specs["ports"])
        lines += [
            self.comp("mpo-patch-panel", panels, "zone panels at both ends of leaf-spine trunks + hall MDA uplinks"),
            self.comp("cdu-1500kw", cdus, f"N+{s.facility.cdu_spares_per_hall}"),
        ]
        capex = self.cat.facility["capex_usd_per_mw_it"]
        lines.append(
            Line(
                "facility:hall",
                "Facility build: powered shell, electrical, mechanical (per MW IT)",
                "facility",
                _r(it_kw / 1000, 3),
                0,
                capex,
                "facility",
            )
        )
        sp_ids = [a.id for _, a in chunk]
        return Assembly(
            aid,
            5,
            f"Data hall ({len(chunk)} SuperPods, {gpus:,} GPUs)",
            lines,
            attrs={
                "superpods": len(chunk),
                "racks": racks,
                "gpus": gpus,
                "it_mw": _r(it_kw / 1000),
                "facility_mw": _r(it_kw / 1000 * s.facility.pue),
                "hall_it_mw_max": s.facility.hall_it_mw_max,
                "liquid_mw": _r(liquid_kw / 1000),
                "air_mw": _r((it_kw - liquid_kw) / 1000),
                "cdus": cdus,
                "patch_panels": panels,
                "uplinks_to_core": uplinks,
            },
            diagram={
                "kind": "hall",
                "superpods": [
                    {
                        "id": i,
                        "gpus": self.asm[i].attrs["gpus"],
                        "racks": self.asm[i].attrs["racks"],
                        "mw": _r(self.asm[i].power_w / 1e6),
                    }
                    for i in sp_ids
                ],
                "cdus": cdus,
            },
        )

    def build_campus(self, halls: list[tuple[Assembly, list]]) -> Assembly:
        s, f = self.spec, self.fabric
        lines = [self.child(self.asm[h], n) for h, n in sorted(Counter(a.id for a, _ in halls).items())]
        core_switches = (f.t3 + f.t4) * f.planes
        core_groups: list[LinkGroup] = []
        if f.tiers >= 3:
            runs = []
            for i, (_, chunk) in enumerate(halls):
                n = sum(sp.leaves * f.leaf_up for sp, _ in chunk) * f.planes
                runs.append((physical.hall_to_core_m(s, i, len(halls)), n))
            core_groups = physical.group(s, self.cat, runs)
            lines += [
                self.comp(
                    f.switch_id,
                    f.t3 * f.planes,
                    f"{'super-spine' if f.tiers == 3 else 'block aggregation'}: {f.t3} per plane",
                ),
                *self.media_lines(core_groups, "spine to super-spine (cross-hall)"),
            ]
        t4_groups: list[LinkGroup] = []
        if f.tiers == 4:
            t4_groups = physical.group(s, self.cat, [(physical.core_local_m(s), f.links_t3_t4 * f.planes)])
            lines += [
                self.comp(f.switch_id, f.t4 * f.planes, f"core: {f.t4} per plane"),
                *self.media_lines(t4_groups, "aggregation to core"),
            ]
        self.link_groups["campus"] = core_groups + t4_groups
        core_racks = physical.network_racks(core_switches, self.switch_ru, s.layout.network_rack_ru)
        if core_racks:
            lines.append(self.comp("rack-48u-orv3", core_racks, "core network racks"))
        lines.append(self.comp("wan-edge-router", s.facility.wan_edge_routers, "campus WAN / DCI edge"))
        it_kw = sum(ln.power_w for ln in lines) / 1000
        core_kw = it_kw - sum(ln.power_w for ln in lines if ln.kind == "assembly") / 1000
        lines.append(
            Line(
                "facility:core",
                "Facility build for core network and WAN rooms (per MW IT)",
                "facility",
                _r(core_kw / 1000, 3),
                0,
                self.cat.facility["capex_usd_per_mw_it"],
                "facility",
            )
        )
        facility_mw = it_kw / 1000 * s.facility.pue
        sub = self.cat.component("substation-250mva")
        lines.append(
            self.comp(
                "substation-250mva",
                ceil(facility_mw / sub.specs["capacity_mw"]),
                f"{facility_mw:,.0f} MW facility load at PUE {s.facility.pue}",
            )
        )
        return self.add(
            Assembly(
                "campus",
                6,
                "Campus",
                lines,
                attrs={
                    "halls": len(halls),
                    "gpus": f.gpus,
                    "it_mw": _r(it_kw / 1000),
                    "facility_mw": _r(facility_mw),
                    "pue": s.facility.pue,
                    "core_switches": core_switches,
                    "fabric_tiers": f.tiers,
                    "cross_hall_media": {g.media: g.links for g in core_groups},
                },
                diagram={
                    "kind": "campus",
                    "halls": [
                        {
                            "id": a.id,
                            "gpus": a.attrs["gpus"],
                            "mw": a.attrs["it_mw"],
                            "to_core_m": physical.hall_to_core_m(s, i, len(halls)),
                        }
                        for i, (a, _) in enumerate(halls)
                    ],
                    "core_switches": core_switches,
                    "planes": f.planes,
                    "wan": s.facility.wan_edge_routers,
                    "substations": ceil(facility_mw / sub.specs["capacity_mw"]),
                },
            )
        )

    # ------------------------------------------------------- roll-ups
    def flatten(self, aid: str, memo: dict | None = None) -> dict[str, list]:
        """Indivisible items under an assembly: ref -> [qty, Line, power_w, cost_usd].

        Power and cost are summed, not re-derived from one line, because the same
        item (fiber, say) can carry a different unit cost in different assemblies.
        """
        memo = {} if memo is None else memo
        if aid in memo:
            return memo[aid]
        out: dict[str, list] = {}
        for ln in self.asm[aid].lines:
            if ln.kind == "assembly":
                for ref, (q, proto, pw, cost) in self.flatten(ln.ref, memo).items():
                    acc = out.setdefault(ref, [0, proto, 0.0, 0.0])
                    acc[0] += q * ln.qty
                    acc[2] += pw * ln.qty
                    acc[3] += cost * ln.qty
            else:
                acc = out.setdefault(ln.ref, [0, ln, 0.0, 0.0])
                acc[0] += ln.qty
                acc[2] += ln.power_w
                acc[3] += ln.cost_usd
        memo[aid] = out
        return out

    def complexity(self) -> dict:
        f = self.fabric
        flat = self.flatten("campus")
        weights = Counter()
        for aid, groups in self.link_groups.items():
            n = 1 if aid == "campus" else self.asm[aid].qty_total
            for g in groups:
                weights[self.cat.media[g.media].kind] += g.links * n
        copper, optical = weights["copper"], weights["optical"]
        labor = self.cat.labor
        racks = sum(q for _, (q, ln, *_) in flat.items() if ln.category == "rack")
        switches = f.switches
        hours = (
            racks * labor["rack_install_hours"]
            + switches * labor["switch_install_hours"]
            + 2 * copper * labor["copper_termination_minutes"] / 60
            + 2 * optical * labor["optical_termination_minutes"] / 60
        )
        frus = sum(q for _, (q, ln, *_) in flat.items() if ln.kind in ("component", "media"))
        return {
            "switches": switches,
            "fabric_tiers": f.tiers,
            "links_copper": copper,
            "links_optical": optical,
            "cable_terminations": 2 * (copper + optical),
            "optical_modules_800g_eq": sum(
                q for ref, (q, ln, *_) in flat.items() if ln.kind == "media" and ln.category == "optics"
            ),
            "bgp_sessions": (f.links_leaf_spine + f.links_spine_t3 + f.links_t3_t4) * f.planes,
            "distinct_skus": sum(1 for q, ln, *_ in flat.values() if ln.kind in ("component", "media", "fiber") and q),
            "field_replaceable_units": int(frus),
            "install_labor_hours": round(hours),
            "racks_total": int(racks),
        }

    # ------------------------------------------------------------ compile
    def compile(self) -> dict:
        s, f = self.spec, self.fabric
        node, tray = self.build_nodes()
        rack = self.build_rack(node, tray)
        halls = self.build_halls(rack)
        campus = self.build_campus(halls)
        # quantities across the whole build
        campus.qty_total = 1
        for a in self._topological():
            for ln in a.lines:
                if ln.kind == "assembly":
                    self.asm[ln.ref].qty_total += int(ln.qty) * a.qty_total

        tiers = []
        for level, key, title, blurb in TIERS:
            if level == 1:
                tiers.append(self._tier1(level, key, title, blurb))
                continue
            assemblies = [a for a in self.asm.values() if a.tier == level]
            assemblies.sort(key=lambda a: (-a.qty_total, a.id))
            tiers.append(
                {
                    "level": level,
                    "key": key,
                    "title": title,
                    "blurb": blurb,
                    "assemblies": [self._asm_doc(a) for a in assemblies],
                }
            )

        total_cost = campus.cost_usd
        facility_cost = sum(cost for _, ln, _, cost in self.flatten("campus").values() if ln.kind == "facility")
        wiring = Wiring(s, f) if f.tiers in (2, 3) else None
        roce_plan = self._roce()
        doc = {
            "format_version": FORMAT_VERSION,
            "name": s.name,
            "title": s.title,
            "architecture": s.architecture,
            "description": s.description.strip(),
            "spec": s.model_dump(mode="json"),
            "summary": {
                "gpus": f.gpus,
                "gpu_target": s.gpu_target,
                "racks": f.racks,
                "superpods": len(f.superpods),
                "halls": campus.attrs["halls"],
                "it_mw": campus.attrs["it_mw"],
                "facility_mw": campus.attrs["facility_mw"],
                "capex_usd": _r(total_cost, 0),
                "it_capex_usd": _r(total_cost - facility_cost, 0),
                "facility_capex_usd": _r(facility_cost, 0),
                "capex_per_gpu_usd": _r(total_cost / f.gpus, 0),
                "kw_per_gpu_all_in": _r(campus.power_w / f.gpus / 1000, 3),
            },
            "fabric": self._fabric_doc(),
            "complexity": self.complexity(),
            "roce": roce_plan,
            "bgp": wiring.summary() if wiring else None,
            "alternatives": alternatives(s, self.cat),
            "notes": self._notes(),
            "tiers": tiers,
            "references": self._references(),
        }
        doc["digest"] = digest(doc)
        return doc

    def _topological(self) -> list[Assembly]:
        """Assemblies with every parent before its children, starting at the campus."""
        seen: set[str] = set()
        post: list[Assembly] = []

        def visit(aid: str) -> None:
            if aid in seen:
                return
            seen.add(aid)
            for ln in self.asm[aid].lines:
                if ln.kind == "assembly":
                    visit(ln.ref)
            post.append(self.asm[aid])

        visit("campus")
        return post[::-1]

    def _line_doc(self, ln: Line) -> dict:
        return {
            "ref": ln.ref,
            "name": ln.name,
            "category": ln.category,
            "kind": ln.kind,
            "qty": _r(ln.qty),
            "unit_power_w": _r(ln.unit_power_w),
            "unit_cost_usd": _r(ln.unit_cost_usd, 2),
            "power_w": _r(ln.power_w),
            "cost_usd": _r(ln.cost_usd, 2),
            "note": ln.note,
        }

    def _asm_doc(self, a: Assembly) -> dict:
        return {
            "id": a.id,
            "name": a.name,
            "qty_total": a.qty_total,
            "power_w": _r(a.power_w),
            "cost_usd": _r(a.cost_usd, 2),
            "power_w_total": _r(a.power_w * a.qty_total),
            "cost_usd_total": _r(a.cost_usd * a.qty_total, 2),
            "attrs": a.attrs,
            "diagram": a.diagram,
            "bom": [self._line_doc(ln) for ln in a.lines],
        }

    def _tier1(self, level, key, title, blurb) -> dict:
        flat = self.flatten("campus")
        items = []
        for ref, (q, ln, pw, cost) in flat.items():
            if ln.kind not in ("component", "media", "fiber") or not q:
                continue
            refs = []
            if ln.kind == "component":
                refs = list(self.cat.component(ref).refs)
                specs = self.cat.component(ref).specs
            elif ln.kind == "media":
                m = self.cat.media[ref.removeprefix("media:")]
                refs, specs = list(m.refs), {"max_reach_m": m.max_reach_m, "kind": m.kind}
            else:
                specs = {}
            items.append(
                {
                    "ref": ref,
                    "name": ln.name,
                    "category": ln.category,
                    "kind": ln.kind,
                    "qty": _r(q),
                    "unit_power_w": _r(pw / q),
                    "unit_cost_usd": _r(cost / q, 2),
                    "power_w": _r(pw),
                    "cost_usd": _r(cost, 2),
                    "specs": specs,
                    "refs": refs,
                }
            )
        cat_order = [
            "accelerator",
            "cpu",
            "memory",
            "storage",
            "nic",
            "pcie",
            "scale_up_switch",
            "switch",
            "optics",
            "copper",
            "fiber",
            "scale_up_copper",
            "chassis",
            "rack",
            "power",
            "network_mgmt",
            "structured_cabling",
            "cooling",
            "wan",
            "utility",
        ]
        items.sort(key=lambda i: (cat_order.index(i["category"]) if i["category"] in cat_order else 99, i["ref"]))
        return {"level": level, "key": key, "title": title, "blurb": blurb, "items": items}

    def _fabric_doc(self) -> dict:
        f = self.fabric
        layers = {}
        for aid, groups in self.link_groups.items():
            n = 1 if aid == "campus" else self.asm[aid].qty_total
            layer = "host" if aid.startswith("su-") else "leaf_spine" if aid.startswith("superpod-") else "core"
            for g in groups:
                d = layers.setdefault(layer, {}).setdefault(g.media, {"links": 0, "max_m": 0.0})
                d["links"] += g.links * n
                d["max_m"] = max(d["max_m"], g.max_m)
        return {
            "switch": f.switch_id,
            "switch_name": self.switch.name,
            "planes": f.planes,
            "port_gbps": f.port_gbps,
            "radix": f.radix,
            "tiers": f.tiers,
            "max_endpoints": f.max_endpoints,
            "max_endpoints_3_tier": max_endpoints(f.radix, 3),
            "leaf_down": f.leaf_down,
            "leaf_up": f.leaf_up,
            "rails": f.rails,
            "oversubscription": self.spec.scale_out.oversubscription,
            "per_plane": {"leaf": f.leaves, "spine": f.spines, "t3": f.t3, "t4": f.t4},
            "switches": {
                "leaf": f.leaves * f.planes,
                "spine": f.spines * f.planes,
                "super_spine": f.t3 * f.planes,
                "core": f.t4 * f.planes,
                "total": f.switches,
            },
            "links": {
                "host": f.links_host * f.planes,
                "leaf_spine": f.links_leaf_spine * f.planes,
                "spine_t3": f.links_spine_t3 * f.planes,
                "t3_t4": f.links_t3_t4 * f.planes,
            },
            "media_by_layer": layers,
            "superpod_sizes": dict(Counter(sp.racks for sp in f.superpods)),
        }

    def _roce(self) -> dict:
        f, s = self.fabric, self.spec

        def worst(prefix: str) -> float:
            return max(
                (g.max_m for aid, gs in self.link_groups.items() if aid.startswith(prefix) for g in gs), default=0.0
            )

        host, ls, core = worst("su-"), worst("superpod-"), worst("campus")
        roles = {"leaf": [(f.leaf_down, host), (f.leaf_up, ls)]}
        if f.tiers == 2:
            roles["spine"] = [(f.radix, ls)]
        elif f.tiers >= 3:
            roles["spine"] = [(f.radix // 2, ls), (f.radix // 2, core)]
            roles["super_spine"] = [(f.radix, core)]
        return roce.plan(
            f.port_gbps, s.scale_out.mtu, s.scale_out.roce_priority, float(self.switch.specs.get("buffer_mb", 0)), roles
        )

    def _notes(self) -> list[str]:
        f, s = self.fabric, self.spec
        notes = []
        k800 = f.radix * f.port_gbps // 800 if f.port_gbps < 800 else f.radix
        notes.append(
            f"A {self.switch.name.split(' (')[0]} has radix {f.radix} at {f.port_gbps}G. A non-blocking leaf "
            f"splits it {f.leaf_down} down / {f.leaf_up} up, so leaves = GPUs / {f.leaf_down} per plane, not "
            f"GPUs / {f.radix}."
        )
        notes.append(
            f"Max endpoints for a non-blocking 3-tier Clos at radix k is k^3/4: {max_endpoints(f.radix, 3):,} at "
            f"k={f.radix}, but only {max_endpoints(k800, 3):,} at k={k800} (800G ports on the same ASIC)."
        )
        if f.planes > 1:
            notes.append(
                f"Each {s.scale_out.nic_gbps}G NIC is split into {f.planes} x {f.port_gbps}G planes (multi-plane, as "
                f"in Alibaba HPN and ConnectX-8 multi-plane), which raises the radix and keeps {f.gpus:,} GPUs in "
                f"{f.tiers} tiers."
            )
        alt = [a for a in alternatives(s, self.cat) if a.get("feasible") and not a.get("selected")]
        for a in alt:
            notes.append(
                f"Alternative: {a['switch_name'].split(' (')[0]} with {a['planes']} plane(s) needs {a['tiers']} tiers "
                f"and {a['switches']:,} switches."
            )
        notes.append(
            f"Port ends: {f.tiers} link layers x 2 ends x {f.gpus:,} GPUs x {f.planes} plane(s) = "
            f"{2 * f.tiers * f.gpus * f.planes:,} logical ports; modules are counted as 800G equivalents and copper "
            f"links (DAC/AEC) carry no transceivers."
        )
        return notes

    def _references(self) -> dict:
        used = set()
        for c in self.cat.components.values():
            used.update(c.refs)
        for m in self.cat.media.values():
            used.update(m.refs)
        used.update(self.cat.facility.get("refs", []))
        used.update(
            [
                "al-fares-2008",
                "rfc7938",
                "rfc6996",
                "ieee-8021qbb",
                "rfc3168",
                "dcqcn-2015",
                "meta-roce-2024",
                "alibaba-hpn-2024",
                "google-jupiter-2022",
                "aws-ultracluster",
                "nvidia-dgx-superpod-gb200",
                "sonic",
                "frr",
            ]
        )
        return {r: self.cat.references[r] for r in sorted(used) if r in self.cat.references}


def digest(doc: dict) -> str:
    body = {k: v for k, v in doc.items() if k != "digest"}
    return hashlib.sha256(canonical_json(body).encode()).hexdigest()


def canonical_json(doc: dict) -> str:
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compile_design(spec: DesignSpec, catalog: Catalog) -> dict:
    return Compiler(spec, catalog).compile()
