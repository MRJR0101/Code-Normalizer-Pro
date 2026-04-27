# Project Checklist

## Purpose and Scope

- [ ] Define project goal in one sentence.
- [ ] Define success metrics (time, quality, reliability, cost).
- [ ] Identify primary users and top use cases.
- [ ] List explicit non-goals.

## Documentation and Ownership

- [ ] Create/maintain README with quick start and run commands.
- [ ] Create/maintain CHANGELOG.
- [ ] Add license file.
- [ ] Add owner/contact for maintenance.

## Source Control

- [ ] Initialize git repository.
- [ ] Add .gitignore.
- [ ] Protect main branch (PR/checks).
- [ ] Use commit message convention.

## Environment and Dependencies

- [ ] Pin runtime versions.
- [ ] Use dependency lockfile.
- [ ] Separate dev/test/prod configuration.
- [ ] Validate required environment variables at startup.

## Code Quality

- [ ] Add linting.
- [ ] Add formatting.
- [ ] Add static/type checks.
- [ ] Add pre-commit hooks.

## Testing

- [ ] Add unit tests for core logic.
- [ ] Add integration tests for critical paths.
- [ ] Add regression tests for known bugs.
- [ ] Add smoke test command.
- [ ] Define minimum coverage target.

## Safety and Security

- [ ] Validate all external input.
- [ ] Use safe defaults.
- [ ] Add timeout/retry/backoff for network calls.
- [ ] Add idempotency for repeatable operations.
- [ ] Add backup/rollback for destructive operations.
- [ ] Run dependency vulnerability scans.
- [ ] Scan secrets in repo and CI.

## Observability

- [ ] Add structured logs with run/request IDs.
- [ ] Add clear error categories/messages.
- [ ] Add health check command/endpoint.
- [ ] Define alert thresholds.

## Performance

- [ ] Capture baseline runtime/memory/throughput.
- [ ] Profile bottlenecks before optimizing.
- [ ] Set resource limits and safeguards.

## Data and Retention

- [ ] Define data retention policy.
- [ ] Define archival and cleanup jobs.
- [ ] Define schema migration/version strategy.
- [ ] Test recovery/restore procedure.

## CI/CD and Release

- [ ] Add CI for lint/test/build/security checks.
- [ ] Define release process (tag, artifact, notes).
- [ ] Define deployment rollback steps.
- [ ] Add post-deploy verification checklist.

## Operations

- [ ] Create runbook (start/stop/status/resume).
- [ ] Document common failures and fixes.
- [ ] Document backup and restore drill steps.
- [ ] Schedule periodic health audits.

## Maintenance Cadence

- [ ] Review metrics monthly.
- [ ] Remove dead code/files routinely.
- [ ] Rotate keys/tokens on schedule.
- [ ] Re-prioritize technical debt quarterly.
