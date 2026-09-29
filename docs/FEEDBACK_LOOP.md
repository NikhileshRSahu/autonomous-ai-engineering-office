# Feedback, Critique, and Verification Loop

The feedback layer exists to prevent one model from proposing a change and then grading its own work.

## Candidate lifecycle

```text
OBSERVE
  ↓
separate facts from interpretation
  ↓
HYPOTHESIZE
  ↓
list alternatives + confidence
  ↓
prefer discriminating test
  ↓
PROPOSE ACTIONS
  ↓
Evidence Analyst
  ↓
Domain Reviewer
  ↓
Adversarial Critic
  ↓
APPROVE | REJECT | MORE EVIDENCE
  ↓
AUTHORIZED EXECUTION
  ↓
record action results + hashes
  ↓
feedback check again
  ↓
INDEPENDENT VERIFICATION
  ↓
PASS | FAIL | BLOCKED
```

## Evidence Analyst

`feedback.EvidenceAnalyst` rejects substantive mutation when the report has no observations or there is no persisted evidence reference. It does not decide that the proposed root cause is true; it decides whether the proposal has enough recorded basis to proceed.

## Domain Reviewer

`feedback.DomainReviewer` checks executed tool/action results. Any failed action invalidates the implementation evidence rather than allowing the worker to pretend the mutation completed.

## Adversarial Critic

`feedback.AdversarialCritic` rejects obvious forms of benchmark/test manipulation, including candidate writes to acceptance paths and common test-disabling/masking patterns.

## Independent Verifier

`verification.Verifier` is not the implementation agent. It loads acceptance gates, captures hashes, executes command gates, checks expected exit/output, checks required evidence, and refuses PASS when acceptance files change.

## Retry discipline

A failed candidate becomes `failed_attempt` memory with its actions, hypotheses and verification report. The next iteration receives that evidence and an instruction to form a new hypothesis without weakening the gates.

Feedback loops are bounded. Repeated unproductive cycles result in BLOCKED/Director intervention rather than infinite model conversation.

## High-risk actions

Feedback approval is not security approval. Shell/Git commands are separately risk-classified. High-risk actions create persisted approval requests; execution remains blocked until explicitly approved.

## Why agent consensus is not proof

Multiple logical agents may share one underlying model and training biases. Agreement is therefore not treated as independent evidence. Tests, measurements, hashes, external sources and real runtime behavior are the proof layer.
