# Position-Aware Reorganize Guide

**Purpose:** Practical guide for the optimizer's Reorganize operation, translating U-shaped attention research into specific instruction placement rules.

**Research Base:** `.real-agents/docs/system-prompt-length-research.md` — Q2 (Attention sinks, StreamingLLM), Q7 (Position recall), Q1 (Lost in the Middle).

---

## Mechanism Summary

### Attention Sink (StreamingLLM, ICLR 2024)

**Mechanism:** SoftMax constraint requires attention scores to sum to 1. When no strong semantic match exists between query and context, excess attention must be distributed to tokens that are universally visible.

**Key Finding:** The first 4 tokens disproportionately accumulate attention weight (>50% of total attention mass) across all attention heads beyond layer 2.

```
Σ attention_scores = 1 (over all context tokens)

When no query has strong match to context:
→ Excess attention must go somewhere
→ Initial tokens are universally visible → trained sinks
→ Evicting initial tokens = perplexity collapse
```

**Implication:** Instructions at Position 1-2 receive privileged attention that the architecture cannot ignore without degrading perplexity.

---

### U-Shaped Attention Bias ("Found in the Middle")

**Source:** Liu et al. (2023), "Lost in the Middle" (TACL, arXiv:2307.03172)

**Pattern:**
- Beginning of context: High attention
- End of context: High attention  
- Middle of context: Lowest attention (dead zone)

This is a U-shaped curve, not linear degradation.

---

### Architectural Origin ("Lost in the Middle at Birth")

**Cause:** Combination of:
1. **Causal masking** — causal models attend to previous tokens but not future ones
2. **Residual connections** — initial token representations persist through layers
3. **Attention sink positional privilege** — not semantic, purely positional

**Result:** 
- **Primacy tail** — instructions at the start receive sustained attention
- **Recency delta** — recent tokens (end) receive fresh attention injection

---

## Position Priority Rule

| Position | Attention Priority | Recommendation |
|----------|-------------------|----------------|
| Position 1-2 | **Highest (Primacy)** | Place most critical instructions |
| Position -2 to -1 | **High (Recency)** | Place second-most critical instructions |
| Middle (20-80%) | **Lowest (Dead Zone)** | AVOID placing critical instructions |
| Last position | **High (Recency anchor)** | Place call-to-action, final task directive |

**Critical Instructions Include:**
- Role definition
- Safety constraints
- Core behavioral directives
- Output format requirements

---

## Before/After Reorganization Example

### Before: "Lost in Middle" Structure

```
[System prompt with ~1500 tokens]

You are a helpful coding assistant. (Position 1 - GOOD)

... [500 tokens of context, examples, backstory] ...
(Position 200-700 - DEAD ZONE - critical instruction buried here)

... [another 500 tokens] ...

CRITICAL: Never modify production code without explicit approval. (Position 1200 - GOOD but too late)
```

**Problem:** The "Never modify production code" instruction is at position 1200, but critical instructions are buried in the middle (position 200-700). Attention at position 1200 is high due to recency, but the middle-positioned content (examples, context) has already diluted attention allocation.

---

### After: Primacy + Recency Structure

```
You are a helpful coding assistant. (Position 1 - PRIMACY)

CRITICAL CONSTRAINTS:
- Never modify production code without explicit approval
- Always preserve original file structure unless explicitly asked
- If a task requires system-level changes, ask for confirmation first
(Position 2-5 - exploits attention sink)

... [non-critical context, examples, backstory] ...
(Position 100-600 - DEAD ZONE - acceptable for non-critical content)

... [secondary instructions, edge cases] ...

FINAL DIRECTIVE:
When unsure about any modification, ask before proceeding.
(Position -1 to -2 - RECENCY ANCHOR)
```

**Why It Works:**
1. Critical constraints appear at Position 1-5 → attention sink + primacy
2. Non-critical context fills the dead zone (no attention loss on critical content)
3. Final directive at recency anchor → guaranteed fresh attention injection

---

## When Reorganize Helps

**Apply Reorganize when ALL conditions are met:**
- Prompt length > 2,000 tokens
- Critical instructions currently in middle 20-80% of prompt
- Task requires faithful use of middle-placed content
- Eval results show poor compliance with middle-positioned instructions

**Indicator from eval data:**
- Accuracy sub-metrics failing for instructions that appear mid-prompt
- Delegation routing failing for instructions buried in middle

---

## When Reorganize May Not Help

**Do NOT reorganize when:**
- Prompt length < 500 tokens (position effects minimal at this length)
- Task is simple/single-step (attention allocation not a bottleneck)
- Instructions are already at edges (no reorganization needed)
- Recency is detrimental (e.g., task where first instruction must dominate)

**Warning:** Reorganizing short prompts can introduce errors without benefit.

---

## Reorganize Operation Checklist

Before applying Reorganize:

- [ ] Identify all critical instructions (role, safety, format)
- [ ] Map current positions of critical instructions
- [ ] Count total prompt tokens (use tokenizer if available)
- [ ] Calculate dead zone: tokens from 20% to 80% of length
- [ ] Check if critical instructions fall in dead zone
- [ ] Plan new positions: primacy (1-5), recency (-5 to -1)
- [ ] Move non-critical content to fill dead zone
- [ ] Add recency anchor for most important final directive

**Note:** Within-message ordering of instruction types (role→constraint→example→output_format) is empirically unstudied (Q9 gap). The primacy/recency advantage is established; optimal internal ordering within these zones is not.

---

## Research Gaps

| Gap | Implication |
|-----|-------------|
| Within-message ordering ablation | Optimal internal ordering of instructions within primacy/recency zones is empirically unstudied |
| Model-specific position sensitivity | Optimal positions may vary by model family (RoPE vs ALiBi) |
| Optimal position for instruction types | Whether formatting vs behavioral vs safety instructions benefit differently from primacy vs recency is unknown |
