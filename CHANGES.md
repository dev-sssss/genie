# PipelineGenie generation-engine rewrite — what changed and why

## Bug found along the way (unrelated to generation quality, but real)
`requirements.txt` lists `groq` but `main.py` actually calls OpenRouter via
`requests`, and uses `dotenv`/`os.environ`. Neither `requests` nor
`python-dotenv` were pinned. If you ever install from a clean venv using only
`requirements.txt`, `/generate-pipeline` would 500 on import. Fixed in the
updated `requirements.txt` (also added `PyYAML`, needed for output
validation below). If `groq` is used elsewhere in the project, keep it — I
removed it here since nothing in `main.py`/`pipeline_generator.py` calls it.

## The core problem
Two independent, unreconciled "plans" were being sent to the LLM for every
generation call:

- `analysis.recommended_pipeline` — built deterministically by
  `recommended_pipeline.py` from the repo analysis. Genuinely good: real
  commands, real GitHub Action names, real secret group names. But it only
  knows the repo — it has no idea what platform the user picked, whether
  they want an approval gate, their coverage threshold, etc. It also has
  zero support for SSH/VM deploy targets (EC2, Azure VM, GCP VM) — it only
  knows Helm/kubectl/ECS/Lambda.
- `strategy_steps` / `resolved_commands` — built by the old
  `PipelineGeneratorEngine._build_strategy()` from `spec` only. Much weaker:
  produces English sentences like `"Deploy via SSH: SSH into server, ..."`
  instead of real commands, and ignores ~15 of the ~20 sections in the
  wizard spec (`security_scans`, `quality_checks`, `approval`, `cache`,
  `health_checks`, `notification_channels`, `database_tasks`,
  `custom_pipeline`, `environments`, `rollback_strategy`, etc.).

Both got dumped into one system prompt that just said "format this into
valid YAML for the platform," with no schema shown and no instruction on
which source wins. That's why your sample output invented a fictional
`apiVersion: v1 / kind: Pipeline` schema — the model had contradictory,
under-specified input and picked something structurally safe-looking but
wrong.

## What the rewrite does

**`pipeline_generator.py` (rewritten)**
`PipelineGeneratorEngine` now does one job: produce a single, reconciled
`final_pipeline_plan`.
- Starts from `analysis.recommended_pipeline` (the good, repo-aware plan).
- Applies `spec` as filters/overrides on top of it: drops stages/jobs the
  user explicitly disabled (lint, specific security scans, specific test
  tiers, specific environments), applies their coverage threshold, image
  name/tag, k8s namespace/replicas, notification channels, migration
  command, custom before/after hooks, approval flags, rollback strategy.
- Adds a new deterministic branch, `_inject_vm_deploy_stage`, that builds
  real SSH/SSM deploy + rollback + health-check stages for EC2/VM targets —
  this is the exact case that broke in your sample output, and it was
  previously unhandled by both the old engine and `recommended_pipeline.py`.
- Expanded `_validate_capabilities` to also warn (not just error) on
  under-specified but non-fatal cases: SSH target with no host/key secret
  present, approval requested with no environment enabled, migrations
  requested with no known migration command.

**`pipeline_templates.py` (new)**
Literal schema skeletons for all 6 platforms (GitHub Actions, GitLab CI,
Jenkins, Azure DevOps, CircleCI, Bitbucket Pipelines), plus a shared set of
hard formatting rules ("use only commands from the plan," "secrets via
native syntax only," "no invented top-level keys," etc.). This is what gets
injected into the system prompt so the model is filling in a known shape
instead of inventing one.

**`main.py` (`/generate-pipeline` rewritten)**
- Builds the merged plan via the engine, picks the right schema block for
  the chosen platform, and sends the LLM only that plan — not a second,
  contradictory raw dump of `analysis` + `spec`.
- **Validates the LLM's output before trusting it**: for YAML platforms, it
  actually parses the YAML and checks required top-level keys per platform
  (`jobs`/`on`/`name` for GH Actions, `stages` for GitLab, etc.); for
  Jenkins it checks for the `pipeline { stages { } }` skeleton. It also
  explicitly flags the exact failure you hit — `apiVersion`/`kind` — as
  invalid for every non-Jenkins platform.
- **Retries once with the validation error appended** if the first attempt
  fails, so the model can self-correct, before giving up and returning
  `GENERATION_FAILED_VALIDATION` instead of silently claiming `"status":
  "VALID"` on broken output (this was happening before — v1 trusted
  whatever the model said its own status was).

## What you still need to do

1. **Wire these three files in** (drop-in replacements for the same paths
   in `repo-analyzer-service/app/` and the root `requirements.txt`).
2. **Test across all 6 platforms with a real repo**, not just Node/EC2 —
   especially confirm the Jenkins/Azure DevOps skeletons match your actual
   target syntax conventions (I wrote them from standard docs; if your team
   has house conventions — shared libraries, specific agent labels — bake
   those into `pipeline_templates.py`).
3. **Decide the `groq` question** — if it's used by another module I didn't
   see in this zip (this upload only contained `repo-analyzer-service`, not
   an `ai-generator-service`), don't drop it from requirements.txt; add
   `requests`/`python-dotenv`/`PyYAML` alongside it instead.
4. **Add an actual `actionlint`/`yamllint` subprocess call** if you want
   stronger-than-schema-key validation — my `_validate_generated_output` is
   deliberately dependency-light (pure PyYAML parse + key check) so it
   works without installing external linters, but a real linter would catch
   more (e.g. invalid `runs-on` values, bad `needs:` references).
5. **Load-test the retry path** — right now a failed retry still costs you
   2 LLM calls and returns an error to the user; you may want to log those
   failures somewhere so you can see over time which platforms/spec
   combinations trip validation most, and fix the template rather than
   relying on the retry every time.

## Round 2 — closing the gaps flagged after round 1

1. **Missing/empty `analysis.recommended_pipeline` now fails loudly.**
   `_merge_recommended_with_spec` used to silently build a near-empty plan if
   that field was absent (stale payload, hand-built test request, old
   frontend build). It now adds a real validation error and `run()`
   re-checks `validation.passed` after the merge step, returning
   `INVALID_CONFIGURATION` with a clear reason instead of quietly generating
   a broken pipeline.

2. **Dangling `&&` in VM/SSH deploy commands fixed.** If either the install
   or build command resolves to an empty string, the SSH/SSM remote command
   is now built by filtering blanks and joining with `&&`, instead of always
   splicing both slots in regardless of content.

3. **`kubernetes.service_type` from the wizard is now applied** to the
   deploy stage instead of being silently dropped (it was collected by the
   frontend but never read anywhere in the engine).

4. **Dockerfile / docker-compose / Terraform / Kubernetes manifests / Helm
   charts are now actually requested from the LLM.** `pipeline_templates.py`
   gained `get_manifest_prompt_block()`, which checks
   `docker_configurations.generate_dockerfile/generate_compose`,
   `infrastructure.terraform`, `kubernetes.generate_manifests/generate_helm`,
   and the `generate_manifests` block, and — only for what's actually
   checked — injects a skeleton + instruction to populate `generated_files`
   with that file. Before this, checking those boxes in the wizard had no
   effect at all; the LLM was never told they existed.

5. **Missing requested manifests are now surfaced, not silent.**
   `main.py` gained `_missing_requested_manifests()`, which runs after
   generation and appends a plain-English warning to the response's
   `validation.warnings` for each manifest type the user asked for that
   didn't show up in `generated_files`. This is intentionally a warning, not
   a hard failure — the pipeline file itself may still be perfectly valid
   even if, say, the Helm chart didn't get generated — but you'll see it
   now instead of finding out later.

## One more thing found while merging into your zip
`update_prompt.py` at the repo-analyzer-service root is a leftover dev/patch
script — it still writes the *old* system prompt referencing `strategy_steps`
and `engine_resolved_commands`. It isn't imported by `main.py`, so it's inert,
but running it by hand would stomp `main.py` back to the old broken prompt.
Left it in place untouched since I can't be sure you don't still use it as a
scratch tool, but you likely want to delete it now that main.py has the
correct prompt built in directly.
