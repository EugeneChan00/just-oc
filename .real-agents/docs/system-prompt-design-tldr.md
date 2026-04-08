# System Prompt Design: TL;DR Reference Card

**Full Research**: `.real-agents/docs/system-prompt-length-research.md`

---

## The Three Numbers

| What | How Many Tokens | Source |
|------|----------------|--------|
| **Instruction Saturation** | ~500–2,000 | Compliance drops beyond this (Control Illusion, AAAI-26) |
| **Density Floor** | 10–30% of current | Compression studies show 2–20x lossless compression (LLMLingua, LLMLingua-2, MemCom) |
| **Position Sweet Spot** | Beginning + End | "Lost in Middle" + StreamingLLM confirm edges > middle |

---

## Evidence Quality at a Glance

```
Attention sinks .............. ████████░░ HIGH     (StreamingLLM, ICLR 2024)
Instruction density ......... ███████░░░ MED-HIGH (LLMLingua papers)
Position effects ............ ██████░░░░ MEDIUM   ("Lost in Middle", position ≠ system prompt)
Hierarchy failures .......... ████████░░ HIGH     (Control Illusion, AAAI-26)
Model variation ............. ██████░░░░ MEDIUM   (GPT-4/Gemini unknown)
Noise tolerance ............. ░░░░░░░░░░ UNKNOWN  (Q8 blocked)
Repetition effects .......... ░░░░░░░░░░ UNKNOWN  (Q6 not completed)
```

---

## 5 Design Heuristics

### 1. Compress Before Adding
Run your prompt through LLMLingua before adding more content. 50–90% of tokens are removable with negligible accuracy loss.

### 2. Beginning = Safe Zone
System instructions at the very start benefit from the attention sink effect. This is architecturally privileged — the model cannot ignore these tokens without perplexity collapse.

### 3. End = Reinforcement Safety Net
Repeat critical instructions at the end. The recency effect means the model will attend to them even if buried mid-context.

### 4. Middle = Danger Zone
"Lost in the Middle" is real. Instructions buried in the middle of long prompts are significantly underweighted. If you must bury something, put it last, not in the middle.

### 5. Conflicts Kill Compliance
More constraints ≠ better. When system-level constraints conflict with user-level constraints, compliance collapses to 9.6–45.8%. Test for conflicts before adding constraints.

---

## What NOT to Do

| Myth | Reality | Source |
|------|---------|--------|
| "500–2000 tokens is optimal" | No benchmark supports this | Q10 (Low confidence) |
| "Repetition reinforces" | Unknown — Q6 not completed | Q6 (blocked) |
| "System > User hierarchy works" | Fails 54–90% of the time | Control Illusion (AAAI-26) |
| "More instructions = better" | Conflicts collapse compliance | Control Illusion |
| "Benchmarks study prompt length" | They don't | Q10 |

---

## Task IDs for Follow-Up

| Query | Task ID | Action |
|-------|---------|--------|
| Q1 (Degradation curve) | `ses_294b4d665ffehTbwBssGGZ9zeD` | `task resume` + vendor docs request |
| Q2 (Attention saturation) | `ses_294b4be64ffeA1UPLFvxQErGit` | `task resume` + position encoding analysis |
| Q3 (Memory vs IF tradeoff) | `ses_294b4a7d0ffeI3gyDkXeiaD8r5` | `task resume` + broader lit search |
| Q4 (Instruction density) | `ses_294b492c1ffeHUky5LtIBKfpkt` | `task resume` + empirical study design |
| Q5 (Model thresholds) | `ses_294b47ebeffe06G4qV0nh5JXu0` | `task resume` + GPT-4/Gemini search |
| Q6 (Repetition) | `ses_294b46b87ffe7reftb8MUbJInP` | **New dispatch required** |
| Q7 (Position recall) | `ses_294b456dfffej5rBbKtu5n5jEr` | `task resume` + SALT-NLP search |
| Q8 (Noise tolerance) | `ses_294b4428bffeXxxNW0K6U8VgiI` | `task resume` with chaining budget |
| Q9 (Instruction hierarchy) | `ses_294b42fd6ffegpGS461gejM0Jx` | `task resume` + within-msg ablation |
| Q10 (Literature synthesis) | `ses_294b41afcffeu1tXFX5RSOejEM` | `task resume` + original study design |

---

## How to Follow Up

```bash
# Example: Resume Q1 with vendor docs request
task(task_id="ses_294b4d665ffehTbwBssGGZ9zeD", 
     prompt="Continue Q1 research. Now search for OpenAI/Anthropic internal guidance on prompt length optimization.")
```

---

## Key Primary Sources

1. **Liu et al. (2023)**, "Lost in the Middle" — TACL — U-shaped position effect
2. **Xiao et al. (2024)**, "StreamingLLM" — ICLR 2024 — Attention sink mechanism
3. **Geng et al. (2025)**, "Control Illusion" — AAAI-26 — Hierarchy failure data
4. **Jiang et al. (2023)**, "LLMLingua" — EMNLP 2023 — 20x compression
5. **Lee et al. (2025)**, "LLM CoT Compression" — arXiv:2503.01141 — 2–20x CoT compression
6. **Brown et al. (2020)**, "GPT-3 Few-Shot" — arXiv:2005.14165 — k-shot saturation
