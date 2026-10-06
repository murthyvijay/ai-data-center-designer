import ipaddress

import pytest

from dcdesigner import compile_design, nos
from dcdesigner.fabric import plan_fabric
from dcdesigner.wiring import Wiring

from conftest import spec_from


@pytest.fixture(scope="module", params=["arch-a-nvl72-300k", "arch-b-ocp8-300k"])
def small(request, catalog):
    # Three SuperPods plus a partial one: small enough to wire exhaustively.
    target = {"arch-a-nvl72-300k": 72 * (56 * 3 + 23), "arch-b-ocp8-300k": 32 * (128 * 3 + 31)}[request.param]
    spec = spec_from(request.param, gpu_target=target)
    plan = plan_fabric(spec, catalog)
    assert plan.tiers == 3
    return spec, plan, Wiring(spec, plan)


def _all_devices(plan, w):
    for p in range(plan.planes):
        yield from (w.leaf(p, i) for i in range(plan.leaves))
        yield from (w.spine(p, i) for i in range(plan.spines))
        yield from (w.super_spine(p, i) for i in range(plan.t3))


def test_every_link_is_symmetric(small):
    spec, plan, w = small
    devices = {d.name: d for d in _all_devices(plan, w)}
    fabric_links = 0
    for d in devices.values():
        idx = [p.index for p in d.ports]
        assert len(idx) == len(set(idx)) and max(idx) < d.radix
        for port in d.ports:
            if port.role == "host":
                continue
            peer = devices[port.peer]
            back = next(p for p in peer.ports if p.index == port.peer_port)
            assert back.peer == d.name and back.peer_port == port.index
            assert (back.local_ip, back.peer_ip) == (port.peer_ip, port.local_ip)
            assert back.peer_asn == d.asn and port.peer_asn == peer.asn
            net = ipaddress.ip_network(f"{port.local_ip}/31", strict=False)
            assert ipaddress.ip_address(port.peer_ip) in net
            fabric_links += 1
    assert fabric_links == 2 * (plan.links_leaf_spine + plan.links_spine_t3) * plan.planes


def test_every_gpu_lands_once_per_plane(small):
    spec, plan, w = small
    for p in range(plan.planes):
        gpus = [port.peer for i in range(plan.leaves) for port in w.leaf(p, i).ports if port.role == "host"]
        assert len(gpus) == len(set(gpus)) == plan.gpus


def test_rail_alignment(small):
    spec, plan, w = small
    leaf = w.leaf(0, 0)
    rails = {int(port.peer.rsplit("gpu", 1)[1]) % plan.rails for port in leaf.ports if port.role == "host"}
    assert len(rails) == 1


def test_loopbacks_and_asns_unique(small):
    spec, plan, w = small
    devs = list(_all_devices(plan, w))
    assert len({d.loopback for d in devs}) == len(devs)
    assert len({d.asn for d in devs if d.role == "leaf"}) == plan.leaves * plan.planes


@pytest.mark.parametrize("nos_name", ["sonic", "eos", "nxos"])
def test_configs_render(nos_name, arch_b, catalog):
    doc = compile_design(arch_b, catalog)
    w = Wiring(arch_b, plan_fabric(arch_b, catalog))
    for role in ("leaf", "spine", "super"):
        dev = w.device(role, 1, 0)
        text = nos.render(nos_name, dev, doc["roce"])
        assert dev.name in text and str(dev.asn) in text
        peers = [p for p in dev.ports if p.peer_asn is not None]
        assert sum(text.count(f"{p.peer_ip}\n") + text.count(f"{p.peer_ip} remote-as") for p in peers) >= len(peers)


def test_port_names(arch_b, catalog):
    w = Wiring(arch_b, plan_fabric(arch_b, catalog))
    dev = w.device("leaf", 0, 0)
    assert nos.port_name("sonic", dev, 0) == "Ethernet0"
    assert nos.port_name("sonic", dev, 1) == "Ethernet4"
    assert nos.port_name("sonic", dev, 2) == "Ethernet8"
    assert nos.port_name("eos", dev, 1) == "Ethernet1/5"
    assert nos.port_name("nxos", dev, 3) == "Ethernet1/2/2"
