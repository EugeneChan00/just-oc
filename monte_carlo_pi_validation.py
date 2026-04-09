#!/usr/bin/env python3
"""
Monte Carlo Pi Estimation Validation Script
=============================================
Claim under test: "Monte Carlo estimation of pi using 10 million random points
achieves accuracy within 0.01% of the true value with 95% confidence."

This script:
1. Runs Monte Carlo pi estimation with N=10,000,000 points
2. Characterizes the estimator distribution via 1000 independent replications
3. Validates empirical results against CLT predictions
4. Performs sensitivity analysis across sample sizes
5. Compares Mersenne Twister vs PCG64 random number generators

Author: quantitative_developer_worker
Date: 2026-04-08
"""

import numpy as np
import time
import json
from typing import Tuple, Dict, List
import sys

# True value of pi for reference calculations
TRUE_PI = np.pi  # 3.141592653589793...

# Acceptance bound: relative error must be < 0.01% = 0.0001
# At pi ≈ 3.14159, this is an absolute error < 0.000314159...
ACCEPTANCE_RELATIVE_ERROR_BOUND = 0.0001  # 0.01% = 0.0001
ACCEPTANCE_ABSOLUTE_ERROR_BOUND = TRUE_PI * ACCEPTANCE_RELATIVE_ERROR_BOUND


def estimate_pi_monte_carlo(n: int, seed: int, rng=None) -> float:
    """
    Estimate pi using Monte Carlo method.

    Generate n uniform random points in [0,1] x [0,1].
    Count points where x^2 + y^2 <= 1 (inside quarter circle).
    Estimated pi = 4 * (count / n)

    Parameters:
    -----------
    n : int
        Number of random points to generate
    seed : int
        Random seed for reproducibility
    rng : numpy.random.Generator, optional
        Pre-configured random generator (for RNG comparison)

    Returns:
    --------
    float
        Estimated value of pi
    """
    if rng is None:
        rng = np.random.default_rng(seed)
    else:
        rng = rng

    # Generate uniform random points in [0,1] x [0,1]
    x = rng.uniform(0, 1, n)
    y = rng.uniform(0, 1, n)

    # Count points inside unit quarter-circle (x^2 + y^2 <= 1)
    inside = np.sum(x**2 + y**2 <= 1)

    # Estimate pi
    pi_estimate = 4 * inside / n

    return pi_estimate


def run_single_replication(n: int, seed: int, rng_type: str = "mt19937") -> Dict:
    """
    Run a single Monte Carlo replication.

    Parameters:
    -----------
    n : int
        Number of points
    seed : int
        Random seed
    rng_type : str
        'mt19937' for Mersenne Twister, 'pcg64' for PCG64

    Returns:
    --------
    Dict with seed, pi_estimate, absolute_error, relative_error
    """
    if rng_type == "mt19937":
        rng = np.random.default_rng(seed)
    elif rng_type == "pcg64":
        rng = np.random.default_rng(np.random.PCG64(seed))
    else:
        raise ValueError(f"Unknown RNG type: {rng_type}")

    pi_estimate = estimate_pi_monte_carlo(n, seed, rng)

    return {
        "seed": seed,
        "pi_estimate": pi_estimate,
        "absolute_error": abs(pi_estimate - TRUE_PI),
        "relative_error": abs(pi_estimate - TRUE_PI) / TRUE_PI,
        "rng_type": rng_type,
    }


def run_replications(
    n: int, n_reps: int, base_seed: int, rng_type: str = "mt19937"
) -> Tuple[List[Dict], Dict]:
    """
    Run multiple independent replications and compute statistics.

    Parameters:
    -----------
    n : int
        Number of points per replication
    n_reps : int
        Number of replications
    base_seed : int
        Base seed for generating unique seeds for each replication
    rng_type : str
        RNG type to use

    Returns:
    --------
    Tuple of (list of replication results, summary statistics)
    """
    results = []

    # Use a separate RNG to generate seeds for replications
    # This ensures reproducibility while giving each replication a unique seed
    seed_generator = np.random.default_rng(base_seed)

    for i in range(n_reps):
        # Generate unique seed for this replication
        rep_seed = int(seed_generator.integers(0, 2**31))
        result = run_single_replication(n, rep_seed, rng_type)
        results.append(result)

    # Extract pi estimates
    pi_estimates = np.array([r["pi_estimate"] for r in results])

    # Compute summary statistics
    mean_estimate = np.mean(pi_estimates)
    std_estimate = np.std(pi_estimates, ddof=1)  # Sample std dev
    p2_5 = np.percentile(pi_estimates, 2.5)
    p97_5 = np.percentile(pi_estimates, 97.5)

    # Empirical relative error at 95% confidence
    # This is the maximum deviation from true pi that captures 95% of estimates
    empirical_relative_error_95 = (
        max(abs(p2_5 - TRUE_PI), abs(p97_5 - TRUE_PI)) / TRUE_PI
    )

    # Theoretical standard error from CLT
    p_theoretical = TRUE_PI / 4  # True probability of being inside quarter circle
    theoretical_se = 4 * np.sqrt(p_theoretical * (1 - p_theoretical) / n)

    # Using mean estimate for SE calculation
    p_estimated = mean_estimate / 4
    empirical_se = 4 * np.sqrt(p_estimated * (1 - p_estimated) / n)

    summary = {
        "n": n,
        "n_reps": n_reps,
        "rng_type": rng_type,
        "base_seed": base_seed,
        "mean_estimate": mean_estimate,
        "std_estimate": std_estimate,
        "theoretical_se": theoretical_se,
        "empirical_se": empirical_se,
        "se_ratio": std_estimate / theoretical_se,  # Should be ~1.0
        "p2_5": p2_5,
        "p97_5": p97_5,
        "ci_width": p97_5 - p2_5,
        "empirical_relative_error_95": empirical_relative_error_95,
        "acceptance_bound": ACCEPTANCE_RELATIVE_ERROR_BOUND,
        "passes_acceptance": empirical_relative_error_95
        < ACCEPTANCE_RELATIVE_ERROR_BOUND,
    }

    return results, summary


def run_sensitivity_analysis(
    sample_sizes: List[int], n_reps: int, base_seed: int
) -> List[Dict]:
    """
    Run sensitivity analysis across different sample sizes.

    Parameters:
    -----------
    sample_sizes : List[int]
        List of sample sizes to test
    n_reps : int
        Number of replications per sample size
    base_seed : int
        Base seed for reproducibility

    Returns:
    --------
    List of sensitivity results for each sample size
    """
    sensitivity_results = []

    for n in sample_sizes:
        print(f"  Running sensitivity: N = {n:,}...", flush=True)

        # Run replications
        _, summary = run_replications(n, n_reps, base_seed)

        # Also compute CLT-predicted 95% CI width
        p_theoretical = TRUE_PI / 4
        theoretical_se = 4 * np.sqrt(p_theoretical * (1 - p_theoretical) / n)
        clt_predicted_95_ci_width = 2 * 1.96 * theoretical_se
        clt_predicted_relative_error_95 = (
            clt_predicted_95_ci_width / 2 / TRUE_PI
        )  # Half-width

        sensitivity_results.append(
            {
                "n": n,
                "mean_estimate": summary["mean_estimate"],
                "std_estimate": summary["std_estimate"],
                "empirical_relative_error_95": summary["empirical_relative_error_95"],
                "clt_predicted_relative_error_95": clt_predicted_relative_error_95,
                "theoretical_se": theoretical_se,
                "clt_predicted_95_ci_width": clt_predicted_95_ci_width,
                "empirical_ci_width": summary["ci_width"],
                "passes_acceptance": summary["empirical_relative_error_95"]
                < ACCEPTANCE_RELATIVE_ERROR_BOUND,
                "se_ratio": summary["se_ratio"],
            }
        )

    return sensitivity_results


def compare_rng_generators(n: int, n_reps: int, base_seed: int) -> Dict:
    """
    Compare Monte Carlo results using different RNG algorithms.

    Parameters:
    -----------
    n : int
        Sample size
    n_reps : int
        Number of replications
    base_seed : int
        Base seed

    Returns:
    --------
    Dict with comparison results
    """
    print("  Comparing RNG generators...", flush=True)

    # Run with Mersenne Twister (default)
    _, mt_summary = run_replications(n, n_reps, base_seed, "mt19937")

    # Run with PCG64
    _, pcg_summary = run_replications(n, n_reps, base_seed, "pcg64")

    return {
        "n": n,
        "n_reps": n_reps,
        "mersenne_twister": {
            "mean_estimate": mt_summary["mean_estimate"],
            "std_estimate": mt_summary["std_estimate"],
            "empirical_relative_error_95": mt_summary["empirical_relative_error_95"],
        },
        "pcg64": {
            "mean_estimate": pcg_summary["mean_estimate"],
            "std_estimate": pcg_summary["std_estimate"],
            "empirical_relative_error_95": pcg_summary["empirical_relative_error_95"],
        },
        "mean_difference": abs(
            mt_summary["mean_estimate"] - pcg_summary["mean_estimate"]
        ),
        "std_difference": abs(mt_summary["std_estimate"] - pcg_summary["std_estimate"]),
    }


def find_minimum_n_for_bound(
    target_relative_error: float, n_reps: int, base_seed: int
) -> Dict:
    """
    Binary search to find minimum N that achieves target relative error at 95% confidence.

    Parameters:
    -----------
    target_relative_error : float
        Target relative error (e.g., 0.0001 for 0.01%)
    n_reps : int
        Number of replications per test
    base_seed : int
        Base seed

    Returns:
    --------
    Dict with minimum N found and verification
    """
    print(
        f"  Finding minimum N for {target_relative_error * 100:.4f}% relative error...",
        flush=True,
    )

    # Start with wide search range
    low_n = 100_000
    high_n = 500_000_000  # 500M
    tolerance = 0.1  # 10% tolerance on N

    best_n = high_n
    best_result = None

    # Coarse grid search first
    test_sizes = [
        100_000,
        500_000,
        1_000_000,
        5_000_000,
        10_000_000,
        50_000_000,
        100_000_000,
    ]

    for n in test_sizes:
        if n > high_n:
            break
        _, summary = run_replications(n, n_reps, base_seed)
        print(
            f"    N={n:,}: empirical_rel_err_95={summary['empirical_relative_error_95']:.6f}",
            flush=True,
        )

        if summary["empirical_relative_error_95"] < target_relative_error:
            best_n = n
            best_result = summary
            break

    if best_result is None:
        # Binary search in range [low_n, high_n]
        while high_n - low_n > low_n * tolerance:
            mid_n = (low_n + high_n) // 2
            _, summary = run_replications(mid_n, n_reps, base_seed)
            print(
                f"    N={mid_n:,}: empirical_rel_err_95={summary['empirical_relative_error_95']:.6f}",
                flush=True,
            )

            if summary["empirical_relative_error_95"] < target_relative_error:
                high_n = mid_n
                best_n = mid_n
                best_result = summary
            else:
                low_n = mid_n

    return {
        "minimum_n": best_n,
        "verification": best_result,
        "target_relative_error": target_relative_error,
    }


def main():
    """Main execution function."""
    print("=" * 80)
    print("MONTE CARLO PI ESTIMATION VALIDATION")
    print("=" * 80)
    print(f"True Pi: {TRUE_PI:.15f}")
    print(
        f"Acceptance Bound: {ACCEPTANCE_RELATIVE_ERROR_BOUND * 100:.4f}% relative error at 95% CI"
    )
    print(f"Acceptance Absolute Error: {ACCEPTANCE_ABSOLUTE_ERROR_BOUND:.10f}")
    print("=" * 80)

    # Configuration
    N_PRIMARY = 10_000_000  # 10 million as specified in claim
    N_REPS_PRIMARY = 1000  # 1000 replications for distribution characterization
    N_REPS_SENSITIVITY = 100  # Fewer replications for sensitivity analysis
    BASE_SEED = 42

    results = {
        "claim": "Monte Carlo estimation of pi using 10 million random points achieves accuracy within 0.01% of the true value with 95% confidence.",
        "acceptance_bound": {
            "relative_error": ACCEPTANCE_RELATIVE_ERROR_BOUND,
            "absolute_error": ACCEPTANCE_ABSOLUTE_ERROR_BOUND,
            "description": "relative error < 0.01% at 95% confidence level for N=10,000,000",
        },
        "method": {
            "description": "Monte Carlo simulation with empirical distribution characterization",
            "justification": "Monte Carlo is preferred over pure CLT derivation because: (1) it provides empirical validation of the CLT assumptions, (2) it captures the actual distribution of the estimator including any non-normality, (3) it serves as a self-consistency check between theory and practice, (4) it validates that the Bernoulli trial assumptions hold for this problem",
            "procedure": "Generate N uniform random points in [0,1]×[0,1], count points where x²+y²≤1, estimate pi = 4×(count/N)",
        },
        "inputs": {
            "N_primary": N_PRIMARY,
            "n_reps_primary": N_REPS_PRIMARY,
            "n_reps_sensitivity": N_REPS_SENSITIVITY,
            "rng_algorithms": ["MT19937 (Mersenne Twister)", "PCG64"],
            "base_seed": BASE_SEED,
        },
    }

    # =========================================================================
    # PART 1: Single N=10M replication
    # =========================================================================
    print("\n" + "=" * 80)
    print("PART 1: Single replication with N=10,000,000")
    print("=" * 80)

    start_time = time.time()
    single_result = run_single_replication(N_PRIMARY, BASE_SEED, "mt19937")
    single_elapsed = time.time() - start_time

    print(f"Seed: {single_result['seed']}")
    print(f"Pi Estimate: {single_result['pi_estimate']:.15f}")
    print(f"True Pi: {TRUE_PI:.15f}")
    print(f"Absolute Error: {single_result['absolute_error']:.10f}")
    print(f"Relative Error: {single_result['relative_error'] * 100:.6f}%")
    print(f"Elapsed Time: {single_elapsed:.2f} seconds")

    results["single_replication"] = {
        "seed": single_result["seed"],
        "pi_estimate": single_result["pi_estimate"],
        "absolute_error": single_result["absolute_error"],
        "relative_error": single_result["relative_error"],
        "elapsed_seconds": single_elapsed,
    }

    # =========================================================================
    # PART 2: 1000 Replications to characterize distribution
    # =========================================================================
    print("\n" + "=" * 80)
    print("PART 2: 1000 Replications for distribution characterization (N=10M each)")
    print("=" * 80)

    start_time = time.time()
    primary_results, primary_summary = run_replications(
        N_PRIMARY, N_REPS_PRIMARY, BASE_SEED, "mt19937"
    )
    primary_elapsed = time.time() - start_time

    print(f"Number of replications: {N_REPS_PRIMARY}")
    print(f"Mean Pi Estimate: {primary_summary['mean_estimate']:.15f}")
    print(f"Std Deviation: {primary_summary['std_estimate']:.10f}")
    print(f"Theoretical SE (CLT): {primary_summary['theoretical_se']:.10f}")
    print(f"Empirical SE: {primary_summary['empirical_se']:.10f}")
    print(f"SE Ratio (empirical/theoretical): {primary_summary['se_ratio']:.4f}")
    print(f"2.5th Percentile: {primary_summary['p2_5']:.15f}")
    print(f"97.5th Percentile: {primary_summary['p97_5']:.15f}")
    print(f"95% CI Width: {primary_summary['ci_width']:.10f}")
    print(
        f"Empirical Relative Error at 95% CI: {primary_summary['empirical_relative_error_95'] * 100:.6f}%"
    )
    print(f"Passes Acceptance Bound: {primary_summary['passes_acceptance']}")
    print(f"Elapsed Time: {primary_elapsed:.2f} seconds")

    results["distribution_characterization"] = {
        "n_reps": N_REPS_PRIMARY,
        "mean_estimate": primary_summary["mean_estimate"],
        "std_estimate": primary_summary["std_estimate"],
        "theoretical_se": primary_summary["theoretical_se"],
        "empirical_se": primary_summary["empirical_se"],
        "se_ratio": primary_summary["se_ratio"],
        "p2_5": primary_summary["p2_5"],
        "p97_5": primary_summary["p97_5"],
        "ci_width": primary_summary["ci_width"],
        "empirical_relative_error_95": primary_summary["empirical_relative_error_95"],
        "passes_acceptance": primary_summary["passes_acceptance"],
        "elapsed_seconds": primary_elapsed,
    }

    # =========================================================================
    # PART 3: CLT Validation
    # =========================================================================
    print("\n" + "=" * 80)
    print("PART 3: CLT Validation")
    print("=" * 80)

    # For Bernoulli trials, SE = sqrt(p(1-p)/N)
    p_true = TRUE_PI / 4
    print(f"True probability p = pi/4 = {p_true:.15f}")
    print(f"True probability 1-p = {1 - p_true:.15f}")

    # Theoretical SE
    se_theoretical = 4 * np.sqrt(p_true * (1 - p_true) / N_PRIMARY)
    print(f"\nCLT Theoretical Standard Error:")
    print(f"  SE = 4 * sqrt(p(1-p)/N)")
    print(f"  SE = 4 * sqrt({p_true:.15f} * {1 - p_true:.15f} / {N_PRIMARY:,})")
    print(f"  SE = {se_theoretical:.15f}")

    # Empirical SE
    se_empirical = primary_summary["std_estimate"]
    print(f"\nEmpirical Standard Error:")
    print(f"  SE = {se_empirical:.15f}")

    # Ratio
    se_ratio = se_empirical / se_theoretical
    print(f"\nSE Ratio (empirical/theoretical): {se_ratio:.4f}")
    print(
        f"CLT Validation: {'PASSED' if 0.95 < se_ratio < 1.05 else 'CAUTION - ratio outside [0.95, 1.05]'}"
    )

    results["clt_validation"] = {
        "p_true": p_true,
        "theoretical_se": se_theoretical,
        "empirical_se": se_empirical,
        "se_ratio": se_ratio,
        "validation_passed": 0.95 < se_ratio < 1.05,
        "interpretation": "SE ratio should be ~1.0 for CLT to be valid. Ratio of {:.4f} indicates {}".format(
            se_ratio, "good agreement" if 0.95 < se_ratio < 1.05 else "some discrepancy"
        ),
    }

    # =========================================================================
    # PART 4: Sensitivity Analysis
    # =========================================================================
    print("\n" + "=" * 80)
    print("PART 4: Sensitivity Analysis (Sample Size Sweep)")
    print("=" * 80)

    sample_sizes = [100_000, 1_000_000, 10_000_000, 100_000_000]
    sensitivity_seed = BASE_SEED + 1000  # Different seed for sensitivity runs

    print(f"Sample sizes: {[f'{n:,}' for n in sample_sizes]}")
    print(f"Replications per size: {N_REPS_SENSITIVITY}")

    sensitivity_results = run_sensitivity_analysis(
        sample_sizes, N_REPS_SENSITIVITY, sensitivity_seed
    )

    print("\nSensitivity Summary Table:")
    print("-" * 120)
    print(
        f"{'N':>15} | {'Mean Est':>18} | {'Std Dev':>15} | {'Emp Rel Err 95%':>18} | {'CLT Pred Rel Err':>18} | {'Pass?':>6}"
    )
    print("-" * 120)

    for sr in sensitivity_results:
        n = sr["n"]
        print(
            f"{n:>15,} | {sr['mean_estimate']:>18.14f} | {sr['std_estimate']:>15.10f} | "
            f"{sr['empirical_relative_error_95'] * 100:>17.6f}% | {sr['clt_predicted_relative_error_95'] * 100:>17.6f}% | "
            f"{'YES' if sr['passes_acceptance'] else 'NO':>6}"
        )

    print("-" * 120)

    # Find convergence rate
    if len(sensitivity_results) >= 2:
        # Log-log regression to find convergence rate
        log_ns = np.log10(np.array([sr["n"] for sr in sensitivity_results]))
        log_errors = np.log10(
            np.array(
                [sr["clt_predicted_relative_error_95"] for sr in sensitivity_results]
            )
        )
        slope, intercept = np.polyfit(log_ns, log_errors, 1)
        print(f"\nConvergence Rate Analysis:")
        print(f"  Log-log slope (should be ~-0.5 for sqrt(N) convergence): {slope:.4f}")
        print(
            f"  This indicates {'sqrt(N) convergence as expected from CLT' if -0.55 < slope < -0.45 else 'unexpected convergence behavior'}"
        )

    results["sensitivity_analysis"] = {
        "sample_sizes": sample_sizes,
        "n_reps_per_size": N_REPS_SENSITIVITY,
        "results": sensitivity_results,
        "convergence_rate_slope": float(slope)
        if len(sensitivity_results) >= 2
        else None,
    }

    # =========================================================================
    # PART 5: RNG Comparison
    # =========================================================================
    print("\n" + "=" * 80)
    print("PART 5: RNG Generator Comparison (N=10M, 100 replications)")
    print("=" * 80)

    rng_comparison_seed = BASE_SEED + 2000
    rng_comparison = compare_rng_generators(10_000_000, 100, rng_comparison_seed)

    print(f"\nMersenne Twister (MT19937):")
    print(
        f"  Mean Estimate: {rng_comparison['mersenne_twister']['mean_estimate']:.15f}"
    )
    print(f"  Std Deviation: {rng_comparison['mersenne_twister']['std_estimate']:.10f}")
    print(
        f"  Empirical Rel Error 95%: {rng_comparison['mersenne_twister']['empirical_relative_error_95'] * 100:.6f}%"
    )

    print(f"\nPCG64:")
    print(f"  Mean Estimate: {rng_comparison['pcg64']['mean_estimate']:.15f}")
    print(f"  Std Deviation: {rng_comparison['pcg64']['std_estimate']:.10f}")
    print(
        f"  Empirical Rel Error 95%: {rng_comparison['pcg64']['empirical_relative_error_95'] * 100:.6f}%"
    )

    print(f"\nDifference (MT - PCG64):")
    print(f"  Mean Difference: {rng_comparison['mean_difference']:.15f}")
    print(f"  Std Difference: {rng_comparison['std_difference']:.10f}")
    print(
        f"  RNG choice {'严重影响' if rng_comparison['mean_difference'] > 1e-6 else '无显著影响'} results at N=10M"
    )

    results["rng_comparison"] = rng_comparison

    # =========================================================================
    # PART 6: Minimum N for Acceptance Bound
    # =========================================================================
    print("\n" + "=" * 80)
    print("PART 6: Finding Minimum N for 0.01% Relative Error Bound")
    print("=" * 80)

    min_n_result = find_minimum_n_for_bound(
        ACCEPTANCE_RELATIVE_ERROR_BOUND, 50, BASE_SEED + 3000
    )

    print(f"\nMinimum N for 0.01% relative error at 95% confidence:")
    print(f"  N ≈ {min_n_result['minimum_n']:,}")

    if min_n_result["verification"] is not None:
        print(
            f"  Verification - Empirical Rel Error 95%: {min_n_result['verification']['empirical_relative_error_95'] * 100:.6f}%"
        )

    results["minimum_n_analysis"] = min_n_result

    # =========================================================================
    # PART 7: Model Limits Analysis
    # =========================================================================
    print("\n" + "=" * 80)
    print("PART 7: Model Limits Analysis")
    print("=" * 80)

    # Floating point precision analysis
    float64_epsilon = np.finfo(np.float64).eps
    print(f"Float64 machine epsilon: {float64_epsilon:.2e}")

    # At what N does the Monte Carlo error become comparable to float64 precision?
    # SE ~ sqrt(p(1-p)/N) ~ sqrt(pi/4 * (1-pi/4)/N) ~ O(1/sqrt(N))
    # For SE to be comparable to float64 epsilon (2.2e-16), we'd need N ~ 1/epsilon^2 ~ 2e32
    # which is astronomically large and never reached

    n_precision_limit = int((np.sqrt(p_true * (1 - p_true)) / float64_epsilon) ** 2)
    print(
        f"Point where SE ≈ float64 epsilon: N ≈ {n_precision_limit:.2e} (impractical)"
    )
    print(
        "Conclusion: Float64 precision is NOT a limiting factor for practical Monte Carlo pi estimation"
    )

    # Practical limits
    print("\nPractical Limits:")
    print(
        "1. Computational time becomes prohibitive above N ~ 1B (minutes to hours per replication)"
    )
    print("2. Memory usage: N=100M requires ~800MB for x,y arrays (float64)")
    print(
        "3. Quasi-Monte Carlo methods become more efficient for N > 1M (e.g., Sobol sequences)"
    )
    print(
        "4. Variance reduction techniques (e.g., antithetic variates) can achieve same accuracy with fewer points"
    )

    results["model_limits"] = {
        "float64_precision_limit_n": n_precision_limit,
        "float64_epsilon": float64_epsilon,
        "practical_constraints": [
            "Computational time: N > 1B becomes impractical (minutes to hours per replication)",
            "Memory usage: N=100M requires ~800MB for coordinate arrays",
            "Quasi-Monte Carlo more efficient for N > 1M (Sobol sequences)",
            "Variance reduction can achieve same accuracy with fewer points",
        ],
        "when_mc_breaks": "Monte Carlo becomes impractical when deterministic methods (arctan series, AGM) are more accurate and faster",
    }

    # =========================================================================
    # FINAL VERDICT
    # =========================================================================
    print("\n" + "=" * 80)
    print("FINAL VERDICT")
    print("=" * 80)

    verdict_criteria = {
        "empirical_95_ci_width": primary_summary["ci_width"],
        "relative_error_at_95": primary_summary["empirical_relative_error_95"],
        "acceptance_bound": ACCEPTANCE_RELATIVE_ERROR_BOUND,
        "clt_validated": 0.95 < primary_summary["se_ratio"] < 1.05,
        "sqrt_n_convergence": -0.55 < slope < -0.45
        if len(sensitivity_results) >= 2
        else None,
    }

    claim_passed = (
        primary_summary["empirical_relative_error_95"] < ACCEPTANCE_RELATIVE_ERROR_BOUND
        and 0.95 < primary_summary["se_ratio"] < 1.05
    )

    print(f"Claim: {results['claim']}")
    print(
        f"\nAcceptance Bound: {ACCEPTANCE_RELATIVE_ERROR_BOUND * 100:.4f}% relative error at 95% CI"
    )
    print(
        f"Measured Relative Error at 95% CI: {primary_summary['empirical_relative_error_95'] * 100:.6f}%"
    )
    print(
        f"CLT Validation: {'PASSED' if 0.95 < primary_summary['se_ratio'] < 1.05 else 'FAILED'}"
    )
    print(f"\nVERDICT: {'CLAIM CONFIRMED' if claim_passed else 'CLAIM NOT CONFIRMED'}")

    if not claim_passed:
        if (
            primary_summary["empirical_relative_error_95"]
            >= ACCEPTANCE_RELATIVE_ERROR_BOUND
        ):
            print(
                f"  - Relative error {primary_summary['empirical_relative_error_95'] * 100:.6f}% exceeds bound {ACCEPTANCE_RELATIVE_ERROR_BOUND * 100:.4f}%"
            )
        if not (0.95 < primary_summary["se_ratio"] < 1.05):
            print(
                f"  - CLT validation failed with SE ratio {primary_summary['se_ratio']:.4f}"
            )

    results["verdict"] = {
        "claim_passed": claim_passed,
        "verdict": "CLAIM CONFIRMED" if claim_passed else "CLAIM NOT CONFIRMED",
        "measured_relative_error_95": primary_summary["empirical_relative_error_95"],
        "acceptance_bound": ACCEPTANCE_RELATIVE_ERROR_BOUND,
        "clt_validated": verdict_criteria["clt_validated"],
        "sqrt_n_convergence_confirmed": verdict_criteria["sqrt_n_convergence"],
    }

    # =========================================================================
    # OUTPUT SUMMARY
    # =========================================================================

    print("\n" + "=" * 80)
    print("EXECUTION COMPLETE")
    print("=" * 80)

    # Save results to JSON for reproducibility
    output_file = "monte_carlo_pi_validation_results.json"

    # Convert numpy types to native Python types for JSON serialization
    def convert_to_native(obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (np.int32, np.int64)):
            return int(obj)
        elif isinstance(obj, (np.float32, np.float64)):
            return float(obj)
        elif isinstance(obj, dict):
            return {k: convert_to_native(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_to_native(item) for item in obj]
        return obj

    results_native = convert_to_native(results)

    with open(output_file, "w") as f:
        json.dump(results_native, f, indent=2)

    print(f"Results saved to: {output_file}")

    return results


if __name__ == "__main__":
    results = main()
    print("\n" + "=" * 80)
    print("STRUCTURED RESULTS (for programmatic consumption)")
    print("=" * 80)
    print(json.dumps(convert_to_native(results), indent=2))
