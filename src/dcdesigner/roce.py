"""Lossless RoCE parameters: PFC headroom and ECN marking thresholds.

PFC headroom per port and lossless priority (IEEE 802.1Qbb) must absorb what
is in flight after a PAUSE is sent: two cable delays, the peer's response
time, and up to one MTU in each direction already being serialized:

    headroom = 2 x MTU + rate x (2 x length x 5 ns/m + t_response)

t_response (1.5 us) is a conservative planning value covering MAC/PHY/FEC
latency at both ends plus the 802.1Qbb response budget; check your ASIC
vendor's headroom calculator before production.

ECN (RFC 3168) thresholds start from the DCQCN paper's 40G values
(Kmin 5 KB, Kmax 200 KB, Pmax 1 %) scaled linearly with port speed. They are
starting points to tune with traffic, not final values.
"""

from __future__ import annotations

from math import ceil

T_RESPONSE_S = 1.5e-6
PROPAGATION_S_PER_M = 5e-9
DCQCN_BASE_GBPS = 40
DCQCN_KMIN_KB = 5
DCQCN_KMAX_KB = 200
DCQCN_PMAX = 0.01
ROCE_DSCP = 26
CNP_DSCP = 48
CNP_PRIORITY = 6


def headroom_bytes(port_gbps: int, length_m: float, mtu: int) -> int:
    rate = port_gbps * 1e9 / 8
    return ceil(2 * mtu + rate * (2 * length_m * PROPAGATION_S_PER_M + T_RESPONSE_S))


def ecn_thresholds(port_gbps: int) -> dict:
    scale = port_gbps / DCQCN_BASE_GBPS
    return {
        "kmin_kb": round(DCQCN_KMIN_KB * scale),
        "kmax_kb": round(DCQCN_KMAX_KB * scale),
        "pmax": DCQCN_PMAX,
    }


def plan(port_gbps: int, mtu: int, priority: int, buffer_mb: float, roles: dict[str, list[tuple[int, float]]]) -> dict:
    """roles maps a switch role to [(port count, worst-case cable m), ...]."""
    out_roles = {}
    for role, groups in roles.items():
        per_port = [(n, headroom_bytes(port_gbps, m, mtu), m) for n, m in groups if n]
        total = sum(n * h for n, h, _ in per_port)
        out_roles[role] = {
            "ports": [{"count": n, "worst_cable_m": m, "headroom_bytes": h} for n, h, m in per_port],
            "headroom_total_mb": round(total / 1e6, 3),
            "buffer_mb": buffer_mb,
            "headroom_share_of_buffer": round(total / (buffer_mb * 1e6), 4) if buffer_mb else None,
        }
    return {
        "lossless_priority": priority,
        "roce_dscp": ROCE_DSCP,
        "cnp_dscp": CNP_DSCP,
        "cnp_priority": CNP_PRIORITY,
        "mtu": mtu,
        "port_gbps": port_gbps,
        "ecn": ecn_thresholds(port_gbps),
        "t_response_us": T_RESPONSE_S * 1e6,
        "roles": out_roles,
        "refs": ["ieee-8021qbb", "rfc3168", "dcqcn-2015", "meta-roce-2024"],
    }
