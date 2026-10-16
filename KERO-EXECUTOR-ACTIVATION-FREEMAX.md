# Kero — Conditional CI/Cloud Executor Activation (RDC control plane)
Source: Segundo Cerebro #14309, policy #14222, batch KERO-EXECUTORS-RDC-20261015-RUN-001.

## Safety: no automatic provider activation
Existing public runners GitHub/CircleCI and free Render are already governed by the central queue in Supabase. These files only stage manual provider-specific smoke jobs for external accounts; they are **not** proof of account ownership, quota, paid-tier eligibility, or homologation.

Before enabling any provider, verify:
1. Account/project ownership and a credential already legitimately stored in its provider; never commit tokens or paste them in logs.
2. Zero-overage guarantee. Absence of a visible usage balance is a **BLOCK**, not proof of free capacity.
3. Genuine distinct capability or an independent fallback to existing GitHub public/CircleCI/Render.
4. Provider policy, minimum free tier, runtime constraints; no remote Desktop Commander agent in ephemeral CI/Colab.
5. Branch-scoped dry-run only, approved free minutes, <= 5 minutes, no proprietary data, no deploy/secrets.
6. Signed evidence: job URL, artifact hash, stdout redacted, time, quota state, test result and rollback reference.
7. Only after successful E2E, promote the existing row in brain.compute_executors using the existing locking/queue workflow. Never add a shadow queue.
No publication changes to keromotoboy.com.br; GOLEM retains site ownership.

## Candidate-specific gates
- Bitbucket: ONLY `custom.kero-public-safe-static`, explicit manual trigger and verified quota/no-overage.
- Azure: `trigger: none`, `pr: none`, boolean freeMaxVerified defaults FALSE; requires already provisioned Azure DevOps org/subscription and externally verified zero-billing; no provisioning by this pipeline.
- GitLab: existing `.gitlab-ci.yml`; GitLab CLI currently installed but auth not proven. Do not trigger until verified.
- Buildkite: existing `.buildkite/pipeline.yml`; requires workspace, project and free-credit validation.
- Deno Deploy: existing `deno-slot/main.ts`; test `deno check` locally, no remote deploy before linked free org/app confirmed.
- HF ZeroGPU and Lightning: verify free-account eligibility and CPU/GPU actual grants, do not invoke billable Jobs.
- GitHub private: billing API inaccessible (test on 15/10), keep disabled until hard spending cap and remaining usage are independently verified.
- Cloudflare Edge: already a gateway (not a compute executor), do not reclassify or duplicate.
- Colab/Kaggle/Codespaces/Modal/paid HF: reserve or reject, not auto workers.
To cancel: close draft PR and drop isolated branch; no active provider resources were created by this staged configuration.
