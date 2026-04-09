"""
autoresearch.harness.tools.bounded_search

Tool wrapper that restricts file-search operations (glob/grep) to a declared write boundary.
This is a PERMISSION-PLANE enforcement mechanism: it turns a broad filesystem-access tool
into a scoped tool with deterministic boundary checking.

Path canonicalization uses os.path.realpath() to:
- Resolve symlinks
- Normalize relative paths (remove ../)
- Handle path traversal attacks

The boundary check is CODE-ENFORCED (not prompt-enforced) because:
1. Path canonicalization requires deterministic filesystem operations an LLM cannot perform
2. Symlink resolution requires actual filesystem access
3. The security guarantee (no out-of-boundary access) must be deterministic, not probabilistic
"""

import fnmatch
import glob as stdlib_glob
import os
import re
from dataclasses import dataclass
from typing import List, Optional, Union


@dataclass
class BoundaryRejection:
    """Structured error object for out-of-boundary search rejections."""

    attempted_path: str
    declared_boundary: str
    canonical_attempted_path: str
    canonical_boundary: str
    reason: str

    def to_dict(self) -> dict:
        return {
            "error": "BOUNDARY_VIOLATION",
            "attempted_path": self.attempted_path,
            "declared_boundary": self.declared_boundary,
            "canonical_attempted_path": self.canonical_attempted_path,
            "canonical_boundary": self.canonical_boundary,
            "reason": self.reason,
        }


class BoundedSearchError(Exception):
    """Exception raised when a search attempt violates the write boundary."""

    def __init__(self, rejection: BoundaryRejection):
        self.rejection = rejection
        super().__init__(f"BOUNDARY_VIOLATION: {rejection.reason}")

    def to_dict(self) -> dict:
        return self.rejection.to_dict()


class BoundedSearch:
    """
    Tool wrapper that restricts glob/regex searches to a declared write boundary.

    The wrapper intercepts all search requests, canonicalizes both the search path
    and the boundary using os.path.realpath(), and rejects out-of-boundary searches
    with a structured error.

    This is entirely CODE-ENFORCED — no LLM involvement in boundary decisions.
    """

    def __init__(self, write_boundary: str):
        """
        Initialize the bounded search wrapper.

        Args:
            write_boundary: Directory path to restrict searches to. Must be an
                           absolute path or will be converted to one.
        """
        if not write_boundary:
            raise ValueError("write_boundary must be a non-empty string")

        self._write_boundary = write_boundary
        # Canonicalize the boundary path once at initialization
        # realpath resolves symlinks and normalizes the path
        try:
            self._canonical_boundary = os.path.realpath(write_boundary)
        except OSError as e:
            raise ValueError(f"Cannot resolve write_boundary '{write_boundary}': {e}")

        if not os.path.isabs(self._canonical_boundary):
            raise ValueError(
                f"write_boundary must resolve to an absolute path, got: {self._canonical_boundary}"
            )

    @property
    def write_boundary(self) -> str:
        """Return the original (non-canonicalized) write boundary."""
        return self._write_boundary

    @property
    def canonical_boundary(self) -> str:
        """Return the canonicalized write boundary."""
        return self._canonical_boundary

    def _canonicalize_path(self, path: str) -> str:
        """
        Canonicalize a search path using os.path.realpath().

        This resolves:
        - Symlinks
        - Relative path components (../, ./)
        - Redundant path separators

        Args:
            path: The path to canonicalize

        Returns:
            The canonical absolute path, or empty string if path is invalid
        """
        # Handle None or empty path
        if not path:
            return ""

        # Use realpath for full symlink resolution and path normalization
        # realpath resolves symlinks, normalizes relative paths, and rejects
        # invalid paths (e.g., null bytes)
        try:
            return os.path.realpath(path)
        except (OSError, ValueError):
            # If realpath fails:
            # - OSError: file doesn't exist, but we can still normalize path
            # - ValueError: invalid path (e.g., null bytes)
            # Fall back to normpath + abspath for path traversal normalization
            # Note: This cannot resolve null bytes but can normalize ../ etc.
            try:
                return os.path.abspath(os.path.normpath(path))
            except Exception:
                # As a last resort, return empty string to trigger rejection
                return ""

    def _check_boundary(self, path: str) -> Optional[BoundaryRejection]:
        """
        Check if a search path is within the write boundary.

        Uses path canonicalization to detect:
        - Direct out-of-boundary paths
        - Path traversal attacks (../)
        - Symlink traversal attacks

        Args:
            path: The search path to check

        Returns:
            None if the path is within boundary, or a BoundaryRejection if violated
        """
        if not path:
            return BoundaryRejection(
                attempted_path=path,
                declared_boundary=self._write_boundary,
                canonical_attempted_path="",
                canonical_boundary=self._canonical_boundary,
                reason="Empty or None path provided",
            )

        canonical_path = self._canonicalize_path(path)

        # Check if the canonical path starts with the canonical boundary
        # We add os.sep to prevent "/allowed" from matching "/allowed_extra"
        boundary_with_sep = self._canonical_boundary + os.sep

        if not canonical_path.startswith(boundary_with_sep):
            # Also handle the edge case where the path IS the boundary
            if canonical_path != self._canonical_boundary:
                return BoundaryRejection(
                    attempted_path=path,
                    declared_boundary=self._write_boundary,
                    canonical_attempted_path=canonical_path,
                    canonical_boundary=self._canonical_boundary,
                    reason=(
                        f"Path '{canonical_path}' is not within boundary "
                        f"'{self._canonical_boundary}'. Path traversal or "
                        f"out-of-boundary access attempt detected."
                    ),
                )

        return None

    def glob(
        self, pattern: str, *, path: Optional[str] = None
    ) -> Union[List[str], BoundaryRejection]:
        """
        Perform a glob-style pattern search within the write boundary.

        Args:
            pattern: Glob pattern (e.g., "**/*.py", "*.txt")
            path: Base path for the search. If None, uses write_boundary.
                  Must be within write_boundary.

        Returns:
            List of matching file paths if within boundary, or BoundaryRejection if violated.

        Note:
            Results are passed through unmodified — the wrapper only gates
            the search scope, it does not filter or annotate results.
        """
        # Determine the search base path
        search_path = path if path is not None else self._write_boundary

        # Check boundary
        rejection = self._check_boundary(search_path)
        if rejection is not None:
            return rejection

        # Perform the glob search using the standard library
        # The wrapper only gates; it doesn't transform results
        try:
            matches = stdlib_glob.glob(
                pattern,
                root_dir=search_path,
                recursive=True,
            )
            # Return full paths
            return [os.path.join(search_path, m) for m in matches]
        except OSError as e:
            # Handle permission errors or other OS-level failures
            return BoundaryRejection(
                attempted_path=search_path,
                declared_boundary=self._write_boundary,
                canonical_attempted_path=self._canonicalize_path(search_path),
                canonical_boundary=self._canonical_boundary,
                reason=f"Glob search failed: {e}",
            )

    def grep(
        self,
        pattern: str,
        *,
        path: Optional[str] = None,
        regex: bool = False,
        file_pattern: str = "*",
    ) -> Union[List[str], BoundaryRejection]:
        """
        Perform a content search (regex or literal) within the write boundary.

        Args:
            pattern: Search pattern (literal string or regex if regex=True)
            path: Base path for the search. If None, uses write_boundary.
            regex: If True, treat pattern as regex; otherwise literal string
            file_pattern: Glob pattern to filter files (e.g., "*.py", "*.txt")

        Returns:
            List of matching lines (format: "filepath:linenum:content") if within
            boundary, or BoundaryRejection if violated.

        Note:
            Results are passed through unmodified — the wrapper only gates
            the search scope, it does not filter or annotate results.
        """
        # Determine the search base path
        search_path = path if path is not None else self._write_boundary

        # Check boundary
        rejection = self._check_boundary(search_path)
        if rejection is not None:
            return rejection

        # Compile the search pattern
        if regex:
            try:
                compiled_pattern = re.compile(pattern)
            except re.error as e:
                return BoundaryRejection(
                    attempted_path=search_path,
                    declared_boundary=self._write_boundary,
                    canonical_attempted_path=self._canonicalize_path(search_path),
                    canonical_boundary=self._canonical_boundary,
                    reason=f"Invalid regex pattern: {e}",
                )
        else:
            compiled_pattern = re.compile(re.escape(pattern))

        results: List[str] = []

        try:
            # Walk the directory tree within the bounded path
            for dirpath, dirnames, filenames in os.walk(search_path):
                for filename in filenames:
                    # Check if file matches the file_pattern using fnmatch
                    if not fnmatch.fnmatch(filename, file_pattern):
                        continue

                    filepath = os.path.join(dirpath, filename)

                    # Double-check the file is still within boundary
                    # (could have changed via symlink during walk)
                    rejection = self._check_boundary(filepath)
                    if rejection is not None:
                        continue  # Skip files that wandered out of bounds

                    try:
                        with open(
                            filepath, "r", encoding="utf-8", errors="replace"
                        ) as f:
                            for linenum, line in enumerate(f, 1):
                                if compiled_pattern.search(line):
                                    results.append(
                                        f"{filepath}:{linenum}:{line.rstrip()}"
                                    )
                    except (OSError, IOError):
                        # Skip files we can't read (permission denied, etc.)
                        continue
        except OSError as e:
            return BoundaryRejection(
                attempted_path=search_path,
                declared_boundary=self._write_boundary,
                canonical_attempted_path=self._canonicalize_path(search_path),
                canonical_boundary=self._canonical_boundary,
                reason=f"Grep search failed: {e}",
            )

        return results


# Convenience function for direct use
def create_bounded_search(write_boundary: str) -> BoundedSearch:
    """
    Factory function to create a BoundedSearch wrapper.

    Args:
        write_boundary: Directory path to restrict searches to

    Returns:
        Configured BoundedSearch instance

    Raises:
        ValueError: If write_boundary is invalid
    """
    return BoundedSearch(write_boundary)
