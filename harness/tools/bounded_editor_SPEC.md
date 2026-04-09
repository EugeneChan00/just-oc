# Bounded File Editor Tool Wrapper — Specification

## 1. Overview

**Purpose:** A sandboxed file-editor tool wrapper that restricts all file operations to a declared directory boundary. The boundary is immutable after initialization — it cannot be changed during execution. All operations that would escape the boundary are denied with structured error responses.

**File:** `harness/tools/bounded_editor.py`
**Classification:** Security-critical sandboxing primitive

---

## 2. Boundary Declaration Syntax

### 2.1 Initialization Contract

The sandbox boundary is declared **once at construction time** and **never mutates**.

```python
class BoundedEditor:
    def __init__(
        self,
        boundary_path: str | Path,
        permissions: Permissions = None,
        audit_logger: AuditLogger = None,
    ) -> None:
        ...
```

**Parameters:**
- `boundary_path: str | Path` — **Required.** The absolute filesystem path that is the root of the sandbox. All file operations are restricted to this path and its subdirectories. The path is canonicalized at init time using `Path.resolve()` (which resolves symlinks and normalizes `..`).
- `permissions: Permissions` — Optional. An immutable permission flags object (see Section 5). Defaults to `Permissions.READ | Permissions.WRITE | Permissions.APPEND | Permissions.DELETE | Permissions.RENAME` (all operations allowed within boundary).
- `audit_logger: AuditLogger` — Optional. A callable that accepts audit events. If `None`, audit events are written to `sys.stderr` in JSON lines format.

**Immutability:** After `__init__` completes, `self._boundary` is a `Path` object that MUST NOT be reassigned. Any attempt to change the boundary after construction is a logic error and must raise `BoundaryLockedError` if detected.

**Validation at init:**
- If `boundary_path` does not exist → raise `BoundaryNotFoundError` at init time
- If `boundary_path` is not a directory → raise `BoundaryNotDirectoryError` at init time
- If `boundary_path` is not absolute after canonicalization → raise `BoundaryMustBeAbsoluteError`

---

## 3. Enforcement Mechanism

### 3.1 Path Canonicalization

**Every file path** presented to any method of `BoundedEditor` is canonicalized before boundary comparison:

```python
def _canonicalize(self, path: str | Path) -> Path:
    p = Path(path)
    # Resolve symlinks and normalize .. notation
    return p.resolve()
```

This uses `Path.resolve()` which:
- Converts relative paths to absolute
- Resolves `..` components
- Resolves symlinks (including chained symlinks)
- Raises `ValueError` on empty path

### 3.2 Boundary Check Algorithm

For any operation on `target_path`:

```
1. canonical = _canonicalize(target_path)
2. boundary = self._boundary  # already canonical at init
3. if not str(canonical).startswith(str(boundary) + os.sep):
       AND canonical != boundary:
       → raise BoundaryViolationError(target_path, self._boundary)
4. else:
       → proceed with operation
```

**Note:** The `startswith` check ensures that a path like `/sandbox/../etc/passwd` resolves to `/etc/passwd` and is correctly denied, because the resolved path `/etc/passwd` does not start with `/sandbox/`.

### 3.3 Symlink Handling

Symlinks are handled at canonicalization time — `Path.resolve()` follows symlinks recursively until the final non-symlink path. This means:

- A symlink from `/sandbox/link → /etc/passwd` → operation denied
- A symlink from `/sandbox/link → /sandbox/allowed.txt` → operation allowed
- A symlink chain `/sandbox/a → /sandbox/b → /sandbox/c → /sandbox/allowed.txt` → allowed
- A symlink chain `/sandbox/a → /sandbox/b → /etc/passwd` → denied

**No symlink passthrough:** The wrapper does NOT allow operations on symlinks that point outside the boundary. The final resolved path is what matters.

### 3.4 Permission Plane (Code-Enforced)

Boundary enforcement is **100% code-enforced**. There is no prompt or prose that gates it. If the path check fails, the operation does not proceed regardless of agent intent.

---

## 4. Error Response Model

### 4.1 Error Hierarchy

```
BoundedEditorError (base)
├── BoundaryViolationError
│   ├── PathTraversalAttempt  # .. or absolute path escape
│   ├── SymlinkEscapeAttempt  # symlink resolves outside
│   └── SymlinkBoundaryBreak  # symlink points outside at check time
├── BoundaryLockedError       # attempted boundary mutation
├── BoundaryNotFoundError     # boundary directory does not exist
├── BoundaryNotDirectoryError # boundary_path is not a directory
├── BoundaryMustBeAbsoluteError
├── PermissionDeniedError     # operation not allowed by flags
└── OperationError            # underlying OS error (ENOENT, EACCES, etc.)
```

### 4.2 Error Response Format

All errors raised by `BoundedEditor` conform to this structure:

```python
@dataclass
class BoundaryViolationError(BoundedEditorError):
    code: str = "BOUNDARY_VIOLATION"
    subcode: str = "PATH_TRAVERSAL" | "SYMLINK_ESCAPE" | "SYMLINK_BOUNDARY_BREAK"
    message: str = "..."
    attempted_path: Path
    boundary_path: Path
    operation: str  # "read" | "write" | "append" | "delete" | "rename"
    timestamp: float = field(default_factory=time.time)
```

**Error message format (human-readable for agent):**
```
[BOUNDARY_VIOLATION] Operation 'write' denied: path '/etc/passwd' resolves 
outside boundary '/sandbox'. Attempted to access a path outside the declared 
sandbox boundary. This incident has been logged.
```

### 4.3 Error Handling Contract

- **All boundary violations raise structured exceptions** — never silently ignored
- **Never return `None` or a falsy value** to indicate boundary violation
- **Never print-and-continue** — the exception propagates
- **The agent sees the structured error** with `code`, `subcode`, `message`, `attempted_path`, `boundary_path`, `operation`, `timestamp`

---

## 5. Permission Flags

### 5.1 Flags Definition

```python
class Permissions:
    READ    = 1 << 0  # 1  — open file for reading, stat
    WRITE   = 1 << 1  # 2  — open file for writing (truncate), create
    APPEND  = 1 << 2  # 4  — open file for appending, create if not exist
    DELETE  = 1 << 3  # 8  — delete files and directories
    RENAME  = 1 << 4  # 16 — rename files and directories

    ALL     = READ | WRITE | APPEND | DELETE | RENAME
    NONE    = 0
```

### 5.2 Permission Enforcement

Permission checks occur **after** the boundary check, **before** the operation is attempted. If a permission flag is not set for the requested operation:

```python
if not (self._permissions & Permissions.WRITE):
    raise PermissionDeniedError(
        operation="write",
        required_permission="WRITE",
        message="Write operation denied: WRITE permission flag is not set",
    )
```

### 5.3 Default Permissions

If no `permissions` argument is provided at init, all operations are allowed **within the boundary**:
```python
permissions: Permissions = Permissions.ALL
```

---

## 6. Audit Trail

### 6.1 Audit Event Schema

Every operation (allowed or denied) emits an audit event:

```python
@dataclass
class AuditEvent:
    event_type: str       # "ALLOWED" | "DENIED"
    operation: str        # "read" | "write" | "append" | "delete" | "rename"
    path: Path            # canonical path
    boundary: Path       # the enforced boundary
    permission_used: str # "READ" | "WRITE" | "APPEND" | "DELETE" | "RENAME"
    allowed: bool
    denied_reason: str | None  # None if allowed, error code if denied
    timestamp: float
    agent_id: str | None  # if known, otherwise None
```

### 6.2 Audit Logger Interface

```python
class AuditLogger(Protocol):
    def log(self, event: AuditEvent) -> None:
        ...
```

Default implementation (when `audit_logger=None`) writes JSON lines to `sys.stderr`:
```json
{"event_type": "DENIED", "operation": "write", "path": "/etc/passwd", "boundary": "/sandbox", "allowed": false, "denied_reason": "BOUNDARY_VIOLATION", "timestamp": 1234567890.0}
```

### 6.3 What Must Be Logged

- **Every allowed operation:** operation type, canonical path, timestamp
- **Every denied operation:** operation type, canonical path, denial reason, timestamp
- **Boundary violation events:** must include the attempted path and the boundary path

---

## 7. Public API

### 7.1 Class Signature

```python
class BoundedEditor:
    def __init__(
        self,
        boundary_path: str | Path,
        permissions: Permissions = None,
        audit_logger: AuditLogger = None,
    ) -> None:
        """Initialize the bounded editor with an immutable boundary."""

    def open(self, path: str | Path, mode: str = "r") -> IOBase | TextIO:
        """Open a file within the boundary. Mode: 'r', 'w', 'a', 'r+'."""
        
    def read(self, path: str | Path) -> bytes:
        """Read entire file contents within the boundary."""
        
    def write(self, path: str | Path, content: bytes | str) -> int:
        """Write content to a file within the boundary. Creates if not exists."""
        
    def append(self, path: str | Path, content: bytes | str) -> int:
        """Append content to a file within the boundary. Creates if not exists."""
        
    def delete(self, path: str | Path) -> None:
        """Delete a file or empty directory within the boundary."""
        
    def rename(self, src: str | Path, dst: str | Path) -> None:
        """Rename a file or directory within the boundary."""
        
    def exists(self, path: str | Path) -> bool:
        """Check if a path exists within the boundary."""
        
    def get_boundary(self) -> Path:
        """Return the canonical boundary path. Returns a copy, not the internal ref."""
        
    def get_permissions(self) -> Permissions:
        """Return a copy of the current permission flags."""
        
    def close(self) -> None:
        """Close the editor and release resources. Idempotent."""
```

### 7.2 Method Behavior Summary

| Method | Permission | Boundary Check | Raises on Violation |
|--------|------------|----------------|---------------------|
| `open` | READ for 'r', WRITE for 'w', APPEND for 'a', READ\|WRITE for 'r+' | Yes | `BoundaryViolationError` |
| `read` | READ | Yes | `BoundaryViolationError` |
| `write` | WRITE | Yes | `BoundaryViolationError` |
| `append` | APPEND | Yes | `BoundaryViolationError` |
| `delete` | DELETE | Yes | `BoundaryViolationError` |
| `rename` | RENAME | Yes (both src and dst) | `BoundaryViolationError` |
| `exists` | READ | Yes | `BoundaryViolationError` |
| `get_boundary` | (none) | No | — |
| `get_permissions` | (none) | No | — |
| `close` | (none) | No | — |

---

## 8. Edge Cases

### 8.1 Path Traversal Attacks (`..` Notation)

**Attack:** `/sandbox/../../etc/passwd`
**Defense:** `Path.resolve()` normalizes `..` components before the `startswith` check. The resolved path `/etc/passwd` does not start with `/sandbox`, so the operation is denied.

### 8.2 Relative Path Attacks

**Attack:** `../../etc/passwd` with CWD set to `/sandbox`
**Defense:** `Path.resolve()` converts to absolute path using the actual CWD. If CWD is inside the sandbox, the resolved path still must pass the boundary check. If CWD is outside, the resolved absolute path is checked against the boundary and denied.

### 8.3 Symlink Escape

**Attack:** A file `/sandbox/malicious_link` is a symlink to `/etc/passwd`. Agent calls `read("/sandbox/malicious_link")`.
**Defense:** `Path.resolve()` follows the symlink and returns `/etc/passwd`. The boundary check denies it.

### 8.4 Symlink Chaining Escape

**Attack:** `/sandbox/a → /sandbox/b → /sandbox/c → /etc/passwd`
**Defense:** `Path.resolve()` follows the entire symlink chain recursively. Final resolved path is `/etc/passwd`. Denied.

### 8.5 Symlink to Directory Inside Boundary

**Attack:** `/sandbox/link → /sandbox/allowed_subdir/file.txt`
**Defense:** `Path.resolve()` resolves to `/sandbox/allowed_subdir/file.txt`. Starts with `/sandbox`. Allowed.

### 8.6 Race Conditions (TOCTOU)

**Attack:** Agent checks `exists("/sandbox/file.txt")` → allowed → then a symlink is created pointing outside before `read()` is called.
**Defense:** Every method performs its own independent canonicalization and boundary check immediately before the operation. There is no caching of path resolution between checks. The check-and-operate window is minimized to the instruction-level.

**Residual risk acknowledgment:** Python's `Path.resolve()` and `os.open()` are not atomic. For high-security environments, the caller should be informed that this is a best-effort sandbox and not a cryptographic or hard security boundary. The wrapper mitigates but does not eliminate all TOCTOU.

### 8.7 Empty Boundary

**Attack:** `BoundedEditor("")`
**Defense:** `Path.resolve()` on an empty path raises `ValueError`. Caught at init time.

### 8.8 Non-Existent Boundary

**Attack:** `BoundedEditor("/nonexistent")`
**Defense:** Checked at init time. `BoundaryNotFoundError` raised.

### 8.9 Boundary Is a File (Not Directory)

**Attack:** `BoundedEditor("/sandbox/somefile.txt")`
**Defense:** Checked at init time. `BoundaryNotDirectoryError` raised.

### 8.10 Boundary with Trailing Slash

**Attack:** `BoundedEditor("/sandbox/")` vs `BoundedEditor("/sandbox")`
**Defense:** `Path.resolve()` normalizes trailing slashes. Both resolve to `/sandbox` (no trailing slash). The `startswith(str(boundary) + os.sep)` check handles this correctly — `/sandbox/file` starts with `/sandbox/`, and `/sandbox` equals boundary directly.

### 8.11 Path with Embedded Null Byte

**Attack:** `/sandbox/file.txt\0malicious`
**Defense:** `Path()` on a string with `\0` raises `ValueError`. This is Python's built-in protection.

### 8.12 Very Deep Symlink Chain

**Attack:** A symlink chain of 100+ symlinks to escape the boundary.
**Defense:** `Path.resolve()` has a recursion limit (default Python stack). This will raise `RuntimeError: maximum recursion depth exceeded`. The error is logged and the operation denied. This is acceptable — the escape is still prevented.

### 8.13 Path Component Is a File When Directory Expected

**Attack:** `/sandbox/subdir/file.txt/../..` where `subdir` is actually a file.
**Defense:** `Path.resolve()` follows the path component by component. If a file is encountered where a directory is expected in the traversal, it is included in the resolution. The final resolved path is checked. This is acceptable Python behavior.

---

## 9. Prompt-vs-Code Classification

| Behavior | Classification | Justification |
|----------|----------------|---------------|
| Boundary declaration at init | Code-enforced | Security-critical invariant; must not be bypassable |
| Boundary immutability after init | Code-enforced | Security-critical; mutation would break sandbox |
| Path canonicalization | Code-enforced | Security-critical; must resolve every path consistently |
| Boundary check on every operation | Code-enforced | Security-critical; every operation must be checked |
| Permission flag enforcement | Code-enforced | Security-critical; determines allowed operations |
| Audit event emission | Code-enforced | Security audit trail; required for forensics |
| Error codes and structured errors | Code-enforced | Hallucination guard; agent must receive deterministic error |
| Default permissions (ALL) | Code-enforced | Default must be explicit; no silent permissive defaults |

---

## 10. Behavioral Guarantees

### 10.1 Guaranteed (Code-Enforced)

- Boundary is immutable after init
- Every file operation checks boundary before execution
- Every file operation checks permissions before execution
- Every operation emits an audit event
- Boundary violations always raise structured exceptions
- Symlinks are resolved before boundary comparison

### 10.2 Not Guaranteed (Prompt-Enforced / Acknowledged Risk)

- TOCTOU race condition elimination (mitigated but not eliminated)
- Atomicity of check-and-operate (not atomic at OS level)
- Hard security against determined kernel-level attacker (best-effort userspace sandbox)

---

## 11. Testing Interface Requirements

### 11.1 Test Fixtures the Implementation Must Support

```python
import pytest

def test_boundary_violation_on_absolute_path_escape():
    editor = BoundedEditor("/sandbox")
    with pytest.raises(BoundaryViolationError) as exc_info:
        editor.read("/etc/passwd")
    assert exc_info.value.subcode == "PATH_TRAVERSAL"

def test_boundary_violation_on_dotdot_traversal():
    editor = BoundedEditor("/sandbox")
    with pytest.raises(BoundaryViolationError):
        editor.read("/sandbox/../../etc/passwd")

def test_symlink_escape_denied(tmp_path):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / "malicious_link").symlink_to("/etc/passwd")
    editor = BoundedEditor(str(sandbox))
    with pytest.raises(BoundaryViolationError) as exc_info:
        editor.read("malicious_link")
    assert exc_info.value.subcode == "SYMLINK_ESCAPE"

def test_symlink_chain_escape_denied(tmp_path):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / "a").symlink_to(sandbox / "b")
    (sandbox / "b").symlink_to("/etc/passwd")
    editor = BoundedEditor(str(sandbox))
    with pytest.raises(BoundaryViolationError):
        editor.read("a")

def test_allowed_symlink_inside_boundary(tmp_path):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / "allowed.txt").write_text("hello")
    (sandbox / "link").symlink_to(sandbox / "allowed.txt")
    editor = BoundedEditor(str(sandbox))
    content = editor.read("link")
    assert content == b"hello"

def test_permission_flags_respected(tmp_path):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    editor = BoundedEditor(str(sandbox), permissions=Permissions.READ)
    with pytest.raises(PermissionDeniedError):
        editor.write("file.txt", "content")

def test_boundary_immutable_after_init(tmp_path):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    editor = BoundedEditor(str(sandbox))
    with pytest.raises(BoundaryLockedError):
        editor._boundary = Path("/other")  # type: ignore

def test_nonexistent_boundary_raises_at_init():
    with pytest.raises(BoundaryNotFoundError):
        BoundedEditor("/nonexistent/path")

def test_file_as_boundary_raises_at_init(tmp_path):
    file_path = tmp_path / "file.txt"
    file_path.write_text("not a directory")
    with pytest.raises(BoundaryNotDirectoryError):
        BoundedEditor(str(file_path))

def test_rename_across_boundary_denied(tmp_path):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("escape")
    editor = BoundedEditor(str(sandbox))
    with pytest.raises(BoundaryViolationError):
        editor.rename("outside.txt", "sandbox/newfile.txt")
```

---

## 12. Sandbox Escape Attack Scenarios

The implementation MUST deny all of the following:

| Scenario | Attack Vector | Expected Outcome |
|----------|---------------|------------------|
| Absolute path escape | `/etc/passwd` when boundary is `/sandbox` | `BoundaryViolationError`, subcode=`PATH_TRAVERSAL` |
| Dotdot traversal | `/sandbox/../../etc/passwd` | `BoundaryViolationError`, subcode=`PATH_TRAVERSAL` |
| Relative dotdot | `../../etc/passwd` (CWD outside) | `BoundaryViolationError`, subcode=`PATH_TRAVERSAL` |
| Symlink escape | symlink inside sandbox → `/etc/passwd` | `BoundaryViolationError`, subcode=`SYMLINK_ESCAPE` |
| Symlink chain escape | chain of symlinks resolving outside | `BoundaryViolationError`, subcode=`SYMLINK_ESCAPE` |
| Symlink-to-directory inside boundary | symlink → `/sandbox/subdir/file` | Allowed |
| Permissions: write denied | `WRITE` not set, attempting `write()` | `PermissionDeniedError` |
| Permissions: delete denied | `DELETE` not set, attempting `delete()` | `PermissionDeniedError` |
| Boundary mutation attempt | `editor._boundary = Path("/new")` | `BoundaryLockedError` |
| Boundary directory deleted | `/sandbox` deleted after init | `BoundaryViolationError` on next operation (OS-level ENOENT wraps to `OperationError`) |

---

## 13. Implementation Requirements

1. **File:** `harness/tools/bounded_editor.py`
2. **Dependencies:** Standard library only (`pathlib`, `typing`, `dataclasses`, `time`, `sys`, `os`)
3. **No external packages** required
4. **Python version:** 3.10+
5. **Module must be importable** as `from harness.tools.bounded_editor import BoundedEditor, Permissions, BoundedEditorError, BoundaryViolationError, PermissionDeniedError`
6. **All exceptions must be importable** from the module
7. **Implementation must be a single file** — no splitting across multiple files
8. **Tests are NOT in scope** for this dispatch — they will be authored by `test_engineer_worker` separately

---

## 14. Deliverable

A single file `harness/tools/bounded_editor.py` containing:
- `BoundedEditor` class with all methods in Section 7
- `Permissions` flags class in Section 5
- All exception types in Section 4.1
- `AuditEvent` dataclass
- `AuditLogger` protocol
- `BoundedEditorError` base class
- All enforcement logic as specified in Sections 3 and 5
- Default audit logger that writes JSON lines to `sys.stderr`
