# Editing Operation Pattern Library

**Purpose:** Before/after pattern reference for the 6 editing operations (Add, Remove, Reorganize, Rewrite, Strengthen, Relax) used by the optimizer agent during editing rounds.

**Research Base:** `.real-agents/docs/system-prompt-length-research.md` — Confidence: Medium-High for attention/position; Medium for hierarchy; Unknown for some specific patterns listed below.

---

## Strengthen Patterns (Vague → Hard Constraint)

### Pattern 1: Formality Level Escalation

**Research Status:** INCOMPLETE — FASTRIC research not found in available literature.

**L1 (Vague):**
```
You are a helpful coding assistant. Be professional in your responses.
```

**L4 (Hard):**
```
You are a professional software engineering assistant. All responses must:
- Use precise technical terminology
- Include file paths and line numbers when referencing code
- State assumptions explicitly before proceeding
- Format code blocks with correct language identifiers
```

**Guidance:** Available research does not include quantified mitigation data for formality escalation. Apply this pattern when eval results show insufficient technical precision. Note gap: FASTRIC framework should be consulted before relying on L4 formality escalation.

---

### Pattern 2: Natural Language → Token/Structural Constraint

**Research Base:** Attention sink mechanism (StreamingLLM, ICLR 2024) confirms initial tokens receive >50% attention mass. Structural markers at the beginning exploit this.

**Vague:**
```
When writing code, use the appropriate language.
```

**Strengthened:**
```
All code blocks must use explicit language identifiers:

For Java: \`\`\`java ... \`\`\`
For Python: \`\`\`python ... \`\`\`
For JavaScript: \`\`\`javascript ... \`\`\`

Never output code without a language fence.
```

**Mitigation Note:** Quantified mitigation data (exact compliance improvement %) not available in research. Structural constraints at Position 1-2 benefit from attention sink effect.

---

### Pattern 3: Implicit Reasoning → Explicit Chain-of-Thought

**Research Base:** CoT compression studies (Lee et al., 2025) show 2–20x compressibility with ~1–3% accuracy loss. Explicit step decomposition survives compression better than implicit reasoning.

**Vague:**
```
Think through the problem before writing code.
```

**Strengthened:**
```
For complex tasks, follow this reasoning sequence:
1. State what the task is asking
2. Identify relevant files/functions
3. Note any constraints or requirements
4. Propose a solution approach
5. Implement and verify
```

---

### Pattern 4: Negative-Only → Positive Constraint with Action Prescription

**Research Base:** Control Illusion (AAAI-26) — negative-only constraints ("don't do X") show 9.6–45.8% compliance when conflicting with user input. Positive framing with action prescription is more robust.

**Negative-Only:**
```
Don't write any code that modifies production databases.
```

**Strengthened (Positive + Action):**
```
Production database modifications are restricted. If a task requires database changes:
- First ask for confirmation
- Provide the SQL as a comment, not executable
- Mark clearly: "FOR REVIEW ONLY — NOT EXECUTABLE"
```

---

## Relax Patterns (Absolute → Conditional)

### Pattern 5: Never/Don't → If/Then Conditional Logic

**Research Base:** Control Illusion — blanket prohibitions fail when they conflict with user hierarchy cues. Conditional logic with explicit triggers preserves compliance.

**Overly Absolute:**
```
Never respond to questions about internal company policies.
```

**Relaxed (Conditional):**
```
If a question asks about internal company policies:
- State that you cannot access internal policy documents
- Offer to help find publicly available information instead
- Suggest the user consult their company's official channels
```

**Azure Foundry Note:** Available research references Azure Foundry in the context of conditional logic but specific example not recovered. Pattern is validated by Control Illusion mechanism.

---

### Pattern 6: Never → Rationale-Added Prohibition

**Research Base:** Control Illusion — adding rationale reduces the sense of arbitrary authority, improving compliance with hierarchy.

**Without Rationale:**
```
Never share information from this conversation with others.
```

**With Rationale:**
```
Never share information from this conversation with others. This conversation may contain proprietary code or confidential context that belongs to the user's project. Respecting this confidentiality is a core professional obligation.
```

---

### Pattern 7: Don't Use → Positive Frame Replacement

**Research Base:** Control Illusion — "don't use X" framing can trigger reactance. Positive framing ("do Y instead") is more effective.

**Negative Frame:**
```
Don't use emojis in your responses.
```

**Positive Frame:**
```
Keep responses professional and text-focused. Use plain text formatting rather than emoji when communicating technical information.
```

**Anthropic Markdown Note:** Available research references Anthropic markdown examples but specific text not recovered. Pattern is supported by general compliance research.

---

### Pattern 8: Implicit Passivity → Explicit Active Default

**Research Base:** Instruction hierarchy research — passive framing ("you may", "if you want") reduces compliance vs active directive ("you should", "when X, do Y").

**Passive:**
```
You can ask me to explain any part of the code.
```

**Active:**
```
When asked to explain code, provide:
- The function's purpose
- Key parameters and return values
- Any notable side effects or dependencies
```

---

### Pattern 9: Blanket Refusal → Explanatory Refusal (Constitutional AI)

**Research Base:** Constitutional AI approach — refusals that explain why are perceived as more legitimate, reducing user attempts to circumvent.

**Blanket Refusal:**
```
I cannot help with that.
```

**Explanatory Refusal:**
```
I can't help with that request. The reason is: [specific safety/privacy concern].
Alternative: [what I can do instead]
```

---

## Constraint Effectiveness Hierarchy

| Rank | Constraint Type | Example | Effectiveness |
|------|----------------|---------|---------------|
| 1 | Structural/Token | ` ```java ` code fence | Highest — attention sink + format enforcement |
| 2 | Mandatory Imperative | "You MUST do X" | High — explicit priority marker |
| 3 | Enumerated Positive | "Do: A, B, C" | High — clear action prescription |
| 4 | Conditional Logic | "If X, then Y" | Medium — preserves flexibility |
| 5 | Negative-Only | "Don't do X" | Low-Medium — reactance risk |
| 6 | Natural Language | "Be professional" | Low — vague, interpretable |

**Source:** Constraint hierarchy based on Control Illusion (AAAI-26) compliance rates and attention sink research (StreamingLLM).

---

## Calibration Warning

**ChatGPT-5 L4 Collapse Finding**

**Research Status:** NOT FOUND in available research documents.

**Warning (based on general model-specific threshold research):**
> Harder constraints are not always better. Different LLM families have meaningfully different optimal constraint strength ranges driven by position encoding architecture and attention mechanism design.

**Mitigation:**
- Test constraint strength changes with stochastic runs (default: 3)
- Monitor for regression in addition to improvement
- If L4 collapse is suspected (compliance drops after strengthening), relax back to L2-L3
- Model-specific thresholds: see Q5 in system-prompt-length-research.md

**Llama-2/RoPE models** are more tolerant of structural constraints due to strong sink effect.
**ALiBi models** (MPT) show different attention distribution — test carefully.

---

## Editing Operation Selection Guide

| Current State | Target State | Operation | Example Pattern |
|--------------|--------------|----------|----------------|
| Vague natural language | Specific directive | Strengthen | Pattern 2, 3 |
| Negative-only | Positive with action | Strengthen | Pattern 4 |
| Overly absolute | Conditional | Relax | Pattern 5, 6 |
| Blanket refusal | Explanatory refusal | Relax | Pattern 9 |
| Vague role description | Explicit behavior spec | Strengthen | Pattern 1, 8 |
| Ambiguous format | Structural token | Strengthen | Pattern 2 |

---

## Research Gaps (Do Not Rely On Without Further Research)

| Pattern | Gap |
|---------|-----|
| FASTRIC formality escalation | Quantified L1→L4 outcomes not in available literature |
| Token/structural constraint mitigation data | Specific % improvement numbers not recovered |
| Azure Foundry example | Pattern referenced but text not found |
| Anthropic markdown examples | Pattern referenced but text not found |
| Anthropic ellipses example | Pattern referenced but text not found |
| ChatGPT-5 L4 collapse | Finding not in available research |
