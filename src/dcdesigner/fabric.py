"""Scale-out Clos synthesizer.

Builds a rail-optimized folded Clos (fat-tree) per plane from switch radix,
NIC speed and the scalable-unit (SU) / SuperPod grouping in the spec.

Design rules (see docs/design-notes.md for derivations):

* Radix k is the number of logical ports at the plane's port speed:
  k = ASIC bandwidth / port speed (a 51.2T ASIC is 64 x 800G or 128 x 400G).
* Leaves split their ports d down / u up, with d:u equal to the
  oversubscription ratio (1:1 is non-blocking, so d = u = k/2).
* Leaves are rail-aligned: rail r of every node in an SU lands on the same
  leaf group, so an SU needs rails x ceil(GPUs per rail / d) leaves.
* A SuperPod is a leaf/spine block. Every leaf links to the SuperPod's spines
  and a spine has k/2 ports down and k/2 up, so a SuperPod holds at most k/2
  leaves. With a single SuperPod the spine uses all k ports down (2 tiers).
* Super-spines interconnect SuperPods. Each super-spine reaches every
  SuperPod, so up to k SuperPods fit in 3 tiers; beyond that, SuperPods are
  grouped into blocks of k/2 under a fourth tier.
* Maximum non-blocking endpoints for t tiers: 2 * (k/2)^t (k^3/4 for t = 3,
  Al-Fares et al. 2008).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from .catalog import Catalog
from .schema import DesignSpec


class FabricError(ValueError):
    pass


@dataclass(frozen=True)
class SuperPodPlan:
    index: int
    racks: int
    gpus: int
    su_racks: tuple[int, ...]
    su_leaves: tuple[int, ...]  # per plane
    leaves: int  # per plane
    spines: int  # per plane
    leaf_offset: int  # global leaf index of this SuperPod's first leaf (per plane)
    spine_offset: int

    @property
    def key(self) -> str:
        return f"{self.racks}r"


@dataclass(frozen=True)
class FabricPlan:
    switch_id: str
    planes: int
    port_gbps: int
    radix: int
    ports_per_cage: int
    leaf_down: int
    leaf_up: int
    rails: int
    tiers: int
    racks: int
    gpus: int
    superpods: tuple[SuperPodPlan, ...]
    leaves: int  # per plane
    spines: int  # per plane
    t3: int  # per plane (super-spine, or block aggregation in a 4-tier fabric)
    t4: int  # per plane (core, 4-tier fabrics only)
    t3_blocks: tuple[int, ...]  # 4-tier only: T3 switches per block of SuperPods
    links_host: int  # per plane
    links_leaf_spine: int  # per plane
    links_spine_t3: int  # per plane
    links_t3_t4: int  # per plane

    @property
    def switches_per_plane(self) -> int:
        return self.leaves + self.spines + self.t3 + self.t4

    @property
    def switches(self) -> int:
        return self.switches_per_plane * self.planes

    @property
    def max_endpoints(self) -> int:
        return max_endpoints(self.radix, self.tiers)

    @property
    def spine_down(self) -> int:
        return self.radix if self.tiers == 2 else self.radix // 2

    def superpod_of_leaf(self, leaf: int) -> SuperPodPlan:
        for sp in self.superpods:
            if sp.leaf_offset <= leaf < sp.leaf_offset + sp.leaves:
                return sp
        raise IndexError(leaf)

    def superpod_of_spine(self, spine: int) -> SuperPodPlan:
        for sp in self.superpods:
            if sp.spine_offset <= spine < sp.spine_offset + sp.spines:
                return sp
        raise IndexError(spine)


def max_endpoints(radix: int, tiers: int) -> int:
    if tiers <= 1:
        return radix
    return 2 * (radix // 2) ** tiers


def radix_at(catalog: Catalog, switch_id: str, port_gbps: int) -> tuple[int, int]:
    """Returns (logical ports, logical ports per physical cage) at a port speed."""
    specs = catalog.component(switch_id).specs
    cage_gbps = int(specs["cage_gbps"])
    if port_gbps > cage_gbps or cage_gbps % port_gbps:
        raise FabricError(f"{switch_id}: {port_gbps}G ports do not break out evenly from {cage_gbps}G cages")
    per_cage = cage_gbps // port_gbps
    return int(specs["cages"]) * per_cage, per_cage


def _leaf_split(radix: int, oversub: float) -> tuple[int, int]:
    down = int(radix * oversub / (1 + oversub))
    return down, radix - down


def _leaves_for(racks: int, gpus_per_rack: int, rails: int, leaf_down: int) -> int:
    if racks == 0:
        return 0
    per_rail = racks * gpus_per_rack // rails
    return rails * ceil(per_rail / leaf_down)


def _fit_grouping(su_racks: int, sus: int, gpr: int, rails: int, d: int, limit: int) -> tuple[int, int]:
    while su_racks > 1 and _leaves_for(su_racks, gpr, rails, d) > limit:
        su_racks -= 1
    per_su = _leaves_for(su_racks, gpr, rails, d)
    return su_racks, max(1, min(sus, limit // per_su))


def plan_fabric(
    spec: DesignSpec,
    catalog: Catalog,
    *,
    switch_id: str | None = None,
    planes: int | None = None,
    autofit: bool = False,
) -> FabricPlan:
    """Plans the fabric. With autofit, the SU and SuperPod sizes from the spec are
    shrunk until they fit the radix (used to compare other switch choices)."""
    so = spec.scale_out
    switch_id = switch_id or so.switch
    planes = planes or so.planes
    if so.nic_gbps % planes:
        raise FabricError("NIC speed must divide evenly across planes")
    port_gbps = so.nic_gbps // planes
    k, per_cage = radix_at(catalog, switch_id, port_gbps)
    d, u = _leaf_split(k, so.oversubscription)
    gpr = spec.gpus_per_rack
    racks = ceil(spec.gpu_target / gpr)
    gpus = racks * gpr
    if gpus <= k:
        # One switch per plane with every port facing a GPU: no fabric tiers above it.
        d, u = k, 0

    su_size, sus = so.su_racks, so.sus_per_superpod
    if autofit:
        su_size, sus = _fit_grouping(su_size, sus, gpr, so.rails, d, k // 2)
    sp_racks = su_size * sus
    full, rem = divmod(racks, sp_racks)
    sizes = [sp_racks] * full + ([rem] if rem else [])

    superpods: list[SuperPodPlan] = []
    leaf_off = spine_off = 0
    single = len(sizes) == 1
    spine_down = k if single else k // 2
    for i, r in enumerate(sizes):
        su_full, su_rem = divmod(r, su_size)
        su_racks = tuple([su_size] * su_full + ([su_rem] if su_rem else []))
        su_leaves = tuple(_leaves_for(x, gpr, so.rails, d) for x in su_racks)
        leaves = sum(su_leaves)
        if leaves > spine_down:
            raise FabricError(
                f"SuperPod of {r} racks needs {leaves} leaves per plane, but a spine has only "
                f"{spine_down} down ports at {port_gbps}G; shrink su_racks or sus_per_superpod"
            )
        spines = ceil(leaves * u / spine_down) if u else 0
        superpods.append(SuperPodPlan(i, r, r * gpr, su_racks, su_leaves, leaves, spines, leaf_off, spine_off))
        leaf_off += leaves
        spine_off += spines

    leaves = leaf_off
    spines = spine_off
    up_total = sum(sp.leaves * u for sp in superpods if sp.spines)
    t3 = t4 = 0
    blocks: tuple[int, ...] = ()
    links_spine_t3 = links_t3_t4 = 0
    if leaves == 1:
        tiers = 1
    elif single:
        tiers = 2
    elif len(superpods) <= k:
        tiers = 3
        t3 = ceil(up_total / k)
        links_spine_t3 = up_total
    else:
        tiers = 4
        per_block = k // 2
        groups = [superpods[i : i + per_block] for i in range(0, len(superpods), per_block)]
        if len(groups) > k:
            raise FabricError(
                f"{len(superpods)} SuperPods exceed a 4-tier fabric at radix {k}; "
                "use a higher-radix switch or more planes"
            )
        blocks = tuple(ceil(sum(sp.leaves * u for sp in g) / per_block) for g in groups)
        t3 = sum(blocks)
        t4 = ceil(up_total / k)
        links_spine_t3 = links_t3_t4 = up_total

    return FabricPlan(
        switch_id=switch_id,
        planes=planes,
        port_gbps=port_gbps,
        radix=k,
        ports_per_cage=per_cage,
        leaf_down=d,
        leaf_up=u if tiers > 1 else 0,
        rails=so.rails,
        tiers=tiers,
        racks=racks,
        gpus=gpus,
        superpods=tuple(superpods),
        leaves=leaves,
        spines=spines,
        t3=t3,
        t4=t4,
        t3_blocks=blocks,
        links_host=gpus,
        links_leaf_spine=up_total,
        links_spine_t3=links_spine_t3,
        links_t3_t4=links_t3_t4,
    )


def alternatives(spec: DesignSpec, catalog: Catalog) -> list[dict]:
    """Evaluates the same cluster on other switch / plane choices for comparison."""
    out = []
    switches = sorted(c.id for c in catalog.components.values() if c.category == "switch")
    for sw in switches:
        for planes in (1, 2):
            row = {"switch": sw, "switch_name": catalog.component(sw).name, "planes": planes}
            try:
                p = plan_fabric(spec, catalog, switch_id=sw, planes=planes, autofit=True)
            except FabricError as e:
                row.update(feasible=False, reason=str(e))
            else:
                row.update(
                    feasible=True,
                    port_gbps=p.port_gbps,
                    radix=p.radix,
                    tiers=p.tiers,
                    max_endpoints=p.max_endpoints,
                    switches=p.switches,
                    superpod_gpus=p.superpods[0].gpus,
                    leaves=p.leaves * planes,
                    spines=p.spines * planes,
                    t3=p.t3 * planes,
                    t4=p.t4 * planes,
                    fabric_links=(p.links_leaf_spine + p.links_spine_t3 + p.links_t3_t4) * planes,
                    selected=(sw == spec.scale_out.switch and planes == spec.scale_out.planes),
                )
            out.append(row)
    return out
