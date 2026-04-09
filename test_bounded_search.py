#!/usr/bin/env python3
"""
Behavioral test script for bounded_search wrapper.
Tests all attack vectors from the dispatch brief.

Run from workspace root: python3 test_bounded_search.py
"""

import os
import sys
import tempfile
import shutil

# Add the module path
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "autoresearch", "harness", "tools")
)

from bounded_search import BoundedSearch, BoundaryRejection


def test_direct_out_of_boundary():
    """Test (a): Direct out-of-boundary path"""
    print("\n=== TEST (a): Direct out-of-boundary path ===")

    with tempfile.TemporaryDirectory() as allowed_dir:
        bs = BoundedSearch(allowed_dir)

        # Attempt to search an out-of-boundary path
        result = bs.glob("*.py", path="/home/user/other_project/secret.py")

        assert isinstance(result, BoundaryRejection), (
            f"Expected BoundaryRejection, got {type(result)}"
        )
        assert "not within boundary" in result.reason.lower(), (
            f"Unexpected reason: {result.reason}"
        )
        print(f"  PASS: Direct out-of-boundary rejected")
        print(f"    Attempted: /home/user/other_project/secret.py")
        print(f"    Canonical attempted: {result.canonical_attempted_path}")
        print(f"    Boundary: {result.canonical_boundary}")


def test_relative_path_traversal():
    """Test (b): Relative path traversal (../)"""
    print("\n=== TEST (b): Relative path traversal ===")

    with tempfile.TemporaryDirectory() as allowed_dir:
        bs = BoundedSearch(allowed_dir)

        # Attempt path traversal: allowed_dir/../../etc/passwd
        traversal_path = os.path.join(allowed_dir, "..", "..", "etc", "passwd")
        result = bs.glob("*.py", path=traversal_path)

        assert isinstance(result, BoundaryRejection), (
            f"Expected BoundaryRejection, got {type(result)}"
        )
        print(f"  PASS: Path traversal rejected")
        print(f"    Attempted: {traversal_path}")
        print(f"    Canonical attempted: {result.canonical_attempted_path}")
        print(f"    Boundary: {result.canonical_boundary}")

        # Also test the actual search pattern with traversal
        traversal_search = os.path.join(allowed_dir, "subdir", "..", "..", "..", "etc")
        result2 = bs.grep("password", path=traversal_search)
        assert isinstance(result2, BoundaryRejection), (
            f"Expected BoundaryRejection for grep, got {type(result2)}"
        )
        print(f"  PASS: Grep path traversal rejected")


def test_symlink_traversal():
    """Test (c): Symlink traversal attack"""
    print("\n=== TEST (c): Symlink traversal ===")

    with tempfile.TemporaryDirectory() as allowed_dir:
        # Create a symlink inside allowed_dir that points to /
        symlink_path = os.path.join(allowed_dir, "symlink_to_root")
        try:
            os.symlink("/", symlink_path)
        except OSError as e:
            print(
                f"  SKIP: Cannot create symlink (permission denied or platform issue): {e}"
            )
            return

        bs = BoundedSearch(allowed_dir)

        # Attempt to access /etc/passwd via symlink: allowed_dir/symlink_to_root/etc/passwd
        attack_path = os.path.join(allowed_dir, "symlink_to_root", "etc", "passwd")

        # First verify the symlink was created and resolves correctly
        canonical_attack = os.path.realpath(attack_path)
        print(f"    Symlink attack path: {attack_path}")
        print(f"    Resolves to: {canonical_attack}")

        result = bs.glob("*", path=attack_path)

        assert isinstance(result, BoundaryRejection), (
            f"Expected BoundaryRejection, got {type(result)}"
        )
        print(f"  PASS: Symlink traversal rejected")
        print(f"    Attempted: {attack_path}")
        print(f"    Canonical attempted: {result.canonical_attempted_path}")
        print(f"    Boundary: {result.canonical_boundary}")


def test_null_byte_injection():
    """Test (e): Null byte injection (bonus)"""
    print("\n=== TEST (e): Null byte injection (bonus) ===")

    with tempfile.TemporaryDirectory() as allowed_dir:
        bs = BoundedSearch(allowed_dir)

        # Attempt null byte injection
        null_byte_path = allowed_dir + "\0malicious"
        result = bs.glob("*.py", path=null_byte_path)

        # Python's os.path.realpath handles null bytes by returning empty or raising
        # Our implementation should reject this
        assert isinstance(result, BoundaryRejection), (
            f"Expected BoundaryRejection, got {type(result)}"
        )
        print(f"  PASS: Null byte injection rejected")
        print(f"    Reason: {result.reason}")


def test_valid_search_within_boundary():
    """Test that valid searches within boundary work correctly"""
    print("\n=== TEST (valid): Search within boundary ===")

    with tempfile.TemporaryDirectory() as allowed_dir:
        # Create some test files
        test_file = os.path.join(allowed_dir, "test.py")
        with open(test_file, "w") as f:
            f.write("password = 'secret123'\n")

        subdir = os.path.join(allowed_dir, "subdir")
        os.makedirs(subdir)
        test_file2 = os.path.join(subdir, "another.py")
        with open(test_file2, "w") as f:
            f.write("api_key = 'abc123'\n")

        bs = BoundedSearch(allowed_dir)

        # Test glob with **/*.py for recursive matching
        result = bs.glob("**/*.py")
        assert not isinstance(result, BoundaryRejection), (
            f"Expected valid result, got {result}"
        )
        assert len(result) == 2, f"Expected 2 files, got {len(result)}"
        print(f"  PASS: Glob returned {len(result)} files")

        # Test grep
        result2 = bs.grep("password")
        assert not isinstance(result2, BoundaryRejection), (
            f"Expected valid result, got {result2}"
        )
        assert len(result2) >= 1, f"Expected at least 1 match, got {len(result2)}"
        print(f"  PASS: Grep found {len(result2)} matches")

        # Test with explicit path
        result3 = bs.grep("api_key", path=allowed_dir)
        assert not isinstance(result3, BoundaryRejection), (
            f"Expected valid result, got {result3}"
        )
        print(f"  PASS: Grep with explicit path succeeded")


def test_subdirectory_access():
    """Test that subdirectory access within boundary works"""
    print("\n=== TEST (valid): Subdirectory access ===")

    with tempfile.TemporaryDirectory() as allowed_dir:
        subdir = os.path.join(allowed_dir, "level1", "level2")
        os.makedirs(subdir)
        test_file = os.path.join(subdir, "deep.py")
        with open(test_file, "w") as f:
            f.write("secret = 'nested'\n")

        bs = BoundedSearch(allowed_dir)

        # Access nested subdirectory
        result = bs.grep("secret", path=subdir)
        assert not isinstance(result, BoundaryRejection), (
            f"Expected valid result, got {result}"
        )
        print(f"  PASS: Subdirectory access allowed")


def test_edge_case_exact_boundary_match():
    """Test that exact boundary match is handled correctly"""
    print("\n=== TEST (edge): Exact boundary match ===")

    with tempfile.TemporaryDirectory() as allowed_dir:
        bs = BoundedSearch(allowed_dir)

        # The boundary itself should be accessible for listing
        result = bs.glob("*", path=allowed_dir)
        # Should return empty list or list of files, not a rejection
        assert not isinstance(result, BoundaryRejection), (
            f"Expected valid result, got {result}"
        )
        print(f"  PASS: Exact boundary match allowed")


def test_synthetic_path_traversal():
    """Test path traversal without actual filesystem traversal"""
    print("\n=== TEST (synthetic): Synthetic path traversal ===")

    # Use a path that looks like traversal but isn't real
    with tempfile.TemporaryDirectory() as allowed_dir:
        bs = BoundedSearch(allowed_dir)

        # Synthetic path: /allowed/../../../thing
        synthetic = os.path.join(allowed_dir, "..", "..", "..", "thing")
        result = bs.glob("*.py", path=synthetic)

        assert isinstance(result, BoundaryRejection), (
            f"Expected BoundaryRejection, got {type(result)}"
        )
        print(f"  PASS: Synthetic traversal rejected")
        print(f"    Attempted: {synthetic}")
        print(f"    Canonical: {result.canonical_attempted_path}")


def main():
    print("=" * 60)
    print("BOUNDED_SEARCH WRAPPER - BEHAVIORAL TEST SUITE")
    print("=" * 60)

    tests = [
        test_direct_out_of_boundary,
        test_relative_path_traversal,
        test_symlink_traversal,
        test_null_byte_injection,
        test_valid_search_within_boundary,
        test_subdirectory_access,
        test_edge_case_exact_boundary_match,
        test_synthetic_path_traversal,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
