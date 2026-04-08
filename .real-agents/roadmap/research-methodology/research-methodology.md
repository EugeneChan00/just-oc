---
id: research-methodology
title: "Research Methodology Standards"
goal: >
  Establishes mandatory source quality standards, mechanism-seeking discipline,
  and evidence classification requirements for all researcher sub-agents.
  Every research dispatch must adhere to these standards or explicitly
  surface deviations as assumptions.
base_branch: main
directive_type: executable
cleanup: on-success
merge_strategy: auto
---

<spec>

<feature id="FEAT-01" name="Source Hierarchy Enforcement">
<description>
All research claims must be traceable to source quality tier. Sources are
classified at point of citation. Researcher must explicitly name the tier,
not just the source.
</description>

<criterion id="CRIT-01" type="structural">
Primary sources are required for any mechanistic claim.

<implementation>
Mechanism claims (how X works, why X happens) must cite: original papers,
official documentation, source code, postmortems by builders, regulatory
filings, raw data. Secondary sources are acceptable only for context framing,
not for mechanistic content.
</implementation>

<test_assertions>
  assert: "mechanism claims cite primary sources"   against: true
  assert: "secondary sources flagged by researcher"  against: true
</test_assertions>
</criterion>

<criterion id="CRIT-02" type="structural">
Source credibility assessment is explicit per citation.

<implementation>
Every cited source must have an explicit credibility assessment adjacent
to the citation: who published it, what their incentive is, what their
track record is, whether they have source access, whether their claims
are verified by independent sources.
</implementation>
</criterion>
</feature>

<feature id="FEAT-02" name="Mechanism Extraction Discipline">
<description>
Research is not a surface summary. Every pattern, tool, or claim must
be reduced to its irreducible mechanism with explicit conditions and failure modes.
</description>

<criterion id="CRIT-03" type="behavioral">
Every returned pattern includes: irreducible mechanism, assumptions, conditions, failure modes.

<implementation>
For each pattern investigated, the output must include:
- Irreducible mechanism: "X works because [mechanism], not because [surface description]"
- Assumptions: conditions that must hold for the mechanism to produce the claimed value
- Conditions: environmental, architectural, or scale dependencies
- Failure modes: what breaks, how it breaks, and under what conditions

A pattern report without these fields is incomplete and must be returned for revision.
</implementation>

<test_assertions>
  assert: "all patterns have irreducible_mechanism field"     against: true
  assert: "all patterns have assumptions array"              against: true
  assert: "all patterns have failure_modes array"            against: true
</test_assertions>
</criterion>

<criterion id="CRIT-04" type="structural">
Principle vs tactic vs cosmetic vs cargo-cult separation is explicit.

<implementation>
Each pattern must be classified as:
- Core principle: durable, mechanism-driven, transferable
- Context-dependent tactic: works only under specific conditions
- Cosmetic feature: incidental presentation, no mechanism value
- Cargo-cult pattern: copied without understanding original mechanism

Classifications must be justified, not asserted.
</implementation>
</criterion>
</feature>

<feature id="FEAT-03" name="Evidence Classification">
<description>
Every claim is classified. Classification is explicit, not inferable from confidence.
</description>

<criterion id="CRIT-05" type="behavioral">
All claims labeled fact/inference/assumption/unknown with source.

<implementation>
Each substantive claim must have:
- Classification: fact | inference | assumption | unknown
- Source: citation or "no source / researcher inference"
- Confidence: high | medium | low
- Justification: why this classification given the source quality

Claims without classification are returned as incomplete.
</implementation>

<test_assertions>
  assert: "all claims have classification field"    against: true
  assert: "all claims have source field"           against: true
  assert: "unknown claims surfaced as 'unknown'"   against: true
</test_assertions>
</criterion>

<criterion id="CRIT-06" type="behavioral">
Source disagreement is reported, not smoothed.

<implementation>
When sources conflict on a substantive claim, the conflict is reported
as a finding with: the disagreement, the competing claims, the source
contexts and credibility, and the lead's decision about which to weight.
No forced consensus.
</implementation>
</criterion>
</feature>

<feature id="FEAT-04" name="Falsification-First Discipline">
<description>
Researchers actively seek disconfirming evidence, not just supporting evidence.
The goal is durable understanding, not confirmation.
</description>

<criterion id="CRIT-07" type="behavioral">
Failure modes are primary output, not afterthought.

<implementation>
For each mechanism, researcher must enumerate:
1. What would prove this mechanism is false?
2. Has that disconfirming evidence been sought?
3. What is the current status of that evidence?

A mechanism report that only lists success conditions and never asks "when does this break?"
is incomplete.
</implementation>

<test_assertions>
  assert: "all mechanisms have falsification_attempted field"    against: true
  assert: "disconfirming evidence documented where sought"       against: true
</test_assertions>
</criterion>
</feature>

<adversarial>
<strategy>
Probe for surface-level pattern catalogs without mechanism depth.
Claim classification is easy to game — look for "inference labeled as fact"
or "assumption not labeled as assumption." Source disagreement should not
be invisible — if two credible sources conflict, the researcher must
surface the conflict, not pick a winner silently.
</strategy>
<mutations>
Ask researcher: "What would change your conclusion?" — if they cannot answer,
the mechanism is not understood. Ask: "What is the most likely failure mode
of this mechanism?" — if they answer with a surface description, mechanism
has not been extracted.
</mutations>
<structural>
Look for pattern reports that list features without explaining why they matter.
Look for claims without citations or with tertiary sources claiming to be
mechanistic. Look for "confidence: high" on single-source claims.
</structural>
<test_quality>
Not applicable to research — this is the research quality standard itself.
</test_quality>
</adversarial>

</spec>


<directive>

<scope>
This directive applies to ALL research dispatches via the `task` tool.
It injects into every researcher agent dispatch as "## Principle".

In scope:
- Source quality enforcement (FEAT-01)
- Mechanism extraction requirements (FEAT-02)
- Evidence classification (FEAT-03)
- Falsification-first discipline (FEAT-04)

Out of scope:
- Research scope decisions (those are made by the dispatching lead)
- Solution recommendations (those belong to the lead or solution_architect)
- Product/architecture decisions
</scope>

<principle>
Research is mechanism-seeking, not feature-collecting. Every claim is
sourced and classified. Every pattern is reduced to its irreducible
mechanism with explicit conditions and failure modes. Source disagreement
is surfaced, not smoothed. Disconfirming evidence is sought as seriously
as confirming evidence.
</principle>

<step number="1" worktree="research-methodology" merge_strategy="none">
<name>validate-source-hierarchy</name>
<profile>researcher</profile>
<acceptance_criteria>
- FEAT-01.CRIT-01
- FEAT-01.CRIT-02
</acceptance_criteria>
<prompt>
Create a source quality validation checklist for researcher agents.

The checklist must include:
1. Source tier definitions (primary vs secondary vs tertiary) with examples
2. Credibility assessment questions per citation (who published, incentive, track record, independent verification)
3. A forced disclosure: for every mechanistic claim, what is the primary source?
4. Warning signs of source degradation (vendor marketing, single-source without verification, tertiary sources making mechanistic claims)

Save to: `.real-agents/roadmap/research-methodology/source-quality-checklist.md`

Format as a markdown reference document that researchers can consult.
</prompt>
<verify>
**What to check:** File exists at `.real-agents/roadmap/research-methodology/source-quality-checklist.md`.
Contains source tier definitions, credibility assessment questions, forced disclosure
requirements, and warning signs.

**Anti-patterns to detect:**
- Tier definitions that could include vendor marketing as "primary"
- Credibility questions that don't probe for conflict of interest
- Warning signs that are too subtle to catch common degradation patterns
</verify>
<on_failure retry="2" escalate="abort"/>
</step>

<step number="2" worktree="research-methodology" merge_strategy="none">
<name>create-mechanism-template</name>
<profile>researcher</profile>
<depends_on>validate-source-hierarchy</depends_on>
<acceptance_criteria>
- FEAT-02.CRIT-03
- FEAT-02.CRIT-04
</acceptance_criteria>
<prompt>
Create a mechanism extraction template for researcher agents.

The template must include fields for each investigated pattern:
1. Name
2. Irreducible mechanism (one sentence, mechanism-only, no surface description)
3. Assumptions (array — what must be true for this to work)
4. Conditions (array — environmental/architectural/scale dependencies)
5. Failure modes (array — what breaks, how, under what conditions)
6. Principle vs tactic vs cosmetic vs cargo-cult classification with justification
7. Source citations with tier and credibility assessment
8. Confidence level with justification

Save to: `.real-agents/roadmap/research-methodology/mechanism-template.md`

This template becomes the required output format for all pattern investigations.
</prompt<verify>
**What to check:** File exists at `.real-agents/roadmap/research-methodology/mechanism-template.md`.
Contains all required fields for mechanism extraction. Fields are mandatory (not optional).
Classification has a justification field, not just a label.

**Anti-patterns to detect:**
- Template fields that are optional when they should be mandatory
- No guidance on what constitutes a proper "irreducible mechanism" vs surface description
- Classification without justification field
</verify>
<on_failure retry="2" escalate="abort"/>
</step>

<step number="3" worktree="research-methodology" merge_strategy="none">
<name>create-falsification-guide</name>
<profile>researcher</profile>
<depends_on>create-mechanism-template</depends_on>
<acceptance_criteria>
- FEAT-04.CRIT-07
</acceptance_criteria>
<prompt>
Create a falsification discipline guide for researcher agents.

The guide must include:
1. Why falsification-first matters (durability vs confirmation bias)
2. Falsification questions per mechanism: "What would prove this false?", "Has this been tested?", "What evidence would change your conclusion?"
3. Source disagreement protocol: how to surface conflicts without smoothing
4. "Unknown" as a valid finding — when to use it and how to frame it
5. Warning signs that a researcher is in confirmation mode instead of falsification mode

Save to: `.real-agents/roadmap/research-methodology/falsification-guide.md`
</prompt>
<verify>
**What to check:** File exists at `.real-agents/roadmap/research-methodology/falsification-guide.md`.
Contains falsification questions, disagreement protocol, unknown-finding guidance,
and warning signs for confirmation bias.

**Anti-patterns to detect:**
- Falsification questions that are too narrow (only obvious refutations)
- No guidance on what to do when sources genuinely disagree
- "Unknown" not treated as a valid honest finding
</verify>
<on_failure retry="2" escalate="abort"/>
</step>

</directive>
