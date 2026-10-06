"""Markdown report: one section per tier, each with its own BOM summary."""

from __future__ import annotations


def _money(x: float) -> str:
    if abs(x) >= 1e9:
        return f"${x / 1e9:,.2f}B"
    if abs(x) >= 1e6:
        return f"${x / 1e6:,.2f}M"
    if abs(x) >= 1e3:
        return f"${x / 1e3:,.1f}K"
    return f"${x:,.0f}"


def _power(w: float) -> str:
    if abs(w) >= 1e6:
        return f"{w / 1e6:,.2f} MW"
    if abs(w) >= 1e3:
        return f"{w / 1e3:,.1f} kW"
    return f"{w:,.0f} W"


def _qty(q: float) -> str:
    return f"{q:,.3f}".rstrip("0").rstrip(".") if q != int(q) else f"{int(q):,}"


def markdown(doc: dict) -> str:
    s, c, f = doc["summary"], doc["complexity"], doc["fabric"]
    out = [
        f"# {doc['title']}",
        "",
        doc["description"],
        "",
        f"Design digest `{doc['digest'][:16]}` (same spec and catalog always give the same digest).",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| GPUs built (target) | {s['gpus']:,} ({s['gpu_target']:,}) |",
        f"| Racks / SuperPods / halls | {s['racks']:,} / {s['superpods']} / {s['halls']} |",
        f"| IT power / facility power | {s['it_mw']:,.1f} MW / {s['facility_mw']:,.1f} MW |",
        f"| Capex (planning placeholder) | {_money(s['capex_usd'])} ({_money(s['capex_per_gpu_usd'])} per GPU) |",
        f"| Scale-out fabric | {f['tiers']}-tier, {f['planes']} plane(s) x {f['port_gbps']}G, radix {f['radix']} |",
        f"| Switches (leaf / spine / super-spine / core) | {f['switches']['leaf']:,} / {f['switches']['spine']:,} / "
        f"{f['switches']['super_spine']:,} / {f['switches']['core']:,} |",
        f"| Optical modules (800G eq.) | {c['optical_modules_800g_eq']:,} |",
        f"| Copper / optical links | {c['links_copper']:,} / {c['links_optical']:,} |",
        f"| BGP sessions | {c['bgp_sessions']:,} |",
        f"| Install labor (estimate) | {c['install_labor_hours']:,} technician-hours |",
        "",
        "## Design notes",
        "",
        *[f"- {n}" for n in doc["notes"]],
        "",
    ]
    for tier in doc["tiers"]:
        out += [f"## Tier {tier['level']}: {tier['title']}", "", tier["blurb"] + ".", ""]
        if tier["level"] == 1:
            out += ["| Item | Qty (whole build) | Power | Cost |", "|---|---:|---:|---:|"]
            for i in tier["items"]:
                out.append(f"| {i['name']} | {_qty(i['qty'])} | {_power(i['power_w'])} | {_money(i['cost_usd'])} |")
            out.append("")
            continue
        for a in tier["assemblies"]:
            out += [
                f"### {a['name']} x {a['qty_total']:,}",
                "",
                f"Per unit: {_power(a['power_w'])}, {_money(a['cost_usd'])}. "
                f"All units: {_power(a['power_w_total'])}, {_money(a['cost_usd_total'])}.",
                "",
                "| Item | Qty per unit | Power | Cost | Note |",
                "|---|---:|---:|---:|---|",
            ]
            for ln in a["bom"]:
                out.append(
                    f"| {ln['name']} | {_qty(ln['qty'])} | {_power(ln['power_w'])} | {_money(ln['cost_usd'])} "
                    f"| {ln['note']} |"
                )
            out.append("")
    out += ["## References", ""]
    for rid, r in doc["references"].items():
        out.append(f"- `{rid}`: [{r['title']}]({r['url']}), {r['publisher']}")
    out.append("")
    return "\n".join(out)
