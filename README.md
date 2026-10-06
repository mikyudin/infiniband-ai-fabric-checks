# infiniband-ai-fabric-checks

Verification for **[InfiniBand in AI Fabrics: What Ethernet Is Borrowing](https://mike.ydn.au/infiniband-ai-fabrics/)**.

Companion to that post. Every figure quoted in it is recomputed here from
published datasheets, kernel headers, specifications and papers. Standard
library only, no dependencies, no network access, no credentials.

```
python3 infiniband-ai-fabric-checks.py
```

```
8/8 groups passed, 3 skipped, 0 failed
```

## Why this exists

Most of the InfiniBand-versus-Ethernet argument for AI back-end fabrics runs
on market share. Market share says what hyperscalers bought, and Dell'Oro's
own explanation for Ethernet's lead is supplier diversity, not performance.
This file does the arithmetic on what the protocols and the switches actually
are: header bytes, address space, fat-tree radix, credit windows and
all-reduce bandwidth.

## Findings

Each of these is asserted by the script rather than stated.

| Finding | Figure |
|---|---|
| NVIDIA quotes Quantum-2 throughput bidirectionally and Quantum-X800 unidirectionally | Headline step **2.25x**; like for like **4.5x** |
| NVIDIA's "5X higher scalability" for Quantum-X800 | Two-tier endpoints, 10,368 / 2,048 = **5.06x** |
| Unicast LIDs in one InfiniBand subnet | **49,151** (0x0001 to 0xBFFF) |
| Two-tier Quantum-X800 fabric, endpoints plus switches | **10,584 LIDs**: fits at LMC 0, not at LMC 3 |
| Three-tier Quantum-X800 fabric against the LID space | **15.2x** too big for one subnet |
| Per-packet overhead at the 4096-byte transport MTU | InfiniBand **26 B (99.37%)**; RoCEv2/IPv6 with 802.1Q tag **106 B (97.48%)** |
| Worst-case header efficiency gap | **1.89 points**, an upper bound |
| Two-tier 800G endpoints: Quantum-X800 against 102.4 Tb/s Ethernet | **10,368 vs 8,192**, 1.27x |
| All-reduce bytes per rank, point-to-point, as a multiple of the buffer | 2(n-1)/n: **1.75** at 8 ranks, approaching 2 |
| Best bandwidth saving from in-network reduction (SHARP) | **under 2x**, for every cluster size |
| 2014 InfiniBand credit window (12-bit, 64 B blocks) | **128 KiB** per lane: a 1.31 us round trip at 800 Gb/s |

One result ran against expectation. The Quantum-X800 datasheet's SHARP
"boosting performance by up to 9X" looks like an all-reduce speed-up far
beyond the 2x bandwidth ceiling. It is not one: NVIDIA's launch release defines
it as nine times the previous generation's in-network compute (14.4 TFLOPS), a
property of the switch rather than of a job.

## Groups

1. The market, as Dell'Oro's 2026 releases report it.
2. Fat-tree arithmetic: two- and three-tier endpoints for each switch,
   checked against the vendors' own claims.
3. The datasheet trap: one vendor, two throughput conventions.
4. The LID ceiling, and which fabrics fit in one subnet.
5. Header overhead per packet, native InfiniBand against RoCEv2.
6. Credit windows under the 2014 accounting, and the round trip they cover.
7. All-reduce: point-to-point algorithms against in-network reduction.
8. Meta's two 24,576-GPU clusters and what their RoCE paper reports.

## Sources

All retrieved **6 October 2026** and recorded in the `FACTS` table.

- **Dell'Oro Group** press releases, 10 March 2026 and 2 June 2026, and its
  2026 predictions post.
- **NVIDIA** Quantum-2 product page, Quantum-X800 datasheet, Spectrum-X page,
  and the X800 launch release (18 March 2024).
- **Broadcom** Tomahawk 6 release (3 June 2025).
- **Linux** `include/rdma/ib_pack.h` and `include/rdma/ib_verbs.h` for header
  sizes and the `IB_MTU_4096` ceiling; **Wireshark**'s InfiniBand dissector
  for the 2-byte VCRC; **IEEE 802.3** for FCS and inter-frame overhead.
- **OpenSM** (`linux-rdma/opensm`): `include/iba/ib_types.h` for the unicast
  LID range and `opensm(8)` for LMC.
- **Crupnicoff (Mellanox)**, *InfiniBand Credit-Based Link-Layer
  Flow-Control*, IEEE 802.1 DCB TG, March 2014.
- **Hoefler et al.**, *Ultra Ethernet's Design Principles and Architectural
  Innovations*, arXiv:2508.08906.
- **Meta**, *Building Meta's GenAI Infrastructure* (12 March 2024) and
  Gangidi et al., *RDMA over Ethernet for Distributed AI Training at Meta
  Scale*, SIGCOMM 2024.
- **NVIDIA nccl-tests**, `doc/PERFORMANCE.md`, for the all-reduce bound.

## What this is not

- Not measured. This is arithmetic on published documents. The only measured
  results it carries are Meta's, quoted as Meta reported them.
- Not a recommendation for either fabric. It says which arguments survive the
  arithmetic and which do not.
- Not a statement about current XDR credit accounting. The InfiniBand
  specification is member-gated, and group 6 uses the 2014 description.

Three items are skipped rather than guessed, and the script prints why:
Dell'Oro's dollar figures (paid report), InfiniBand's physical-layer framing
(no public source, so the header gaps are upper bounds), and whether XDR still
uses 12-bit credit fields.

One input is a declared assumption rather than a published fact:
`FIBRE_NS_PER_M` (4.9 ns per metre), used only to turn a time budget into a
cable length in group 6.

## Licence

MIT. See [LICENSE](LICENSE).
