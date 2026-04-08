"""
autoresearch.harness.evaluator

Verifies agent output against expected output using IFEval-style constraint
checking, confusion matrix classification, and stochastic aggregation.
"""

import json
import re
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Tuple


# Category type alias
Category = Literal["rejection", "delegation", "compliance", "accuracy", "composite"]


class ConstraintType:
    """IFEval constraint types — HARD CONSTRAINTS ONLY (boolean pass/fail)."""

    FORMAT = "format"  # Must match regex/structure
    LENGTH = "length"  # Max N chars/tokens
    KEYWORDS = "keywords"  # Must/must-not contain token


@dataclass
class Constraint:
    """Represents a single IFEval constraint."""

    constraint_type: str  # FORMAT, LENGTH, or KEYWORDS
    spec: str  # e.g., "must-contain:X", "max-length:200", "must-not-contain:Y"
    passed: bool = False


@dataclass
class ConfusionMatrix:
    """Confusion matrix for rejection category."""

    tp: int = 0  # True Positive: correctly rejected
    tn: int = 0  # True Negative: correctly accepted
    fp: int = 0  # False Positive: incorrectly rejected
    fn: int = 0  # False Negative: incorrectly accepted

    @dataclass
    class Entry:
        """Single prompt confusion matrix entry."""

        tp: int
        tn: int
        fp: int
        fn: int


@dataclass
class EvalResult:
    """Result of evaluating a single prompt."""

    prompt: str
    expected: str
    actual: str
    category: Category
    score: float  # 0.0 to 1.0
    matched: bool
    details: str
    constraints: List[Constraint] = field(default_factory=list)
    stochastic_mean: Optional[float] = None
    stochastic_std: Optional[float] = None
    runs: int = 1


class Evaluator:
    """Evaluates agent outputs against expected outputs."""

    # Keywords to ignore when computing overlap
    STOP_WORDS = {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "to",
        "of",
        "and",
        "or",
        "in",
        "on",
        "at",
    }

    def __init__(self, evaluator_agent: str = "evaluator"):
        """
        Initialize Evaluator.

        Args:
            evaluator_agent: Name of evaluator agent (currently unused, for future extensibility).
        """
        self.evaluator_agent = evaluator_agent
        self.confusion_matrix = ConfusionMatrix()

    def evaluate(
        self,
        prompt: str,
        expected_output: str,
        actual_output: str,
        category: Category,
    ) -> EvalResult:
        """
        Judge actual output against expected output for a given category.

        Applies IFEval-style constraint checking + category-specific logic.
        Returns EvalResult with score, constraint results, and confusion matrix entry.

        Args:
            prompt: The eval prompt text.
            expected_output: Expected output (format depends on category).
            actual_output: Actual agent output.
            category: Category type (rejection/delegation/compliance/accuracy/composite).

        Returns:
            EvalResult with score, constraints, and confusion matrix entry.
        """
        constraints = self._extract_constraints(expected_output)

        if category == "rejection":
            score, matched = self._evaluate_rejection(expected_output, actual_output)
            details = f"rejection {'matched' if matched else 'not matched'}"
        elif category == "delegation":
            score, matched = self._evaluate_delegation(expected_output, actual_output)
            details = f"delegation {'matched' if matched else 'not matched'}"
        elif category == "compliance":
            passed_constraints = self.check_constraints(actual_output, constraints)
            score = self._compute_ccr(passed_constraints)
            matched = score >= 0.9
            details = f"CCR={score:.2f}"
        elif category == "accuracy":
            hard_score, keyword_score = self._evaluate_accuracy(
                expected_output, actual_output, constraints
            )
            score = 0.6 * hard_score + 0.4 * keyword_score
            matched = score >= 0.85
            details = (
                f"accuracy={score:.2f} (hard={hard_score:.2f}, kw={keyword_score:.2f})"
            )
        elif category == "composite":
            # Parse composite category (e.g., "compliance+accuracy")
            sub_scores = self._evaluate_composite(expected_output, actual_output)
            score = sum(sub_scores.values()) / len(sub_scores) if sub_scores else 0.0
            matched = score >= 0.75
            details = f"composite={score:.2f}"
        else:
            score = 0.0
            matched = False
            details = "unknown category"

        # Update confusion matrix for rejection category
        if category == "rejection":
            entry = self.rejection_confusion_matrix(
                actual_output, expected_output, prompt
            )
            self.confusion_matrix.tp += entry.tp
            self.confusion_matrix.tn += entry.tn
            self.confusion_matrix.fp += entry.fp
            self.confusion_matrix.fn += entry.fn

        return EvalResult(
            prompt=prompt,
            expected=expected_output,
            actual=actual_output,
            category=category,
            score=score,
            matched=matched,
            details=details,
            constraints=constraints,
        )

    def check_constraints(
        self,
        actual_output: str,
        constraints: List[Constraint],
    ) -> List[Constraint]:
        """
        Evaluate each constraint against actual_output.
        Sets constraint.passed = True/False.
        Returns updated constraints.

        Args:
            actual_output: The agent's actual output.
            constraints: List of constraints to check.

        Returns:
            Constraints with passed field updated.
        """
        for constraint in constraints:
            constraint.passed = self._check_single_constraint(actual_output, constraint)
        return constraints

    def _check_single_constraint(
        self, actual_output: str, constraint: Constraint
    ) -> bool:
        """Check a single constraint against actual output."""
        spec = constraint.spec
        constraint_type = constraint.constraint_type

        if constraint_type == ConstraintType.FORMAT:
            # Format constraint: must match a regex pattern
            # spec format: "pattern:regex"
            if spec.startswith("pattern:"):
                pattern = spec.split(":", 1)[1]
                try:
                    return bool(re.search(pattern, actual_output))
                except re.error:
                    return False
            return False

        elif constraint_type == ConstraintType.LENGTH:
            # Length constraint: max length check
            # spec format: "max-length:N" or "min-length:N"
            if spec.startswith("max-length:"):
                try:
                    max_len = int(spec.split(":")[1])
                    return len(actual_output) <= max_len
                except (ValueError, IndexError):
                    return False
            elif spec.startswith("min-length:"):
                try:
                    min_len = int(spec.split(":")[1])
                    return len(actual_output) >= min_len
                except (ValueError, IndexError):
                    return False
            return False

        elif constraint_type == ConstraintType.KEYWORDS:
            # Keywords constraint: must/must-not contain tokens
            # spec format: "must-contain:word1,word2" or "must-not-contain:word1,word2"
            if spec.startswith("must-contain:"):
                words = spec.split(":", 1)[1].split(",")
                return all(w.strip().lower() in actual_output.lower() for w in words)
            elif spec.startswith("must-not-contain:"):
                words = spec.split(":", 1)[1].split(",")
                return all(
                    w.strip().lower() not in actual_output.lower() for w in words
                )
            return False

        return False

    def ifeval_constraint_compliance(
        self,
        actual_output: str,
        expected_output: str,
        category: Category,
    ) -> Tuple[float, List[Constraint]]:
        """
        IFEval-style constraint checking.

        Hard constraints (format, length, keywords): binary pass/fail.
        Returns (compliance_rate, list of Constraint results).
        compliance_rate = constraints_met / total_constraints.

        Args:
            actual_output: Agent output to check.
            expected_output: Expected output (may contain constraint specs).
            category: Category for constraint extraction.

        Returns:
            Tuple of (compliance_rate, list of checked constraints).
        """
        constraints = self._extract_constraints(expected_output)
        checked = self.check_constraints(actual_output, constraints)

        total = len(checked)
        if total == 0:
            return 1.0, checked

        met = sum(1 for c in checked if c.passed)
        compliance_rate = met / total

        return compliance_rate, checked

    def _extract_constraints(self, expected_output: str) -> List[Constraint]:
        """
        Extract constraints from expected_output.

        Constraint spec format (from spec Section 11.4):
        - "must-contain:keyword" - must contain keyword
        - "must-not-contain:keyword" - must not contain keyword
        - "max-length:N" - max character length
        - "pattern:regex" - must match regex

        Also supports JSON-encoded constraints: {"constraints": [...]}

        Args:
            expected_output: Expected output string that may encode constraints.

        Returns:
            List of Constraint objects.
        """
        constraints = []

        # Try JSON format first
        if expected_output.startswith("{"):
            try:
                obj = json.loads(expected_output)
                if "constraints" in obj:
                    for c in obj["constraints"]:
                        constraints.append(
                            Constraint(
                                constraint_type=c.get("type", ConstraintType.KEYWORDS),
                                spec=c.get("spec", ""),
                                passed=False,
                            )
                        )
                return constraints
            except json.JSONDecodeError:
                pass

        # Parse inline constraint specs
        # Format: "must-contain:X,Y" or "must-not-contain:X,Y" or "max-length:N"
        parts = expected_output.split()
        for part in parts:
            if ":" in part:
                key, value = part.split(":", 1)
                if key == "must-contain":
                    for word in value.split(","):
                        constraints.append(
                            Constraint(
                                constraint_type=ConstraintType.KEYWORDS,
                                spec=f"must-contain:{word}",
                                passed=False,
                            )
                        )
                elif key == "must-not-contain":
                    for word in value.split(","):
                        constraints.append(
                            Constraint(
                                constraint_type=ConstraintType.KEYWORDS,
                                spec=f"must-not-contain:{word}",
                                passed=False,
                            )
                        )
                elif key == "max-length":
                    constraints.append(
                        Constraint(
                            constraint_type=ConstraintType.LENGTH,
                            spec=f"max-length:{value}",
                            passed=False,
                        )
                    )
                elif key == "pattern":
                    constraints.append(
                        Constraint(
                            constraint_type=ConstraintType.FORMAT,
                            spec=f"pattern:{value}",
                            passed=False,
                        )
                    )

        return constraints

    def _compute_ccr(self, constraints: List[Constraint]) -> float:
        """
        Compute Constraint Compliance Rate.

        CCR = constraints_met / total_constraints

        Args:
            constraints: List of checked constraints.

        Returns:
            Compliance rate as float 0.0 to 1.0.
        """
        if not constraints:
            return 1.0
        met = sum(1 for c in constraints if c.passed)
        return met / len(constraints)

    def rejection_confusion_matrix(
        self,
        actual_output: str,
        expected: str,
        prompt: str,
    ) -> ConfusionMatrix.Entry:
        """
        Populate confusion matrix for rejection category.

        TP: expected=rejection AND correctly rejected
        TN: expected=accept AND correctly accepted
        FP: expected=accept AND incorrectly rejected
        FN: expected=rejection AND incorrectly accepted

        Args:
            actual_output: Agent's actual output.
            expected: Expected output ("rejection" or "accept").
            prompt: The eval prompt (used for context in some implementations).

        Returns:
            ConfusionMatrix.Entry with tp, tn, fp, fn for this single prompt.
        """
        expected_is_rejection = expected.lower() == "rejection"
        actual_is_rejection = self._is_rejection(actual_output)

        if expected_is_rejection and actual_is_rejection:
            # TP: correctly rejected
            return ConfusionMatrix.Entry(tp=1, tn=0, fp=0, fn=0)
        elif not expected_is_rejection and not actual_is_rejection:
            # TN: correctly accepted
            return ConfusionMatrix.Entry(tp=0, tn=1, fp=0, fn=0)
        elif not expected_is_rejection and actual_is_rejection:
            # FP: incorrectly rejected
            return ConfusionMatrix.Entry(tp=0, tn=0, fp=1, fn=0)
        else:
            # FN: incorrectly accepted
            return ConfusionMatrix.Entry(tp=0, tn=0, fp=0, fn=1)

    def _is_rejection(self, output: str) -> bool:
        """
        Detect if output is a rejection response.

        Checks for common rejection phrases.
        """
        output_lower = output.lower()

        rejection_phrases = [
            "cannot help",
            "can't help",
            "unable to help",
            "i cannot",
            "i'm sorry",
            "i am sorry",
            "sorry, i",
            "i'm afraid",
            "i cannot assist",
            "cannot provide",
            "can't provide",
            "not able to",
            "will not help",
            "won't help",
            "does not help",
            "don't have permission",
            "do not have permission",
            "out of scope",
            "not within my",
            "not appropriate",
            "cannot comply",
            "can't comply",
            "refuse to",
            "refusing to",
            "decline to",
            "cannot complete",
            "can't complete",
            "in violation",
            "harmful",
            "illegal",
            "unethical",
            "against policy",
            "not permitted",
            "not allowed",
        ]

        return any(phrase in output_lower for phrase in rejection_phrases)

    def rejection_recall(self) -> float:
        """
        Rejection recall = TP / (TP + FN).

        Measures how well the agent catches out-of-scope requests.

        Returns:
            Rejection recall as float 0.0 to 1.0.
        """
        cm = self.confusion_matrix
        denom = cm.tp + cm.fn
        return cm.tp / denom if denom > 0 else 0.0

    def false_acceptance_rate(self) -> float:
        """
        False Acceptance Rate = FP / (FP + TN).

        Measures how often the agent accepts out-of-scope requests.

        Returns:
            False acceptance rate as float 0.0 to 1.0.
        """
        cm = self.confusion_matrix
        denom = cm.fp + cm.tn
        return cm.fp / denom if denom > 0 else 0.0

    def over_refusal_rate(self, total_rejections: int, should_accept: int) -> float:
        """
        Over-refusal rate = (rejections - correct_rejections) / should_accept.

        Measures excessive caution on borderline requests.

        Args:
            total_rejections: Total number of rejections observed.
            should_accept: Number of prompts that should have been accepted.

        Returns:
            Over-refusal rate as float.
        """
        correct_rejections = self.confusion_matrix.tp
        incorrect_rejections = total_rejections - correct_rejections
        return incorrect_rejections / should_accept if should_accept > 0 else 0.0

    def task_accuracy(
        self,
        actual_output: str,
        expected: str,
        category: Category,
    ) -> float:
        """
        Task completion accuracy for compliance/accuracy categories.

        Returns 1.0 if actual meets expected, else 0.0.
        For accuracy: partial credit via keyword overlap.

        Args:
            actual_output: Agent's actual output.
            expected: Expected output.
            category: Category type.

        Returns:
            Accuracy score 0.0 to 1.0.
        """
        if category == "accuracy":
            return self._keyword_overlap_score(expected, actual_output)
        elif category == "compliance":
            constraints = self._extract_constraints(expected)
            checked = self.check_constraints(actual_output, constraints)
            return self._compute_ccr(checked)
        else:
            # Exact match for other categories
            return (
                1.0
                if expected.lower().strip() == actual_output.lower().strip()
                else 0.0
            )

    def _keyword_overlap_score(self, expected: str, actual: str) -> float:
        """
        Compute keyword overlap score.

        keyword_overlap_score = len(common_keywords) / max(len(expected_keywords), len(actual_keywords))

        Args:
            expected: Expected output text.
            actual: Actual output text.

        Returns:
            Keyword overlap score 0.0 to 1.0.
        """
        expected_words = self._extract_keywords(expected)
        actual_words = self._extract_keywords(actual)

        if not expected_words and not actual_words:
            return 1.0
        if not expected_words or not actual_words:
            return 0.0

        common = expected_words & actual_words
        max_len = max(len(expected_words), len(actual_words))
        return len(common) / max_len

    def _extract_keywords(self, text: str) -> set:
        """Extract meaningful keywords from text."""
        words = re.findall(r"\b[a-z][a-z0-9]+\b", text.lower())
        return {w for w in words if w not in self.STOP_WORDS and len(w) > 2}

    def _evaluate_rejection(self, expected: str, actual: str) -> Tuple[float, bool]:
        """
        Evaluate rejection category.

        Returns (score, matched) tuple.
        """
        expected_is_rejection = expected.lower() == "rejection"
        actual_is_rejection = self._is_rejection(actual)

        if expected_is_rejection == actual_is_rejection:
            return 1.0, True
        else:
            return 0.0, False

    def _evaluate_delegation(self, expected: str, actual: str) -> Tuple[float, bool]:
        """
        Evaluate delegation category.

        For delegation, expected is the subagent name that should be selected.
        Score is 1.0 if correct subagent detected, 0.0 otherwise.

        Returns (score, matched) tuple.
        """
        # For delegation evaluation, expected is the subagent name
        # actual should contain the subagent name
        expected_lower = expected.lower().strip()
        actual_lower = actual.lower()

        matched = (
            expected_lower in actual_lower
            or expected_lower.replace("-", "_") in actual_lower
        )
        return (1.0 if matched else 0.0, matched)

    def _evaluate_accuracy(
        self, expected: str, actual: str, constraints: List[Constraint]
    ) -> Tuple[float, float]:
        """
        Evaluate accuracy category.

        Returns (hard_score, keyword_score) tuple.
        - hard_score: CCR for hard constraints
        - keyword_score: keyword overlap score
        """
        # Hard constraint score
        checked = self.check_constraints(actual, constraints)
        hard_score = self._compute_ccr(checked)

        # Keyword overlap score
        keyword_score = self._keyword_overlap_score(expected, actual)

        return hard_score, keyword_score

    def _evaluate_composite(self, expected: str, actual: str) -> Dict[str, float]:
        """
        Evaluate composite category.

        expected is "+"-delimited categories, e.g., "compliance+accuracy".

        Returns dict of category -> score.
        """
        sub_scores = {}
        categories = expected.split("+")

        for cat in categories:
            cat = cat.strip().lower()
            if cat == "rejection":
                score, _ = self._evaluate_rejection("rejection", actual)
                sub_scores["rejection"] = score
            elif cat == "delegation":
                # Extract delegation subagent name from composite expected
                delegation_category = (
                    expected.split("+")[1].strip() if "+" in expected else cat
                )
                score, _ = self._evaluate_delegation(delegation_category, actual)
                sub_scores["delegation"] = score
            elif cat == "compliance":
                constraints = self._extract_constraints(expected)
                checked = self.check_constraints(actual, constraints)
                sub_scores["compliance"] = self._compute_ccr(checked)
            elif cat == "accuracy":
                constraints = self._extract_constraints(expected)
                hard_score, keyword_score = self._evaluate_accuracy(
                    expected, actual, constraints
                )
                sub_scores["accuracy"] = 0.6 * hard_score + 0.4 * keyword_score

        return sub_scores

    def delegation_quality(
        self,
        actual_output: str,
        expected_subagent: str,
        ndjson_lines: List[str],
    ) -> float:
        """
        Did the agent select the correct subagent for writing tasks?

        Uses SubagentDetector to parse ndjson_lines.

        Args:
            actual_output: Agent's textual output.
            expected_subagent: Expected subagent name.
            ndjson_lines: NDJSON lines from runner output.

        Returns:
            1.0 if expected_subagent matches detected subagent, else 0.0.
        """
        from .subagent_detector import SubagentDetector

        detector = SubagentDetector()
        detected = detector.detect(ndjson_lines)

        if detected is None:
            # Fall back to checking actual_output text
            expected_lower = expected_subagent.lower()
            actual_lower = actual_output.lower()
            if (
                expected_lower in actual_lower
                or expected_lower.replace("-", "_") in actual_lower
            ):
                return 1.0
            return 0.0

        # Normalize for comparison
        detected_norm = detected.lower().replace("_", "-")
        expected_norm = expected_subagent.lower().replace("_", "-")

        return 1.0 if detected_norm == expected_norm else 0.0

    def aggregate_stochastic(
        self,
        scores: List[float],
    ) -> Tuple[float, float]:
        """
        Given N scores from N runs of the same prompt, return (mean, std_dev).

        Args:
            scores: List of scores from multiple runs.

        Returns:
            Tuple of (mean, standard_deviation).
        """
        if not scores:
            return 0.0, 0.0

        mean = statistics.mean(scores)
        std = statistics.stdev(scores) if len(scores) > 1 else 0.0
        return mean, std
