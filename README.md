# ai-data-center-designer

A deterministic **Silicon-to-Data-Hall compiler** for AI clusters. Give it a
short design spec (accelerator, node, rack, scale-out switch, floor geometry,
facility limits) and it produces a full design, one tier at a time:

| Tier | What you see |
|---|---|
| 1 Indivisible units | Every GPU, CPU, NIC, switch, optic and cable in the build, with power and cost |
| 2 Node | Compute tray or 8-GPU server and its scale-up mesh (NVLink / UALink) |
| 3 Rack | Elevation, kW against budget, liquid vs air heat, power shelves |
| 4 Pod / SuperPod | Rail-optimized leaves per scalable unit, leaf/spine block, link media |
| 5 Data hall | SuperPods packed under the hall's MW cap, patch panels, CDUs |
| 6 Campus | Halls, super-spine core, cross-hall optics, WAN edge, substations |

Each tier's bill of materials lists its own items plus child assemblies as
opaque lines, so the rack view does not mention spines and the hall view does
not mention GPUs. The same spec and catalog always produce byte-identical
output (a SHA-256 digest is included).

It also emits the scale-out fabric plan (tiers, switch counts, alternatives),
PFC headroom and ECN settings for lossless RoCE, an eBGP/ASN/IP plan, and
reference switch configs for **SONiC, Arista EOS and Cisco NX-OS**.

Design rules, derivations and the corrections to the original 300K sizing
table are in [docs/design-notes.md](docs/design-notes.md).

## Quick start

```sh
pip install -e .[dev]
dcd report presets/arch-a-nvl72-300k.yaml          # markdown, one BOM table per tier
dcd compile presets/arch-b-ocp8-300k.yaml -o b.json # full design document
dcd config presets/arch-b-ocp8-300k.yaml --nos eos --role spine --plane 1 --index 42
dcd web                                             # rebuild web/designs.js from presets/
open web/index.html                                 # the tier-by-tier viewer, no server needed
```

## Presets: 300K GPUs two ways

| | A: NVL72 style | B: OCP 8-GPU style |
|---|---|---|
| GPUs per rack | 72 (18 trays, 117.7 kW, liquid) | 32 (4 servers, 45.7 kW, hybrid) |
| Racks | 4,167 | 9,375 |
| SuperPod | 56 racks, 4,032 GPUs | 128 racks, 4,096 GPUs |
| Fabric | 3-tier, 2 × 400G planes on 51.2T | same |
| Switches | 23,820 | 23,440 |
| Optical modules (800G eq.) | 1.39M | 1.43M |
| IT / facility power | 542 / 623 MW | 479 / 599 MW |
| Data halls | 6 | 9 |

Full reports: [examples/](examples/).

## Editing assumptions

* `src/dcdesigner/data/catalog.yaml`: parts, power, planning prices, media
  reach, facility $/MW, labor rates. Prices are placeholders, not quotes.
* `src/dcdesigner/data/references.yaml`: the public standards, MSAs, papers
  and datasheets every rule cites (IEEE, IETF, OCP, UALink, NVIDIA, Broadcom,
  Cisco, Arista, Juniper, Google, Meta, AWS).
* `presets/*.yaml`: the design spec (see `src/dcdesigner/schema.py`).

## Layout

```
src/dcdesigner/
  schema.py    input spec (pydantic)
  fabric.py    rail-optimized Clos synthesizer
  physical.py  floor-plan reach model and link-media classifier
  compiler.py  six-tier assemblies, BOM roll-ups, complexity
  roce.py      PFC headroom and ECN thresholds
  wiring.py    device naming, port map, ASN and IP plan
  nos.py       SONiC / EOS / NX-OS config rendering
web/           static viewer (index.html + generated designs.js)
```
