# Architecture B: Universal OCP 8-GPU style, 300K GPUs

Four 8-GPU servers per 48U hybrid-cooled rack (cold plates on GPU/CPU, air for the rest). Each GPU has one 800G NIC split into 2 x 400G planes on an 8-rail optimized, non-blocking 3-tier Clos of 51.2T switches.

Design digest `dfba3431879fb6b0` (same spec and catalog always give the same digest).

## Summary

| Metric | Value |
|---|---|
| GPUs built (target) | 300,000 (300,000) |
| Racks / SuperPods / halls | 9,375 / 74 / 9 |
| IT power / facility power | 479.1 MW / 598.9 MW |
| Capex (planning placeholder) | $22.66B ($75.5K per GPU) |
| Scale-out fabric | 3-tier, 2 plane(s) x 400G, radix 128 |
| Switches (leaf / spine / super-spine / core) | 9,376 / 9,376 / 4,688 / 0 |
| Optical modules (800G eq.) | 1,425,088 |
| Copper / optical links | 375,040 / 1,425,088 |
| BGP sessions | 1,200,128 |
| Install labor (estimate) | 421,870 technician-hours |

## Design notes

- A 51.2T Ethernet switch has radix 128 at 400G. A non-blocking leaf splits it 64 down / 64 up, so leaves = GPUs / 64 per plane, not GPUs / 128.
- Max endpoints for a non-blocking 3-tier Clos at radix k is k^3/4: 524,288 at k=128, but only 65,536 at k=64 (800G ports on the same ASIC).
- Each 800G NIC is split into 2 x 400G planes (multi-plane, as in Alibaba HPN and ConnectX-8 multi-plane), which raises the radix and keeps 300,000 GPUs in 3 tiers.
- Alternative: 102.4T Ethernet switch with 1 plane(s) needs 3 tiers and 11,720 switches.
- Alternative: 102.4T Ethernet switch with 2 plane(s) needs 3 tiers and 23,440 switches.
- Alternative: 51.2T Ethernet switch with 1 plane(s) needs 4 tiers and 32,816 switches.
- Port ends: 3 link layers x 2 ends x 300,000 GPUs x 2 plane(s) = 3,600,000 logical ports; modules are counted as 800G equivalents and copper links (DAC/AEC) carry no transceivers.

## Tier 1: Indivisible units

Compute silicon, NICs, switch ASICs, memory, storage and link media.

| Item | Qty (whole build) | Power | Cost |
|---|---:|---:|---:|
| OAM accelerator, 1000 W class (B200 / MI3xx class) | 300,000 | 300.00 MW | $9.00B |
| Host CPU (x86 / Arm server class) | 75,000 | 26.25 MW | $675.00M |
| Host DDR5 memory, 2 TB per node | 37,500 | 12.00 MW | $600.00M |
| NVMe SSD 7.68 TB (local scratch) | 300,000 | 7.50 MW | $360.00M |
| 800G SuperNIC / HCA (ConnectX-8 class, PCIe Gen6 x16) | 300,000 | 13.50 MW | $1.05B |
| PCIe Gen6 switch (144-lane class) | 150,000 | 11.25 MW | $225.00M |
| UALink 1.0 scale-up switch ASIC | 75,000 | 22.50 MW | $600.00M |
| 51.2T Ethernet switch (64 x 800G OSFP, TH5 / G200 class), 2RU | 23,440 | 32.82 MW | $1.05B |
| 800G 2xDR4 / DR8 retimed optics (500 m SMF) | 294,912 | 4.42 MW | $250.68M |
| 800G 2xFR4 retimed optics (2 km SMF) | 231,424 | 3.82 MW | $254.57M |
| 800G LPO 2xDR4 (linear pluggable optics, no DSP) | 898,752 | 7.64 MW | $584.19M |
| Active electrical cable AEC (800G, retimed copper) | 187,520 | 2.25 MW | $112.51M |
| Duplex LC SMF jumper/trunk | 231,424 | 0 W | $58.59M |
| MPO-16 SMF trunk | 1,193,664 | 0 W | $171.95M |
| 8-GPU server chassis (OAI UBB baseboard, fans, PSUs, BMC) | 37,500 | 33.75 MW | $1.69B |
| 48U ORv3 rack, rear-door / manifold (hybrid cooling) | 10,698 | 0 W | $267.45M |
| Power shelf, 33 kW (6 x 5.5 kW PSU) | 28,125 | 0 W | $253.12M |
| Out-of-band management switch (1G/10G, 48 port) | 9,375 | 1.41 MW | $37.50M |
| 1U MPO/MTP patch panel (48 MPO ports) | 37,504 | 0 W | $56.26M |
| Coolant distribution unit, 1.5 MW liquid-to-liquid | 229 | 0 W | $91.60M |
| Campus WAN edge / DCI router (400G ZR capable) | 4 | 12.0 kW | $1.00M |
| Utility substation bay, 250 MVA (cost carried in facility capex) | 3 | 0 W | $0 |

## Tier 2: Node

Host or compute tray with its scale-up mesh.

### 8-GPU OAI server x 37,500

Per unit: 11.4 kW, $378.6K. All units: 426.75 MW, $14.20B.

| Item | Qty per unit | Power | Cost | Note |
|---|---:|---:|---:|---|
| OAM accelerator, 1000 W class (B200 / MI3xx class) | 8 | 8.0 kW | $240.0K |  |
| 800G SuperNIC / HCA (ConnectX-8 class, PCIe Gen6 x16) | 8 | 360 W | $28.0K |  |
| Host CPU (x86 / Arm server class) | 2 | 700 W | $18.0K |  |
| Host DDR5 memory, 2 TB per node | 1 | 320 W | $16.0K |  |
| NVMe SSD 7.68 TB (local scratch) | 8 | 200 W | $9.6K |  |
| PCIe Gen6 switch (144-lane class) | 4 | 300 W | $6.0K |  |
| UALink 1.0 scale-up switch ASIC | 2 | 600 W | $16.0K |  |
| 8-GPU server chassis (OAI UBB baseboard, fans, PSUs, BMC) | 1 | 900 W | $45.0K |  |

## Tier 3: Rack

Mechanical, thermal and electrical boundary.

### 48U ORv3 hybrid-cooled rack x 9,375

Per unit: 45.7 kW, $1.57M. All units: 428.16 MW, $14.72B.

| Item | Qty per unit | Power | Cost | Note |
|---|---:|---:|---:|---|
| 8-GPU OAI server | 4 | 45.5 kW | $1.51M |  |
| 48U ORv3 rack, rear-door / manifold (hybrid cooling) | 1 | 0 W | $25.0K |  |
| Out-of-band management switch (1G/10G, 48 port) | 1 | 150 W | $4.0K |  |
| Power shelf, 33 kW (6 x 5.5 kW PSU) | 3 | 0 W | $27.0K | N+1 |

## Tier 4: Pod / SuperPod

Rail-optimized leaves (SU) and the non-blocking leaf/spine block (SuperPod).

### Scalable unit (16 racks, 512 GPUs) x 585

Per unit: 760.2 kW, $26.33M. All units: 444.73 MW, $15.40B.

| Item | Qty per unit | Power | Cost | Note |
|---|---:|---:|---:|---|
| 48U ORv3 hybrid-cooled rack | 16 | 730.7 kW | $25.13M |  |
| 51.2T Ethernet switch (64 x 800G OSFP, TH5 / G200 class), 2RU | 16 | 22.4 kW | $720.0K | leaf: 8 per plane x 2 planes |
| 48U ORv3 rack, rear-door / manifold (hybrid cooling) | 1 | 0 W | $25.0K | network racks, middle of row |
| Active electrical cable AEC (800G, retimed copper) | 320 | 3.8 kW | $192.0K | GPU to leaf: 640 x 400G links, 800G-equivalent cables, avg 5.8 m |
| 800G LPO 2xDR4 (linear pluggable optics, no DSP) | 384 | 3.3 kW | $249.6K | GPU to leaf: 384 x 400G links, both ends, 800G-equivalent modules |
| MPO-16 SMF trunk | 384 | 0 W | $19.1K | GPU to leaf: avg 8.2 m, max 8.8 m |

### SuperPod (128 racks, 4,096 GPUs) x 73

Per unit: 6.33 MW, $222.42M. All units: 462.14 MW, $16.24B.

| Item | Qty per unit | Power | Cost | Note |
|---|---:|---:|---:|---|
| Scalable unit (16 racks, 512 GPUs) | 8 | 6.08 MW | $210.66M |  |
| 51.2T Ethernet switch (64 x 800G OSFP, TH5 / G200 class), 2RU | 128 | 179.2 kW | $5.76M | spine: 64 per plane x 2 planes |
| 48U ORv3 rack, rear-door / manifold (hybrid cooling) | 7 | 0 W | $175.0K | spine racks |
| 800G LPO 2xDR4 (linear pluggable optics, no DSP) | 8,192 | 69.6 kW | $5.32M | leaf to spine: 8,192 x 400G links, both ends, 800G-equivalent modules |
| MPO-16 SMF trunk | 8,192 | 0 W | $507.6K | leaf to spine: avg 18.3 m, max 22.8 m |

### Scalable unit (15 racks, 480 GPUs) x 1

Per unit: 714.0 kW, $24.72M. All units: 714.0 kW, $24.72M.

| Item | Qty per unit | Power | Cost | Note |
|---|---:|---:|---:|---|
| 48U ORv3 hybrid-cooled rack | 15 | 685.0 kW | $23.56M |  |
| 51.2T Ethernet switch (64 x 800G OSFP, TH5 / G200 class), 2RU | 16 | 22.4 kW | $720.0K | leaf: 8 per plane x 2 planes |
| 48U ORv3 rack, rear-door / manifold (hybrid cooling) | 1 | 0 W | $25.0K | network racks, middle of row |
| Active electrical cable AEC (800G, retimed copper) | 320 | 3.8 kW | $192.0K | GPU to leaf: 640 x 400G links, 800G-equivalent cables, avg 5.8 m |
| 800G LPO 2xDR4 (linear pluggable optics, no DSP) | 320 | 2.7 kW | $208.0K | GPU to leaf: 320 x 400G links, both ends, 800G-equivalent modules |
| MPO-16 SMF trunk | 320 | 0 W | $15.9K | GPU to leaf: avg 8.1 m, max 8.8 m |

### SuperPod (31 racks, 992 GPUs) x 1

Per unit: 1.54 MW, $53.99M. All units: 1.54 MW, $53.99M.

| Item | Qty per unit | Power | Cost | Note |
|---|---:|---:|---:|---|
| Scalable unit (16 racks, 512 GPUs) | 1 | 760.2 kW | $26.33M |  |
| Scalable unit (15 racks, 480 GPUs) | 1 | 714.0 kW | $24.72M |  |
| 51.2T Ethernet switch (64 x 800G OSFP, TH5 / G200 class), 2RU | 32 | 44.8 kW | $1.44M | spine: 16 per plane x 2 planes |
| 48U ORv3 rack, rear-door / manifold (hybrid cooling) | 2 | 0 W | $50.0K | spine racks |
| 800G LPO 2xDR4 (linear pluggable optics, no DSP) | 2,048 | 17.4 kW | $1.33M | leaf to spine: 2,048 x 400G links, both ends, 800G-equivalent modules |
| MPO-16 SMF trunk | 2,048 | 0 W | $115.5K | leaf to spine: avg 13.7 m, max 13.8 m |

## Tier 5: Data hall

SuperPods, structured cabling and the facility envelope.

### Data hall (9 SuperPods, 36,864 GPUs) x 8

Per unit: 56.98 MW, $2.65B. All units: 455.80 MW, $21.17B.

| Item | Qty per unit | Power | Cost | Note |
|---|---:|---:|---:|---|
| SuperPod (128 racks, 4,096 GPUs) | 9 | 56.98 MW | $2.00B |  |
| 1U MPO/MTP patch panel (48 MPO ports) | 4,608 | 0 W | $6.91M | zone panels at both ends of leaf-spine trunks + hall MDA uplinks |
| Coolant distribution unit, 1.5 MW liquid-to-liquid | 28 | 0 W | $11.20M | N+1 |
| Facility build: powered shell, electrical, mechanical (per MW IT) | 56.976 | 0 W | $626.74M |  |

### Data hall (2 SuperPods, 5,088 GPUs) x 1

Per unit: 7.87 MW, $365.91M. All units: 7.87 MW, $365.91M.

| Item | Qty per unit | Power | Cost | Note |
|---|---:|---:|---:|---|
| SuperPod (128 racks, 4,096 GPUs) | 1 | 6.33 MW | $222.42M |  |
| SuperPod (31 racks, 992 GPUs) | 1 | 1.54 MW | $53.99M |  |
| 1U MPO/MTP patch panel (48 MPO ports) | 640 | 0 W | $960.0K | zone panels at both ends of leaf-spine trunks + hall MDA uplinks |
| Coolant distribution unit, 1.5 MW liquid-to-liquid | 5 | 0 W | $2.00M | N+1 |
| Facility build: powered shell, electrical, mechanical (per MW IT) | 7.867 | 0 W | $86.54M |  |

## Tier 6: Campus / DC

Halls joined by the super-spine core, WAN edge and utility power.

### Campus x 1

Per unit: 479.12 MW, $22.66B. All units: 479.12 MW, $22.66B.

| Item | Qty per unit | Power | Cost | Note |
|---|---:|---:|---:|---|
| Data hall (2 SuperPods, 5,088 GPUs) | 1 | 7.87 MW | $365.91M |  |
| Data hall (9 SuperPods, 36,864 GPUs) | 8 | 455.80 MW | $21.17B |  |
| 51.2T Ethernet switch (64 x 800G OSFP, TH5 / G200 class), 2RU | 4,688 | 6.56 MW | $210.96M | super-spine: 2344 per plane |
| 800G LPO 2xDR4 (linear pluggable optics, no DSP) | 73,728 | 626.7 kW | $47.92M | spine to super-spine (cross-hall): 73,728 x 400G links, both ends, 800G-equivalent modules |
| MPO-16 SMF trunk | 73,728 | 0 W | $8.79M | spine to super-spine (cross-hall): avg 66.0 m, max 66.0 m |
| 800G 2xDR4 / DR8 retimed optics (500 m SMF) | 294,912 | 4.42 MW | $250.68M | spine to super-spine (cross-hall): 294,912 x 400G links, both ends, 800G-equivalent modules |
| MPO-16 SMF trunk | 294,912 | 0 W | $114.78M | spine to super-spine (cross-hall): avg 291.0 m, max 366.0 m |
| 800G 2xFR4 retimed optics (2 km SMF) | 231,424 | 3.82 MW | $254.57M | spine to super-spine (cross-hall): 231,424 x 400G links, both ends, 800G-equivalent modules |
| Duplex LC SMF jumper/trunk | 231,424 | 0 W | $58.59M | spine to super-spine (cross-hall): avg 570.4 m, max 666.0 m |
| 48U ORv3 rack, rear-door / manifold (hybrid cooling) | 224 | 0 W | $5.60M | core network racks |
| Campus WAN edge / DCI router (400G ZR capable) | 4 | 12.0 kW | $1.00M | campus WAN / DCI edge |
| Facility build for core network and WAN rooms (per MW IT) | 15.444 | 0 W | $169.88M |  |
| Utility substation bay, 250 MVA (cost carried in facility capex) | 3 | 0 W | $0 | 599 MW facility load at PUE 1.25 |

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
