#!/usr/bin/env python3
"""
SHA-256 Hashing Performance Benchmark
Claim under test: A single-threaded Python process can hash 1 million SHA-256
digests in under 5 seconds on commodity hardware.

This script is fully reproducible: fixed seed, explicit inputs, deterministic output.
"""

import hashlib
import time
import gc
import os
import sys

# === CONFIGURATION ===
INPUT_COUNTS = [100_000, 500_000, 1_000_000, 2_000_000, 5_000_000, 10_000_000]
ALGORITHMS = ["sha256", "sha512"]
NUM_RUNS = 5  # Number of runs per configuration for statistics
RANDOM_SEED = 42


# === HARDWARE CAPTURE ===
def get_hardware_info():
    """Capture precise hardware environment."""
    info = {}
    try:
        with open("/proc/cpuinfo") as f:
            lines = f.readlines()
            model = [l for l in lines if "model name" in l]
            cache = [l for l in lines if "cache size" in l]
            cores = [l for l in lines if "cpu cores" in l]
            mhz = [l for l in lines if "cpu MHz" in l]
            info["cpu_model"] = model[0].split(":")[1].strip() if model else "unknown"
            info["cache_size"] = cache[0].split(":")[1].strip() if cache else "unknown"
            info["cpu_cores"] = cores[0].split(":")[1].strip() if cores else "unknown"
            info["cpu_mhz"] = mhz[0].split(":")[1].strip() if mhz else "unknown"
    except:
        info["cpu_model"] = "unknown"
        info["cache_size"] = "unknown"

    try:
        with open("/proc/meminfo") as f:
            lines = f.readlines()
            mem = [l for l in lines if "MemTotal" in l]
            if mem:
                info["ram_total"] = mem[0].split(":")[1].strip()
    except:
        info["ram_total"] = "unknown"

    info["hostname"] = os.uname().nodename
    info["os"] = os.uname().sysname + " " + os.uname().release
    info["python_version"] = sys.version
    info["random_seed"] = RANDOM_SEED

    return info


# === BENCHMARK CORE ===
def generate_inputs(count, seed):
    """Generate 'count' distinct byte strings. Uses deterministic mapping."""
    # Using sequential integers encoded as bytes - fully deterministic
    return [str(i).encode("utf-8") for i in range(count)]


def run_benchmark(algorithm, input_count, disable_gc=False, verify=False):
    """
    Hash 'input_count' inputs with specified algorithm.
    Returns (wall_clock_time, final_digest, hash_count)
    """
    if disable_gc:
        gc.disable()

    try:
        # Generate inputs
        inputs = generate_inputs(input_count, RANDOM_SEED)

        # Create hasher
        hasher = getattr(hashlib, algorithm)

        # Warm-up run to ensure library is loaded (not timed)
        _ = hasher()

        # Start timing
        start = time.perf_counter()

        # Compute all hashes
        digest = None
        for inp in inputs:
            h = hasher(inp)
            digest = h.digest()  # Force actual computation

        # End timing
        end = time.perf_counter()
        elapsed = end - start

        # Verify determinism: re-run and confirm same individual hashes
        if verify:
            digests = []
            for inp in inputs:
                digests.append(hasher(inp).digest())
            # Check last digest matches (intermediate values are not stored)
            assert digests[-1] == digest, (
                f"Digest mismatch: {digests[-1].hex()[:16]} != {digest.hex()[:16]}"
            )

        return elapsed, digest, input_count

    finally:
        if disable_gc:
            gc.enable()


def run_multiple_trials(algorithm, input_count, disable_gc=False, num_runs=NUM_RUNS):
    """Run benchmark multiple times and return statistics."""
    times = []
    final_digest = None

    for i in range(num_runs):
        elapsed, digest, count = run_benchmark(algorithm, input_count, disable_gc)
        times.append(elapsed)
        final_digest = digest

    times_arr = sorted(times)
    mean_t = sum(times) / len(times)
    std_t = (sum((t - mean_t) ** 2 for t in times) / len(times)) ** 0.5

    return {
        "times": times,
        "mean": mean_t,
        "std": std_t,
        "min": min(times),
        "max": max(times),
        "median": times_arr[len(times_arr) // 2],
        "final_digest": final_digest.hex()[:32] + "..." if final_digest else None,
        "final_digest_full": final_digest.hex() if final_digest else None,
    }


def format_result(name, result, input_count, bound):
    """Format a result for display."""
    status = "PASS" if result["mean"] < bound else "FAIL"
    return (
        f"{name}:\n"
        f"  Count: {input_count:,}\n"
        f"  Mean:  {result['mean']:.4f}s\n"
        f"  Std:   {result['std']:.4f}s\n"
        f"  Min:   {result['min']:.4f}s\n"
        f"  Max:   {result['max']:.4f}s\n"
        f"  Bound: {bound}s → {status}\n"
        f"  Final digest: {result['final_digest']}\n"
    )


# === MAIN ===
def main():
    print("=" * 70)
    print("SHA-256 HASHING PERFORMANCE BENCHMARK")
    print("=" * 70)

    # Hardware info
    hw = get_hardware_info()
    print("\n--- HARDWARE ENVIRONMENT ---")
    for k, v in hw.items():
        print(f"  {k}: {v}")

    print(f"\n--- BENCHMARK PARAMETERS ---")
    print(f"  Algorithms: {ALGORITHMS}")
    print(f"  Input counts: {INPUT_COUNTS}")
    print(f"  Runs per config: {NUM_RUNS}")
    print(f"  GC test: enabled and disabled")

    print("\n" + "=" * 70)
    print("PRIMARY CLAIM TEST: 1M SHA-256 hashes < 5 seconds")
    print("=" * 70)

    bound = 5.0  # seconds

    # Primary test: 1M SHA-256, GC enabled
    print("\n--- SHA-256 @ 1,000,000 inputs (GC enabled) ---")
    result_gc_on = run_multiple_trials("sha256", 1_000_000, disable_gc=False)
    print(format_result("SHA-256 1M GC-ON", result_gc_on, 1_000_000, bound))

    # Verify determinism
    print("  Verifying determinism...")
    _, digest1, _ = run_benchmark("sha256", 1_000_000, disable_gc=False, verify=True)
    _, digest2, _ = run_benchmark("sha256", 1_000_000, disable_gc=False, verify=True)
    assert digest1 == digest2, "Results are non-deterministic!"
    print(f"  Determinism verified. Digest: {digest1.hex()[:32]}...")

    # Primary test: 1M SHA-256, GC disabled
    print("\n--- SHA-256 @ 1,000,000 inputs (GC disabled) ---")
    result_gc_off = run_multiple_trials("sha256", 1_000_000, disable_gc=True)
    print(format_result("SHA-256 1M GC-OFF", result_gc_off, 1_000_000, bound))

    # Sensitivity: Input count scaling
    print("\n" + "=" * 70)
    print("SENSITIVITY ANALYSIS: Input Count Scaling (SHA-256, GC enabled)")
    print("=" * 70)
    scaling_results = {}
    for count in INPUT_COUNTS:
        print(f"\n--- SHA-256 @ {count:,} inputs ---")
        r = run_multiple_trials("sha256", count, disable_gc=False)
        scaling_results[count] = r
        print(format_result(f"SHA-256 {count:,}", r, count, float("inf")))

    # Sensitivity: Algorithm comparison
    print("\n" + "=" * 70)
    print("SENSITIVITY ANALYSIS: Algorithm Comparison (1M inputs, GC enabled)")
    print("=" * 70)
    for algo in ALGORITHMS:
        print(f"\n--- {algo.upper()} @ 1,000,000 inputs ---")
        r = run_multiple_trials(algo, 1_000_000, disable_gc=False)
        print(format_result(f"{algo.upper()} 1M", r, 1_000_000, float("inf")))

    # Sensitivity: GC impact
    print("\n" + "=" * 70)
    print("SENSITIVITY ANALYSIS: GC Impact (SHA-256 @ 1M inputs)")
    print("=" * 70)
    gc_impact = {
        "gc_on_mean": result_gc_on["mean"],
        "gc_off_mean": result_gc_off["mean"],
        "gc_on_std": result_gc_on["std"],
        "gc_off_std": result_gc_off["std"],
    }
    if result_gc_off["mean"] > 0 and result_gc_on["mean"] > 0:
        diff_pct = (
            100 * (result_gc_off["mean"] - result_gc_on["mean"]) / result_gc_on["mean"]
        )
        gc_impact["impact_pct"] = diff_pct
        print(
            f"  GC ON  mean: {result_gc_on['mean']:.4f}s ± {result_gc_on['std']:.4f}s"
        )
        print(
            f"  GC OFF mean: {result_gc_off['mean']:.4f}s ± {result_gc_off['std']:.4f}s"
        )
        print(f"  Impact: {diff_pct:+.2f}%")

    # Final verification digest for 1M SHA-256
    print("\n" + "=" * 70)
    print("VERIFICATION: Final digest of 1M SHA-256 hashes")
    print("=" * 70)
    _, final_d, _ = run_benchmark("sha256", 1_000_000, disable_gc=False, verify=True)
    print(f"  Expected: deterministic based on sequential integer inputs 0-999999")
    print(f"  Actual digest (first 64 hex chars): {final_d.hex()}")

    # Summary for verdict
    print("\n" + "=" * 70)
    print("SUMMARY FOR VERDICT")
    print("=" * 70)
    print(f"  Primary claim: 1M SHA-256 hashes < 5s")
    print(f"  GC ON  range:  [{result_gc_on['min']:.4f}s, {result_gc_on['max']:.4f}s]")
    print(f"  GC ON  mean:    {result_gc_on['mean']:.4f}s ± {result_gc_on['std']:.4f}s")
    print(
        f"  GC OFF range:  [{result_gc_off['min']:.4f}s, {result_gc_off['max']:.4f}s]"
    )
    print(
        f"  GC OFF mean:    {result_gc_off['mean']:.4f}s ± {result_gc_off['std']:.4f}s"
    )
    print(f"  Acceptance bound: < 5.0000s (strict)")

    # Linear scaling check
    if 100_000 in scaling_results and 1_000_000 in scaling_results:
        ratio_10x = (
            scaling_results[1_000_000]["mean"] / scaling_results[100_000]["mean"]
        )
        print(f"  Scaling ratio (1M vs 100K): {ratio_10x:.2f}x (ideal: 10x)")

    return {
        "hw": hw,
        "result_gc_on": result_gc_on,
        "result_gc_off": result_gc_off,
        "scaling_results": {
            k: {"mean": v["mean"], "std": v["std"], "min": v["min"], "max": v["max"]}
            for k, v in scaling_results.items()
        },
        "bound": bound,
    }


if __name__ == "__main__":
    results = main()
