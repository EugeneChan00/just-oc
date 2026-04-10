#!/usr/bin/env python3
"""
Bandwidth Utilization Analysis: REST API over 1Gbps Link
Claim: 2KB JSON payload @ 10,000 RPS on 1Gbps - does it saturate?

Method: Closed-form protocol stack calculation
"""

import math

# === CONSTANTS ===
LINK_SPEED_BPS = 1_000_000_000  # 1 Gbps
LINK_SPEED_MBPS = 1_000  # 1 Gbps in Mbps

# === PROTOCOL OVERHEAD ESTIMATES ===
# All sizes in bytes

# HTTP overhead
HTTP_RESP_HEADER_MIN = 200
HTTP_RESP_HEADER_TYP = 300
HTTP_RESP_HEADER_MAX = 400

# TLS overhead (per record, for established connection)
TLS_RECORD_HEADER = 5  # content type(1) + version(2) + length(2)
TLS_PADDING_OVERHEAD = 20  # conservative for block cipher padding
TLS_OVERHEAD_PER_RECORD = TLS_RECORD_HEADER + TLS_PADDING_OVERHEAD  # ~25 bytes typical

# TCP overhead
TCP_HEADER = 20  # without options
TCP_ACK_OVERHEAD_PER_SEG = TCP_HEADER  # ACK packets

# IP overhead
IP_HEADER = 20  # without options

# Ethernet overhead
ETH_HEADER = 14  # dst(6) + src(6) + ethertype(2)
ETH_FCS = 4  # Frame Check Sequence
ETH_IFG = 12  # Inter-Frame Gap
ETH_PREAMBLE = 8  # Preamble (sometimes included)
ETH_OVERHEAD = ETH_HEADER + ETH_FCS + ETH_IFG + ETH_PREAMBLE  # = 38 bytes

# VLAN tag (common in production)
VLAN_TAG = 4
ETH_OVERHEAD_VLAN = ETH_OVERHEAD + VLAN_TAG  # = 42 bytes

# Conservative estimate: use VLAN overhead (production typical)
ETH_OV = ETH_OVERHEAD_VLAN  # bytes per Ethernet frame

# MSS for TCP segmentation
MSS = 1460  # typical MTU 1500 - IP(20) - TCP(20)

# === REQUEST DIRECTION OVERHEAD (upstream - client to server) ===
# HTTP request header (GET/POST line + headers)
HTTP_REQ_HEADER = 250  # bytes (typical small request)
TCP_ACK_SIZE = TCP_HEADER + IP_HEADER + ETH_OV  # pure ACK packet

# === ASSUMPTIONS ===
# 1. Established TLS connection (no handshake overhead amortized)
# 2. HTTP/1.1 keep-alive (connection reused)
# 3. No HTTP/2 multiplexing (fundamental model limitation)
# 4. Linear ACK per response segment
# 5. No significant retransmissions in healthy network (0.1% assumed)


def compute_per_packet_overhead(
    payload_bytes, http_header_bytes, is_response=True, is_data=True
):
    """
    Compute total on-wire bytes for a single packet.

    For data packets (payload-carrying):
      ETH(14+4+12+8) + IP(20) + TCP(20) + TLS(25) + HTTP_hdr + payload

    For ACK packets:
      ETH(14+4+12+8) + IP(20) + TCP(20) = 52 bytes + ETH overhead
    """
    if is_data:
        # Layer 4: TLS record
        tls_overhead = TLS_OVERHEAD_PER_RECORD
        # Layer 7: HTTP header
        http_overhead = http_header_bytes if is_response else HTTP_REQ_HEADER

        # Total layer 7 data
        layer7_size = http_overhead + payload_bytes

        # TCP segmentation
        num_tcp_segs = math.ceil(layer7_size / MSS)

        # Layer 4: TCP
        tcp_overhead_total = num_tcp_segs * TCP_HEADER

        # Layer 3: IP
        ip_overhead_total = num_tcp_segs * IP_HEADER

        # Layer 2: Ethernet (one frame per TCP segment)
        eth_overhead_total = num_tcp_segs * ETH_OV

        # Total on-wire
        total_on_wire = (
            layer7_size
            + tls_overhead
            + tcp_overhead_total
            + ip_overhead_total
            + eth_overhead_total
        )

        return {
            "layer7_payload": payload_bytes,
            "http_header": http_header_bytes,
            "layer7_total": layer7_size,
            "tls_overhead": tls_overhead,
            "tcp_overhead": tcp_overhead_total,
            "ip_overhead": ip_overhead_total,
            "eth_overhead": eth_overhead_total,
            "num_tcp_segs": num_tcp_segs,
            "total_on_wire": total_on_wire,
        }
    else:
        # ACK packet (no payload)
        return {
            "layer7_payload": 0,
            "http_header": 0,
            "layer7_total": 0,
            "tls_overhead": 0,
            "tcp_overhead": TCP_HEADER,
            "ip_overhead": IP_HEADER,
            "eth_overhead": ETH_OV,
            "num_tcp_segs": 1,
            "total_on_wire": TCP_HEADER + IP_HEADER + ETH_OV,
        }


def compute_bandwidth(payload_bytes, http_header, rps, include_request_overhead=True):
    """
    Compute total bandwidth utilization for given payload, header, and RPS.
    Returns downstream, upstream, and total in bps and % of 1Gbps.
    """
    # Downstream (server to client): data packets
    downstream = compute_per_packet_overhead(
        payload_bytes, http_header, is_response=True, is_data=True
    )
    downstream_bps = downstream["total_on_wire"] * 8 * rps

    # Upstream: ACKs for each TCP segment + request headers
    num_segs = downstream["num_tcp_segs"]

    if include_request_overhead:
        # Request from client (HTTP GET + headers)
        upstream_req = compute_per_packet_overhead(
            0, http_header, is_response=False, is_data=False
        )
        # Note: upstream_req has is_data=False, so http_header is not used for data

        # Actually for request, we need to include HTTP request header separately
        req_total = HTTP_REQ_HEADER + TCP_HEADER + IP_HEADER + ETH_OV

        # ACKs for downstream data packets (one ACK per TCP segment)
        ack_total = num_segs * (TCP_HEADER + IP_HEADER + ETH_OV)

        upstream_bps = (req_total + ack_total) * 8 * rps
    else:
        upstream_bps = num_segs * (TCP_HEADER + IP_HEADER + ETH_OV) * 8 * rps

    total_bps = downstream_bps + upstream_bps
    utilization = (total_bps / LINK_SPEED_BPS) * 100

    return {
        "downstream_bps": downstream_bps,
        "upstream_bps": upstream_bps,
        "total_bps": total_bps,
        "utilization_pct": utilization,
        "num_segments": num_segs,
        "downstream_per_resp": downstream,
    }


def bytes_to_mbps(bps):
    return bps / 1_000_000


def compute_uncertainty_range(payload_bytes, rps):
    """Compute utilization range from HTTP header min to max."""
    res_min = compute_bandwidth(payload_bytes, HTTP_RESP_HEADER_MIN, rps)
    res_max = compute_bandwidth(payload_bytes, HTTP_RESP_HEADER_MAX, rps)
    res_typ = compute_bandwidth(payload_bytes, HTTP_RESP_HEADER_TYP, rps)

    return {
        "min_util": res_min["utilization_pct"],
        "typ_util": res_typ["utilization_pct"],
        "max_util": res_max["utilization_pct"],
    }


# === BASELINE: 2KB payload, 10,000 RPS ===
print("=" * 80)
print("BASELINE ANALYSIS: 2KB Payload @ 10,000 RPS")
print("=" * 80)

baseline = compute_bandwidth(2000, HTTP_RESP_HEADER_TYP, 10000)
baseline_unc = compute_uncertainty_range(2000, 10000)
unc = baseline_unc  # Use baseline_unc for reporting

print(f"\n--- Protocol Stack Breakdown (per response) ---")
d = baseline["downstream_per_resp"]
print(f"  Layer 7 (HTTP + TLS):")
print(f"    JSON payload:           {d['layer7_payload']:,} bytes")
print(f"    HTTP response header:   {d['http_header']} bytes")
print(f"    TLS record overhead:   {d['tls_overhead']} bytes")
print(f"    Layer 7 total:          {d['layer7_total']:,} bytes")
print(
    f"  Layer 4 (TCP):            {d['tcp_overhead']:,} bytes ({d['num_tcp_segs']} segment(s) × 20)"
)
print(
    f"  Layer 3 (IP):             {d['ip_overhead']:,} bytes ({d['num_tcp_segs']} × 20)"
)
print(
    f"  Layer 2 (Ethernet):       {d['eth_overhead']:,} bytes ({d['num_tcp_segs']} × {ETH_OV})"
)
print(f"  Total on-wire per resp:  {d['total_on_wire']:,} bytes")
print(f"\n--- Per-Response Breakdown ---")
print(f"  TCP segments needed:     {d['num_tcp_segs']}")
print(f"  Ethernet frames:         {d['num_tcp_segs']} (one per TCP segment)")
print(f"\n--- Bandwidth Calculation ---")
print(
    f"  Downstream:  {bytes_to_mbps(baseline['downstream_bps']):.2f} Mbps ({baseline['downstream_bps'] / 1e6:.2f} × 10³ bps)"
)
print(f"  Upstream:    {bytes_to_mbps(baseline['upstream_bps']):.2f} Mbps")
print(f"  Total:       {bytes_to_mbps(baseline['total_bps']):.2f} Mbps")
print(f"  Utilization: {baseline['utilization_pct']:.2f}%")
print(f"\n--- Uncertainty Range (HTTP header 200-400 bytes) ---")
print(f"  Min utilization: {unc['min_util']:.2f}%")
print(f"  Typ utilization: {unc['typ_util']:.2f}%")
print(f"  Max utilization: {unc['max_util']:.2f}%")
print(f"  Range:           ±{(unc['max_util'] - unc['min_util']) / 2:.2f}%")

print("\n" + "=" * 80)
print("PAYLOAD SENSITIVITY: 1KB to 10KB @ 10,000 RPS")
print("=" * 80)
print(
    f"\n{'Payload':>10} | {'Segments':>8} | {'Down(Mbps)':>11} | {'Up(Mbps)':>9} | {'Total(Mbps)':>12} | {'Util%':>7} | {'Sat?'}"
)
print("-" * 80)

payload_results = {}
for kb in range(1, 11):
    payload = kb * 1000
    res = compute_bandwidth(payload, HTTP_RESP_HEADER_TYP, 10000)
    unc = compute_uncertainty_range(payload, 10000)
    sat = "YES" if unc["max_util"] >= 100 else "NO"
    payload_results[kb] = {
        "util": res["utilization_pct"],
        "unc_min": unc["min_util"],
        "unc_max": unc["max_util"],
        "segs": res["num_segments"],
        "down": bytes_to_mbps(res["downstream_bps"]),
        "up": bytes_to_mbps(res["upstream_bps"]),
    }
    print(
        f"  {kb:>6} KB | {res['num_segments']:>8} | {bytes_to_mbps(res['downstream_bps']):>11.2f} | {bytes_to_mbps(res['upstream_bps']):>9.2f} | {bytes_to_mbps(res['total_bps']):>12.2f} | {res['utilization_pct']:>7.2f}% | {sat}"
    )

print("\n" + "=" * 80)
print("RPS SENSITIVITY: 5,000 to 20,000 RPS @ 2KB Payload")
print("=" * 80)
print(
    f"\n{'RPS':>10} | {'Segments':>8} | {'Down(Mbps)':>11} | {'Up(Mbps)':>9} | {'Total(Mbps)':>12} | {'Util%':>7} | {'Sat?'}"
)
print("-" * 80)

rps_results = {}
for rps in [5000, 7500, 10000, 12500, 15000, 17500, 20000]:
    res = compute_bandwidth(2000, HTTP_RESP_HEADER_TYP, rps)
    unc = compute_uncertainty_range(2000, rps)
    sat = "YES" if unc["max_util"] >= 100 else "NO"
    rps_results[rps] = {
        "util": res["utilization_pct"],
        "unc_min": unc["min_util"],
        "unc_max": unc["max_util"],
        "segs": res["num_segments"],
    }
    print(
        f"  {rps:>6} | {res['num_segments']:>8} | {bytes_to_mbps(res['downstream_bps']):>11.2f} | {bytes_to_mbps(res['upstream_bps']):>9.2f} | {bytes_to_mbps(res['total_bps']):>12.2f} | {res['utilization_pct']:>7.2f}% | {sat}"
    )

print("\n" + "=" * 80)
print("CROSS-SENSITIVITY HEATMAP: Payload (rows) vs RPS (cols)")
print("=" * 80)
print("\nUtilization % at each (payload, RPS) combination:")
print("-" * 80)

rps_cols = [5000, 7500, 10000, 12500, 15000, 17500, 20000]
header = f"{'Payload':>8}" + "".join([f"{rps:>10}" for rps in rps_cols])
print(header)
print("-" * len(header))

for kb in range(1, 11):
    payload = kb * 1000
    row = f"  {kb:>6}KB"
    for rps in rps_cols:
        res = compute_bandwidth(payload, HTTP_RESP_HEADER_TYP, rps)
        row += f"{res['utilization_pct']:>10.1f}%"
    print(row)

print("\n--- Legend ---")
print("  < 50%: Safe (well below saturation)")
print("  50-80%: Moderate (comfortable margin)")
print("  80-95%: High (approaching saturation)")
print("  >= 100%: SATURATED (link overloaded)")

print("\n" + "=" * 80)
print("SATURATION THRESHOLD ANALYSIS")
print("=" * 80)

# Find payload threshold at 10,000 RPS
sat_payload_kb = None
sat_payload_util = None
for kb in range(1, 20):
    payload = kb * 1000
    sat_uncmaybe = compute_uncertainty_range(payload, 10000)
    if sat_uncmaybe["max_util"] >= 100:
        sat_payload_kb = kb
        sat_payload_util = sat_uncmaybe["max_util"]
        print(
            f"  Payload saturation at 10,000 RPS: ~{kb}KB (max util = {sat_uncmaybe['max_util']:.1f}%)"
        )
        break

# Find RPS threshold at 2KB payload
sat_rps = None
sat_rps_util = None
for rps in range(5000, 50000, 500):
    sat_unc_rps = compute_uncertainty_range(2000, rps)
    if sat_unc_rps["max_util"] >= 100:
        sat_rps = rps
        sat_rps_util = sat_unc_rps["max_util"]
        print(
            f"  RPS saturation at 2KB payload: ~{rps:,} RPS (max util = {sat_unc_rps['max_util']:.1f}%)"
        )
        break

# Find RPS threshold at 2KB payload
sat_rps = None
sat_rps_util = None
for rps in range(5000, 50000, 500):
    unc = compute_uncertainty_range(2000, rps)
    if unc["max_util"] >= 100:
        sat_rps = rps
        sat_rps_util = unc["max_util"]
        print(
            f"  RPS saturation at 2KB payload: ~{rps:,} RPS (max util = {unc['max_util']:.1f}%)"
        )
        break

# Find RPS threshold at 2KB payload
for rps in range(5000, 50000, 500):
    unc = compute_uncertainty_range(2000, rps)
    if unc["max_util"] >= 100:
        print(
            f"  RPS saturation at 2KB payload: ~{rps:,} RPS (max util = {unc['max_util']:.1f}%)"
        )
        break

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"""
Claim under test: "A REST API returning JSON payloads averaging 2KB can serve
                   10,000 requests per second over a 1Gbps network link without
                   saturating bandwidth."

Result: BANDWIDTH CLAIM IS CONFIRMED

  At 2KB payload, 10,000 RPS:
    - Typical utilization:     {baseline["utilization_pct"]:.2f}% of 1Gbps
    - Uncertainty range:       {baseline_unc["min_util"]:.2f}% - {baseline_unc["max_util"]:.2f}% 
      (from HTTP header variance 200-400 bytes)
    - Distance to saturation:  ~{100 - baseline["utilization_pct"]:.1f}% headroom

  Payload saturation threshold: ~{sat_payload_kb}KB at 10,000 RPS
  RPS saturation threshold:     ~{sat_rps:,} RPS at 2KB payload

  The 2KB @ 10,000 RPS scenario uses only ~24% of a 1Gbps link.
  Even with conservative overhead estimates, the claim holds.
""")

# Store key values for reporting
KEY_RESULT = {
    "baseline_util": baseline["utilization_pct"],
    "baseline_unc_min": baseline_unc["min_util"],
    "baseline_unc_max": baseline_unc["max_util"],
    "payload_threshold": sat_payload_kb,
    "rps_threshold": sat_rps,
}

print(f"\nKey values for report: {KEY_RESULT}")
