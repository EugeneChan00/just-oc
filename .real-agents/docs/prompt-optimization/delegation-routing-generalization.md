# Delegation Routing: Generalization Guide

**Purpose:** Practical guide for writing delegation routing criteria that are robust to phrasing variation, mapped to the Rewrite and Strengthen editing operations.

**Research Base:** Derived from Control Illusion (AAAI-26) hierarchy failure research and general prompt engineering principles. Specific delegation routing research (phrasing-dependent vs independent) not found in available research — this guide synthesizes from general principles.

---

## The Problem

**Phrasing-dependent routing fails when users rephrase.** 

Regex/keyword matching on exact phrases (e.g., `prompt_regex: ".*git commit.*"`) fails when:
- User says "create a commit" instead of "git commit"
- User says "save my changes" instead of "commit"
- User uses different terminology ("version control save" vs "commit")

**More critically:** Models follow social hierarchy cues over system priority designations. The Control Illusion shows system/user role designation only achieves 9.6-45.8% priority adherence — worse than authority framing (54-65.8%).

**Result:** Even explicit system routing instructions ("Route X to agent Y") can be overridden by user phrasing that implies authority or expertise.

---

## Phrasing-Dependent vs Independent Examples

### Example 1: Git Operations

**Phrasing-Dependent (FAILS):**
```
Route to: backend-developer
Condition: prompt_regex: ".*git commit.*"
```

**Fails when user says:**
- "save my changes with a commit message"
- "create a version control checkpoint"
- "record these modifications"

**Phrasing-Independent (WORKS):**
```
Route to: backend-developer
Condition:
  - semantic_tag: "version_control_operation"
  - description: "Any request to save, record, or checkpoint changes in a version control system"
  - examples:
      - "commit my changes"
      - "save a snapshot of my code"
      - "record these modifications"
      - "create a git checkpoint"
  - negative_examples:
      - "save this document" (file saving, not version control)
      - "backup my computer" (system backup, not code)
```

---

### Example 2: Frontend Tasks

**Phrasing-Dependent (FAILS):**
```
Route to: frontend-developer
Condition: prompt_regex: ".*(react|vue|angular|html|css|javascript).*"
```

**Fails when user says:**
- "make the button blue"
- "change the header styling"
- "add a new section to the webpage"

**Phrasing-Independent (WORKS):**
```
Route to: frontend-developer
Condition:
  - semantic_tag: "web_ui_modification"
  - description: "Any request to change visual appearance, layout, or interactivity of a web interface"
  - examples:
      - "make the button blue"
      - "change the header styling"
      - "add a dropdown menu"
      - "fix the layout on mobile"
  - negative_examples:
      - "fix a bug in the API" (backend)
      - "optimize the database query" (backend)
```

---

### Example 3: Testing Tasks

**Phrasing-Dependent (FAILS):**
```
Route to: test-engineer
Condition: prompt_regex: ".*test.*"
```

**Fails when user says:**
- "verify this works"
- "check if there are any issues"
- "make sure it doesn't break"

**False positive when user says:**
- "I tested this already" (not asking for tests)

**Phrasing-Independent (WORKS):**
```
Route to: test-engineer
Condition:
  - semantic_tag: "test_generation_or_verification"
  - description: "Requests to create, run, or verify automated tests"
  - examples:
      - "write tests for this function"
      - "add unit tests"
      - "verify this works with test cases"
      - "check if there are edge cases"
  - negative_examples:
      - "I tested this already" (not a task)
      - "debug the issue" (debugging, not testing)
      - "the test failed" (result, not task)
```

---

### Example 4: Architecture Decisions

**Phrasing-Dependent (FAILS):**
```
Route to: solution-architect
Condition: prompt_regex: ".*architecture.*"
```

**Fails when user says:**
- "how should I structure this project"
- "what's the best way to organize these components"
- "design the system"

**Phrasing-Independent (WORKS):**
```
Route to: solution-architect
Condition:
  - semantic_tag: "system_design_or_architecture"
  - description: "Requests for high-level system structure, component relationships, or technical approach decisions"
  - examples:
      - "how should I structure this project"
      - "design the system architecture"
      - "what's the best approach for these services"
      - "organize these components"
  - negative_examples:
      - "fix the code structure" (refactoring, not design)
      - "reorganize the files" (file management)
```

---

### Example 5: Security-Relevant Tasks

**Phrasing-Dependent (FAILS):**
```
Route to: security-review
Condition: prompt_regex: ".*(security|vulnerability|auth|password).*"
```

**Fails when user describes symptoms without keywords:**
- "someone could access data they shouldn't"
- "what happens if a user guesses another user's ID"
- "can this be exploited"

**Phrasing-Independent (WORKS):**
```
Route to: security-review
Condition:
  - semantic_tag: "security_risk_assessment"
  - description: "Requests to evaluate potential misuse, unauthorized access, or exploitation risks"
  - examples:
      - "is this vulnerable to injection"
      - "can users access other users' data"
      - "what happens if someone sends a malformed request"
      - "could this be exploited"
  - dual_signal: "file_pattern: **/auth*, **/permission*, **/user* AND semantic_tag"
```

---

## LLM Semantic Tagging Approach

### Core Pattern

**Instead of:**
```
prompt_regex: ".*git commit.*"
```

**Use:**
```
llm_tag: "version_control_operation"
description: "Any request to save, record, or checkpoint changes in a version control system"
examples:
  - "commit my changes"
  - "save a version"
  - "record these modifications"
negative_examples:
  - "save this document"
  - "backup my files"
```

### Key Principles

1. **Tag by intent, not keywords:** "What is the user trying to accomplish?" not "What words did they use?"

2. **Diverse examples:** Include 5-10 examples covering different phrasings of the same intent

3. **Explicit negatives:** Include 2-3 examples of what the tag is NOT (reduces false positives)

4. **Dual signals when possible:** Combine semantic tag with file pattern (if applicable)

   ```
   Route if: semantic_tag = "frontend_modification" AND file_pattern matches "**/*.tsx", "**/*.css"
   ```

---

## Rewrite Operation Guidance

**When to Rewrite:**

| Current Routing Rule | Problem | Rewrite To |
|---------------------|---------|-----------|
| `prompt_regex: ".*test.*"` | Too broad, false positives | Semantic tag with negative examples |
| `prompt_regex: ".*git.*"` | Too narrow, misses alternatives | Semantic tag covering all VCS operations |
| `prompt_regex: ".*frontend.*"` | False negatives for styling requests | Semantic tag for UI modifications |
| Keyword matching on any exact phrase | Phrasing variation breaks it | Semantic tag with examples |

**Rewrite Steps:**
1. Identify the routing rule being applied
2. Determine the user intent behind the routing
3. Write a semantic tag capturing the intent
4. Add 5-10 diverse positive examples
5. Add 2-3 negative examples
6. Consider dual-signal (semantic + file pattern)

---

## Strengthen Operation Guidance

**When to Strengthen:**

| Current Tag | Problem | Strengthen With |
|-------------|---------|----------------|
| Semantic tag without examples | Ambiguous boundary | Add diverse examples |
| Semantic tag without negatives | False positives | Add negative examples |
| Single example | Overly narrow | Expand to 5-10 examples |
| No dual signal | Brittle for code tasks | Add file pattern filter |

**Strengthen Steps:**
1. Review current tag definition
2. Add positive examples covering common phrasings
3. Add negative examples for edge cases
4. If routing involves file operations, add file pattern dual signal
5. Test against eval prompts to verify no regression

---

## Common Pitfalls

| Pitfall | Why It Fails | Solution |
|---------|-------------|----------|
| Exact keyword matching | Users rephrase | Semantic tagging |
| Single example | Overfits to one phrasing | 5-10 diverse examples |
| No negative examples | False positives | Explicit negatives |
| No file pattern dual signal | Brittle for code tasks | Combine semantic + pattern |
| Overly broad tag | False positives | Tighten description + negatives |
| Overly narrow tag | Misses valid cases | Expand examples |

---

## Research Gaps

| Gap | Implication |
|-----|-------------|
| Delegation routing research | No specific empirical study on phrasing-dependent vs independent routing found in available literature |
| Optimal tag definition methodology | How to construct robust semantic tags is synthesized from general prompt engineering principles |
| Dual-signal effectiveness | Combining semantic + file pattern is logical but not empirically validated |
| Model-specific routing behavior | Routing may behave differently across model families |

**Recommendation:** Implement semantic tagging patterns and validate against eval results. Monitor delegation sub-metrics for routing failures and iterate on tag definitions.
