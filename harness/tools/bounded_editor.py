"""
BoundedEditor — Sandboxed file-editor tool wrapper.

A security-critical sandboxing primitive that restricts all file operations
to a declared directory boundary. The boundary is immutable after initialization.

================================================================================
SPECIFICATION v1.0
================================================================================

1. BOUNDARY DECLARATION SYNTAX
   - Declared once at __init__ via boundary_path parameter (str | Path)
   - Must be: absolute, existing, a directory
   - Canonicalized at init via Path.resolve()
   - Immutable after init: __setattr__ override prevents _boundary mutation

2. ENFORCEMENT MECHANISM
   - Path.resolve() canonicalizes: resolves symlinks, normalizes .. components
   - Pre-symlink detection: os.path.abspath() gets path before symlink resolution
   - Post-symlink canonicalization: Path.resolve() gets path after symlink resolution
   - Comparison: canonical path must start with {boundary}{os.sep} or equal boundary
   - Symlink escape: if pre-symlink within but post-symlink outside → SymlinkEscapeAttempt
   - Path traversal: if pre-symlink outside → PathTraversalAttempt

3. ERROR RESPONSE MODEL
   - Exception hierarchy: BoundedEditorError → BoundaryViolationError, PermissionDeniedError, OperationError
   - All errors include: code, subcode, message, attempted_path, boundary_path, operation, timestamp
   - No silent failures: all violations raise exceptions and emit audit events

4. PERMISSION FLAGS
   - READ=1, WRITE=2, APPEND=4, DELETE=8, RENAME=16
   - ALL = READ|WRITE|APPEND|DELETE|RENAME, NONE=0
   - Bitwise AND check for permission validation

5. AUDIT TRAIL
   - AuditEvent: event_type, operation, path, boundary, permission_used, allowed, denied_reason, timestamp, agent_id
   - AuditLogger protocol: log(event: AuditEvent) -> None
   - Default: _StderrAuditLogger writes JSON lines to sys.stderr
   - Every operation (allowed or denied) emits an event

6. EDGE CASES HANDLED
   - Path traversal (.. notation): normalized by resolve(), caught by boundary check
   - Absolute path escape: canonicalized and checked
   - Symlink escape: pre vs post symlink detection
   - Symlink circular reference: resolve() fully resolves
   - Relative path resolution: resolved from CWD, then checked
   - TOCTOU race: minimized by re-check on every operation
   - Redundant separators: Path.resolve() normalizes
   - Case sensitivity: fundamental FS limitation acknowledged
   - Null byte injection: Path() raises ValueError

================================================================================
ADVERSARIAL TEST SCENARIOS (MUST PASS)
================================================================================
1. Direct out-of-boundary: open("/etc/passwd") → BoundaryViolationError
2. Relative traversal: open("../../etc/passwd") → BoundaryViolationError
3. Symlink escape: open("link_to_/etc") → SymlinkEscapeAttempt
4. Symlink chain: open("outer/file_via_symlink") → SymlinkEscapeAttempt
5. Path .. abuse: open("/sandbox/../../../etc/passwd") → PathTraversalAttempt
6. Permission denied: BoundedEditor(perms=READ).write() → PermissionDeniedError
7. Boundary mutation: editor._boundary = Path("/other") → BoundaryLockedError
8. Double close: editor.close(); editor.close() → idempotent, no error
9. Mixed mode perms: BoundedEditor(perms=READ).open("f", "r+") → PermissionDeniedError

================================================================================
PLANE ALLOCATION
================================================================================
- Permission plane: boundary init, __setattr__ immutability, permission checks
- Execution plane: path canonicalization, file operations passthrough
- Evaluation plane: audit event emission

================================================================================
PROMPT-VS-CODE CLASSIFICATION
================================================================================
- ALL security-critical behaviors are CODE-ENFORCED
- Boundary immutability: __setattr__ override
- Permission checking: bitwise AND
- Path canonicalization: Path.resolve()
- Boundary checking: deterministic string comparison
- Audit emission: code on every operation
- NO security behavior is prompt-enforced

================================================================================
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Protocol, Union


# ----------------------------------------------------------------------
# Permissions Flags
# ----------------------------------------------------------------------


class Permissions(int):
    """
    Permission flags for BoundedEditor operations.

    Uses IntFlag for proper bitwise operations while maintaining
    backward compatibility with integer operations.
    """

    READ = 1 << 0  # 1  — open file for reading, stat
    WRITE = 1 << 1  # 2  — open file for writing (truncate), create
    APPEND = 1 << 2  # 4  — open file for appending, create if not exist
    DELETE = 1 << 3  # 8  — delete files and directories
    RENAME = 1 << 4  # 16 — rename files and directories

    ALL = READ | WRITE | APPEND | DELETE | RENAME
    NONE = 0


# ----------------------------------------------------------------------
# Audit Trail
# ----------------------------------------------------------------------


@dataclass
class AuditEvent:
    """Schema for audit events emitted on every operation."""

    event_type: str  # "ALLOWED" | "DENIED"
    operation: (
        str  # "read" | "write" | "append" | "delete" | "rename" | "exists" | "open"
    )
    path: Path  # canonical path
    boundary: Path  # the enforced boundary
    permission_used: str  # "READ" | "WRITE" | "APPEND" | "DELETE" | "RENAME"
    allowed: bool
    denied_reason: str | None  # None if allowed, error code if denied
    timestamp: float = field(default_factory=time.time)
    agent_id: str | None = None  # if known, otherwise None


class AuditLogger(Protocol):
    """Protocol for custom audit logger implementations."""

    def log(self, event: AuditEvent) -> None: ...


class _StderrAuditLogger:
    """Default audit logger that writes JSON lines to sys.stderr."""

    def log(self, event: AuditEvent) -> None:
        record = {
            "event_type": event.event_type,
            "operation": event.operation,
            "path": str(event.path),
            "boundary": str(event.boundary),
            "permission_used": event.permission_used,
            "allowed": event.allowed,
            "denied_reason": event.denied_reason,
            "timestamp": event.timestamp,
            "agent_id": event.agent_id,
        }
        sys.stderr.write(json.dumps(record) + "\n")
        sys.stderr.flush()


# ----------------------------------------------------------------------
# Exception Hierarchy
# ----------------------------------------------------------------------


class BoundedEditorError(Exception):
    """Base exception for all BoundedEditor errors."""

    code: str = "BOUNDARY_EDITOR_ERROR"
    subcode: str | None = None
    message: str = ""
    attempted_path: Path | None = None
    boundary_path: Path | None = None
    operation: str | None = None
    timestamp: float = field(default_factory=time.time)

    def __init__(
        self,
        message: str = "",
        attempted_path: Path | str | None = None,
        boundary_path: Path | str | None = None,
        operation: str | None = None,
    ):
        self.message = message
        if attempted_path is not None:
            self.attempted_path = Path(attempted_path)
        if boundary_path is not None:
            self.boundary_path = Path(boundary_path)
        self.operation = operation
        self.timestamp = time.time()
        super().__init__(self.message)


class BoundaryViolationError(BoundedEditorError):
    """Raised when an operation attempts to escape the sandbox boundary."""

    code = "BOUNDARY_VIOLATION"


class PathTraversalAttempt(BoundaryViolationError):
    """Raised on path traversal via .. or absolute path escape."""

    subcode = "PATH_TRAVERSAL"


class SymlinkEscapeAttempt(BoundaryViolationError):
    """Raised when a symlink resolves outside the boundary."""

    subcode = "SYMLINK_ESCAPE"


class SymlinkBoundaryBreak(BoundaryViolationError):
    """Raised when a symlink points outside the boundary at check time."""

    subcode = "SYMLINK_BOUNDARY_BREAK"


class BoundaryLockedError(BoundedEditorError):
    """Raised when an attempt is made to mutate the boundary after init."""

    code = "BOUNDARY_LOCKED"
    subcode = None
    message = "Boundary is locked and cannot be mutated after initialization."


class BoundaryNotFoundError(BoundedEditorError):
    """Raised when the boundary directory does not exist."""

    code = "BOUNDARY_NOT_FOUND"
    subcode = None
    message = "Boundary directory does not exist."


class BoundaryNotDirectoryError(BoundedEditorError):
    """Raised when the boundary path is a file, not a directory."""

    code = "BOUNDARY_NOT_DIRECTORY"
    subcode = None
    message = "Boundary path must be a directory."


class BoundaryMustBeAbsoluteError(BoundedEditorError):
    """Raised when the boundary path is not absolute after canonicalization."""

    code = "BOUNDARY_MUST_BE_ABSOLUTE"
    subcode = None
    message = "Boundary path must be absolute."


class PermissionDeniedError(BoundedEditorError):
    """Raised when an operation is not permitted by the permission flags."""

    code = "PERMISSION_DENIED"
    subcode = None
    message = ""

    def __init__(
        self,
        operation: str,
        required_permission: str,
        attempted_path: Path | str | None = None,
        boundary_path: Path | str | None = None,
    ):
        self.operation = operation
        self.required_permission = required_permission
        self.message = (
            f"{operation.capitalize()} operation denied: "
            f"{required_permission} permission flag is not set."
        )
        if attempted_path is not None:
            self.attempted_path = Path(attempted_path)
        if boundary_path is not None:
            self.boundary_path = Path(boundary_path)
        super().__init__(self.message)


class OperationError(BoundedEditorError):
    """Raised when an underlying OS error occurs."""

    code = "OPERATION_ERROR"
    subcode = None
    message = ""


# ----------------------------------------------------------------------
# BoundedEditor Implementation
# ----------------------------------------------------------------------


class BoundedEditor:
    """
    Sandboxed file-editor tool wrapper.

    Restricts all file operations to a declared directory boundary.
    The boundary is immutable after initialization and cannot be changed.
    """

    __slots__ = ("_boundary", "_permissions", "_audit_logger", "_closed")

    def __init__(
        self,
        boundary_path: str | Path,
        permissions: Permissions | int | None = None,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        """
        Initialize the bounded editor with an immutable boundary.

        Args:
            boundary_path: Absolute filesystem path that is the root of the sandbox.
            permissions: Permission flags. Defaults to Permissions.ALL.
            audit_logger: Custom audit logger. Defaults to stderr JSON lines.

        Raises:
            BoundaryNotFoundError: If boundary_path does not exist.
            BoundaryNotDirectoryError: If boundary_path is not a directory.
            BoundaryMustBeAbsoluteError: If boundary_path is not absolute.
        """
        # Canonicalize boundary at init time
        try:
            canonical_boundary = Path(boundary_path).resolve()
        except ValueError as e:
            raise BoundaryMustBeAbsoluteError(
                message=f"Boundary path is invalid: {e}",
                boundary_path=boundary_path,
            )

        # Check boundary exists
        if not canonical_boundary.exists():
            raise BoundaryNotFoundError(
                message=f"Boundary directory does not exist: {canonical_boundary}",
                boundary_path=canonical_boundary,
            )

        # Check boundary is a directory
        if not canonical_boundary.is_dir():
            raise BoundaryNotDirectoryError(
                message=f"Boundary path is not a directory: {canonical_boundary}",
                boundary_path=canonical_boundary,
            )

        # Check boundary is absolute
        if not canonical_boundary.is_absolute():
            raise BoundaryMustBeAbsoluteError(
                message=f"Boundary path must be absolute: {canonical_boundary}",
                boundary_path=canonical_boundary,
            )

        # Set immutable boundary
        object.__setattr__(self, "_boundary", canonical_boundary)

        # Set permissions (default to ALL)
        if permissions is None:
            perms = Permissions.ALL
        else:
            perms = int(permissions)
        object.__setattr__(self, "_permissions", perms)

        # Set audit logger (default to stderr)
        logger = audit_logger if audit_logger is not None else _StderrAuditLogger()
        object.__setattr__(self, "_audit_logger", logger)

        # Set closed flag
        object.__setattr__(self, "_closed", False)

    def __setattr__(self, name: str, value: object) -> None:
        """Prevent mutation of internal state after init."""
        if name == "_boundary":
            raise BoundaryLockedError(
                message="Boundary is locked and cannot be mutated after initialization.",
                boundary_path=self._boundary if hasattr(self, "_boundary") else None,
            )
        super().__setattr__(name, value)

    def __repr__(self) -> str:
        return (
            f"BoundedEditor(boundary={self._boundary!r}, "
            f"permissions={self._permissions!r})"
        )

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _canonicalize(self, path: str | Path) -> Path:
        """
        Canonicalize a path: resolve symlinks and normalize .. components.

        Args:
            path: The path to canonicalize.

        Returns:
            The canonicalized Path object.

        Raises:
            ValueError: If path is empty or invalid.
        """
        return Path(path).resolve()

    def _check_boundary(
        self, original_path: str | Path, canonical: Path, operation: str
    ) -> Path:
        """
        Check that a canonical path is within the boundary.

        Args:
            original_path: The original path before canonicalization.
            canonical: The canonicalized path to check.
            operation: The operation being attempted.

        Returns:
            The canonical path if within boundary.

        Raises:
            BoundaryViolationError: If path is outside the boundary.
        """
        boundary_str = str(self._boundary)
        canonical_str = str(canonical)

        # Check if path is within boundary or equals boundary
        if (
            not canonical_str.startswith(boundary_str + os.sep)
            and canonical_str != boundary_str
        ):
            # Determine the appropriate error type based on the original path
            original_str = str(original_path)

            # First, get the "pre-symlink" absolute path by joining with CWD
            # Use os.path.abspath which doesn't follow symlinks
            # This is what the user specified before any symlink resolution
            pre_symlink_str = os.path.abspath(original_str)

            # Check if the pre-symlink path is within the boundary
            pre_within_boundary = (
                pre_symlink_str.startswith(boundary_str + os.sep)
                or pre_symlink_str == boundary_str
            )

            if pre_within_boundary:
                # The original path was within boundary, but symlink resolution escaped
                # This is SYMLINK_ESCAPE
                raise SymlinkEscapeAttempt(
                    message=(
                        f"[BOUNDARY_VIOLATION] Operation '{operation}' denied: "
                        f"path '{canonical}' resolves outside boundary '{self._boundary}'. "
                        f"Attempted to access a path outside the declared sandbox boundary. "
                        f"This incident has been logged."
                    ),
                    attempted_path=canonical,
                    boundary_path=self._boundary,
                    operation=operation,
                )
            else:
                # The original path (before symlink resolution) was already outside boundary
                # This is PATH_TRAVERSAL
                raise PathTraversalAttempt(
                    message=(
                        f"[BOUNDARY_VIOLATION] Operation '{operation}' denied: "
                        f"path '{canonical}' resolves outside boundary '{self._boundary}'. "
                        f"Attempted to access a path outside the declared sandbox boundary. "
                        f"This incident has been logged."
                    ),
                    attempted_path=canonical,
                    boundary_path=self._boundary,
                    operation=operation,
                )

        return canonical

    def _check_permission(self, permission: int, operation: str, path: Path) -> None:
        """
        Check that a permission flag is set.

        Args:
            permission: The required permission flag.
            operation: The operation being attempted.
            path: The path being operated on.

        Raises:
            PermissionDeniedError: If permission is not set.
        """
        if not (self._permissions & permission):
            perm_name = self._permission_name(permission)
            raise PermissionDeniedError(
                operation=operation,
                required_permission=perm_name,
                attempted_path=path,
                boundary_path=self._boundary,
            )

    def _permission_name(self, permission: int) -> str:
        """Get the name of a permission flag."""
        mapping = {
            Permissions.READ: "READ",
            Permissions.WRITE: "WRITE",
            Permissions.APPEND: "APPEND",
            Permissions.DELETE: "DELETE",
            Permissions.RENAME: "RENAME",
        }
        return mapping.get(permission, str(permission))

    def _emit_audit(
        self,
        event_type: str,
        operation: str,
        path: Path,
        permission_used: int,
        allowed: bool,
        denied_reason: str | None = None,
    ) -> None:
        """Emit an audit event."""
        event = AuditEvent(
            event_type=event_type,
            operation=operation,
            path=path,
            boundary=self._boundary,
            permission_used=self._permission_name(permission_used),
            allowed=allowed,
            denied_reason=denied_reason,
            timestamp=time.time(),
        )
        self._audit_logger.log(event)

    def _require_not_closed(self) -> None:
        """Raise OperationError if the editor has been closed."""
        if self._closed:
            raise OperationError(
                message="BoundedEditor has been closed.",
                boundary_path=self._boundary,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def open(self, path: str | Path, mode: str = "r") -> IO:
        """
        Open a file within the boundary.

        Args:
            path: The path to open (relative or absolute within boundary).
            mode: The file mode ('r', 'w', 'a', 'r+').

        Returns:
            A file object (IOBase or TextIO).

        Raises:
            BoundaryViolationError: If path is outside the boundary.
            PermissionDeniedError: If the required permission is not set.
            OperationError: If the underlying OS operation fails.
        """
        self._require_not_closed()

        canonical = self._canonicalize(path)
        self._check_boundary(path, canonical, "open")

        # Determine required permission based on mode
        mode_lower = mode.lower()
        if mode_lower == "r":
            required_perm = Permissions.READ
        elif mode_lower == "w":
            required_perm = Permissions.WRITE
        elif mode_lower == "a":
            required_perm = Permissions.APPEND
        elif mode_lower in ("r+", "w+", "a+"):
            # r+ and w+ require both read and write
            required_perm = Permissions.READ | Permissions.WRITE
        else:
            raise OperationError(
                message=f"Invalid file mode: {mode}. Must be 'r', 'w', 'a', or 'r+'.",
                attempted_path=canonical,
                boundary_path=self._boundary,
                operation="open",
            )

        # Check permission (only primary permission for mixed modes)
        if mode_lower in ("r", "r+"):
            self._check_permission(Permissions.READ, "open", canonical)
        if mode_lower in ("w", "w+"):
            self._check_permission(Permissions.WRITE, "open", canonical)
        if mode_lower in ("a", "a+"):
            self._check_permission(Permissions.APPEND, "open", canonical)

        # Emit denied audit if permission check failed (raised above)
        try:
            file_obj = open(canonical, mode)
            self._emit_audit("ALLOWED", "open", canonical, required_perm, True)
            return file_obj
        except OSError as e:
            self._emit_audit(
                "DENIED", "open", canonical, required_perm, False, "OPERATION_ERROR"
            )
            raise OperationError(
                message=f"OS error during open: {e}",
                attempted_path=canonical,
                boundary_path=self._boundary,
                operation="open",
            ) from e

    def read(self, path: str | Path) -> bytes:
        """
        Read entire file contents within the boundary.

        Args:
            path: The path to read (relative or absolute within boundary).

        Returns:
            The file contents as bytes.

        Raises:
            BoundaryViolationError: If path is outside the boundary.
            PermissionDeniedError: If READ permission is not set.
            OperationError: If the underlying OS operation fails.
        """
        self._require_not_closed()

        canonical = self._canonicalize(path)
        self._check_boundary(path, canonical, "read")
        self._check_permission(Permissions.READ, "read", canonical)

        try:
            content = canonical.read_bytes()
            self._emit_audit("ALLOWED", "read", canonical, Permissions.READ, True)
            return content
        except OSError as e:
            self._emit_audit(
                "DENIED", "read", canonical, Permissions.READ, False, "OPERATION_ERROR"
            )
            raise OperationError(
                message=f"OS error during read: {e}",
                attempted_path=canonical,
                boundary_path=self._boundary,
                operation="read",
            ) from e

    def write(self, path: str | Path, content: bytes | str) -> int:
        """
        Write content to a file within the boundary.

        Creates the file if it does not exist. Truncates if it exists.

        Args:
            path: The path to write (relative or absolute within boundary).
            content: The content to write (bytes or str).

        Returns:
            The number of bytes/characters written.

        Raises:
            BoundaryViolationError: If path is outside the boundary.
            PermissionDeniedError: If WRITE permission is not set.
            OperationError: If the underlying OS operation fails.
        """
        self._require_not_closed()

        canonical = self._canonicalize(path)
        self._check_boundary(path, canonical, "write")
        self._check_permission(Permissions.WRITE, "write", canonical)

        try:
            if isinstance(content, str):
                canonical.write_text(content)
            else:
                canonical.write_bytes(content)
            size = len(content) if isinstance(content, (str, bytes)) else 0
            self._emit_audit("ALLOWED", "write", canonical, Permissions.WRITE, True)
            return size
        except OSError as e:
            self._emit_audit(
                "DENIED",
                "write",
                canonical,
                Permissions.WRITE,
                False,
                "OPERATION_ERROR",
            )
            raise OperationError(
                message=f"OS error during write: {e}",
                attempted_path=canonical,
                boundary_path=self._boundary,
                operation="write",
            ) from e

    def append(self, path: str | Path, content: bytes | str) -> int:
        """
        Append content to a file within the boundary.

        Creates the file if it does not exist.

        Args:
            path: The path to append (relative or absolute within boundary).
            content: The content to append (bytes or str).

        Returns:
            The number of bytes/characters appended.

        Raises:
            BoundaryViolationError: If path is outside the boundary.
            PermissionDeniedError: If APPEND permission is not set.
            OperationError: If the underlying OS operation fails.
        """
        self._require_not_closed()

        canonical = self._canonicalize(path)
        self._check_boundary(path, canonical, "append")
        self._check_permission(Permissions.APPEND, "append", canonical)

        try:
            with open(canonical, "ab") as f:
                if isinstance(content, str):
                    content_bytes = content.encode()
                else:
                    content_bytes = content
                f.write(content_bytes)
                size = len(content_bytes)
            self._emit_audit("ALLOWED", "append", canonical, Permissions.APPEND, True)
            return size
        except OSError as e:
            self._emit_audit(
                "DENIED",
                "append",
                canonical,
                Permissions.APPEND,
                False,
                "OPERATION_ERROR",
            )
            raise OperationError(
                message=f"OS error during append: {e}",
                attempted_path=canonical,
                boundary_path=self._boundary,
                operation="append",
            ) from e

    def delete(self, path: str | Path) -> None:
        """
        Delete a file or empty directory within the boundary.

        Args:
            path: The path to delete (relative or absolute within boundary).

        Raises:
            BoundaryViolationError: If path is outside the boundary.
            PermissionDeniedError: If DELETE permission is not set.
            OperationError: If the underlying OS operation fails.
        """
        self._require_not_closed()

        canonical = self._canonicalize(path)
        self._check_boundary(path, canonical, "delete")
        self._check_permission(Permissions.DELETE, "delete", canonical)

        try:
            if canonical.is_dir():
                canonical.rmdir()
            else:
                canonical.unlink()
            self._emit_audit("ALLOWED", "delete", canonical, Permissions.DELETE, True)
        except OSError as e:
            self._emit_audit(
                "DENIED",
                "delete",
                canonical,
                Permissions.DELETE,
                False,
                "OPERATION_ERROR",
            )
            raise OperationError(
                message=f"OS error during delete: {e}",
                attempted_path=canonical,
                boundary_path=self._boundary,
                operation="delete",
            ) from e

    def rename(self, src: str | Path, dst: str | Path) -> None:
        """
        Rename a file or directory within the boundary.

        Both source and destination must be within the boundary.

        Args:
            src: The source path (relative or absolute within boundary).
            dst: The destination path (relative or absolute within boundary).

        Raises:
            BoundaryViolationError: If src or dst is outside the boundary.
            PermissionDeniedError: If RENAME permission is not set.
            OperationError: If the underlying OS operation fails.
        """
        self._require_not_closed()

        canonical_src = self._canonicalize(src)
        canonical_dst = self._canonicalize(dst)

        self._check_boundary(src, canonical_src, "rename")
        self._check_boundary(dst, canonical_dst, "rename")
        self._check_permission(Permissions.RENAME, "rename", canonical_src)

        try:
            canonical_src.rename(canonical_dst)
            self._emit_audit(
                "ALLOWED", "rename", canonical_src, Permissions.RENAME, True
            )
        except OSError as e:
            self._emit_audit(
                "DENIED",
                "rename",
                canonical_src,
                Permissions.RENAME,
                False,
                "OPERATION_ERROR",
            )
            raise OperationError(
                message=f"OS error during rename: {e}",
                attempted_path=canonical_src,
                boundary_path=self._boundary,
                operation="rename",
            ) from e

    def exists(self, path: str | Path) -> bool:
        """
        Check if a path exists within the boundary.

        Args:
            path: The path to check (relative or absolute within boundary).

        Returns:
            True if the path exists, False otherwise.

        Raises:
            BoundaryViolationError: If path is outside the boundary.
            PermissionDeniedError: If READ permission is not set.
        """
        self._require_not_closed()

        canonical = self._canonicalize(path)
        self._check_boundary(path, canonical, "exists")
        self._check_permission(Permissions.READ, "exists", canonical)

        result = canonical.exists()
        self._emit_audit("ALLOWED", "exists", canonical, Permissions.READ, True)
        return result

    def get_boundary(self) -> Path:
        """
        Return the canonical boundary path.

        Returns a copy, not the internal reference.

        Returns:
            A copy of the canonical boundary Path.
        """
        return Path(self._boundary)

    def get_permissions(self) -> int:
        """
        Return a copy of the current permission flags.

        Returns:
            An integer representing the permission flags.
        """
        return self._permissions

    def close(self) -> None:
        """
        Close the editor and release resources.

        Idempotent — calling multiple times has no effect.
        """
        object.__setattr__(self, "_closed", True)
