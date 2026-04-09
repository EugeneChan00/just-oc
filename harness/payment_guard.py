"""
Payment Guard — Hallucination validation for payment_processor dispatch flow.

This module is a DETERMINISTIC Python guard (NO LLM calls).
It validates LLM-extracted payment parameters before the API call.

PLANE ALLOCATION:
- Permission/policy plane: gate/kill decision on payment API call
- Execution plane: validation logic implementation

PROMPT-VS-CODE CLASSIFICATION (per-requirement justification):

1. AMOUNT RANGE VALIDATION -> CODE-ENFORCED
   Justification: Exact numeric comparison (amount >= min AND amount <= max) requires
   deterministic arithmetic. An LLM cannot reliably compare Decimal values — it may
   hallucinate comparisons or use imprecise floating-point reasoning. Code enforcement
   guarantees the boundary check is exact and repeatable.

2. DESTINATION FORMAT VALIDATION -> CODE-ENFORCED
   Justification: Regex matching must be precise and deterministic. Prose like "validate
   the account looks right" leaves format interpretation to the LLM, which may accept
   malformed identifiers or reject valid ones based on creative interpretation.
   Regex in code is exact and cannot be "creatively interpreted."

3. SEMANTIC CROSS-CHECK -> CODE-ENFORCED
   Justification: Verifying that the extracted amount appears in the original instruction
   via normalized numeric matching must be deterministic. An LLM checking its own output
   creates a hallucination-checking-hallucination problem. The guard must perform exact
   substring-to-Decimal comparison without LLM involvement.

4. AUDIT LOGGING -> CODE-ENFORCED
   Justification: Structured logging requires deterministic, machine-readable output
   (dict format with fixed schema). An LLM deciding "what to log" could omit critical
   fields, add spurious fields, or mangle timestamps. Code enforcement guarantees
   every validation event produces a complete, schema-compliant log entry.

5. GATE DECISION (pass/fail) -> CODE-ENFORCED
   Justification: The guard's role as a gate between LLM output and API call requires
   a deterministic, binary decision. If the LLM could "creatively interpret" a pass,
   it could override the guard entirely. The gate must be a hard wall: pass or fail,
   nothing in between, nothing overrideable by the LLM.

WRITE BOUNDARY: harness/payment_guard.py ONLY.
No modifications to payment_processor agent prompt or any other file.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationConfig:
    """Configurable bounds and formats for payment validation.

    All fields are immutable after construction to prevent runtime mutation
    of validation thresholds — a determined caller cannot circumvent the
    guard by modifying config after construction.
    """

    min_amount: Decimal = Decimal("0.01")
    max_amount: Decimal = Decimal("10000.00")
    account_pattern: str = r"^\d{4}$"  # default: 4-digit numeric suffix

    def __post_init__(self) -> None:
        """Validate config invariants at construction time."""
        if self.min_amount <= 0:
            raise ValueError("min_amount must be positive")
        if self.max_amount < self.min_amount:
            raise ValueError("max_amount must be >= min_amount")
        # Compile and discard to validate regex; store raw string for reproducibility
        re.compile(self.account_pattern)


# ------------------------------------------------------------------------------
# Data Structures
# ------------------------------------------------------------------------------


@dataclass
class ExtractedPaymentParams:
    """The parameters extracted from the LLM's interpretation of the instruction."""

    amount: Decimal
    destination_account: str
    original_instruction: str


@dataclass
class ValidationResult:
    """Structured validation result returned to the calling harness.

    The harness reads `passed` to gate/kill the API call. `error` and
    `failure_reasons` provide machine-readable details for audit and debugging.
    """

    passed: bool
    error: Optional[str] = None
    extracted_params: Optional[ExtractedPaymentParams] = None
    failure_reasons: tuple[str, ...] = field(default_factory=tuple)


# ------------------------------------------------------------------------------
# Audit Logger
# ------------------------------------------------------------------------------

# Structured dict-based logger; handler must be configured by the calling harness.
# Using a named logger avoids polluting the root logger.
_AUDIT_LOGGER = logging.getLogger("payment_guard.audit")


def _build_audit_record(
    params: ExtractedPaymentParams,
    result: ValidationResult,
) -> dict:
    """Build a complete, schema-compliant audit record dictionary."""
    return {
        "event": "payment_guard_validation",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "original_instruction": params.original_instruction,
        "extracted_amount": str(params.amount),
        "extracted_destination": params.destination_account,
        "validation_passed": result.passed,
        "error": result.error,
        "failure_reasons": list(result.failure_reasons),
    }


def _emit_audit_log(params: ExtractedPaymentParams, result: ValidationResult) -> None:
    """Emit a structured audit log entry for every validation event (pass or fail)."""
    record = _build_audit_record(params, result)
    # Use exc_info=False; the record dict carries all context
    _AUDIT_LOGGER.info("", extra=record)


# ------------------------------------------------------------------------------
# Amount Format Helpers (for semantic cross-check)
# ------------------------------------------------------------------------------

# Regex patterns for extracting candidate amount strings from natural language.
_AMOUNT_PATTERNS: list[tuple[str, str]] = [
    # ($500), ($500.00), ($500.0)
    (r"\$\s*(\d+(?:\.\d{1,2})?)", "dollar"),
    # 500$, 500.00$ (space-tolerant)
    (r"(\d+(?:\.\d{1,2})?)\s*\$", "dollar"),
    # Plain numbers: 500, 500.00, 500.0
    (r"(?<!\w)(\d+(?:\.\d{1,2})?)(?!\w)", "plain"),
    # Words: five hundred, fifty (singular/plural handled by simple replace)
    # Added dynamically below.
]

# Word-to-digit lookup for common English number words.
_DIGIT_WORDS: dict[str, int] = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    "hundred": 100,
    "thousand": 1000,
}

# Currency words to strip before English number parsing.
_CURRENCY_WORDS: frozenset[str] = frozenset(
    {
        "dollar",
        "dollars",
        "cent",
        "cents",
        "pound",
        "pounds",
        "euro",
        "euros",
        "yen",
        "buck",
        "bucks",
    }
)


def _text2number_from_tokens(tokens: list[str]) -> Optional[Decimal]:
    """Convert a pre-tokenized list to a Decimal if it forms a valid number phrase.

    Operates on already-split tokens. This avoids the join-reparse problem where
    "five hundred dollars" would become "five hundred" after stripping, losing
    the signal that the original phrase contained a currency word.

    Returns None if the tokens cannot be parsed as a number phrase.
    This is deterministic and requires no LLM.
    """
    total: int = 0
    current: int = 0

    for token in tokens:
        if token in _DIGIT_WORDS:
            val = _DIGIT_WORDS[token]
            if val == 100:
                current = current * 100 if current else 100
            elif val == 1000:
                current = current * 1000 if current else 1000
                total += current
                current = 0
            else:
                current += val
        else:
            return None  # Unrecognized token

    total += current
    if total == 0:
        return None
    return Decimal(total)


def _extract_candidate_decimals(instruction: str) -> set[Decimal]:
    """Extract all candidate Decimal values that could represent amounts in the instruction.

    This is a deterministic string-parsing function — no LLM involved.
    It finds all substrings matching amount-like patterns and parses them
    as Decimal values. The set eliminates duplicates.
    """
    candidates: set[Decimal] = set()

    # --- Pattern-based extraction ---
    for pattern, _ in _AMOUNT_PATTERNS:
        for match in re.finditer(pattern, instruction, re.IGNORECASE):
            try:
                val = Decimal(match.group(1))
                if val > 0:
                    candidates.add(val)
            except (InvalidOperation, ValueError):
                continue

    # --- English number words extraction ---
    # Split into word tokens, then examine each token and consecutive sequences
    # as potential number phrases. This avoids the "join-reparse" problem.
    all_tokens: list[str] = re.split(r"[\s\-]+", instruction.lower())
    for start in range(len(all_tokens)):
        for end in range(start + 1, len(all_tokens) + 1):
            segment = all_tokens[start:end]
            # Skip if any token is a currency word (not part of a number phrase)
            if any(t in _CURRENCY_WORDS for t in segment):
                continue
            num = _text2number_from_tokens(segment)
            if num is not None and num > 0:
                candidates.add(num)

    return candidates


# ------------------------------------------------------------------------------
# Core Validation Functions
# ------------------------------------------------------------------------------


def _validate_amount_range(
    amount: Decimal,
    config: ValidationConfig,
) -> tuple[bool, str]:
    """Validate amount is strictly within [min_amount, max_amount]."""
    if amount < config.min_amount:
        return False, (f"amount {amount} is below minimum allowed {config.min_amount}")
    if amount > config.max_amount:
        return False, (f"amount {amount} exceeds maximum allowed {config.max_amount}")
    return True, ""


def _validate_account_format(
    account: str,
    config: ValidationConfig,
) -> tuple[bool, str]:
    """Validate destination account identifier against configured regex pattern."""
    pattern = config.account_pattern
    if not re.fullmatch(pattern, account):
        return False, (
            f"destination_account '{account}' does not match required format "
            f"pattern '{pattern}'"
        )
    return True, ""


def _semantic_cross_check(
    extracted_amount: Decimal,
    original_instruction: str,
) -> tuple[bool, str]:
    """Verify extracted amount appears verbatim (or in equivalent numeric form) in instruction.

    Algorithm:
    1. Extract all candidate Decimal values from the original instruction text
       using deterministic regex patterns and English number-word parsing.
    2. Compare extracted_amount against each candidate using Decimal equality
       (handles $500 vs 500.00 equivalence natively).
    3. If any candidate equals extracted_amount, the semantic check PASSES.
    4. If no candidate matches, the check FAILS — the LLM may have hallucinated
       an amount not present in the user's instruction.

    This is CODE-ENFORCED because:
    - String extraction uses exact regex — no LLM interpretation
    - Decimal comparison is exact arithmetic — no floating-point drift
    - An LLM-checking-hallucination problem is avoided by not using an LLM here
    """
    candidates = _extract_candidate_decimals(original_instruction)

    # Normalize to compare: both must be positive
    if extracted_amount <= 0:
        return False, f"extracted amount {extracted_amount} is not positive"

    for candidate in candidates:
        if candidate == extracted_amount:
            return True, ""  # Match found

    return False, (
        f"extracted amount {extracted_amount} not found verbatim in "
        f"original instruction; possible hallucination"
    )


# ------------------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------------------


def validate_payment_guard(
    amount: Decimal,
    destination_account: str,
    original_instruction: str,
    config: Optional[ValidationConfig] = None,
) -> ValidationResult:
    """Main guard entry point.

    Validates LLM-extracted payment parameters against all configured rules,
    logs the result, and returns a structured ValidationResult.

    This function is DETERMINISTIC: no LLM calls, no randomness, no mutation
    of inputs. The same inputs always produce the same result.

    Parameters
    ----------
    amount: Decimal
        The payment amount extracted by the LLM from the user's instruction.
    destination_account: str
        The destination account identifier extracted by the LLM.
    original_instruction: str
        The original natural-language instruction from the user (for semantic
        cross-check and audit logging).
    config: ValidationConfig, optional
        Validation bounds and patterns. Uses defaults if not provided.

    Returns
    -------
    ValidationResult
        passed: bool — True only if ALL validations pass
        error: Optional[str] — human-readable error summary (first failure)
        failure_reasons: tuple[str, ...] — all individual failure reasons
        extracted_params: ExtractedPaymentParams — echo back inputs for audit

    The calling harness MUST check result.passed before calling the payment API.
    The guard itself NEVER calls the payment API.
    """
    if config is None:
        config = ValidationConfig()

    params = ExtractedPaymentParams(
        amount=amount,
        destination_account=destination_account,
        original_instruction=original_instruction,
    )

    failure_reasons: list[str] = []

    # --- Check 1: Account format ---
    ok, err = _validate_account_format(destination_account, config)
    if not ok:
        failure_reasons.append(f"account_format: {err}")

    # --- Check 2: Amount range ---
    ok, err = _validate_amount_range(amount, config)
    if not ok:
        failure_reasons.append(f"amount_range: {err}")

    # --- Check 3: Semantic cross-check ---
    ok, err = _semantic_cross_check(amount, original_instruction)
    if not ok:
        failure_reasons.append(f"semantic_cross_check: {err}")

    # --- Assemble result ---
    if failure_reasons:
        result = ValidationResult(
            passed=False,
            error=f"{len(failure_reasons)} validation(s) failed; see failure_reasons",
            extracted_params=params,
            failure_reasons=tuple(failure_reasons),
        )
    else:
        result = ValidationResult(
            passed=True,
            error=None,
            extracted_params=params,
            failure_reasons=(),
        )

    # --- Audit log (every event, pass or fail) ---
    _emit_audit_log(params, result)

    return result
