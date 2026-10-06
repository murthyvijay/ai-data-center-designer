import pytest

from dcdesigner.fabric import FabricError, max_endpoints, plan_fabric

from conftest import spec_from


def test_fat_tree_capacity_formula():
    # k^3/4 for three tiers (Al-Fares 2008), k^2/2 for two.
    assert max_endpoints(64, 3) == 65_536
    assert max_endpoints(128, 3) == 524_288
    assert max_endpoints(64, 2) == 2_048


def test_arch_a_counts(arch_a, catalog):
    p = plan_fabric(arch_a, catalog)
    assert (p.radix, p.port_gbps, p.leaf_down, p.leaf_up, p.tiers) == (128, 400, 64, 64, 3)
    assert p.racks == 4167 and p.gpus == 300_024
    # 74 full SuperPods of 56 racks plus one of 23 racks.
    assert [sp.racks for sp in p.superpods].count(56) == 74 and p.superpods[-1].racks == 23
    assert (p.leaves, p.spines, p.t3) == (4764, 4764, 2382)
    assert p.switches == 23_820


def test_arch_b_counts(arch_b, catalog):
    p = plan_fabric(arch_b, catalog)
    assert p.racks == 9375 and p.gpus == 300_000
    assert (p.leaves, p.spines, p.t3) == (4688, 4688, 2344)
    assert p.switches == 23_440


def test_non_blocking_links_balance(arch_b, catalog):
    p = plan_fabric(arch_b, catalog)
    # Every leaf has as many uplinks as down ports; spine up equals spine down.
    assert p.links_leaf_spine == p.leaves * p.leaf_up
    assert p.links_spine_t3 == p.links_leaf_spine
    assert p.links_leaf_spine >= p.links_host
    assert p.t3 * p.radix >= p.links_spine_t3


def test_single_plane_800g_on_51t_needs_four_tiers(arch_b, catalog):
    p = plan_fabric(arch_b, catalog, planes=1, autofit=True)
    assert p.radix == 64 and p.tiers == 4
    assert p.gpus > max_endpoints(64, 3)


def test_102t_single_plane_three_tiers(arch_b, catalog):
    p = plan_fabric(arch_b, catalog, switch_id="switch-102t4", planes=1, autofit=True)
    assert (p.radix, p.tiers, p.switches) == (128, 3, 11_720)


def test_superpod_too_big_for_spine(catalog):
    spec = spec_from("arch-b-ocp8-300k", scale_out__sus_per_superpod=9)
    with pytest.raises(FabricError):
        plan_fabric(spec, catalog)


def test_small_cluster_two_tier(catalog):
    spec = spec_from("arch-b-ocp8-300k", gpu_target=2048)
    p = plan_fabric(spec, catalog)
    assert p.tiers == 2 and p.t3 == 0
    assert p.spines * p.radix >= p.leaves * p.leaf_up


def test_tiny_cluster_one_tier(catalog):
    spec = spec_from("arch-b-ocp8-300k", gpu_target=64, scale_out__rails=1, scale_out__planes=1)
    p = plan_fabric(spec, catalog)
    assert p.tiers == 1 and p.leaves == 1 and p.spines == 0
