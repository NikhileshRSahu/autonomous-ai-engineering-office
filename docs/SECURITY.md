# Security and Approval Model

The Office assumes autonomous tooling can be dangerous and therefore fails closed.

- File operations resolve their final path and reject `..`/symlink escapes outside the project root.
- Every agent has separate read/write scopes.
- High-risk shell patterns (push/publish/deploy/destructive/privileged/remote pipe-to-shell) require explicit approval; `auto_mode` does **not** bypass this.
- Mutating tool actions are persisted as audit events.
- Acceptance specifications are copied to `.office/acceptance/` and hashed before a candidate run. Mutation forces verification failure.
- The Critic rejects obvious test-disabling and gate-masking changes.
- Evidence text is redacted for common tokens, bearer credentials and private keys before persistence.
- Malformed model output, unknown tools, missing permissions, missing evidence and unknown model routes fail closed.

For production use, run projects in OS/container sandboxes and use least-privilege credentials. Never give autonomous workers unrestricted production secrets merely because the Office has internal permission checks.

## Universal intake boundary

Project intake is treated as an untrusted-input boundary.

- ZIP/TAR member paths are normalized and must remain inside the allocated workspace.
- ZIP symlinks and special Unix entries are rejected. TAR symlinks, hardlinks, devices, FIFOs and other special members are rejected.
- Archive file-count and expanded-byte limits are enforced before activation.
- Browser uploads stream through bounded sessions; relative paths are validated, duplicates are rejected, and byte/file limits are enforced while data arrives.
- Git is invoked with subprocess argument lists, not shell interpolation; credentials are redacted from persisted/user-facing provenance and errors.
- Pasted filenames and uploaded relative paths cannot be absolute or contain traversal components.
- A failed import never enters the floor registry. Managed partial workspaces/staging are removed on failure/cancel.
- Intake never runs imported code. Execution remains behind the normal Office task/tool/approval/verification boundaries.

Defaults are configurable through `OfficeConfig`: `intake_workspace_root`, `intake_staging_root`, `intake_max_files`, `intake_max_bytes`, and `intake_session_ttl`.
