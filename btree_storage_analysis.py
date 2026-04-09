#!/usr/bin/env python3
"""
B-tree Storage Requirement Calculator
======================================
Closed-form calculation of disk space for B-tree storage.

Assumes: PostgreSQL-style B-tree (LEAF = true variant)
- Leaf pages store actual tuples (key + value inline)
- Internal pages store (key, child_pointer) pairs
- Page header: 24 bytes (PostgreSQL convention)
- Special space for LP (line pointer) array in leaf pages
"""

import math
from typing import NamedTuple

# =============================================================================
# INPUT PARAMETERS (BASE CASE FROM CLAIM)
# =============================================================================


class BTreeParams(NamedTuple):
    record_count: int  # Number of records: 100,000,000
    record_size: int  # Record size in bytes: 1024 (1KB)
    page_size: int  # Page size in bytes: 4096 (4KB)
    fill_factor: float  # Fill factor as fraction: 0.50
    key_size: int  # Key size in bytes: 8 (int64)
    pointer_size: int  # Child/page pointer size in bytes: 6 (PostgreSQL page pointer)
    page_header_overhead: int  # Page header size in bytes: 24
    leaf_special_overhead: int  # Extra overhead per leaf page (LP array, etc.): 8

    def __repr__(self):
        return (
            f"BTreeParams(record_count={self.record_count:,}, "
            f"record_size={self.record_size}, page_size={self.page_size}, "
            f"fill_factor={self.fill_factor})"
        )


# =============================================================================
# CORE CALCULATIONS
# =============================================================================


def compute_leaf_entries_per_page(params: BTreeParams) -> int:
    """
    For a leaf page, compute how many records fit.

    Usable space = page_size - page_header_overhead - leaf_special_overhead
    At fill_factor, usable space is multiplied by fill_factor
    Each record needs: record_size bytes

    Returns max number of records per leaf page (floor).
    """
    usable = (
        params.page_size - params.page_header_overhead - params.leaf_special_overhead
    )
    usable_at_fill = int(usable * params.fill_factor)
    entries = usable_at_fill // params.record_size
    return max(1, entries)  # At least 1 entry per page


def compute_internal_entries_per_page(params: BTreeParams) -> int:
    """
    For an internal page, compute how many (key, child_pointer) pairs fit.

    Each entry: key_size + pointer_size
    No fill factor for internal pages (they use what they need, limited by page space)
    Note: Some B-tree variants use fill factor for internal pages too, but typically
    internal pages are kept more full to reduce tree height.

    Returns max number of entries per internal page (floor).
    """
    usable = params.page_size - params.page_header_overhead
    entry_size = params.key_size + params.pointer_size
    entries = usable // entry_size
    return max(2, entries)  # At least 2 entries (for proper B-tree structure)


def compute_leaf_page_count(params: BTreeParams) -> int:
    """Compute number of leaf pages needed."""
    entries_per_leaf = compute_leaf_entries_per_page(params)
    return math.ceil(params.record_count / entries_per_leaf)


def compute_tree_height(params: BTreeParams, leaf_pages: int) -> tuple[int, list[int]]:
    """
    Compute B-tree height and page counts per level.

    Returns (height, page_counts_per_level) where page_counts_per_level[0] = leaf pages
    Height = number of levels - 1 (height 0 = single leaf page tree)
    """
    entries_per_internal = compute_internal_entries_per_page(params)

    page_counts = [leaf_pages]
    current_level_pages = leaf_pages

    while current_level_pages > 1:
        current_level_pages = math.ceil(current_level_pages / entries_per_internal)
        page_counts.append(current_level_pages)

    height = len(page_counts) - 1
    return height, page_counts


def compute_internal_page_count(
    params: BTreeParams, page_counts_per_level: list[int]
) -> int:
    """Sum all non-leaf pages."""
    # page_counts includes leaf pages at index 0, root at last index
    return sum(page_counts_per_level[1:])


def compute_total_space(params: BTreeParams) -> dict:
    """
    Compute complete storage breakdown.

    Returns dict with:
    - leaf_pages, internal_pages, total_pages
    - leaf_bytes, internal_bytes, metadata_bytes, total_bytes
    - total_gb (raw), total_gb_with_10pct_overhead
    """
    leaf_pages = compute_leaf_page_count(params)
    height, page_counts = compute_tree_height(params, leaf_pages)
    internal_pages = compute_internal_page_count(params, page_counts)

    total_pages = leaf_pages + internal_pages

    leaf_bytes = leaf_pages * params.page_size
    internal_bytes = internal_pages * params.page_size

    # Additional overhead: free space map (1 byte per page typically), metadata pages
    # Estimate ~1% for visibility map, free space map, and metadata
    metadata_bytes = int(total_pages * params.page_size * 0.01)

    total_bytes = leaf_bytes + internal_bytes + metadata_bytes
    total_gb_raw = total_bytes / (1024**3)
    total_gb_with_overhead = (
        total_bytes * 1.10 / (1024**3)
    )  # 10% for WAL, fragmentation

    return {
        "params": params,
        "height": height,
        "leaf_pages": leaf_pages,
        "internal_pages": internal_pages,
        "total_pages": total_pages,
        "leaf_bytes": leaf_bytes,
        "internal_bytes": internal_bytes,
        "metadata_bytes": metadata_bytes,
        "total_bytes": total_bytes,
        "total_gb_raw": total_gb_raw,
        "total_gb_with_overhead": total_gb_with_overhead,
        "entries_per_leaf": compute_leaf_entries_per_page(params),
        "entries_per_internal": compute_internal_entries_per_page(params),
        "page_counts_per_level": page_counts,
    }


def print_storage_breakdown(result: dict):
    """Pretty-print storage breakdown."""
    p = result["params"]
    print("=" * 70)
    print("B-TREE STORAGE CALCULATION")
    print("=" * 70)
    print(f"\nInput Parameters:")
    print(f"  Record count:        {p.record_count:,} records")
    print(
        f"  Record size:         {p.record_size} bytes ({p.record_size / 1024:.1f}KB)"
    )
    print(f"  Page size:           {p.page_size} bytes ({p.page_size / 1024:.1f}KB)")
    print(f"  Fill factor:         {p.fill_factor * 100:.0f}%")
    print(f"  Key size:            {p.key_size} bytes")
    print(f"  Pointer size:        {p.pointer_size} bytes")
    print(f"  Page header overhead: {p.page_header_overhead} bytes")

    print(f"\nB-tree Structure:")
    print(f"  Entries per leaf page:     {result['entries_per_leaf']}")
    print(f"  Entries per internal page: {result['entries_per_internal']}")
    print(f"  Tree height:               {result['height']} (including leaf level)")
    print(f"  Pages per level:           {result['page_counts_per_level']}")

    print(f"\nStorage Breakdown:")
    print(f"  Leaf pages:        {result['leaf_pages']:>15,}")
    print(f"  Internal pages:    {result['internal_pages']:>15,}")
    print(f"  Total pages:       {result['total_pages']:>15,}")
    print(f"  Leaf storage:       {result['leaf_bytes'] / (1024**3):>12.2f} GB")
    print(f"  Internal storage:  {result['internal_bytes'] / (1024**3):>12.2f} GB")
    print(f"  Metadata overhead:  {result['metadata_bytes'] / (1024**3):>12.2f} GB")
    print(f"  Total (raw):       {result['total_gb_raw']:>12.2f} GB")
    print(f"  Total (+10% ovhd): {result['total_gb_with_overhead']:>12.2f} GB")
    print("=" * 70)


# =============================================================================
# SENSITIVITY ANALYSIS
# =============================================================================


def sensitivity_fill_factor(base_params: BTreeParams) -> list[dict]:
    """Sweep fill factor from 40% to 80% in 10% increments."""
    results = []
    for ff in [0.40, 0.50, 0.60, 0.70, 0.80]:
        params = base_params._replace(fill_factor=ff)
        r = compute_total_space(params)
        r["fill_factor"] = ff
        r["leaf_entries"] = compute_leaf_entries_per_page(params)
        results.append(r)
    return results


def sensitivity_record_size(base_params: BTreeParams) -> list[dict]:
    """Sweep record size: 512B, 1KB, 2KB."""
    results = []
    for rs in [512, 1024, 2048]:
        params = base_params._replace(record_size=rs)
        r = compute_total_space(params)
        r["record_size"] = rs
        results.append(r)
    return results


def sensitivity_page_size(base_params: BTreeParams) -> list[dict]:
    """Sweep page size: 4KB, 8KB, 16KB."""
    results = []
    for ps in [4096, 8192, 16384]:
        params = base_params._replace(page_size=ps)
        r = compute_total_space(params)
        r["page_size"] = ps
        results.append(r)
    return results


def cross_sensitivity_matrix(base_params: BTreeParams):
    """
    Cross-sensitivity: fill_factor x record_size x page_size
    Returns a 3D matrix of total_gb_raw.
    """
    fill_factors = [0.40, 0.50, 0.60, 0.70, 0.80]
    record_sizes = [512, 1024, 2048]
    page_sizes = [4096, 8192, 16384]

    matrix = {}
    for ff in fill_factors:
        matrix[ff] = {}
        for rs in record_sizes:
            matrix[ff][rs] = {}
            for ps in page_sizes:
                params = base_params._replace(
                    fill_factor=ff, record_size=rs, page_size=ps
                )
                r = compute_total_space(params)
                matrix[ff][rs][ps] = r["total_gb_raw"]

    return matrix


def print_sensitivity_table(results: list[dict], label: str, value_key: str):
    """Print a sensitivity sweep table."""
    print(f"\n{label}")
    print("-" * 70)
    print(
        f"{'Value':<15} {'Leaf Pgs':<15} {'Intl Pgs':<12} {'Total Pgs':<15} {'GB':<10}"
    )
    print("-" * 70)
    for r in results:
        val = r.get(value_key, r["params"].fill_factor)
        if value_key == "fill_factor":
            val_str = f"{val * 100:.0f}%"
        elif value_key == "record_size":
            val_str = f"{val}B"
        elif value_key == "page_size":
            val_str = f"{val}KB"
        else:
            val_str = str(val)
        print(
            f"{val_str:<15} {r['leaf_pages']:<15,} {r['internal_pages']:<12,} {r['total_pages']:<15,} {r['total_gb_raw']:<10.2f}"
        )
    print("-" * 70)


def print_cross_sensitivity_matrix(matrix):
    """Print the 3D cross-sensitivity matrix in readable format."""
    print("\n" + "=" * 100)
    print("CROSS-SENSITIVITY MATRIX: Total Disk Space (GB)")
    print("Rows: Fill Factor | Columns: Record Size | Depth: Page Size")
    print("=" * 100)

    for ff in sorted(matrix.keys()):
        print(f"\nFill Factor = {ff * 100:.0f}%")
        print("-" * 80)
        header = f"{'Rec Size':<12}"
        for ps in sorted(matrix[ff][list(matrix[ff].keys())[0]].keys()):
            header += f"{ps // 1024}KB Page"
        print(header)
        print("-" * 80)

        for rs in sorted(matrix[ff].keys()):
            row = f"{rs}B".ljust(12)
            for ps in sorted(matrix[ff][rs].keys()):
                gb = matrix[ff][rs][ps]
                # Highlight if outside 160-240GB bound
                if gb < 160:
                    marker = "*"
                elif gb > 240:
                    marker = "*"
                else:
                    marker = ""
                row += f"{gb:>10.1f}{marker}  "
            print(row)

    print("\n* indicates values OUTSIDE 160-240GB acceptance bound")


# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == "__main__":
    # Base parameters from the claim
    base_params = BTreeParams(
        record_count=100_000_000,
        record_size=1024,  # 1KB records
        page_size=4096,  # 4KB pages
        fill_factor=0.50,  # 50% fill
        key_size=8,  # 8-byte integer keys
        pointer_size=6,  # PostgreSQL page pointer (6 bytes)
        page_header_overhead=24,  # PostgreSQL page header
        leaf_special_overhead=8,  # LP array overhead per leaf
    )

    print("\n" + "=" * 70)
    print("CLAIM UNDER TEST")
    print("=" * 70)
    print("'Storing 100 million 1KB records in a B-tree with 4KB pages and")
    print("50% fill factor requires approximately 200GB of disk space.'")
    print("\nACCEPTANCE BOUND: 160GB to 240GB (160 <= computed <= 240)")
    print("=" * 70)

    # Compute base case
    result = compute_total_space(base_params)
    print_storage_breakdown(result)

    # Check against acceptance bound
    print("\nACCEPTANCE BOUND CHECK:")
    in_bound = 160 <= result["total_gb_raw"] <= 240
    print(f"  Computed: {result['total_gb_raw']:.2f} GB")
    print(f"  Bound:    160.00 GB <= x <= 240.00 GB")
    print(f"  Status:   {'WITHIN BOUND' if in_bound else 'OUTSIDE BOUND'}")

    # Sensitivity: Fill Factor
    print_sensitivity_table(
        sensitivity_fill_factor(base_params),
        "SENSITIVITY: Fill Factor (40%-80%)",
        "fill_factor",
    )

    # Sensitivity: Record Size
    print_sensitivity_table(
        sensitivity_record_size(base_params),
        "SENSITIVITY: Record Size (512B, 1KB, 2KB)",
        "record_size",
    )

    # Sensitivity: Page Size
    print_sensitivity_table(
        sensitivity_page_size(base_params),
        "SENSITIVITY: Page Size (4KB, 8KB, 16KB)",
        "page_size",
    )

    # Cross-sensitivity matrix
    matrix = cross_sensitivity_matrix(base_params)
    print_cross_sensitivity_matrix(matrix)

    # Detailed reproducibility log
    print("\n" + "=" * 70)
    print("REPRODUCIBILITY LOG: Complete Arithmetic")
    print("=" * 70)

    p = base_params
    print(f"\n--- LEAF NODE CALCULATION ---")
    usable_leaf = p.page_size - p.page_header_overhead - p.leaf_special_overhead
    print(
        f"Usable space per leaf: {p.page_size} - {p.page_header_overhead} - {p.leaf_special_overhead} = {usable_leaf} bytes"
    )
    usable_at_fill = usable_leaf * p.fill_factor
    print(
        f"At {p.fill_factor * 100:.0f}% fill: {usable_leaf} * {p.fill_factor} = {usable_at_fill} bytes"
    )
    leaf_entries = usable_at_fill // p.record_size
    print(
        f"Records per leaf: floor({usable_at_fill} / {p.record_size}) = {leaf_entries}"
    )
    leaf_pages = math.ceil(p.record_count / leaf_entries)
    print(
        f"Leaf pages needed: ceil({p.record_count:,} / {leaf_entries}) = {leaf_pages:,}"
    )

    print(f"\n--- INTERNAL NODE CALCULATION ---")
    usable_internal = p.page_size - p.page_header_overhead
    print(
        f"Usable space per internal: {p.page_size} - {p.page_header_overhead} = {usable_internal} bytes"
    )
    internal_entry_size = p.key_size + p.pointer_size
    print(
        f"Entry size (key+ptr): {p.key_size} + {p.pointer_size} = {internal_entry_size} bytes"
    )
    internal_entries = usable_internal // internal_entry_size
    print(
        f"Entries per internal: floor({usable_internal} / {internal_entry_size}) = {internal_entries}"
    )
    print(f"Fanout: {internal_entries + 1}")  # entries+1 children

    print(f"\n--- TREE HEIGHT CALCULATION ---")
    height, levels = compute_tree_height(p, leaf_pages)
    print(f"Leaf pages: {leaf_pages:,}")
    print(f"Pages at each level (bottom-up): {levels}")
    print(f"Tree height: {height}")

    internal_pages = sum(levels[1:]) if len(levels) > 1 else 0
    print(f"Total internal pages: {internal_pages:,}")

    print(f"\n--- STORAGE TOTALS ---")
    leaf_gb = leaf_pages * p.page_size / (1024**3)
    internal_gb = internal_pages * p.page_size / (1024**3)
    total_pages = leaf_pages + internal_pages
    total_gb = (total_pages * p.page_size) / (1024**3)
    print(f"Leaf storage: {leaf_pages:,} * {p.page_size} bytes = {leaf_gb:.4f} GB")
    print(
        f"Internal storage: {internal_pages:,} * {p.page_size} bytes = {internal_gb:.4f} GB"
    )
    print(f"Total pages: {total_pages:,}")
    print(f"Total raw storage: {total_pages:,} * {p.page_size} = {total_gb:.4f} GB")

    print(f"\n--- FILL FACTOR SWEEP DETAILS ---")
    print(
        f"{'FF':<6} {'Rec/Leaf':<10} {'Leaf Pgs':<15} {'Intl Pgs':<12} {'Total GB':<10} {'In Bound?'}"
    )
    print("-" * 70)
    for ff in [0.40, 0.50, 0.60, 0.70, 0.80]:
        params = base_params._replace(fill_factor=ff)
        usable_at_ff = (
            params.page_size
            - params.page_header_overhead
            - params.leaf_special_overhead
        ) * ff
        rec_per_leaf = int(usable_at_ff) // params.record_size
        leaf_pgs = math.ceil(params.record_count / rec_per_leaf)
        _, lvl = compute_tree_height(params, leaf_pgs)
        intl_pgs = sum(lvl[1:]) if len(lvl) > 1 else 0
        total_pgs = leaf_pgs + intl_pgs
        total_gb = total_pgs * params.page_size / (1024**3)
        in_bound = "YES" if 160 <= total_gb <= 240 else "NO"
        print(
            f"{ff * 100:.0f}%   {rec_per_leaf:<10} {leaf_pgs:<15,} {intl_pgs:<12,} {total_gb:<10.2f} {in_bound}"
        )

    print("\n" + "=" * 70)
    print("MODEL LIMITS")
    print("=" * 70)
    print("""
1. COMPRESSION: This model assumes no compression. PostgreSQL's TOAST can 
   compress data, reducing actual disk usage by 2-10x for compressible data.
   
2. MVCC OVERHEAD: PostgreSQL uses MVCC - each update creates a new tuple version.
   With typical 3-5 versions per row, storage can increase 3-5x.
   
3. FRAGMENTATION: B-tree pages fragment over time with updates/deletes.
   fill_factor targets fragmentation but doesn't eliminate it.
   
4. WAL SPACE: Write-Ahead Log typically 20-30% of data size for recovery.
   This is NOT included in the B-tree page count.
   
5. INDEX OVERHEAD: Secondary indexes (not modeled) multiply storage.
   This only models a single primary B-tree index.
   
6. FREE SPACE MAP: PostgreSQL's FSM adds ~1 byte per page + metadata.
   
7. TEMPORARY SORT SPACE: Large sorts spill to disk outside the table.
""")

    print("\n" + "=" * 70)
    print("FINAL VERDICT")
    print("=" * 70)
    computed_gb = result["total_gb_raw"]
    print(f"Claimed: ~200GB | Acceptance bound: [160GB, 240GB]")
    print(f"Computed: {computed_gb:.2f} GB")
    print(
        f"Deviation from 200GB: {abs(computed_gb - 200):.2f} GB ({(abs(computed_gb - 200) / 200) * 100:.1f}%)"
    )

    if 160 <= computed_gb <= 240:
        print(f"\n*** VERDICT: CLAIM CONFIRMED ***")
        print(f"Computed disk space ({computed_gb:.2f} GB) falls WITHIN the")
        print(f"acceptance bound of 160GB to 240GB.")
    else:
        print(f"\n*** VERDICT: CLAIM REJECTED ***")
        print(f"Computed disk space ({computed_gb:.2f} GB) falls OUTSIDE the")
        print(f"acceptance bound of 160GB to 240GB.")
