"""Deterministic device naming, wiring, ASN and IP plan for the scale-out fabric.

Routing follows RFC 7938: eBGP on every fabric link, one private 4-byte ASN
(RFC 6996) per leaf, one per SuperPod spine group, one per plane for the
super-spines, so AS-path loop prevention stops valley routing. Switch links
use /31s; GPU NIC ports are routed /31 host links (one per GPU per plane).

Wiring rule inside a SuperPod with L leaves of u uplinks and S spines:
link m = leaf * u + uplink goes to spine (m mod S), spine port (m div S).
The same rule spreads spine uplinks over the super-spines. With full blocks
(S = u) this is the textbook fat-tree: uplink j of every leaf lands on spine j.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from math import ceil, log2

from .fabric import FabricPlan, SuperPodPlan
from .schema import DesignSpec

LEAF_ASN_BASE = 4_200_000_000
SPINE_ASN_BASE = 4_201_000_000
SUPER_ASN_BASE = 4_202_000_000
HOST_NET = ipaddress.ip_network("10.0.0.0/8")
LOOPBACK_NET = ipaddress.ip_network("10.255.0.0/16")
P2P_NET = ipaddress.ip_network("100.64.0.0/10")


class WiringError(ValueError):
    pass


@dataclass(frozen=True)
class Port:
    index: int
    role: str  # "host" | "up" | "down"
    peer: str
    peer_port: int | None
    local_ip: str
    peer_ip: str
    peer_asn: int | None
    description: str


@dataclass(frozen=True)
class Device:
    name: str
    role: str  # leaf | spine | super
    plane: int
    asn: int
    loopback: str
    ports: tuple[Port, ...]
    radix: int
    ports_per_cage: int
    port_gbps: int


def leaf_name(p: int, sp: int, local: int) -> str:
    return f"p{p}-sp{sp:03d}-lf{local:03d}"


def spine_name(p: int, sp: int, local: int) -> str:
    return f"p{p}-sp{sp:03d}-sw{local:03d}"


def super_name(p: int, z: int) -> str:
    return f"p{p}-ss{z:04d}"


class Wiring:
    def __init__(self, spec: DesignSpec, plan: FabricPlan):
        if plan.tiers not in (2, 3):
            raise WiringError(f"config generation supports 2- and 3-tier fabrics (this plan has {plan.tiers})")
        self.spec = spec
        self.plan = plan
        self.u = plan.leaf_up
        self.per_plane_devices = plan.leaves + plan.spines + plan.t3
        self.per_plane_links = plan.links_leaf_spine + plan.links_spine_t3
        if self.per_plane_devices * plan.planes + 2 > LOOPBACK_NET.num_addresses:
            raise WiringError("loopback pool too small")
        if self.per_plane_links * plan.planes * 2 > P2P_NET.num_addresses:
            raise WiringError("point-to-point pool too small")
        self.host_block = 2 ** ceil(log2(2 * plan.leaf_down))
        self.plane_host_size = HOST_NET.num_addresses // 4
        if plan.leaves * self.host_block > self.plane_host_size or plan.planes > 4:
            raise WiringError("host address pool too small")
        self._sp_rack_offset = []
        off = 0
        for sp in plan.superpods:
            self._sp_rack_offset.append(off)
            off += sp.racks

    # ------------------------------------------------------------ numbering
    def leaf_asn(self, p: int, leaf: int) -> int:
        return LEAF_ASN_BASE + p * 100_000 + leaf

    def spine_asn(self, p: int, sp: int) -> int:
        return SPINE_ASN_BASE + p * 10_000 + sp

    def super_asn(self, p: int) -> int:
        return SUPER_ASN_BASE + p

    def _loopback(self, p: int, ordinal: int) -> str:
        return str(LOOPBACK_NET.network_address + 1 + p * self.per_plane_devices + ordinal)

    def _p2p(self, p: int, link: int) -> tuple[str, str]:
        base = P2P_NET.network_address + 2 * (p * self.per_plane_links + link)
        return str(base), str(base + 1)  # (lower tier, upper tier)

    def _host(self, p: int, leaf: int, port: int) -> tuple[str, str]:
        base = HOST_NET.network_address + p * self.plane_host_size + leaf * self.host_block + 2 * port
        return str(base), str(base + 1)  # (leaf, GPU NIC)

    # ------------------------------------------------------------- topology
    def _spine_split(self, sp: SuperPodPlan) -> tuple[int, int]:
        return divmod(sp.leaves * self.u, sp.spines)

    def _spine_uplinks(self, sp: SuperPodPlan, s_local: int) -> int:
        q, r = self._spine_split(sp)
        return q + (1 if s_local < r else 0)

    def _spine_up_base(self, sp: SuperPodPlan, s_local: int) -> int:
        q, r = self._spine_split(sp)
        return sp.leaf_offset * self.u + s_local * q + min(s_local, r)

    def _super_of(self, m: int) -> tuple[int, int]:
        z = self.plan.t3
        return m % z, m // z

    def _locate_spine_uplink(self, m: int) -> tuple[SuperPodPlan, int, int]:
        for sp in self.plan.superpods:
            base = sp.leaf_offset * self.u
            if base <= m < base + sp.leaves * self.u:
                q, r = self._spine_split(sp)
                o = m - base
                if o < r * (q + 1):
                    return sp, o // (q + 1), o % (q + 1)
                o -= r * (q + 1)
                return sp, r + o // q, o % q
        raise IndexError(m)

    def _gpu_for(self, sp: SuperPodPlan, leaf_local: int, port: int) -> str | None:
        spec, plan = self.spec, self.plan
        gpr = spec.gpus_per_rack
        per_rail_rack = gpr // plan.rails
        rack_off = self._sp_rack_offset[sp.index]
        li = leaf_local
        for racks, leaves in zip(sp.su_racks, sp.su_leaves, strict=True):
            if li < leaves:
                lpr = leaves // plan.rails
                rail = li // lpr
                n = (li % lpr) * plan.leaf_down + port
                if n >= racks * per_rail_rack:
                    return None
                rack = rack_off + n // per_rail_rack
                slot = (n % per_rail_rack) * plan.rails + rail
                node, gpu = divmod(slot, spec.node.accelerators)
                return f"rack{rack:05d}-n{node:02d}-gpu{gpu}"
            li -= leaves
            rack_off += racks
        raise IndexError(leaf_local)

    # -------------------------------------------------------------- devices
    def leaf(self, p: int, leaf: int) -> Device:
        plan = self.plan
        sp = plan.superpod_of_leaf(leaf)
        l_local = leaf - sp.leaf_offset
        ports = []
        for i in range(plan.leaf_down):
            gpu = self._gpu_for(sp, l_local, i)
            if gpu is None:
                continue
            mine, peer = self._host(p, leaf, i)
            ports.append(Port(i, "host", gpu, None, mine, peer, None, f"{gpu} plane {p}"))
        for j in range(self.u):
            m = l_local * self.u + j
            s_local, s_port = m % sp.spines, m // sp.spines
            mine, peer = self._p2p(p, sp.leaf_offset * self.u + m)
            name = spine_name(p, sp.index, s_local)
            ports.append(
                Port(plan.leaf_down + j, "up", name, s_port, mine, peer, self.spine_asn(p, sp.index), f"to {name}")
            )
        return Device(
            leaf_name(p, sp.index, l_local),
            "leaf",
            p,
            self.leaf_asn(p, leaf),
            self._loopback(p, leaf),
            tuple(ports),
            plan.radix,
            plan.ports_per_cage,
            plan.port_gbps,
        )

    def spine(self, p: int, spine: int) -> Device:
        plan = self.plan
        sp = plan.superpod_of_spine(spine)
        s_local = spine - sp.spine_offset
        ports = []
        total = sp.leaves * self.u
        for port in range(plan.spine_down):
            m = port * sp.spines + s_local
            if m >= total:
                break
            l_local, j = divmod(m, self.u)
            leaf = sp.leaf_offset + l_local
            lower, upper = self._p2p(p, sp.leaf_offset * self.u + m)
            name = leaf_name(p, sp.index, l_local)
            ports.append(
                Port(port, "down", name, plan.leaf_down + j, upper, lower, self.leaf_asn(p, leaf), f"to {name}")
            )
        if plan.tiers == 3:
            base = self._spine_up_base(sp, s_local)
            for t in range(self._spine_uplinks(sp, s_local)):
                m = base + t
                z, z_port = self._super_of(m)
                lower, upper = self._p2p(p, plan.links_leaf_spine + m)
                name = super_name(p, z)
                ports.append(
                    Port(plan.radix // 2 + t, "up", name, z_port, lower, upper, self.super_asn(p), f"to {name}")
                )
        return Device(
            spine_name(p, sp.index, s_local),
            "spine",
            p,
            self.spine_asn(p, sp.index),
            self._loopback(p, plan.leaves + spine),
            tuple(ports),
            plan.radix,
            plan.ports_per_cage,
            plan.port_gbps,
        )

    def super_spine(self, p: int, z: int) -> Device:
        plan = self.plan
        if plan.tiers != 3:
            raise WiringError("this fabric has no super-spine tier")
        ports = []
        for port in range(plan.radix):
            m = port * plan.t3 + z
            if m >= plan.links_spine_t3:
                break
            sp, s_local, t = self._locate_spine_uplink(m)
            lower, upper = self._p2p(p, plan.links_leaf_spine + m)
            name = spine_name(p, sp.index, s_local)
            ports.append(
                Port(port, "down", name, plan.radix // 2 + t, upper, lower, self.spine_asn(p, sp.index), f"to {name}")
            )
        return Device(
            super_name(p, z),
            "super",
            p,
            self.super_asn(p),
            self._loopback(p, plan.leaves + plan.spines + z),
            tuple(ports),
            plan.radix,
            plan.ports_per_cage,
            plan.port_gbps,
        )

    def device(self, role: str, plane: int, index: int) -> Device:
        if not 0 <= plane < self.plan.planes:
            raise WiringError(f"plane must be 0..{self.plan.planes - 1}")
        limit = {"leaf": self.plan.leaves, "spine": self.plan.spines, "super": self.plan.t3}[role]
        if not 0 <= index < limit:
            raise WiringError(f"{role} index must be 0..{limit - 1}")
        return {"leaf": self.leaf, "spine": self.spine, "super": self.super_spine}[role](plane, index)

    def summary(self) -> dict:
        plan = self.plan
        sessions = (plan.links_leaf_spine + plan.links_spine_t3) * plan.planes
        return {
            "model": "eBGP everywhere (RFC 7938), /31 point-to-point, ECMP across all uplinks",
            "asn": {
                "leaf": f"{LEAF_ASN_BASE} + plane*100000 + leaf (one per leaf)",
                "spine": f"{SPINE_ASN_BASE} + plane*10000 + superpod (shared by a SuperPod's spines)",
                "super_spine": f"{SUPER_ASN_BASE} + plane (shared per plane)",
                "unique_asns": (plan.leaves + len(plan.superpods) + (1 if plan.t3 else 0)) * plan.planes,
            },
            "ip_plan": {
                "gpu_host_links": (
                    f"{HOST_NET} (one /10 per plane, a /{32 - int(log2(self.host_block))} per leaf, /31 per GPU port)"
                ),
                "switch_links": f"{P2P_NET} (/31 per fabric link)",
                "loopbacks": f"{LOOPBACK_NET} (/32 per switch)",
            },
            "bgp_sessions": sessions,
            "max_paths": max(plan.leaf_up, plan.radix // 2),
            "refs": ["rfc7938", "rfc6996", "meta-roce-2024"],
        }
