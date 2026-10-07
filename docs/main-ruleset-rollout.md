# Main ruleset rollout plan

Status: AUDITED / NOT YET ENFORCED

## Current facts
- Repository currently has no GitHub rulesets.
- Existing security workflows:
  - Action Pin Policy
  - CodeQL
  - Control Lint
- `control-sync.yml` is triggered by direct pushes to `main` under `control/jobs/*.json`.
- Enabling a strict PR-only ruleset immediately could break the current control-plane ingestion path.

## Safe rollout

### Phase 1 — non-breaking
1. Keep current direct control-job path working.
2. Require immutable SHA pinning for third-party Actions.
3. Keep CodeQL active.
4. Audit workflow permissions and keep least privilege.
5. Do not grant broad bypass to humans or bots.

### Phase 2 — prepare enforcement
1. Make required validation workflows run consistently for every protected change so required checks cannot be missing because of path filters.
2. Convert any automation that must modify protected files to a PR-based or explicitly scoped GitHub App/OIDC path.
3. Validate control/jobs ingestion end-to-end through the new path.
4. Confirm no production control flow depends on unrestricted direct push to main.

### Phase 3 — enable ruleset
Target branch: `main`.

Recommended protections after Phase 2 passes:
- block force pushes;
- block deletions;
- require pull request for protected source/workflow changes;
- require security/status checks that are guaranteed to run;
- require conversation resolution;
- restrict bypass to the minimum automation identity needed;
- keep admin emergency bypass manual and auditable.

## Required checks candidates
- Action Pin Policy / enforce
- CodeQL / Analyze (javascript-typescript)
- CodeQL / Analyze (python)
- Control Lint checks, after verifying their stable check names.

Do not activate a required check until it is guaranteed to run on every change covered by the ruleset.

## Human/admin boundary
Actual ruleset activation requires repository administration permission. Before activation, verify that the control-sync path has a compatible protected-branch write strategy.
