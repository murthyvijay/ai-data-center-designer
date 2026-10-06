# Architecture A: High-density NVL72 style, 300K GPUs

18 compute trays (2 Grace + 4 Blackwell) and 9 NVLink switch trays per rack, all scale-up traffic on the passive copper spine. Each GPU has one 800G NIC split into 2 x 400G planes so 51.2T switches reach 300K GPUs in three tiers.

Design digest `de7b475289e5ddbf` (same spec and catalog always give the same digest).

## Summary

| Metric | Value |
|---|---|
| GPUs built (target) | 300,024 (300,000) |
| Racks / SuperPods / halls | 4,167 / 75 / 6 |
| IT power / facility power | 542.1 MW / 623.5 MW |
| Capex (planning placeholder) | $26.44B ($88.1K per GPU) |
| Scale-out fabric | 3-tier, 2 plane(s) x 400G, radix 128 |
| Switches (leaf / spine / super-spine / core) | 9,528 / 9,528 / 4,764 / 0 |
| Optical modules (800G eq.) | 1,390,656 |
| Copper / optical links | 428,976 / 1,390,656 |
| BGP sessions | 1,219,584 |
| Install labor (estimate) | 389,825 technician-hours |

## Design notes

- A 51.2T Ethernet switch has radix 128 at 400G. A non-blocking leaf splits it 64 down / 64 up, so leaves = GPUs / 64 per plane, not GPUs / 128.
- Max endpoints for a non-blocking 3-tier Clos at radix k is k^3/4: 524,288 at k=128, but only 65,536 at k=64 (800G ports on the same ASIC).
- Each 800G NIC is split into 2 x 400G planes (multi-plane, as in Alibaba HPN and ConnectX-8 multi-plane), which raises the radix and keeps 300,024 GPUs in 3 tiers.
- Alternative: 102.4T Ethernet switch with 1 plane(s) needs 3 tiers and 11,910 switches.
- Alternative: 102.4T Ethernet switch with 2 plane(s) needs 3 tiers and 11,920 switches.
- Alternative: 51.2T Ethernet switch with 1 plane(s) needs 4 tiers and 33,348 switches.
- Port ends: 3 link layers x 2 ends x 300,024 GPUs x 2 plane(s) = 3,600,288 logical ports; modules are counted as 800G equivalents and copper links (DAC/AEC) carry no transceivers.

## Tier 1: Indivisible units

Compute silicon, NICs, switch ASICs, memory, storage and link media.

| Item | Qty (whole build) | Power | Cost |
|---|---:|---:|---:|
| Blackwell GPU (GB200 superchip half) | 300,024 | 360.03 MW | $11.25B |
| Grace CPU (72-core Arm, incl. LPDDR5X) | 150,012 | 45.00 MW | $900.07M |
| NVMe SSD 7.68 TB (local scratch) | 300,024 | 7.50 MW | $360.03M |
| 800G SuperNIC / HCA (ConnectX-8 class, PCIe Gen6 x16) | 300,024 | 13.50 MW | $1.05B |
| NVLink 5 switch ASIC (72 ports x 100 GB/s) | 75,006 | 48.75 MW | $1.13B |
| 51.2T Ethernet switch (64 x 800G OSFP, TH5 / G200 class), 2RU | 23,820 | 33.35 MW | $1.07B |
| 800G 2xDR4 / DR8 retimed optics (500 m SMF) | 609,792 | 9.15 MW | $518.32M |
| 800G LPO 2xDR4 (linear pluggable optics, no DSP) | 780,864 | 6.64 MW | $507.56M |
| Active electrical cable AEC (800G, retimed copper) | 214,488 | 2.57 MW | $128.69M |
| MPO-16 SMF trunk | 1,390,656 | 0 W | $267.49M |
| NVLink copper spine cartridge (passive backplane cable set) | 16,668 | 0 W | $300.02M |
| GB200 compute tray chassis, cold plates, board, BMC | 75,006 | 11.25 MW | $1.88B |
| NVLink switch tray chassis | 37,503 | 3.75 MW | $450.04M |
| 48U ORv3 rack, rear-door / manifold (hybrid cooling) | 1,344 | 0 W | $33.60M |
| NVL72 rack frame, liquid manifold, busbar | 4,167 | 0 W | $250.02M |
| Power shelf, 33 kW (6 x 5.5 kW PSU) | 20,835 | 0 W | $187.51M |
| Out-of-band management switch (1G/10G, 48 port) | 4,167 | 625.0 kW | $16.67M |
| 1U MPO/MTP patch panel (48 MPO ports) | 38,112 | 0 W | $57.17M |
| Coolant distribution unit, 1.5 MW liquid-to-liquid | 304 | 0 W | $121.60M |
| Campus WAN edge / DCI router (400G ZR capable) | 4 | 12.0 kW | $1.00M |
| Utility substation bay, 250 MVA (cost carried in facility capex) | 3 | 0 W | $0 |

## Tier 2: Node

Host or compute tray with its scale-up mesh.

### GB200 compute tray x 75,006

Per unit: 5.8 kW, $205.8K. All units: 437.28 MW, $15.44B.

| Item | Qty per unit | Power | Cost | Note |
|---|---:|---:|---:|---|
| Blackwell GPU (GB200 superchip half) | 4 | 4.8 kW | $150.0K |  |
| 800G SuperNIC / HCA (ConnectX-8 class, PCIe Gen6 x16) | 4 | 180 W | $14.0K |  |
| Grace CPU (72-core Arm, incl. LPDDR5X) | 2 | 600 W | $12.0K |  |
| NVMe SSD 7.68 TB (local scratch) | 4 | 100 W | $4.8K |  |
| GB200 compute tray chassis, cold plates, board, BMC | 1 | 150 W | $25.0K |  |

### NVLink switch tray x 37,503

Per unit: 1.4 kW, $42.0K. All units: 52.50 MW, $1.58B.

| Item | Qty per unit | Power | Cost | Note |
|---|---:|---:|---:|---|
| NVLink 5 switch ASIC (72 ports x 100 GB/s) | 2 | 1.3 kW | $30.0K |  |
| NVLink switch tray chassis | 1 | 100 W | $12.0K |  |

## Tier 3: Rack

Mechanical, thermal and electrical boundary.

### NVL72 liquid-cooled rack x 4,167

Per unit: 117.7 kW, $4.26M. All units: 490.41 MW, $17.77B.

| Item | Qty per unit | Power | Cost | Note |
|---|---:|---:|---:|---|
| GB200 compute tray | 18 | 104.9 kW | $3.70M |  |
| NVLink switch tray | 9 | 12.6 kW | $378.0K |  |
| NVL72 rack frame, liquid manifold, busbar | 1 | 0 W | $60.0K |  |
| NVLink copper spine cartridge (passive backplane cable set) | 4 | 0 W | $72.0K |  |
| Out-of-band management switch (1G/10G, 48 port) | 1 | 150 W | $4.0K |  |
| Power shelf, 33 kW (6 x 5.5 kW PSU) | 5 | 0 W | $45.0K | N+1 |

## Tier 4: Pod / SuperPod

Rail-optimized leaves (SU) and the non-blocking leaf/spine block (SuperPod).

### Scalable unit (14 racks, 1,008 GPUs) x 297

Per unit: 1.71 MW, $62.01M. All units: 506.68 MW, $18.42B.

| Item | Qty per unit | Power | Cost | Note |
|---|---:|---:|---:|---|
| NVL72 liquid-cooled rack | 14 | 1.65 MW | $59.69M |  |
| 51.2T Ethernet switch (64 x 800G OSFP, TH5 / G200 class), 2RU | 32 | 44.8 kW | $1.44M | leaf: 16 per plane x 2 planes |
| 48U ORv3 rack, rear-door / manifold (hybrid cooling) | 2 | 0 W | $50.0K | network racks, middle of row |
| Active electrical cable AEC (800G, retimed copper) | 720 | 8.6 kW | $432.0K | GPU to leaf: 1,440 x 400G links, 800G-equivalent cables, avg 5.8 m |
| 800G LPO 2xDR4 (linear pluggable optics, no DSP) | 576 | 4.9 kW | $374.4K | GPU to leaf: 576 x 400G links, both ends, 800G-equivalent modules |
| MPO-16 SMF trunk | 576 | 0 W | $28.5K | GPU to leaf: avg 7.9 m, max 8.2 m |

### SuperPod (56 racks, 4,032 GPUs) x 74

Per unit: 7.07 MW, $259.79M. All units: 523.39 MW, $19.22B.

| Item | Qty per unit | Power | Cost | Note |
|---|---:|---:|---:|---|
| Scalable unit (14 racks, 1,008 GPUs) | 4 | 6.82 MW | $248.05M |  |
| 51.2T Ethernet switch (64 x 800G OSFP, TH5 / G200 class), 2RU | 128 | 179.2 kW | $5.76M | spine: 64 per plane x 2 planes |
| 48U ORv3 rack, rear-door / manifold (hybrid cooling) | 7 | 0 W | $175.0K | spine racks |
| 800G LPO 2xDR4 (linear pluggable optics, no DSP) | 8,192 | 69.6 kW | $5.32M | leaf to spine: 8,192 x 400G links, both ends, 800G-equivalent modules |
| MPO-16 SMF trunk | 8,192 | 0 W | $481.0K | leaf to spine: avg 15.6 m, max 17.4 m |

### Scalable unit (9 racks, 648 GPUs) x 1

Per unit: 1.10 MW, $39.89M. All units: 1.10 MW, $39.89M.

| Item | Qty per unit | Power | Cost | Note |
|---|---:|---:|---:|---|
| NVL72 liquid-cooled rack | 9 | 1.06 MW | $38.37M |  |
| 51.2T Ethernet switch (64 x 800G OSFP, TH5 / G200 class), 2RU | 24 | 33.6 kW | $1.08M | leaf: 12 per plane x 2 planes |
| 48U ORv3 rack, rear-door / manifold (hybrid cooling) | 2 | 0 W | $50.0K | network racks, middle of row |
| Active electrical cable AEC (800G, retimed copper) | 648 | 7.8 kW | $388.8K | GPU to leaf: 1,296 x 400G links, 800G-equivalent cables, avg 5.7 m |

### SuperPod (23 racks, 1,656 GPUs) x 1

Per unit: 2.92 MW, $107.03M. All units: 2.92 MW, $107.03M.

| Item | Qty per unit | Power | Cost | Note |
|---|---:|---:|---:|---|
| Scalable unit (14 racks, 1,008 GPUs) | 1 | 1.71 MW | $62.01M |  |
| Scalable unit (9 racks, 648 GPUs) | 1 | 1.10 MW | $39.89M |  |
| 51.2T Ethernet switch (64 x 800G OSFP, TH5 / G200 class), 2RU | 56 | 78.4 kW | $2.52M | spine: 28 per plane x 2 planes |
| 48U ORv3 rack, rear-door / manifold (hybrid cooling) | 3 | 0 W | $75.0K | spine racks |
| 800G LPO 2xDR4 (linear pluggable optics, no DSP) | 3,584 | 30.5 kW | $2.33M | leaf to spine: 3,584 x 400G links, both ends, 800G-equivalent modules |
| MPO-16 SMF trunk | 3,584 | 0 W | $200.0K | leaf to spine: avg 13.2 m, max 13.8 m |

## Tier 5: Data hall

SuperPods, structured cabling and the facility envelope.

### Data hall (14 SuperPods, 56,448 GPUs) x 5

Per unit: 99.02 MW, $4.76B. All units: 495.10 MW, $23.80B.

| Item | Qty per unit | Power | Cost | Note |
|---|---:|---:|---:|---|
| SuperPod (56 racks, 4,032 GPUs) | 14 | 99.02 MW | $3.64B |  |
| 1U MPO/MTP patch panel (48 MPO ports) | 7,168 | 0 W | $10.75M | zone panels at both ends of leaf-spine trunks + hall MDA uplinks |
| Coolant distribution unit, 1.5 MW liquid-to-liquid | 57 | 0 W | $22.80M | N+1 |
| Facility build: powered shell, electrical, mechanical (per MW IT) | 99.019 | 0 W | $1.09B |  |

### Data hall (5 SuperPods, 17,784 GPUs) x 1

Per unit: 31.21 MW, $1.50B. All units: 31.21 MW, $1.50B.

| Item | Qty per unit | Power | Cost | Note |
|---|---:|---:|---:|---|
| SuperPod (23 racks, 1,656 GPUs) | 1 | 2.92 MW | $107.03M |  |
| SuperPod (56 racks, 4,032 GPUs) | 4 | 28.29 MW | $1.04B |  |
| 1U MPO/MTP patch panel (48 MPO ports) | 2,272 | 0 W | $3.41M | zone panels at both ends of leaf-spine trunks + hall MDA uplinks |
| Coolant distribution unit, 1.5 MW liquid-to-liquid | 19 | 0 W | $7.60M | N+1 |
| Facility build: powered shell, electrical, mechanical (per MW IT) | 31.207 | 0 W | $343.28M |  |

## Tier 6: Campus / DC

Halls joined by the super-spine core, WAN edge and utility power.

### Campus x 1

Per unit: 542.13 MW, $26.44B. All units: 542.13 MW, $26.44B.

| Item | Qty per unit | Power | Cost | Note |
|---|---:|---:|---:|---|
| Data hall (14 SuperPods, 56,448 GPUs) | 5 | 495.10 MW | $23.80B |  |
| Data hall (5 SuperPods, 17,784 GPUs) | 1 | 31.21 MW | $1.50B |  |
| 51.2T Ethernet switch (64 x 800G OSFP, TH5 / G200 class), 2RU | 4,764 | 6.67 MW | $214.38M | super-spine: 2382 per plane |
| 800G 2xDR4 / DR8 retimed optics (500 m SMF) | 609,792 | 9.15 MW | $518.32M | spine to super-spine (cross-hall): 609,792 x 400G links, both ends, 800G-equivalent modules |
| MPO-16 SMF trunk | 609,792 | 0 W | $223.23M | spine to super-spine (cross-hall): avg 271.7 m, max 441.0 m |
| 48U ORv3 rack, rear-door / manifold (hybrid cooling) | 227 | 0 W | $5.67M | core network racks |
| Campus WAN edge / DCI router (400G ZR capable) | 4 | 12.0 kW | $1.00M | campus WAN / DCI edge |
| Facility build for core network and WAN rooms (per MW IT) | 15.828 | 0 W | $174.11M |  |
| Utility substation bay, 250 MVA (cost carried in facility capex) | 3 | 0 W | $0 | 623 MW facility load at PUE 1.15 |

## References

- `al-fares-2008`: [A Scalable, Commodity Data Center Network Architecture (k-ary fat-tree, k^3/4 hosts)](https://dl.acm.org/doi/10.1145/1402958.1402967), ACM SIGCOMM 2008
- `alibaba-hpn-2024`: [Alibaba HPN: A Data Center Network for Large Language Model Training (dual-plane, rail-optimized)](https://dl.acm.org/doi/10.1145/3651890.3672265), ACM SIGCOMM 2024
- `arista-ai`: [Arista AI Networking (Etherlink, rail-optimized leaf/spine designs)](https://www.arista.com/en/solutions/ai-networking), Arista Networks
- `aws-ultracluster`: [Amazon EC2 UltraClusters (non-blocking petabit-scale networks for accelerators)](https://aws.amazon.com/ec2/ultraclusters/), Amazon Web Services
- `broadcom-th5`: [Broadcom Tomahawk 5 BCM78900 (51.2 Tb/s, 64x800G / 128x400G)](https://www.broadcom.com/products/ethernet-connectivity/switching/strataxgs/bcm78900-series), Broadcom
- `broadcom-th6`: [Broadcom Tomahawk 6 BCM78910 (102.4 Tb/s, 64x1.6T / 128x800G)](https://www.broadcom.com/products/ethernet-connectivity/switching/strataxgs/bcm78910-series), Broadcom
- `cisco-silicon-one`: [Cisco Silicon One G200 (51.2 Tb/s) and AI networking](https://www.cisco.com/c/en/us/solutions/silicon-one.html), Cisco
- `cushman-cost-guide`: [Data Center Development Cost Guide (USD per MW of IT load, by market)](https://www.cushmanwakefield.com/en/united-states/insights/data-center-development-cost-guide), Cushman & Wakefield
- `dcqcn-2015`: [Congestion Control for Large-Scale RDMA Deployments (DCQCN)](https://dl.acm.org/doi/10.1145/2785956.2787484), ACM SIGCOMM 2015
- `frr`: [FRRouting documentation (BGP unnumbered, route-maps)](https://docs.frrouting.org/), FRRouting
- `google-jupiter-2022`: [Jupiter Evolving: Transforming Google's Datacenter Network via Optical Circuit Switches and SDN](https://dl.acm.org/doi/10.1145/3544216.3544265), ACM SIGCOMM 2022
- `ieee-8021qbb`: [IEEE 802.1Qbb Priority-based Flow Control (now part of IEEE 802.1Q)](https://1.ieee802.org/dcb/802-1qbb/), IEEE
- `ieee-8023df`: [IEEE 802.3df 800 Gb/s Ethernet (200G/lane PMDs: DR, FR, copper)](https://www.ieee802.org/3/df/), IEEE
- `juniper-ai-dc`: [Juniper AI Data Center networking (rail-optimized Ethernet fabrics for AI clusters)](https://www.juniper.net/us/en/solutions/data-center/ai-infrastructure.html), Juniper Networks
- `lpo-msa`: [Linear Pluggable Optics (LPO) Multi-Source Agreement](https://www.lpo-msa.org/), LPO MSA
- `meta-roce-2024`: [RDMA over Ethernet for Distributed AI Training at Meta Scale](https://dl.acm.org/doi/10.1145/3651890.3672233), ACM SIGCOMM 2024
- `nvidia-dgx-b200`: [NVIDIA DGX B200 (8-GPU HGX system, ~14.3 kW max)](https://www.nvidia.com/en-us/data-center/dgx-b200/), NVIDIA
- `nvidia-dgx-superpod-gb200`: [NVIDIA DGX SuperPOD Reference Architecture with DGX GB200 systems](https://docs.nvidia.com/dgx-superpod/reference-architecture-scalable-infrastructure-gb200/latest/), NVIDIA
- `nvidia-gb200-nvl72`: [NVIDIA GB200 NVL72 (72 GPUs, 36 Grace CPUs, 130 TB/s NVLink domain, liquid cooled)](https://www.nvidia.com/en-us/data-center/gb200-nvl72/), NVIDIA
- `ocp-cooling`: [OCP Cooling Environments (cold plate, CDU and facility liquid loop guidance)](https://www.opencompute.org/projects/cooling-environments), Open Compute Project
- `ocp-oai`: [OCP Open Accelerator Infrastructure (OAM module, UBB baseboard)](https://www.opencompute.org/projects/open-accelerator-infrastructure), Open Compute Project
- `ocp-rack-power`: [OCP Rack & Power (ORv3, high-power racks, Mt Diablo disaggregated power)](https://www.opencompute.org/projects/rack-and-power), Open Compute Project
- `osfp-msa`: [OSFP Multi-Source Agreement (800G / 1.6T pluggable form factor)](https://osfpmsa.org/), OSFP MSA
- `rfc3168`: [RFC 3168: The Addition of Explicit Congestion Notification (ECN) to IP](https://www.rfc-editor.org/rfc/rfc3168), IETF
- `rfc6996`: [RFC 6996: Autonomous System (AS) Reservation for Private Use (4-byte private ASNs)](https://www.rfc-editor.org/rfc/rfc6996), IETF
- `rfc7938`: [RFC 7938: Use of BGP for Routing in Large-Scale Data Centers](https://www.rfc-editor.org/rfc/rfc7938), IETF
- `sonic`: [SONiC open-source network OS (config_db, FRR-based BGP)](https://github.com/sonic-net/SONiC), SONiC Foundation / Linux Foundation
- `ualink-1-0`: [UALink 200G 1.0 Specification (accelerator scale-up interconnect)](https://ualinkconsortium.org/), UALink Consortium
- `uptime-pue`: [Uptime Institute Global Data Center Survey (industry PUE trends)](https://uptimeinstitute.com/resources/research-and-reports), Uptime Institute
