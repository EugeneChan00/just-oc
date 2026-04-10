"""
BoundedSearch — Sandboxed file-search tool wrapper.

A security-critical permission-plane enforcement mechanism that restricts
glob and grep search operations to a declared directory boundary.
The wrapper intercepts all search requests, validates scope against
the canonicalized boundary, and rejects out-of-boundary searches with
structured errors. This turns a broad filesystem-search tool into a
scoped one.

This wrapper is ENTIRELY code-enforced. The boundary check cannot be
prompt-enforced because:
  1. Path canonicalization requires deterministic filesystem operations
     (os.path.realpath, os.path.abspath) that an LLM cannot perform.
  2. Symlink resolution requires actual filesystem access — the resolved
     path may differ from the apparent path in ways an LLM cannot infer.
  3. The security guarantee (no out-of-boundary access) must be
     deterministic, not probabilistic. LLMs cannot provide such guarantees.
"""

from __future__ import annotations

import dataclasses
import glob as stdlib_glob
import os
import re
import time
from pathlib import Path
from typing import Iterator


# ----------------------------------------------------------------------
# Structured Error Return
# ----------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class SearchRejection:
    """
    Structured error object for rejected search operations.

    Returned when a search is rejected because the search path
    or pattern resolves outside the declared write boundary.

    Attributes:
        code: Error code string (e.g., "BOUNDARY_VIOLATION").
        subcode: Subcode for specific violation type.
        attempted_path: The search path/pattern that was attempted.
        declared_boundary: The boundary the search was checked against.
        explanation: Human-readable explanation of the rejection.
        timestamp: Unix timestamp when the rejection occurred.
    """

    code: str
    subcode: str | None
    attempted_path: str
    declared_boundary: str
    explanation: str
    timestamp: float

    def to_dict(self) -> dict:
        """Convert to dictionary for structured return."""
        return {
            "code": self.code,
            "subcode": self.subcode,
            "attempted_path": self.attempted_path,
            "declared_boundary": self.declared_boundary,
            "explanation": self.explanation,
            "timestamp": self.timestamp,
        }


# ----------------------------------------------------------------------
# Exception Hierarchy (for raised exceptions)
# ----------------------------------------------------------------------


class BoundedSearchError(Exception):
    """Base exception for all BoundedSearch errors."""

    code: str = "BOUNDED_SEARCH_ERROR"
    subcode: str | None = None

    def __init__(
        self,
        message: str = "",
        attempted_path: str | None = None,
        boundary_path: str | None = None,
    ):
        self.message = message
        self.attempted_path = attempted_path
        self.boundary_path = boundary_path
        self.timestamp = time.time()
        super().__init__(self.message)


class BoundaryViolationError(BoundedSearchError):
    """Raised when a search attempts to escape the sandbox boundary."""

    code = "BOUNDARY_VIOLATION"


class PathTraversalAttempt(BoundaryViolationError):
    """Raised on path traversal via .. or absolute path escape."""

    subcode = "PATH_TRAVERSAL"


class SymlinkEscapeAttempt(BoundaryViolationError):
    """Raised when a symlink resolves outside the boundary."""

    subcode = "SYMLINK_ESCAPE"


class NullByteInjectionError(BoundedSearchError):
    """Raised when a null byte is detected in the path."""

    code = "NULL_BYTE_INJECTION"
    subcode = None


class BoundaryNotAbsoluteError(BoundedSearchError):
    """Raised when the boundary path is not absolute."""

    code = "BOUNDARY_NOT_ABSOLUTE"
    subcode = None


# ----------------------------------------------------------------------
# BoundedSearch Implementation
# ----------------------------------------------------------------------


class BoundedSearch:
    """
    Sandboxed file-search tool wrapper.

    Restricts all glob and grep search operations to a declared directory
    boundary. The boundary is immutable after initialization.

    The wrapper operates at the permission/policy plane — it intercepts
    search requests, validates scope, and either passes through valid
    searches or returns structured SearchRejection objects.

    Architecture:
      - Permission plane: boundary initialization and validation
      - Execution plane: canonicalization and search passthrough

    Usage:
        searcher = BoundedSearch("/home/user/project")
        result = searcher.glob("src/**/*.py")
        result = searcher.regex("src/", r"def\\s+\\w+\\(")
    """

    __slots__ = ("_boundary", "_boundary_str")

    def __init__(self, write_boundary: str | Path) -> None:
        """
        Initialize the bounded search wrapper.

        Args:
            write_boundary: The root directory that is the sole permitted
                search scope. Must be an absolute path.

        Raises:
            BoundaryNotAbsoluteError: If write_boundary is not absolute.
        """
        boundary = Path(write_boundary).resolve()

        # Boundary must be absolute after canonicalization
        if not boundary.is_absolute():
            raise BoundaryNotAbsoluteError(
                message=f"Write boundary must be absolute, got: {write_boundary}",
                boundary_path=str(boundary),
            )

        object.__setattr__(self, "_boundary", boundary)
        object.__setattr__(self, "_boundary_str", str(boundary))

    def __repr__(self) -> str:
        return f"BoundedSearch(boundary={self._boundary!r})"

    # ------------------------------------------------------------------
    # Path Canonicalization
    # ------------------------------------------------------------------

    def _canonicalize(self, path: str | Path) -> Path:
        """
        Canonicalize a path: resolve symlinks and normalize .. components.

        Uses os.path.realpath which:
          - Resolves symlinks (unlike Path.resolve() which can cache)
          - Normalizes .. components
          - Returns the canonical absolute path

        Args:
            path: The path to canonicalize.

        Returns:
            The canonicalized Path object.
        """
        # os.path.realpath resolves symlinks and normalizes the path
        canonical_str = os.path.realpath(path)
        return Path(canonical_str)

    def _check_path_within_boundary(self, path: str | Path) -> Path:
        """
        Check that a path, once canonicalized, is within the boundary.

        This is the core security check. It:
          1. Canonicalizes the path (resolves symlinks, normalizes ..)
          2. Verifies the canonical path starts with the boundary

        The check is deterministic: same input always produces same result.

        Args:
            path: The path to check.

        Returns:
            The canonicalized Path if within boundary.

        Raises:
            PathTraversalAttempt: If path traversal (../) escapes boundary.
            SymlinkEscapeAttempt: If symlink resolution escapes boundary.
            NullByteInjectionError: If null bytes detected in path.
        """
        path_str = str(path)

        # Check for null bytes (security defense)
        if "\0" in path_str:
            raise NullByteInjectionError(
                message="Null byte detected in path — rejected",
                attempted_path=path_str,
                boundary_path=self._boundary_str,
            )

        # Get the pre-symlink absolute path using os.path.abspath
        # This is what the user specified before any symlink resolution
        pre_symlink_abs = os.path.abspath(path_str)

        # Canonicalize (resolves symlinks)
        canonical = self._canonicalize(path_str)
        canonical_str = str(canonical)
        boundary_str = self._boundary_str

        # Check if pre-symlink path is within boundary
        pre_within = (
            pre_symlink_abs.startswith(boundary_str + os.sep)
            or pre_symlink_abs == boundary_str
        )

        # Check if canonical path is within boundary
        canonical_within = (
            canonical_str.startswith(boundary_str + os.sep)
            or canonical_str == boundary_str
        )

        if not canonical_within:
            if pre_within:
                # Original path was within boundary, but symlink escaped
                raise SymlinkEscapeAttempt(
                    message=(
                        f"[BOUNDARY_VIOLATION] Search denied: path resolves to "
                        f"'{canonical}' which is outside boundary '{self._boundary}'. "
                        f"Symlink traversal detected."
                    ),
                    attempted_path=path_str,
                    boundary_path=boundary_str,
                )
            else:
                # Original path was already outside boundary (or traversal via ..)
                raise PathTraversalAttempt(
                    message=(
                        f"[BOUNDARY_VIOLATION] Search denied: path '{canonical}' "
                        f"is outside boundary '{self._boundary}'. "
                        f"Path traversal or out-of-boundary access attempted."
                    ),
                    attempted_path=path_str,
                    boundary_path=boundary_str,
                )

        return canonical

    # ------------------------------------------------------------------
    # Glob Search
    # ------------------------------------------------------------------

    def glob(
        self, pattern: str, *, include_hidden: bool = False
    ) -> list[str] | SearchRejection:
        """
        Perform a glob-style pattern search within the boundary.

        The search root is always the declared boundary. The pattern
        is joined with the boundary before matching. Only files within
        the boundary will be returned.

        Args:
            pattern: Glob pattern (e.g., "src/**/*.py").
            include_hidden: Whether to include hidden files (default False).

        Returns:
            List of matching file paths (as strings) if within boundary,
            or a SearchRejection if the search was rejected.

        Raises:
            PathTraversalAttempt: If path traversal detected.
            SymlinkEscapeAttempt: If symlink escapes boundary.
            NullByteInjectionError: If null byte in pattern.
        """
        try:
            # The pattern is relative to the boundary
            # We check the combined path to ensure the glob won't escape
            if pattern.startswith("/") or pattern.startswith("\\"):
                # Absolute pattern — check if it falls within boundary
                check_path = pattern
            else:
                # Relative pattern — join with boundary
                check_path = os.path.join(self._boundary_str, pattern)

            self._check_path_within_boundary(check_path)

            # Perform the glob search rooted at boundary
            search_root = self._boundary_str
            full_pattern = os.path.join(search_root, pattern)

            # glob.glob returns paths matching the pattern
            matches = stdlib_glob.glob(full_pattern, recursive=True)

            # Filter to only files within boundary (defensive)
            results = []
            for match in matches:
                canonical_match = os.path.realpath(match)
                if (
                    canonical_match.startswith(self._boundary_str + os.sep)
                    or canonical_match == self._boundary_str
                ):
                    results.append(match)

            return results

        except (
            PathTraversalAttempt,
            SymlinkEscapeAttempt,
            NullByteInjectionError,
        ) as e:
            # Return structured rejection
            return SearchRejection(
                code=e.code,
                subcode=e.subcode,
                attempted_path=e.attempted_path or pattern,
                declared_boundary=self._boundary_str,
                explanation=e.message,
                timestamp=e.timestamp,
            )

    # ------------------------------------------------------------------
    # Regex Content Search
    # ------------------------------------------------------------------

    def regex(
        self, search_root: str | Path, pattern: str
    ) -> Iterator[dict] | SearchRejection:
        """
        Perform a regex content search within files under search_root.

        Searches all files under search_root (within boundary) for the
        given regex pattern. Returns an iterator of match dictionaries.

        Args:
            search_root: The root directory to search (within boundary).
            pattern: Regular expression pattern to search for.

        Returns:
            Iterator of dicts with keys: filepath, lineno, line, match.
            Or SearchRejection if the search was rejected.

        Raises:
            PathTraversalAttempt: If path traversal detected.
            SymlinkEscapeAttempt: If symlink escapes boundary.
            NullByteInjectionError: If null byte in search_root.
            re.error: If pattern is not a valid regex.
        """
        try:
            # Handle relative search_root: join with boundary
            if os.path.isabs(str(search_root)):
                check_path = search_root
            else:
                check_path = os.path.join(self._boundary_str, str(search_root))

            # Check and canonicalize the search root
            root_path = self._check_path_within_boundary(check_path)
            root_str = str(root_path)

            # Compile regex pattern
            compiled_pattern = re.compile(pattern)

            def _search() -> Iterator[dict]:
                """Generator that yields matches within boundary."""
                for dirpath, dirnames, filenames in os.walk(root_str):
                    # Check each directory is within boundary (defensive)
                    canonical_dir = os.path.realpath(dirpath)
                    if not (
                        canonical_dir.startswith(self._boundary_str + os.sep)
                        or canonical_dir == self._boundary_str
                    ):
                        continue

                    for filename in filenames:
                        filepath = os.path.join(dirpath, filename)
                        canonical_filepath = os.path.realpath(filepath)

                        # Verify file is within boundary
                        if not (
                            canonical_filepath.startswith(self._boundary_str + os.sep)
                            or canonical_filepath == self._boundary_str
                        ):
                            continue

                        # Read and search file
                        try:
                            with open(
                                canonical_filepath,
                                "r",
                                encoding="utf-8",
                                errors="replace",
                            ) as f:
                                for lineno, line in enumerate(f, start=1):
                                    match = compiled_pattern.search(line)
                                    if match:
                                        yield {
                                            "filepath": canonical_filepath,
                                            "lineno": lineno,
                                            "line": line.rstrip("\n"),
                                            "match": match.group(0),
                                        }
                        except (OSError, IOError):
                            # Skip files that can't be read (permission denied, etc.)
                            continue

            return _search()

        except (
            PathTraversalAttempt,
            SymlinkEscapeAttempt,
            NullByteInjectionError,
        ) as e:
            return SearchRejection(
                code=e.code,
                subcode=e.subcode,
                attempted_path=e.attempted_path or str(search_root),
                declared_boundary=self._boundary_str,
                explanation=e.message,
                timestamp=e.timestamp,
            )

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def get_boundary(self) -> str:
        """
        Return the canonical boundary path as a string.

        Returns:
            The declared write boundary path.
        """
        return self._boundary_str

    def is_within_boundary(self, path: str | Path) -> bool:
        """
        Check if a path is within the boundary without raising.

        Useful for pre-flight checks without catching exceptions.

        Args:
            path: The path to check.

        Returns:
            True if the path (canonicalized) is within boundary, False otherwise.
        """
        try:
            self._check_path_within_boundary(path)
            return True
        except BoundedSearchError:
            return False


# ----------------------------------------------------------------------
# Adversarial Attack Vector Reference
# ----------------------------------------------------------------------
#
# This wrapper is designed to defend against:
#
# (a) Direct out-of-boundary path: /home/user/other_project/secret.py
#     → PathTraversalAttempt: canonical path doesn't start with boundary
#
# (b) Relative path traversal: write_boundary/../../etc/passwd
#     → PathTraversalAttempt: canonical path resolves to /etc/passwd,
#       which doesn't start with boundary
#
# (c) Symlink traversal: write_boundary/symlink_to_root/etc/passwd
#     where symlink_to_root points to /
#     → SymlinkEscapeAttempt: canonical path /etc/passwd doesn't start
#       with boundary, but pre-symlink path did start with boundary
#
# (d) URL-encoded path components (e.g., %2e%2e/%2e%2e/)
#     → Not implemented: URL encoding is a transport-layer concern;
#       if paths arrive URL-encoded, decode before passing to wrapper
#
# (e) Null bytes in path (e.g., /path/to/file\0.txt)
#     → NullByteInjectionError: rejected at canonicalization entry
#
# (f) Case sensitivity on case-insensitive filesystems
#     → Not fully implemented: os.path.realpath is case-sensitive on
#       Linux; on Windows/macOS with case-insensitive fs, the boundary
#       check may not catch case-manipulation attacks. This is a
#       fundamental limitation of the underlying filesystem.
