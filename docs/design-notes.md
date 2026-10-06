# Design notes: rules, derivations and corrections

This document explains the rules the compiler applies at each tier and checks
the 300K-GPU sizing table from the original proposal against them. Every
number below is produced by the compiler from `presets/*.yaml` and the
editable catalog in `src/dcdesigner/data/catalog.yaml`; rerun
`dcd report <preset>` to regenerate them after changing an assumption.

## The six tiers and what each one owns

| Tier | Unit | Introduced at this tier | Child shown as an opaque line |
|---|---|---|---|
| 1 Indivisible | GPU, CPU, NIC, switch ASIC, optic, cable | specs, power, cost per part | none |
| 2 Node | compute tray or 8-GPU server, scale-up switch tray | scale-up mesh (NVLink / UALink), PCIe Gen6, memory, storage | parts |
| 3 Rack | NVL72 rack or 48U ORv3 rack | power shelves (N+1), frame, manifold, copper spine, OOB switch, RU and kW budget | nodes, switch trays |
| 4 Pod / SuperPod | Scalable unit (one row) and SuperPod (leaf/spine block) | rail-optimized leaves, spines, GPU-leaf and leaf-spine media | racks, SUs |
| 5 Data hall | SuperPods under one power envelope | MPO patch panels, CDUs, facility build per MW | SuperPods |
| 6 Campus | halls + core | super-spines, cross-hall optics, WAN edge, substations | halls |

Tier 1 is the flattened view: the total of every indivisible part across the
whole build. Every other tier's BOM lists its own items plus child assemblies
by name, so the rack view never mentions spines and the hall view never
mentions GPUs. Partial units (the last SU, SuperPod or hall when the cluster
does not divide evenly) are exact assemblies of their own.

## Scale-out fabric rules

* **Radix at the port speed.** A 51.2 Tb/s ASIC is 64 × 800G or 128 × 400G.
  The radix k that matters is the count of logical ports at the speed each
  GPU plane uses.
* **Non-blocking leaf split.** A 1:1 leaf has k/2 ports down and k/2 up.
* **Capacity.** A non-blocking folded Clos with t tiers reaches
  2 × (k/2)^t endpoints: k²/2 for two tiers, k³/4 for three (Al-Fares et
  al., SIGCOMM 2008).
* **Switch counts for three tiers.** Leaves = N / (k/2), spines = N / (k/2),
  super-spines = N / k, so the total is 5N/k per plane (plus rounding for
  rail alignment and partial units), not 3N/k.
* **Rails.** GPU i of every node in a scalable unit lands on the same leaf
  group, so an SU needs rails × ⌈GPUs per rail / (k/2)⌉ leaves per plane.
* **SuperPod.** A spine has k/2 ports down, so a SuperPod holds at most k/2
  leaves per plane. The presets size the SU and SuperPod to fill that exactly.
* **Super-spine.** Each super-spine reaches every SuperPod, so up to k
  SuperPods fit in three tiers; beyond that the compiler adds a fourth tier.
* **Multi-plane.** Splitting each 800G NIC into 2 × 400G planes (Alibaba HPN,
  ConnectX-8 multi-plane) doubles the radix per plane at the cost of twice as
  many, half-speed links. It is the cheapest way to keep 300K GPUs at three
  tiers on 51.2T silicon.

## Corrections to the original 300K sizing table

| Item | Original table | Compiler result | Why |
|---|---|---|---|
| Can 64 × 800G switches build a non-blocking 3-tier fabric for 300K GPUs? | yes | **no** | k³/4 at k = 64 is 65,536 GPUs. 300K needs a fourth tier, or a higher radix. |
| Leaf switches | 4,688 (N / 64) | A: 9,528, B: 9,376 (2 × 400G planes) | N / 64 assumes all 64 ports face GPUs. A non-blocking leaf uses half its ports as uplinks. |
| Spine / super-spine | 4,688 / 4,688 | A: 9,528 / 4,764, B: 9,376 / 4,688 | Spines carry k/2 down and k/2 up; super-spines use all k ports down, so there are half as many. |
| Total switches | 14,064 (3N/k) | A: 23,820, B: 23,440 on 51.2T with 2 planes | Correct total is 5N/k per plane. |
| Same cluster, 51.2T, one 800G plane | n/a | A: 33,348, B: 32,816 switches in **4 tiers** | Shown in the alternatives table. |
| Same cluster, 102.4T (128 × 800G), one plane | n/a | A: 11,910, B: 11,720 switches in 3 tiers | The cheapest option when 102.4T silicon is available. |
| 800G transceivers | ~1.8M | A: 1.39M, B: 1.43M (800G-equivalent modules) plus 375K-429K AEC cables | 6 × N port ends is right for a single-plane, all-optical 3-tier fabric. GPU links within 7 m use AEC copper, which has no transceivers. |
| Transceiver mix | fixed percentages | derived from cable length | A: GPU-leaf 71% AEC / 29% LPO, leaf-spine 100% LPO, spine-core 100% DR. B adds 2×FR4 for halls more than 500 m from the core. Change `layout` in the preset to see the mix move. |
| Rack power, Arch A | ~125 kW | 117.7 kW bottom-up | 18 trays × 5.83 kW + 9 switch trays × 1.4 kW + OOB. |
| Rack power, Arch B | ~42 kW | 45.7 kW bottom-up | 4 × 11.4 kW 8-GPU servers (8 × 1 kW GPU, 2 CPUs, 8 NICs, DRAM, NVMe, PCIe and UALink switches, fans). |
| Total IT power | A ~520 MW, B ~410 MW | A 542 MW, B 479 MW | Bottom-up, including every switch and optic. B lands above the table because each 8-GPU server carries its own CPUs, DRAM, fans and PCIe switches (11.4 kW for 8 kW of GPUs). |
| SuperPod | A 32 racks / 2,304 GPUs, B 32 racks / 1,024 GPUs | A 56 racks / 4,032 GPUs, B 128 racks / 4,096 GPUs | Sized to fill one spine block (64 leaves per plane at k = 128). B's 1,024-GPU pod is exactly what the compiler picks for a single 800G plane (k = 64). |
| "72-rail" for NVL72 | 72 rails | 4 rails | Rails follow the GPU position in a compute tray. The NVLink domain already gives any-to-any inside the rack, and 72 rails would need 72 leaves per group, more than a spine block holds. |
| Data halls | A ~6, B ~10 | A 6 (100 MW cap), B 9 (60 MW cap) | Halls are packed with whole SuperPods up to the IT cap in the preset. |
| Racks | 4,167 / 9,375 | 4,167 / 9,375 | Matches; A builds 300,024 GPUs because racks are whole. |

## Physical reach model

Cable length comes from a simple floor plan (all values in the preset's
`layout` block): host links run in-row to network racks in the middle of each
SU row; leaf-spine links run from SU rows to a spine row in the middle of the
SuperPod; spine-to-super-spine links run from each hall to a core room in the
middle of the campus. Each link takes the cheapest allowed medium whose reach
covers it: DAC ≤ 2.5 m, AEC ≤ 7 m, LPO ≤ 100 m (planning value), DR ≤ 500 m,
2×FR4 ≤ 2 km. Remove `lpo` from `scale_out.allowed_media` to model a
retimed-only design.

## RoCE and routing

* PFC headroom per lossless port = 2 × MTU + rate × (2 × length × 5 ns/m +
  1.5 µs). The compiler reports headroom against the ASIC buffer per role.
* ECN starts from the DCQCN paper's 40G thresholds scaled to port speed
  (Kmin 50 KB, Kmax 2 MB, Pmax 1% at 400G). Tune with real traffic.
* eBGP on every link (RFC 7938) with private 4-byte ASNs (RFC 6996): one per
  leaf, one per SuperPod spine group, one per plane for super-spines.
  /31s on every link, GPU host links routed per plane.

## Cost model and limits

Prices are round planning placeholders; vendors do not publish list prices
for most of these parts. Facility capex is a per-MW-of-IT figure in the range
of public development-cost guides. Replace both with quotes before budgeting.
Not modeled yet: front-end and storage networks, OOB beyond a per-rack switch,
generators and UPS as separate line items, optical circuit switching.
