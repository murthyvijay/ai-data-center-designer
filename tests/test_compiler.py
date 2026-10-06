import json
import subprocess
import sys

import pytest

from dcdesigner import compile_design
from dcdesigner.compiler import canonical_json
from dcdesigner.report import markdown

from conftest import PRESETS, ROOT, spec_from


@pytest.fixture(scope="module")
def docs(arch_a, arch_b, catalog):
    return {"a": compile_design(arch_a, catalog), "b": compile_design(arch_b, catalog)}


def _tier(doc, level):
    return next(t for t in doc["tiers"] if t["level"] == level)


def _item(doc, ref):
    return next((i for i in _tier(doc, 1)["items"] if i["ref"] == ref), None)


def test_deterministic(arch_a, catalog, docs):
    again = compile_design(arch_a, catalog)
    assert canonical_json(again) == canonical_json(docs["a"])


def test_deterministic_across_processes(docs):
    code = (
        "import yaml;from dcdesigner import *;"
        f"s=DesignSpec.model_validate(yaml.safe_load(open(r'{ROOT}/presets/arch-a-nvl72-300k.yaml')));"
        "print(compile_design(s,load_catalog())['digest'])"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True, cwd=ROOT)
    assert out.stdout.strip() == docs["a"]["digest"]


def test_six_tiers(docs):
    assert [t["level"] for t in docs["a"]["tiers"]] == [1, 2, 3, 4, 5, 6]


def test_silicon_totals_match_fabric(docs):
    for doc, gpu in ((docs["a"], "gpu-gb200"), (docs["b"], "gpu-oam-1000w")):
        g = doc["summary"]["gpus"]
        assert _item(doc, gpu)["qty"] == g
        assert _item(doc, "nic-800g")["qty"] == g
        assert _item(doc, "switch-51t2")["qty"] == doc["fabric"]["switches"]["total"]


def test_rollups_conserve_power_and_cost(docs):
    for doc in docs.values():
        campus = _tier(doc, 6)["assemblies"][0]
        items = _tier(doc, 1)["items"]
        facility = doc["summary"]["facility_capex_usd"]
        assert sum(i["power_w"] for i in items) == pytest.approx(campus["power_w"], rel=1e-9)
        assert sum(i["cost_usd"] for i in items) + facility == pytest.approx(campus["cost_usd"], rel=1e-6)


def test_quantities_multiply_through_tiers(docs):
    doc = docs["a"]
    assert _tier(doc, 3)["assemblies"][0]["qty_total"] == doc["summary"]["racks"]
    node = next(a for a in _tier(doc, 2)["assemblies"] if a["id"] == "node")
    assert node["qty_total"] == doc["summary"]["racks"] * 18
    sus = [a for a in _tier(doc, 4)["assemblies"] if a["attrs"]["role"] == "su"]
    assert sum(a["qty_total"] * a["attrs"]["racks"] for a in sus) == doc["summary"]["racks"]


def test_tier_abstraction(docs):
    # A tier's BOM names child assemblies, never the silicon inside them.
    for doc in docs.values():
        for level in (3, 4, 5, 6):
            for a in _tier(doc, level)["assemblies"]:
                refs = {ln["ref"] for ln in a["bom"]}
                assert not refs & {"gpu-gb200", "gpu-oam-1000w", "nic-800g", "cpu-grace", "cpu-x86-host"}
        halls = _tier(doc, 5)["assemblies"]
        assert all(ln["ref"] != "rack" for a in halls for ln in a["bom"])


def test_rack_within_budget(docs):
    for doc in docs.values():
        r = _tier(doc, 3)["assemblies"][0]["attrs"]
        assert r["power_kw"] <= r["power_budget_kw"] and r["rack_units_used"] <= r["rack_units"]


def test_halls_respect_power_cap(docs):
    for doc in docs.values():
        cap = doc["spec"]["facility"]["hall_it_mw_max"]
        assert all(a["attrs"]["it_mw"] <= cap for a in _tier(doc, 5)["assemblies"])


def test_media_follows_reach(docs, catalog):
    for doc in docs.values():
        for layer in doc["fabric"]["media_by_layer"].values():
            for media, d in layer.items():
                assert d["max_m"] <= catalog.media[media].max_reach_m


def test_disallowing_lpo_moves_links_to_retimed_optics(catalog):
    spec = spec_from("arch-a-nvl72-300k", scale_out__allowed_media=["dac", "aec", "dr", "fr"])
    doc = compile_design(spec, catalog)
    assert _item(doc, "media:lpo") is None and _item(doc, "media:dr")["qty"] > 0


def test_report_and_presets_compile(catalog):
    from dcdesigner.cli import load_spec

    for p in PRESETS:
        text = markdown(compile_design(load_spec(p), catalog))
        assert "## Tier 6: Campus / DC" in text


def test_web_data_is_current(tmp_path, catalog):
    from dcdesigner.cli import build_web

    build_web(PRESETS, tmp_path, catalog)
    committed = (ROOT / "web" / "designs.js").read_text()
    assert (tmp_path / "designs.js").read_text() == committed, "run `dcd web` and commit web/designs.js"


def test_json_is_plain(docs):
    json.loads(canonical_json(docs["b"]))


@pytest.mark.parametrize("target", [64, 2048, 20_000])
def test_small_clusters_compile(target, catalog):
    spec = spec_from("arch-b-ocp8-300k", gpu_target=target, scale_out__rails=1 if target == 64 else 8)
    doc = compile_design(spec, catalog)
    assert doc["summary"]["gpus"] >= target
    assert _item(doc, "gpu-oam-1000w")["qty"] == doc["summary"]["gpus"]
