#!/usr/bin/env python3
"""
Verification for "InfiniBand in AI Fabrics: What Ethernet Is Borrowing".

Every number quoted in the post is recomputed here from published figures,
with no network access and no dependencies outside the standard library.

    python3 infiniband-ai-fabric-checks.py

Published inputs live in FACTS below, each with the document it came from.
All were retrieved 2026-10-06. Nothing here is measured on hardware: every
result is arithmetic on vendor datasheets, kernel headers, specifications and
papers.

One input is a declared assumption rather than a published fact, and it is
isolated so a reader can replace it:

  * FIBRE_NS_PER_M, the one-way propagation delay of fibre, used only in
    group 6 to turn a time budget into a cable length.

Groups:

  1. The market: what Dell'Oro's two 2026 releases do and do not say.
  2. Fat-tree arithmetic: endpoints in a non-blocking two- and three-tier
     fat tree for each switch in the post, checked against the vendors' own
     claims where they make one.
  3. The datasheet trap: NVIDIA quotes Quantum-2 throughput bidirectionally
     and Quantum-X800 throughput unidirectionally.
  4. The LID ceiling: how many end ports one InfiniBand subnet can address,
     and which of the fabrics in group 2 fit in one.
  5. Header overhead per packet: native InfiniBand against RoCEv2, at the
     largest MTU the InfiniBand transport allows.
  6. Credit windows: what a 12-bit, 64-byte-block credit counter allows in
     flight per virtual lane, and the round-trip time that covers.
  7. All-reduce: the bytes each rank must move with point-to-point
     algorithms, against in-network reduction.
  8. Meta's two 24,576-GPU clusters, and what their RoCE paper reports.
"""

import sys

FAILURES = []
SKIPPED = []

# Declared assumption, not a published fact. Silica fibre has a group index
# near 1.47, so light covers a metre in about 4.9 ns. Used only in group 6.
FIBRE_NS_PER_M = 4.9


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILURES.append(f"{label}: got {got!r}, want {want!r}")
    print(f"     {'ok  ' if ok else 'FAIL'} {label}: {got}")
    return ok


def close(label, got, want, tol):
    ok = abs(got - want) <= tol
    if not ok:
        FAILURES.append(f"{label}: got {got!r}, want {want!r} +/- {tol}")
    print(f"     {'ok  ' if ok else 'FAIL'} {label}: {got}")
    return ok


# ---------------------------------------------------------------------------
# Published figures, with provenance.
# ---------------------------------------------------------------------------

FACTS = {
    # --- Dell'Oro Group press releases.
    # 2026-03-10, "Ethernet More Than Doubles Size of InfiniBand as the
    # Leading Fabric for AI Scale-Out Networks in 2025": Ethernet "accounted
    # for more than two-thirds of data center switch sales in AI clusters
    # during the fourth quarter of 2025 and for the full year".
    "delloro_eth_share_2025_min": 2 / 3,
    # "2026 Predictions" post: "just two years ago, InfiniBand accounted for
    # nearly 80% of the data center switch sales in AI back-end networks".
    "delloro_ib_share_2023_approx": 0.80,
    # 2026-06-02, "Ethernet Extends Lead ... Despite Strong InfiniBand
    # Rebound": Ethernet "about two-thirds" in 1Q26, and "InfiniBand sales
    # more than tripled during the quarter".
    "delloro_eth_share_1q26_approx": 2 / 3,

    # --- Switch radix, from the vendors' own pages and datasheets.
    # NVIDIA Quantum-2 product page: "64 400Gb/s ports or 128 200Gb/s
    # ports"; "an aggregated 51.2 terabits per second (Tb/s) of
    # bidirectional throughput".
    "quantum2_ports": 64, "quantum2_gbps": 400,
    "quantum2_quoted_tbps": 51.2, "quantum2_quote_is_bidirectional": True,
    # NVIDIA Quantum-X800 datasheet (Q3400-RA): "144 ports at 800Gb/s";
    # "115.2Tb/s throughput"; "a two-level fat-tree topology capable of
    # connecting up to 10,368 network interface cards".
    "x800_ports": 144, "x800_gbps": 800,
    "x800_quoted_tbps": 115.2, "x800_quoted_two_tier": 10368,
    # 51.2 Tb/s Ethernet (Spectrum-4, Tomahawk 5): 64 x 800G or 128 x 400G.
    "eth51_ports_800": 64, "eth51_ports_400": 128,
    # Broadcom Tomahawk 6 release, 2025-06-03 (investors.broadcom.com):
    # "102.4 Terabits/sec of switching capacity in a single chip"; "an option
    # for 1,024 100G SerDes"; "100,000+ XPUs in a two-tier scale-out network
    # at 200 Gbps/link". 512 x 200G is the same 102.4 Tb/s.
    "th6_ports_200": 512, "th6_ports_800": 128,
    "th6_claimed_two_tier_min": 100_000,
    # NVIDIA Spectrum-X page: Spectrum-6 SN6600 "offers 128 ports of 800 G".
    "spectrum6_ports_800": 128,
    # NVIDIA GTC launch release, 2024-03-18, "NVIDIA Unveils Next-Generation
    # Networking Switches": Quantum-X800 is "5x higher bandwidth capacity
    # and a 9x increase of 14.4Tflops of In-Network Computing with ...
    # (SHARPv4) compared to the previous generation". The datasheet's
    # "boosting performance by up to 9X" is that generational compute
    # figure, not an all-reduce speed-up. Its "5X higher scalability"
    # matches the two-tier endpoint ratio checked in group 3.
    "nvidia_x800_scalability_claim": 5,
    "nvidia_x800_inc_tflops": 14.4, "nvidia_x800_inc_gen_multiple": 9,
    # NVIDIA Quantum-2 product page: "Over one million 400Gb/s nodes in a
    # four-switch-tier (three hops) DragonFly+ network".
    "quantum2_dragonfly_nodes_min": 1_000_000,

    # --- InfiniBand addressing. linux-rdma/opensm include/iba/ib_types.h:
    # IB_LID_UCAST_START_HO 0x0001, IB_LID_UCAST_END_HO 0xBFFF,
    # multicast from 0xC000, IB_LID_PERMISSIVE 0xFFFF.
    # opensm(8): "The number of LIDs assigned to each port is 2^LMC. The
    # LMC value must be in the range 0-7."
    "lid_ucast_start": 0x0001, "lid_ucast_end": 0xBFFF,
    "lmc_max": 7,
    # opensm(8): "OpenSM now offers ten routing engines", then a separate
    # "file method which can load routes from a table".
    "opensm_engines_stated": 10,   # quoted in the post, not computed

    # --- Header sizes. Linux include/rdma/ib_pack.h: IB_LRH_BYTES 8,
    # IB_ETH_BYTES 14, IB_VLAN_BYTES 4, IB_GRH_BYTES 40, IB_IP4_BYTES 20,
    # IB_UDP_BYTES 8, IB_BTH_BYTES 12, IB_ICRC_BYTES 4.
    # VCRC is 2 bytes: Wireshark epan/dissectors/packet-infiniband.c,
    # "(- 2) for VCRC which lives at the end of the packet".
    "lrh": 8, "grh": 40, "bth": 12, "icrc": 4, "vcrc": 2,
    "eth": 14, "vlan": 4, "ipv4": 20, "ipv6": 40, "udp": 8,
    # IEEE 802.3: 4-byte FCS; 7-byte preamble + 1-byte SFD + 12-byte
    # minimum inter-packet gap = 20 bytes of line time per frame.
    "fcs": 4, "eth_preamble_sfd_ipg": 20,
    # Linux include/rdma/ib_verbs.h: enum ib_mtu tops out at IB_MTU_4096.
    "ib_mtu_max": 4096,
    # A common switch jumbo MTU, quoted in the post only to say the room
    # above the 4096-byte RDMA MTU goes unused. Not a published fact.
    "jumbo_mtu_example": 9216,
    # Broadcom Tomahawk Ultra release, 2025-07-15: "reducing Ethernet header
    # overhead from 46 bytes to just 10 bytes". Broadcom's own accounting,
    # not comparable with group 5's byte counts.
    "tu_hdr_bytes_from": 46, "tu_hdr_bytes_to": 10,

    # --- Credit-based flow control. Crupnicoff (Mellanox), "InfiniBand
    # Credit-Based Link-Layer Flow-Control", IEEE 802.1 DCB TG, March 2014,
    # citing IBA Vol.1 section 7.9: "Flow Control Blocks 64B";
    # "12 bit fields"; "Max 2048 Credits - 128KB at 64B blocks".
    "fc_block_bytes": 64, "fc_field_bits": 12, "fc_max_credits": 2048,
    # Hoefler et al., "Ultra Ethernet's Design Principles and Architectural
    # Innovations", arXiv:2508.08906: "CBFC uses two 20-bit cyclic counters".
    "uec_cbfc_counter_bits": 20,
    # Same paper: UE 1.0 targets "medium-length (10-150m) links".
    "uec_link_m_max": 150,
    # Same paper: usable bandwidth "grew only by a factor of 100 from Single
    # Data Rate (SDR) to eXtended Data Rate (XDR)". SDR is 2.5 Gbaud with
    # 8b/10b, so 2 Gb/s of data per lane; XDR is 200 Gb/s per lane.
    "uec_sdr_to_xdr_factor": 100,
    "sdr_lane_gbaud": 2.5, "sdr_8b10b": 8 / 10, "xdr_lane_gbps": 200,

    # --- Meta. "Building Meta's GenAI Infrastructure", 2024-03-12: two
    # clusters of 24,576 H100 GPUs, one RoCE, one Quantum2 InfiniBand,
    # "Both of these solutions interconnect 400 Gbps endpoints".
    "meta_gpus_per_cluster": 24576, "meta_endpoint_gbps": 400,
    # Gangidi et al., "RDMA over Ethernet for Distributed AI Training at
    # Meta Scale", SIGCOMM 2024: "RTSW uplink capacity to be 1:2
    # under-subscribed"; relaxed DCQCN gave "marginally better completion
    # time ... by a small margin of 3%" while "PFC became worse by 2-3x";
    # path pinning "degraded the training performance up to more than 30%".
    "meta_uplink_overbuild": 2, "meta_dcqcn_gain_pct": 3,
    "meta_pfc_worse_low": 2, "meta_pfc_worse_high": 3,
    "meta_pinning_loss_pct_min": 30,
}


def note(label, value):
    """A published input the post quotes as-is. Printed, never asserted:
    comparing a fact with itself cannot fail, so it is not a check."""
    print(f"     note {label}: {value}")


def fat_tree(k):
    """Non-blocking fat tree of radix-k switches: (two-tier, three-tier)
    endpoint counts, and the switch count of the two-tier build."""
    return k * k // 2, k ** 3 // 4, k + k // 2


# ---------------------------------------------------------------------------

def group1():
    print("[1] The market, as Dell'Oro reports it")
    eth = FACTS["delloro_eth_share_2025_min"]
    ib_max = 1 - eth
    close("2025: Ethernet share of AI back-end switch sales, at least",
          round(eth, 4), 0.6667, 1e-4)
    close("  so InfiniBand at most (if the two are the whole market)",
          round(ib_max, 4), 0.3333, 1e-4)
    note("2023: InfiniBand share, approximately",
         FACTS["delloro_ib_share_2023_approx"])
    # "Under a third" at the end gives a floor of (start - 33.3), but "nearly
    # 80%" leaves the start inexact, so the post says "roughly 45 points or
    # more" and this checks only the central estimate.
    close("  swing in InfiniBand share over two years, points, approximately",
          round((FACTS["delloro_ib_share_2023_approx"] - ib_max) * 100, 1),
          46.7, 0.05)
    SKIPPED.append("Dell'Oro dollar figures: the report is paid, and the "
                   "press releases give shares and growth multiples only. "
                   "No revenue number is used in the post.")


def group2():
    print("[2] Fat-tree arithmetic")
    q2 = fat_tree(FACTS["quantum2_ports"])
    check("Quantum-2, 64 x 400G: two-tier endpoints", q2[0], 2048)
    check("Quantum-2: three-tier endpoints", q2[1], 65536)
    x8 = fat_tree(FACTS["x800_ports"])
    check("Quantum-X800, 144 x 800G: two-tier endpoints", x8[0], 10368)
    check("  matches NVIDIA's own 10,368", x8[0],
          FACTS["x800_quoted_two_tier"])
    check("  switches in that two-tier build (144 leaf + 72 spine)",
          x8[2], 216)
    check("Quantum-X800: three-tier endpoints", x8[1], 746496)
    e8 = fat_tree(FACTS["eth51_ports_800"])
    check("51.2T Ethernet as 64 x 800G: two-tier endpoints", e8[0], 2048)
    e4 = fat_tree(FACTS["eth51_ports_400"])
    check("51.2T Ethernet as 128 x 400G: two-tier endpoints", e4[0], 8192)
    t8 = fat_tree(FACTS["th6_ports_800"])
    check("102.4T Ethernet as 128 x 800G: two-tier endpoints", t8[0], 8192)
    check("  Spectrum-6 SN6600 has the same 128 x 800G radix",
          FACTS["spectrum6_ports_800"], FACTS["th6_ports_800"])
    t2 = fat_tree(FACTS["th6_ports_200"])
    check("102.4T Ethernet as 512 x 200G: two-tier endpoints", t2[0],
          131072)
    check("  so Broadcom's '100,000+' is conservative",
          t2[0] >= FACTS["th6_claimed_two_tier_min"], True)
    close("Quantum-X800 two-tier against 102.4T at 800G, ratio",
          round(x8[0] / t8[0], 3), 1.266, 0.001)
    close("Quantum-X800 two-tier against 51.2T at 800G, ratio",
          round(x8[0] / e8[0], 3), 5.062, 0.001)


def group3():
    print("[3] The datasheet trap: one vendor, two conventions")
    q2_uni = FACTS["quantum2_ports"] * FACTS["quantum2_gbps"] / 1000
    close("Quantum-2, ports x speed, Tb/s", q2_uni, 25.6, 1e-9)
    close("  NVIDIA's quoted 51.2 is that doubled (bidirectional)",
          q2_uni * 2, FACTS["quantum2_quoted_tbps"], 1e-9)
    x8_uni = FACTS["x800_ports"] * FACTS["x800_gbps"] / 1000
    close("Quantum-X800, ports x speed, Tb/s", x8_uni, 115.2, 1e-9)
    close("  NVIDIA's quoted 115.2 is NOT doubled (unidirectional)",
          x8_uni, FACTS["x800_quoted_tbps"], 1e-9)
    close("Generation step from the two headline numbers",
          round(FACTS["x800_quoted_tbps"] / FACTS["quantum2_quoted_tbps"], 2),
          2.25, 1e-9)
    close("Generation step on a like-for-like basis",
          round(x8_uni / q2_uni, 2), 4.5, 1e-9)
    x8_2t = fat_tree(FACTS["x800_ports"])[0]
    q2_2t = fat_tree(FACTS["quantum2_ports"])[0]
    close("Two-tier endpoints, Quantum-X800 over Quantum-2",
          round(x8_2t / q2_2t, 2), 5.06, 1e-9)
    check("  which is NVIDIA's '5X higher scalability', rounded",
          round(x8_2t / q2_2t), FACTS["nvidia_x800_scalability_claim"])
    e51 = FACTS["eth51_ports_800"] * 800 / 1000
    close("51.2T Ethernet, ports x speed (quoted unidirectionally)", e51,
          51.2, 1e-9)
    close("  so 'Quantum-2 51.2T' carries half a '51.2T' Ethernet chip",
          q2_uni / e51, 0.5, 1e-9)


def group4():
    print("[4] The LID ceiling")
    n = FACTS["lid_ucast_end"] - FACTS["lid_ucast_start"] + 1
    check("Unicast LIDs in one subnet (0x0001 to 0xBFFF)", n, 49151)
    per_lmc = [n // 2 ** l for l in range(FACTS["lmc_max"] + 1)]
    check("  end ports addressable at LMC 0, 1, 2, 3", per_lmc[:4],
          [49151, 24575, 12287, 6143])
    x8 = fat_tree(FACTS["x800_ports"])
    # One LID per switch: OpenSM gives switch port 0 LMC 0 unless lmc_esp0
    # is set, so only end ports are multiplied below. The LMC 3 result is
    # the same either way.
    need = x8[0] + x8[2]
    check("Two-tier Quantum-X800: endpoints plus one LID per switch", need,
          10584)
    check("  fits one subnet at LMC 0", need <= per_lmc[0], True)
    check("  does not fit at LMC 3 (8 paths per port)",
          x8[0] * 8 + x8[2] <= n, False)
    close("Three-tier Quantum-X800 endpoints over the LID space",
          round(x8[1] / n, 1), 15.2, 0.05)
    close("Quantum-2's 'over one million' DragonFly+ over the LID space",
          round(FACTS["quantum2_dragonfly_nodes_min"] / n, 1), 20.3, 0.05)
    q2 = fat_tree(FACTS["quantum2_ports"])
    check("Three-tier Quantum-2 (65,536) exceeds one subnet", q2[1] > n,
          True)


def group5():
    print("[5] Header overhead per packet")
    f = FACTS
    ib = f["lrh"] + f["bth"] + f["icrc"] + f["vcrc"]
    check("Native InfiniBand, in-subnet RC packet: LRH+BTH+ICRC+VCRC", ib, 26)
    r4 = f["eth"] + f["ipv4"] + f["udp"] + f["bth"] + f["icrc"] + f["fcs"]
    check("RoCEv2 over IPv4: Eth+IPv4+UDP+BTH+ICRC+FCS", r4, 62)
    r6 = r4 - f["ipv4"] + f["ipv6"]
    check("RoCEv2 over IPv6", r6, 82)
    w4 = r4 + f["eth_preamble_sfd_ipg"]
    w6 = r6 + f["eth_preamble_sfd_ipg"]
    check("RoCEv2/IPv4 including preamble, SFD and minimum gap", w4, 82)
    check("RoCEv2/IPv6 including preamble, SFD and minimum gap", w6, 102)
    note("  an 802.1Q tag would add, bytes", f["vlan"])
    note("IB transport MTU ceiling, bytes (also RoCE's)", f["ib_mtu_max"])
    note("Jumbo MTU above it that RoCE cannot use, bytes",
         f["jumbo_mtu_example"])
    note("Tomahawk Ultra header claim, Broadcom's accounting, bytes",
         (f["tu_hdr_bytes_from"], f["tu_hdr_bytes_to"]))
    p = f["ib_mtu_max"]
    e_ib = p / (p + ib) * 100
    e_h4 = p / (p + r4) * 100
    e_w4 = p / (p + w4) * 100
    e_w6 = p / (p + w6) * 100
    close("Payload efficiency at 4096 B, InfiniBand, %", round(e_ib, 2),
          99.37, 1e-9)
    close("  RoCEv2/IPv4, headers only, %", round(e_h4, 2), 98.51, 1e-9)
    close("  RoCEv2/IPv4 with Ethernet line overhead, %", round(e_w4, 2),
          98.04, 1e-9)
    close("  RoCEv2/IPv6 with Ethernet line overhead, %", round(e_w6, 2),
          97.57, 1e-9)
    w6q = w6 + f["vlan"]
    e_w6q = p / (p + w6q) * 100
    check("RoCEv2/IPv6 with an 802.1Q tag (PCP-based PFC)", w6q, 106)
    close("  payload efficiency, %", round(e_w6q, 2), 97.48, 1e-9)
    close("Gap, InfiniBand over untagged IPv6 RoCEv2, points",
          round(e_ib - e_w6, 2), 1.80, 1e-9)
    close("Gap, InfiniBand over tagged IPv6 RoCEv2 (worst case), points",
          round(e_ib - e_w6q, 2), 1.89, 1e-9)
    close("Gap, headers only, IPv4, points", round(e_ib - e_h4, 2), 0.86,
          1e-9)
    small = 256
    close("At 256 B payload the IPv6 gap widens to, points",
          round(small / (small + ib) * 100 - small / (small + w6) * 100, 2),
          19.27, 1e-9)
    SKIPPED.append("InfiniBand physical-layer framing (packet delimiters "
                   "and idles) is not counted: the IBTA specification is "
                   "member-gated and I found no public source for its "
                   "size at 64b/66b rates. The gaps in group 5 are "
                   "therefore upper bounds.")


def group6():
    print("[6] Credit windows")
    f = FACTS
    check("12-bit field: modulo space", 2 ** f["fc_field_bits"], 4096)
    check("  usable credits, half the modulo space", f["fc_max_credits"],
          2 ** f["fc_field_bits"] // 2)
    win = f["fc_max_credits"] * f["fc_block_bytes"]
    check("Bytes in flight per VL at the ceiling", win, 131072)
    check("  = 128 KiB", win // 1024, 128)
    rtt = {g: win * 8 / (g * 1e9) * 1e6 for g in (400, 800)}
    close("Round trip that window covers at 400 Gb/s, microseconds",
          round(rtt[400], 2), 2.62, 1e-9)
    close("Round trip that window covers at 800 Gb/s, microseconds",
          round(rtt[800], 2), 1.31, 1e-9)
    m = {g: rtt[g] * 1000 / (2 * FIBRE_NS_PER_M) for g in rtt}
    close("  as fibre, 400 Gb/s, metres, ignoring all processing",
          round(m[400]), 267, 0.5)
    close("  as fibre, 800 Gb/s, metres, ignoring all processing",
          round(m[800]), 134, 0.5)
    note("UE's stated link range tops out at, metres", f["uec_link_m_max"])
    check("UE's CBFC counter is wider than the 2014 IB field, bits",
          f["uec_cbfc_counter_bits"] - f["fc_field_bits"], 8)
    sdr = f["sdr_lane_gbaud"] * f["sdr_8b10b"]
    close("SDR data rate per lane, Gb/s", sdr, 2.0, 1e-9)
    close("  XDR over SDR per lane, matching UE's 'factor of 100'",
          f["xdr_lane_gbps"] / sdr, f["uec_sdr_to_xdr_factor"], 1e-9)
    SKIPPED.append("Whether XDR still uses 12-bit credit fields and 64-byte "
                   "blocks: the 2014 source says the block size was "
                   "'working towards configurable', and the current "
                   "specification is member-gated. Group 6 is the 2014 "
                   "accounting, and the post says so.")


def group7():
    print("[7] All-reduce: point-to-point against in-network")

    def ring(n):
        # nccl-tests doc/PERFORMANCE.md: t = (S/B) * (2*(n-1)/n) for any
        # allreduce built from point-to-point send/receive.
        return 2 * (n - 1) / n

    check("n = 2: bytes sent per rank, as a multiple of S", ring(2), 1.0)
    close("n = 8", ring(8), 1.75, 1e-12)
    close("n = 64", ring(64), 1.96875, 1e-12)
    close("n = 1,024", round(ring(1024), 4), 1.998, 1e-12)
    close("n = 10,368 (one two-tier Quantum-X800 fabric)",
          round(ring(10368), 4), 1.9998, 1e-12)
    # With in-network reduction each rank sends its S once up the tree and
    # receives the reduced S once down it: a factor of exactly 1.
    close("Best-case speed-up at n = 8", ring(8) / 1.0, 1.75, 1e-12)
    # The post says a 9x speed-up would be "more than four times" this bound.
    close("  a hypothetical 9x over the 2x ceiling", 9 / 2, 4.5, 1e-12)
    check("Speed-up is bounded by 2 for every n",
          all(ring(n) < 2 for n in range(2, 100001)), True)
    # The datasheet's "up to 9X" is NOT compared with this bound: NVIDIA's
    # launch release defines it as 9x the previous generation's in-network
    # compute (14.4 TFLOPS), a property of the switch, not of a job.
    note("NVIDIA 'up to 9X' = in-network compute vs previous generation",
         (FACTS["nvidia_x800_inc_gen_multiple"],
          FACTS["nvidia_x800_inc_tflops"]))


def group8():
    print("[8] Meta's two clusters")
    f = FACTS
    agg = f["meta_gpus_per_cluster"] * f["meta_endpoint_gbps"] / 1e6
    close("Endpoint bandwidth per cluster, Pb/s", round(agg, 2), 9.83,
          1e-9)
    note("Leaf uplinks built at this multiple of downlinks",
         f["meta_uplink_overbuild"])
    close("  i.e. this share of uplink capacity bought as insurance, %",
          (1 - 1 / f["meta_uplink_overbuild"]) * 100, 50.0, 1e-9)
    note("Relaxed DCQCN: completion time gain, %", f["meta_dcqcn_gain_pct"])
    note("  at the cost of PFC, times worse",
         (f["meta_pfc_worse_low"], f["meta_pfc_worse_high"]))
    note("Static path pinning cost, %, at least",
         f["meta_pinning_loss_pct_min"])
    x8 = fat_tree(FACTS["x800_ports"])
    check("Meta's 24,576 would need three tiers on Quantum-X800",
          f["meta_gpus_per_cluster"] > x8[0], True)
    check("  and three tiers on 51.2T Ethernet at 400G",
          f["meta_gpus_per_cluster"] > fat_tree(128)[0], True)


# ---------------------------------------------------------------------------

def main():
    groups = [group1, group2, group3, group4, group5, group6, group7,
              group8]
    failed_groups = 0
    for g in groups:
        before = len(FAILURES)
        g()
        if len(FAILURES) > before:
            failed_groups += 1
    print()
    print(f"{len(groups) - failed_groups}/{len(groups)} groups passed,"
          f" {len(SKIPPED)} skipped, {failed_groups} failed")
    for s in SKIPPED:
        print(f"  SKIP {s}")
    for f in FAILURES:
        print(f"  FAIL {f}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
