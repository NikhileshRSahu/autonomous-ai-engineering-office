# Fast Audit and Check & Report

Fast Audit is the read-only, report-first workflow for understanding a project without allowing the Office to edit source, tests, configuration, or Git history.

## Run it

```bash
office start /path/to/project --objective "Understand this project"
office run /path/to/project --mode check-report --objective "Check this project completely and give me a report"
```

For the cheap-first optimized audit plan:

```bash
office run /path/to/project --mode fast-audit --objective "Audit this project and identify the highest-value issues"
```

The Control Room exposes the same modes from the Run Mode picker.

## Safety

Audit modes permit project reads/searches and an allowlist of build/test/simulation commands. They reject project writes, replacements, destructive shell commands, and Git mutation. The Office may still write its own `.office` index, event log, evidence, run record, and report files.

`AUDIT_COMPLETE` means the requested audit finished. It does **not** mean the project has passed its acceptance gates. The report records the independent verification verdict separately.

## Incremental behavior

The first audit creates `.office/index/index.db` with SHA-256 content hashes. Later audits re-hash the project, identify changed/removed files, and send only a bounded changed-file dossier to fresh Qwen analysis. Unchanged project content is not re-sent simply because a new run started.

```bash
office index status /path/to/project
office index rebuild /path/to/project
```

## Model phases

When routed local models are configured, Fast Audit normally performs:

1. one Qwen engineering analysis batch over the changed-file dossier;
2. deterministic configured checks;
3. one strong Nemotron/adversarial review of the consolidated dossier;
4. report construction.

If no local model is configured, deterministic discovery/index/checks still run and the report clearly records the skipped model phases.

## Output

Every audit produces:

```text
<project>/.office/reports/<RUN-ID>/
  REPORT.md
  SUMMARY.html
  run-metadata.json
  timeline.jsonl
  findings.json
  test-results.json
  risks.json
  model-performance.json
  evidence/
```

Find the newest report with:

```bash
office report /path/to/project
```
