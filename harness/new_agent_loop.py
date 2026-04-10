"""
harness/new_agent_loop.py

Event loop harness for the new_agent_worker.
Implements the data transformation pipeline agent's event loop with:
- Input validation against InputSchema
- Output validation against OutputSchema
- Recursion bounds enforcement (max 10 iterations, 1000 records/iteration, 10000 total)
- Error injection testing capabilities
- Performance benchmarking hooks

WRITE BOUNDARY: harness/new_agent_loop.py ONLY.
No modifications to any other file.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional


# ------------------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------------------

MAX_ITERATIONS: int = 10
MAX_RECORDS_PER_ITERATION: int = 1000
MAX_TOTAL_RECORDS: int = 10000
MAX_NESTING_DEPTH: int = 2
MAX_FIELD_COUNT: int = 100
MAX_STRING_LENGTH: int = 10000


# ------------------------------------------------------------------------------
# Error Codes
# ------------------------------------------------------------------------------


class ErrorCode(Enum):
    E_PARSE_ERROR = "E_PARSE_ERROR"
    E_NO_SCHEMA = "E_NO_SCHEMA"
    E_BINARY_DATA = "E_BINARY_DATA"
    E_EXCEEDS_MAX_RECORDS = "E_EXCEEDS_MAX_RECORDS"
    E_NESTING_EXCEEDED = "E_NESTING_EXCEEDED"
    E_SECURITY_RISK = "E_SECURITY_RISK"
    E_MISSING_FIELD = "E_MISSING_FIELD"
    E_TYPE_MISMATCH = "E_TYPE_MISMATCH"
    E_OUT_OF_RANGE = "E_OUT_OF_RANGE"
    E_OUTPUT_VALIDATION_FAILED = "E_OUTPUT_VALIDATION_FAILED"
    E_ITERATION_LIMIT = "E_ITERATION_LIMIT"
    E_RECORDS_PER_ITER_LIMIT = "E_RECORDS_PER_ITER_LIMIT"
    E_TOTAL_RECORDS_LIMIT = "E_TOTAL_RECORDS_LIMIT"


# ------------------------------------------------------------------------------
# Status Types
# ------------------------------------------------------------------------------


class StatusType(Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"


# ------------------------------------------------------------------------------
# Data Structures
# ------------------------------------------------------------------------------


@dataclass
class TransformStats:
    """Statistics for a transformation batch."""

    input_count: int = 0
    output_count: int = 0
    dropped_count: int = 0
    error_count: int = 0

    def to_dict(self) -> dict:
        return {
            "input_count": self.input_count,
            "output_count": self.output_count,
            "dropped_count": self.dropped_count,
            "error_count": self.error_count,
        }


@dataclass
class RecordMetadata:
    """Metadata for a transformed record."""

    transform_applied: List[str] = field(default_factory=list)
    input_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "transform_applied": self.transform_applied,
            "input_hash": self.input_hash,
        }


@dataclass
class TransformedRecord:
    """A single transformed record."""

    id: str
    fields: dict
    metadata: RecordMetadata

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "fields": self.fields,
            "metadata": self.metadata.to_dict(),
        }


@dataclass
class OutputEnvelope:
    """Output envelope conforming to OutputSchema."""

    output_type: str = "TRANSFORMED_RECORDS"
    record_count: int = 0
    records: List[dict] = field(default_factory=list)
    transform_stats: TransformStats = field(default_factory=TransformStats)
    status: StatusType = StatusType.SUCCESS
    error_code: Optional[str] = None
    error_detail: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "output_type": self.output_type,
            "record_count": self.record_count,
            "records": self.records,
            "transform_stats": self.transform_stats.to_dict(),
            "status": self.status.value,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
        }


@dataclass
class PerformanceStats:
    """Performance benchmarking stats."""

    total_processing_time_ms: float = 0.0
    records_per_second: float = 0.0
    iteration_count: int = 0
    memory_usage_bytes: int = 0


# ------------------------------------------------------------------------------
# Error Injection Controller
# ------------------------------------------------------------------------------


class ErrorInjector:
    """Controls error injection for testing."""

    def __init__(self):
        self._lock = threading.Lock()
        self._injections: List[
            tuple[str, Optional[int]]
        ] = []  # (error_type, at_iteration)
        self._injected_count: dict[str, int] = {}
        self._enabled = False

    def inject_error(self, error_type: str, at_iteration: Optional[int] = None) -> None:
        """Register an error to inject."""
        with self._lock:
            self._injections.append((error_type, at_iteration))
            self._injected_count[error_type] = (
                self._injected_count.get(error_type, 0) + 1
            )
            self._enabled = True

    def should_inject(self, error_type: str, current_iteration: int) -> bool:
        """Check if an error should be injected at current iteration."""
        if not self._enabled:
            return False
        with self._lock:
            for err_type, at_iter in self._injections:
                if err_type == error_type:
                    if at_iter is None or at_iter == current_iteration:
                        return True
            return False

    def clear(self) -> None:
        """Clear all injected errors."""
        with self._lock:
            self._injections.clear()
            self._injected_count.clear()
            self._enabled = False

    def get_injected_count(self, error_type: str) -> int:
        """Return how many times an error type was injected."""
        with self._lock:
            return self._injected_count.get(error_type, 0)


# ------------------------------------------------------------------------------
# Schema Validators
# ------------------------------------------------------------------------------


class SchemaValidator:
    """Validates input and output against schemas."""

    @staticmethod
    def compute_input_hash(record: dict) -> str:
        """Compute SHA-256 hash of a record for input_hash field."""
        record_str = json.dumps(record, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(record_str.encode("utf-8")).hexdigest()

    @staticmethod
    def validate_input_schema(
        records: List[dict],
    ) -> tuple[bool, Optional[str], Optional[ErrorCode]]:
        """
        Validate input records against InputSchema.

        Returns:
            (is_valid, error_detail, error_code)
        """
        if not isinstance(records, list):
            return False, "Input must be an array", ErrorCode.E_PARSE_ERROR

        for i, record in enumerate(records):
            if not isinstance(record, dict):
                return (
                    False,
                    f"Record at index {i} must be an object",
                    ErrorCode.E_TYPE_MISMATCH,
                )

            if "id" not in record:
                return (
                    False,
                    f"Record at index {i} missing required field 'id'",
                    ErrorCode.E_MISSING_FIELD,
                )

            if "fields" not in record:
                return (
                    False,
                    f"Record at index {i} missing required field 'fields'",
                    ErrorCode.E_MISSING_FIELD,
                )

            if not isinstance(record.get("id"), str):
                return (
                    False,
                    f"Record at index {i} field 'id' must be a string",
                    ErrorCode.E_TYPE_MISMATCH,
                )

            if not isinstance(record.get("fields"), dict):
                return (
                    False,
                    f"Record at index {i} field 'fields' must be an object",
                    ErrorCode.E_TYPE_MISMATCH,
                )

            # Check field count
            if len(record["fields"]) > MAX_FIELD_COUNT:
                return (
                    False,
                    f"Record at index {i} exceeds max field count ({MAX_FIELD_COUNT})",
                    ErrorCode.E_EXCEEDS_MAX_RECORDS,
                )

            # Check string lengths and nesting depth
            for key, value in record["fields"].items():
                if isinstance(value, str) and len(value) > MAX_STRING_LENGTH:
                    return (
                        False,
                        f"Record at index {i} field '{key}' exceeds max string length ({MAX_STRING_LENGTH})",
                        ErrorCode.E_OUT_OF_RANGE,
                    )

                if isinstance(value, dict):
                    # Pass current_depth=1 because field value is inside 'fields' dict
                    depth = SchemaValidator._get_nesting_depth(value, current_depth=1)
                    if depth > MAX_NESTING_DEPTH:
                        return (
                            False,
                            f"Record at index {i} field '{key}' exceeds max nesting depth ({MAX_NESTING_DEPTH})",
                            ErrorCode.E_NESTING_EXCEEDED,
                        )

                if isinstance(value, bytes):
                    return (
                        False,
                        f"Record at index {i} field '{key}' contains binary data",
                        ErrorCode.E_BINARY_DATA,
                    )

            # Security check for executable content
            record_str = json.dumps(record)
            if any(
                exec_marker in record_str.lower()
                for exec_marker in ["<script", "javascript:", "onerror=", "onclick="]
            ):
                return (
                    False,
                    f"Record at index {i} contains potential executable content",
                    ErrorCode.E_SECURITY_RISK,
                )

        return True, None, None

    @staticmethod
    def _get_nesting_depth(obj, current_depth: int = 0) -> int:
        """Get the nesting depth of a nested dict/list structure."""
        if not isinstance(obj, (dict, list)):
            return current_depth
        if not obj:
            return current_depth
        if isinstance(obj, dict):
            max_child = current_depth + 1
            for value in obj.values():
                max_child = max(
                    max_child,
                    SchemaValidator._get_nesting_depth(value, current_depth + 1),
                )
            return max_child
        else:  # list
            max_child = current_depth + 1
            for item in obj:
                max_child = max(
                    max_child,
                    SchemaValidator._get_nesting_depth(item, current_depth + 1),
                )
            return max_child

    @staticmethod
    def validate_output_schema(envelope: dict) -> tuple[bool, Optional[str]]:
        """
        Validate output envelope against OutputSchema.

        Returns:
            (is_valid, error_detail)
        """
        required_fields = [
            "output_type",
            "record_count",
            "records",
            "transform_stats",
            "status",
        ]
        for field in required_fields:
            if field not in envelope:
                return False, f"Missing required field '{field}'"

        if envelope.get("output_type") != "TRANSFORMED_RECORDS":
            return (
                False,
                f"output_type must be 'TRANSFORMED_RECORDS', got '{envelope.get('output_type')}'",
            )

        if (
            not isinstance(envelope.get("record_count"), int)
            or envelope.get("record_count") < 0
        ):
            return False, "record_count must be a non-negative integer"

        if not isinstance(envelope.get("records"), list):
            return False, "records must be an array"

        # Validate each record
        for i, record in enumerate(envelope.get("records", [])):
            if not isinstance(record, dict):
                return False, f"Record at index {i} must be an object"

            record_required = ["id", "fields", "metadata"]
            for field in record_required:
                if field not in record:
                    return (
                        False,
                        f"Record at index {i} missing required field '{field}'",
                    )

            if not isinstance(record.get("id"), str):
                return False, f"Record at index {i} field 'id' must be a string"

            if not isinstance(record.get("fields"), dict):
                return False, f"Record at index {i} field 'fields' must be an object"

            metadata = record.get("metadata", {})
            if not isinstance(metadata, dict):
                return False, f"Record at index {i} metadata must be an object"

        # Validate transform_stats
        stats = envelope.get("transform_stats", {})
        stats_required = ["input_count", "output_count", "dropped_count", "error_count"]
        for field in stats_required:
            if field not in stats:
                return False, f"transform_stats missing required field '{field}'"
            if not isinstance(stats.get(field), int):
                return False, f"transform_stats.{field} must be an integer"

        # Validate status
        valid_statuses = ["SUCCESS", "PARTIAL", "REJECTED"]
        if envelope.get("status") not in valid_statuses:
            return (
                False,
                f"status must be one of {valid_statuses}, got '{envelope.get('status')}'",
            )

        return True, None


# ------------------------------------------------------------------------------
# Agent Process Runner
# ------------------------------------------------------------------------------


class AgentProcessRunner:
    """Manages subprocess communication with the agent executable."""

    def __init__(self, executable_path: str):
        self._executable_path = executable_path
        self._lock = threading.Lock()

    def send_to_agent(
        self, input_data: dict
    ) -> tuple[bool, Optional[dict], Optional[str]]:
        """
        Send input to agent and get response.

        Returns:
            (success, response_dict, error_detail)
        """
        with self._lock:
            try:
                # Serialize input
                input_json = json.dumps(input_data)

                # Spawn agent process
                process = subprocess.Popen(
                    [sys.executable, self._executable_path],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                )

                # Send input
                process.stdin.write(input_json)
                process.stdin.write("\n")
                process.stdin.flush()

                # Read output line
                output_line = process.stdout.readline()
                process.stdin.close()
                process.wait(timeout=30)

                if not output_line:
                    stderr = process.stderr.read()
                    return False, None, f"Agent produced no output. stderr: {stderr}"

                # Parse output
                try:
                    response = json.loads(output_line)
                    return True, response, None
                except json.JSONDecodeError as e:
                    return False, None, f"Agent output is not valid JSON: {e}"

            except subprocess.TimeoutExpired:
                process.kill()
                return False, None, "Agent process timed out after 30 seconds"
            except FileNotFoundError:
                return (
                    False,
                    None,
                    f"Agent executable not found: {self._executable_path}",
                )
            except Exception as e:
                return (
                    False,
                    None,
                    f"Agent communication error: {str(e)}\n{traceback.format_exc()}",
                )


# ------------------------------------------------------------------------------
# Error Policy
# ------------------------------------------------------------------------------


class ErrorPolicy(Enum):
    """Error handling policies."""

    REJECT = "reject"  # Reject entire batch on error
    PARTIAL = "partial"  # Allow partial output on error
    ESCALATE = "escalate"  # Escalate to lead on error


# ------------------------------------------------------------------------------
# Timeout Controller
# ------------------------------------------------------------------------------


class TimeoutController:
    """Monitors per-record timeout enforcement."""

    def __init__(self, timeout_seconds: float = 5.0):
        self._timeout_seconds = timeout_seconds
        self._lock = threading.Lock()
        self._record_times: dict[str, float] = {}
        self._timed_out_records: set[str] = set()

    def start_record(self, record_id: str) -> None:
        """Mark record processing start time."""
        with self._lock:
            self._record_times[record_id] = time.time()

    def check_record_timeout(self, record_id: str) -> bool:
        """
        Check if record has exceeded timeout.
        Returns True if timed out, False otherwise.
        """
        with self._lock:
            if record_id not in self._record_times:
                return False
            elapsed = time.time() - self._record_times[record_id]
            if elapsed > self._timeout_seconds:
                self._timed_out_records.add(record_id)
                return True
            return False

    def is_record_timed_out(self, record_id: str) -> bool:
        """Check if record was marked as timed out."""
        with self._lock:
            return record_id in self._timed_out_records

    def get_timed_out_count(self) -> int:
        """Return count of timed out records."""
        with self._lock:
            return len(self._timed_out_records)

    def reset(self) -> None:
        """Reset timeout state."""
        with self._lock:
            self._record_times.clear()
            self._timed_out_records.clear()


# ------------------------------------------------------------------------------
# Error Threshold Tracker
# ------------------------------------------------------------------------------


class ErrorThresholdTracker:
    """Tracks error rates and triggers escalation when threshold exceeded."""

    def __init__(self, threshold: float = 0.10):
        self._threshold = threshold  # 10% default
        self._lock = threading.Lock()
        self._total_records = 0
        self._failed_records = 0
        self._threshold_exceeded = False

    def record_result(self, success: bool) -> None:
        """Record whether a record was processed successfully."""
        with self._lock:
            self._total_records += 1
            if not success:
                self._failed_records += 1
            if self._total_records > 0:
                error_rate = self._failed_records / self._total_records
                if error_rate > self._threshold:
                    self._threshold_exceeded = True

    def get_error_rate(self) -> float:
        """Return current error rate."""
        with self._lock:
            if self._total_records == 0:
                return 0.0
            return self._failed_records / self._total_records

    def is_threshold_exceeded(self) -> bool:
        """Return whether error threshold has been exceeded."""
        with self._lock:
            return self._threshold_exceeded

    def get_stats(self) -> dict:
        """Return error tracking statistics."""
        with self._lock:
            return {
                "total_records": self._total_records,
                "failed_records": self._failed_records,
                "error_rate": self.get_error_rate(),
                "threshold_exceeded": self._threshold_exceeded,
                "threshold": self._threshold,
            }

    def reset(self) -> None:
        """Reset error tracking."""
        with self._lock:
            self._total_records = 0
            self._failed_records = 0
            self._threshold_exceeded = False


# ------------------------------------------------------------------------------
# Main Harness
# ------------------------------------------------------------------------------


class NewAgentHarness:
    """
    Event loop harness for new_agent_worker data transformation pipeline.

    Features:
    - Feeds input data to the agent via stdin/event
    - Captures transformed output from stdout/event
    - Validates output against OutputSchema
    - Enforces recursion bounds (max 10 iterations, max 1000 records/iteration, max 10000 total)
    - Provides error injection testing capabilities
    - Provides performance benchmarking hooks

    Attributes
    ----------
    agent_executable_path : str
        Path to the agent executable.
    """

    def __init__(self, agent_executable_path: str):
        """
        Initialize harness with path to agent executable.

        Parameters
        ----------
        agent_executable_path : str
            Path to the agent executable.
        """
        self._agent_path = agent_executable_path
        self._runner = AgentProcessRunner(agent_executable_path)
        self._error_injector = ErrorInjector()
        self._stats = PerformanceStats()
        self._lock = threading.Lock()
        self._transform_stats = TransformStats()
        self._total_records_processed = 0

    def run_batch(self, input_records: List[dict], transform_spec: dict) -> dict:
        """
        Run a batch of records through the agent.

        Args:
            input_records: List of JSON-serializable records
            transform_spec: Transformation specification dict

        Returns:
            Output envelope conforming to OutputSchema:
            {
                "output_type": "TRANSFORMED_RECORDS",
                "record_count": int,
                "records": [...],
                "transform_stats": {
                    "input_count": int,
                    "output_count": int,
                    "dropped_count": int,
                    "error_count": int
                },
                "status": "SUCCESS" | "PARTIAL" | "REJECTED",
                "error_code": str | null,
                "error_detail": str | null
            }
        """
        start_time = time.time()

        with self._lock:
            # Reset per-batch stats
            self._transform_stats = TransformStats()
            self._total_records_processed = 0
            self._stats = PerformanceStats()

            # Validate input schema
            is_valid, error_detail, error_code = SchemaValidator.validate_input_schema(
                input_records
            )
            if not is_valid:
                return self._create_rejected_envelope(
                    error_code=error_code.value
                    if error_code
                    else ErrorCode.E_PARSE_ERROR.value,
                    error_detail=error_detail or "Input validation failed",
                )

            # Check total records limit
            if len(input_records) > MAX_TOTAL_RECORDS:
                return self._create_rejected_envelope(
                    error_code=ErrorCode.E_EXCEEDS_MAX_RECORDS.value,
                    error_detail=f"Input exceeds max total records ({MAX_TOTAL_RECORDS})",
                )

            # Check records per iteration limit
            if len(input_records) > MAX_RECORDS_PER_ITERATION:
                return self._create_rejected_envelope(
                    error_code=ErrorCode.E_RECORDS_PER_ITER_LIMIT.value,
                    error_detail=f"Input exceeds max records per iteration ({MAX_RECORDS_PER_ITERATION})",
                )

            self._transform_stats.input_count = len(input_records)

            # Process in chunks of MAX_RECORDS_PER_ITERATION
            all_transformed_records: List[dict] = []
            total_dropped = 0
            total_errors = 0
            iteration = 0

            try:
                for chunk_start in range(
                    0, len(input_records), MAX_RECORDS_PER_ITERATION
                ):
                    iteration += 1

                    # Check iteration limit
                    if iteration > MAX_ITERATIONS:
                        return self._create_rejected_envelope(
                            error_code=ErrorCode.E_ITERATION_LIMIT.value,
                            error_detail=f"Exceeded max iterations ({MAX_ITERATIONS})",
                        )

                    chunk_end = min(
                        chunk_start + MAX_RECORDS_PER_ITERATION, len(input_records)
                    )
                    chunk = input_records[chunk_start:chunk_end]

                    # Check if we should inject an error
                    if self._error_injector.should_inject("E_PARSE_ERROR", iteration):
                        # Inject malformed JSON by sending a string instead of dict
                        agent_input = "NOT_VALID_JSON{"
                    elif self._error_injector.should_inject(
                        "E_TYPE_MISMATCH", iteration
                    ):
                        # Inject type mismatch by modifying a field
                        agent_input = {
                            "records": chunk,
                            "transform_spec": transform_spec,
                            "_inject_type_mismatch": True,
                        }
                    else:
                        agent_input = {
                            "records": chunk,
                            "transform_spec": transform_spec,
                        }

                    # Send to agent
                    success, response, error_msg = self._runner.send_to_agent(
                        agent_input
                    )

                    if not success:
                        total_errors += len(chunk)
                        # Continue processing other chunks
                        continue

                    # Validate agent output schema
                    is_valid_output, output_error = (
                        SchemaValidator.validate_output_schema(response)
                    )
                    if not is_valid_output:
                        total_errors += len(chunk)
                        # Continue processing
                        continue

                    # Check if we should inject output validation error
                    if self._error_injector.should_inject(
                        "E_OUTPUT_VALIDATION_FAILED", iteration
                    ):
                        response = {"invalid": "response", "with": "missing fields"}

                    # Collect transformed records
                    transformed = response.get("records", [])
                    for record in transformed:
                        # Add metadata if not present
                        if "metadata" not in record:
                            record["metadata"] = {
                                "transform_applied": [],
                                "input_hash": SchemaValidator.compute_input_hash(
                                    input_records[
                                        chunk_start + len(all_transformed_records)
                                    ]
                                    if chunk_start + len(all_transformed_records)
                                    < len(input_records)
                                    else {}
                                ),
                            }
                        all_transformed_records.append(record)

                    # Track stats
                    chunk_output_count = len(transformed)
                    chunk_dropped = len(chunk) - chunk_output_count
                    total_dropped += chunk_dropped

                # Build final output envelope
                self._transform_stats.output_count = len(all_transformed_records)
                self._transform_stats.dropped_count = total_dropped
                self._transform_stats.error_count = total_errors
                self._total_records_processed = len(all_transformed_records)

                # Determine status
                if total_errors == 0 and total_dropped == 0:
                    status = StatusType.SUCCESS
                elif total_errors == 0 and total_dropped > 0:
                    status = (
                        StatusType.SUCCESS
                    )  # Some records dropped is still success if no errors
                else:
                    status = StatusType.PARTIAL

                envelope = OutputEnvelope(
                    output_type="TRANSFORMED_RECORDS",
                    record_count=len(all_transformed_records),
                    records=all_transformed_records,
                    transform_stats=self._transform_stats,
                    status=status,
                    error_code=None,
                    error_detail=None,
                )

            except Exception as e:
                envelope = self._create_rejected_envelope(
                    error_code=ErrorCode.E_PARSE_ERROR.value,
                    error_detail=f"Unexpected error during batch processing: {str(e)}\n{traceback.format_exc()}",
                )

            # Calculate performance stats
            elapsed_time = time.time() - start_time
            self._stats.total_processing_time_ms = elapsed_time * 1000
            self._stats.iteration_count = iteration
            if elapsed_time > 0:
                self._stats.records_per_second = len(input_records) / elapsed_time
            else:
                self._stats.records_per_second = 0.0

            # Try to get memory usage (best effort)
            try:
                import resource

                usage = resource.getrusage(resource.RUSAGE_SELF)
                self._stats.memory_usage_bytes = (
                    usage.ru_maxrss * 1024
                )  # Convert to bytes
            except Exception:
                self._stats.memory_usage_bytes = 0

            return envelope.to_dict()

    def inject_error(
        self,
        error_type: str,
        context: Optional[dict] = None,
        at_iteration: Optional[int] = None,
    ) -> None:
        """
        Inject an error at specified iteration for testing.

        Error types:
            - "E_PARSE_ERROR": Malformed JSON input
            - "E_NO_SCHEMA": Input without identifiable schema
            - "E_BINARY_DATA": Binary data in field
            - "E_EXCEEDS_MAX_RECORDS": Record count > 10000
            - "E_NESTING_EXCEEDED": Document nesting depth > 2
            - "E_SECURITY_RISK": Executable content detected
            - "E_MISSING_FIELD": Required field absent
            - "E_TYPE_MISMATCH": Field type incorrect
            - "E_OUT_OF_RANGE": Numeric value outside bounds
            - "E_OUTPUT_VALIDATION_FAILED": Output schema violation
            - "E_TIMEOUT": Record timeout exceeded

        Parameters
        ----------
        error_type : str
            The type of error to inject.
        context : Optional[dict]
            Context for error injection with keys:
                - "at_iteration": int (optional) - The iteration number at which to inject
                - "record_index": int (optional) - Specific record index to fail
                - "error_message": str (optional) - Custom error message
                - "error_detail": str (optional) - Additional error details
        at_iteration : Optional[int]
            [DEPRECATED - use context dict instead] The iteration number at which to inject.

        Note: For backward compatibility, both context["at_iteration"] and the
        at_iteration kwarg are supported. The context dict takes precedence.
        """
        # Support legacy at_iteration kwarg for backward compatibility
        iteration_to_use = at_iteration
        if context and "at_iteration" in context:
            iteration_to_use = context["at_iteration"]
        self._error_injector.inject_error(error_type, iteration_to_use)

    def dispatch(
        self,
        input_data: dict,
        transform_spec: dict,
        output_schema: dict,
        error_policy: str,
    ) -> dict:
        """
        Dispatch a transformation task to new_agent_worker.

        This is the main entry point for the harness. It:
        1. Validates input data against input_schema (if provided in input_data)
        2. Applies the transformation via run_batch
        3. Validates output against output_schema
        4. Returns success/error/escalated response per Output Contract schemas

        Parameters
        ----------
        input_data : dict
            Input data with structure:
                - "records": List[dict] - Array of records to transform
                - "input_schema": dict (optional) - Schema to validate against
        transform_spec : dict
            Transformation specification with rules to apply.
        output_schema : dict
            Expected output schema to validate against.
        error_policy : str
            Error handling policy: "reject" | "partial" | "escalate"

        Returns
        -------
        dict
            Response conforming to Output Contract schemas:
            - Success: {"status": "success", "output": <data>, "metadata": {...}}
            - Error: {"status": "error", "error": {...}, "metadata": {...}}
            - Escalated: {"status": "escalated", "escalation": {...}, "partial_output": <data>, "metadata": {...}}
        """
        start_time = time.time()

        with self._lock:
            # Reset per-dispatch state
            self.reset()

            # Extract records from input_data
            records = input_data.get("records", [])
            input_schema = input_data.get("input_schema")

            # Validate input schema if provided
            if input_schema:
                is_valid = self.validate_input_schema(input_data, input_schema)
                if not is_valid:
                    return {
                        "status": "error",
                        "error": {
                            "code": ErrorCode.E_NO_SCHEMA.value,
                            "message": "Input schema validation failed",
                            "details": {"input_schema": input_schema},
                        },
                        "metadata": {
                            "records_processed": 0,
                            "records_failed": len(records),
                            "failure_reason": "Input schema validation failed",
                        },
                    }

            # Run the batch transformation
            result = self.run_batch(records, transform_spec)

            # Compute error rate from run_batch stats
            transform_stats = result.get("transform_stats", {})
            input_count = transform_stats.get("input_count", 0)
            error_count = transform_stats.get("error_count", 0)
            output_count = transform_stats.get("output_count", 0)
            error_rate = error_count / input_count if input_count > 0 else 0.0
            threshold_exceeded = error_rate > 0.10

            # Determine response status based on error policy and results
            if result["status"] == StatusType.REJECTED.value:
                if error_policy.lower() == "escalate":
                    return {
                        "status": "escalated",
                        "escalation": {
                            "reason": "Batch rejected due to error threshold or policy",
                            "context": {
                                "error_code": result.get("error_code"),
                                "error_detail": result.get("error_detail"),
                            },
                        },
                        "partial_output": None,
                        "metadata": {
                            "records_processed": result["transform_stats"][
                                "input_count"
                            ],
                            "records_succeeded": result["transform_stats"][
                                "output_count"
                            ],
                            "records_failed": result["transform_stats"]["error_count"],
                            "error_rate": error_rate,
                        },
                    }
                return {
                    "status": "error",
                    "error": {
                        "code": result.get("error_code", ErrorCode.E_PARSE_ERROR.value),
                        "message": result.get("error_detail", "Batch rejected"),
                        "details": result,
                    },
                    "metadata": {
                        "records_processed": result["transform_stats"]["input_count"],
                        "records_failed": result["transform_stats"]["error_count"],
                        "failure_reason": result.get("error_detail"),
                    },
                }

            # Check if output schema validation is needed
            if output_schema:
                is_valid_output = self.validate_output_schema(result, output_schema)
                if not is_valid_output:
                    if error_policy.lower() == "escalate":
                        return {
                            "status": "escalated",
                            "escalation": {
                                "reason": "Output schema validation failed after transformation",
                                "context": {"output_schema": output_schema},
                            },
                            "partial_output": result.get("records"),
                            "metadata": {
                                "records_processed": result["transform_stats"][
                                    "input_count"
                                ],
                                "records_succeeded": result["transform_stats"][
                                    "output_count"
                                ],
                                "records_failed": result["transform_stats"][
                                    "error_count"
                                ],
                                "error_rate": error_rate,
                            },
                        }
                    return {
                        "status": "error",
                        "error": {
                            "code": ErrorCode.E_OUTPUT_VALIDATION_FAILED.value,
                            "message": "Output schema validation failed",
                            "details": {"output_schema": output_schema},
                        },
                        "metadata": {
                            "records_processed": result["transform_stats"][
                                "input_count"
                            ],
                            "records_failed": result["transform_stats"]["error_count"],
                            "failure_reason": "Output schema validation failed",
                        },
                    }

            # Handle threshold exceeded for partial/escalate policies
            if threshold_exceeded and error_policy.lower() in ("partial", "escalate"):
                if error_policy.lower() == "escalate":
                    return {
                        "status": "escalated",
                        "escalation": {
                            "reason": f"Error threshold exceeded: {error_rate:.1%} (threshold: 10%)",
                            "context": self._error_threshold.get_stats(),
                        },
                        "partial_output": result.get("records"),
                        "metadata": {
                            "records_processed": result["transform_stats"][
                                "input_count"
                            ],
                            "records_succeeded": result["transform_stats"][
                                "output_count"
                            ],
                            "records_failed": result["transform_stats"]["error_count"],
                            "error_rate": error_rate,
                        },
                    }

            # Success case
            elapsed_ms = (time.time() - start_time) * 1000
            return {
                "status": "success",
                "output": result.get("records"),
                "metadata": {
                    "records_processed": result["transform_stats"]["input_count"],
                    "records_transformed": result["transform_stats"]["output_count"],
                    "transformation_rules_applied": list(transform_spec.keys()),
                    "processing_time_ms": int(elapsed_ms),
                },
            }

    def validate_input_schema(self, input_data: dict, input_schema: dict) -> bool:
        """
        Code-enforced input validation before agent receives data.

        Validates input_data against the provided input_schema dict.
        The schema can define:
            - Required fields
            - Field types
            - Field constraints (min/max, string length, etc.)
            - Nested object structure

        Parameters
        ----------
        input_data : dict
            Input data to validate. Expected to contain "records" key with list of records.
        input_schema : dict
            Schema definition to validate against. Format:
                {
                    "required_fields": ["id", "fields"],
                    "field_types": {"id": "string", "fields": "object"},
                    "max_field_count": 100,
                    "max_string_length": 10000,
                    "max_nesting_depth": 2
                }

        Returns
        -------
        bool
            True if input is valid against schema, False otherwise.
        """
        records = input_data.get("records", [])

        # Check required fields in schema
        required_fields = input_schema.get("required_fields", [])
        for field in required_fields:
            if field not in input_data:
                return False

        # Validate field types if specified
        field_types = input_schema.get("field_types", {})
        for field, expected_type in field_types.items():
            if field in input_data:
                value = input_data[field]
                if expected_type == "array" and not isinstance(value, list):
                    return False
                if expected_type == "object" and not isinstance(value, dict):
                    return False
                if expected_type == "string" and not isinstance(value, str):
                    return False
                if expected_type == "number" and not isinstance(value, (int, float)):
                    return False

        # Validate records array
        if not isinstance(records, list):
            return False

        # Validate each record against schema
        schema_field_count = input_schema.get("max_field_count", MAX_FIELD_COUNT)
        schema_string_length = input_schema.get("max_string_length", MAX_STRING_LENGTH)
        schema_nesting = input_schema.get("max_nesting_depth", MAX_NESTING_DEPTH)

        for i, record in enumerate(records):
            if not isinstance(record, dict):
                return False

            # Check required record fields
            for field in required_fields:
                if field not in record:
                    return False

            # Check field count
            if "fields" in record and isinstance(record["fields"], dict):
                if len(record["fields"]) > schema_field_count:
                    return False

                # Check string lengths and nesting in fields
                for key, value in record["fields"].items():
                    if isinstance(value, str) and len(value) > schema_string_length:
                        return False
                    if isinstance(value, dict):
                        depth = SchemaValidator._get_nesting_depth(
                            value, current_depth=1
                        )
                        if depth > schema_nesting:
                            return False

        return True

    def validate_output_schema(self, output_data: dict, output_schema: dict) -> bool:
        """
        Code-enforced output validation after agent produces data.

        Validates output_data against the provided output_schema dict.

        Parameters
        ----------
        output_data : dict
            Output data to validate. Expected to be the result from run_batch or similar.
        output_schema : dict
            Schema definition to validate against. Format:
                {
                    "required_fields": ["status", "records", "transform_stats"],
                    "record_required_fields": ["id", "fields", "metadata"],
                    "status_values": ["SUCCESS", "PARTIAL", "REJECTED"],
                    "max_record_count": 10000
                }

        Returns
        -------
        bool
            True if output is valid against schema, False otherwise.
        """
        # Check required top-level fields
        required_fields = output_schema.get("required_fields", [])
        for field in required_fields:
            if field not in output_data:
                return False

        # Validate status value if restricted
        status_values = output_schema.get("status_values")
        if status_values and output_data.get("status") not in status_values:
            return False

        # Validate record count if max specified
        max_count = output_schema.get("max_record_count")
        if max_count and output_data.get("record_count", 0) > max_count:
            return False

        # Validate records array structure
        records = output_data.get("records", [])
        if not isinstance(records, list):
            return False

        record_required = output_schema.get("record_required_fields", [])
        for i, record in enumerate(records):
            if not isinstance(record, dict):
                return False
            for field in record_required:
                if field not in record:
                    return False

            # Validate metadata if required
            if "metadata" in record_required:
                metadata = record.get("metadata", {})
                if not isinstance(metadata, dict):
                    return False

        # Validate transform_stats if present
        if "transform_stats" in required_fields:
            stats = output_data.get("transform_stats", {})
            if not isinstance(stats, dict):
                return False
            stats_fields = [
                "input_count",
                "output_count",
                "dropped_count",
                "error_count",
            ]
            for field in stats_fields:
                if field not in stats:
                    return False
                if not isinstance(stats[field], int):
                    return False

        return True

    def measure_performance(self) -> dict:
        """
        Return performance metrics: throughput, latency, memory usage.

        Returns
        -------
        dict
            Performance metrics with structure:
            {
                "throughput_records_per_second": float,
                "average_latency_ms": float,
                "memory_usage_bytes": int,
                "peak_memory_bytes": int,
                "total_records_processed": int,
                "total_errors": int,
                "error_rate": float
            }
        """
        with self._lock:
            stats = self.get_stats()
            processing_time = stats.get("total_processing_time_ms", 0)
            records_processed = stats.get("transform_stats", {}).get("input_count", 0)
            errors = stats.get("transform_stats", {}).get("error_count", 0)

            # Calculate throughput
            if processing_time > 0:
                throughput = (records_processed / processing_time) * 1000
            else:
                throughput = 0.0

            # Calculate average latency per record
            if records_processed > 0:
                avg_latency = processing_time / records_processed
            else:
                avg_latency = 0.0

            return {
                "throughput_records_per_second": round(throughput, 2),
                "average_latency_ms": round(avg_latency, 2),
                "memory_usage_bytes": stats.get("memory_usage_bytes", 0),
                "peak_memory_bytes": stats.get("memory_usage_bytes", 0),
                "total_records_processed": records_processed,
                "total_errors": errors,
                "error_rate": round(errors / records_processed, 4)
                if records_processed > 0
                else 0.0,
            }

    def get_stats(self) -> dict:
        """
        Return performance statistics.

        Returns:
            {
                "total_processing_time_ms": float,
                "records_per_second": float,
                "iteration_count": int,
                "memory_usage_bytes": int,
                "transform_stats": {
                    "input_count": int,
                    "output_count": int,
                    "dropped_count": int,
                    "error_count": int
                }
            }
        """
        with self._lock:
            return {
                "total_processing_time_ms": self._stats.total_processing_time_ms,
                "records_per_second": self._stats.records_per_second,
                "iteration_count": self._stats.iteration_count,
                "memory_usage_bytes": self._stats.memory_usage_bytes,
                "transform_stats": self._transform_stats.to_dict(),
            }

    def reset(self) -> None:
        """
        Reset harness state between test runs.
        """
        with self._lock:
            self._error_injector.clear()
            self._transform_stats = TransformStats()
            self._stats = PerformanceStats()
            self._total_records_processed = 0

    def _create_rejected_envelope(self, error_code: str, error_detail: str) -> dict:
        """Create a rejected output envelope."""
        envelope = OutputEnvelope(
            output_type="TRANSFORMED_RECORDS",
            record_count=0,
            records=[],
            transform_stats=self._transform_stats,
            status=StatusType.REJECTED,
            error_code=error_code,
            error_detail=error_detail,
        )
        return envelope.to_dict()

    def get_error_injection_count(self, error_type: str) -> int:
        """Return how many times an error type has been injected."""
        return self._error_injector.get_injected_count(error_type)
