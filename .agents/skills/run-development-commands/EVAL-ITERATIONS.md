> **Note for skill-creator:** The `run-development-commands-workspace/` directory is git-ignored (not committed).
> Content evals: last completed iteration is **1**. Start the next run at `iteration-2`.
> See the iteration history table below.

# run-development-commands Skill — Eval Workspace

Content evals measure whether the loaded skill improves output quality. Each run scores assertion pass rate with-skill vs without-skill, saves raw results under `run-development-commands-workspace/`, and appends a row to the iteration history table below.

---

## Content evals

### How to run

Open a fresh Claude Code session (**set the model `Sonnet 4.6` and `medium` effort**) and paste this prompt:

```text
Run run-development-commands skill evals following the "Content evals" section of .agents/skills/run-development-commands/EVAL-ITERATIONS.md.

- Iteration: N (next number after existing iterations)
- Model: sonnet
- Baseline: without_skill
- Skill path: .agents/skills/run-development-commands/
- Evals: .agents/skills/run-development-commands/evals/evals.json

Follow steps 1-6 exactly as documented. Skip step 7 (viewer).
```

### Key details

- **Skill path**: `.agents/skills/run-development-commands/`
- **Evals**: `.agents/skills/run-development-commands/evals/evals.json`
- **Workspace**: `.agents/skills/run-development-commands-workspace/`
- **Baseline**: `without_skill` (no skill — tests what the model knows on its own)
- **Model**: Use `model: "sonnet"` on Agent calls for cost-effective runs

### How runs work

Each eval spawns **two subagents** (clean context, no shared state):
1. **with_skill** — reads SKILL.md, then answers the prompt
2. **without_skill** — answers the same prompt with no skill (general knowledge only)

Both save their response to `outputs/response.md` in their respective directories.

### Directory structure

```text
run-development-commands-workspace/
├── EVAL-ITERATIONS.md             ← iteration history (committed in .agents/skills/run-development-commands/)
└── iteration-N/
    ├── eval-1-run-tests/
    │   ├── eval_metadata.json         ← prompt + assertions for this eval
    │   ├── with_skill/
    │   │   ├── outputs/response.md    ← agent's answer
    │   │   ├── timing.json            ← tokens + duration
    │   │   └── grading.json           ← assertion pass/fail with evidence
    │   └── without_skill/
    │       ├── outputs/response.md
    │       ├── timing.json
    │       └── grading.json
    ├── eval-2-make-migrations/
    │   └── ...
    ├── eval-7-destructive-confirm/
    │   └── ...
    └── benchmark.json                 ← aggregated comparison stats
```

### File descriptions

| File | Created by | Purpose |
|------|-----------|---------|
| `evals/evals.json` | Human | Test cases with prompts, expected outputs, and assertions (simple strings) |
| `eval_metadata.json` | Agent (per eval dir) | Copy of prompt + assertions for that specific eval |
| `outputs/response.md` | Subagent | The actual answer produced by the run |
| `timing.json` | Agent (from task notification) | `total_tokens` and `duration_ms` captured at run completion |
| `grading.json` | Agent (or grader) | Each assertion graded with `text`, `passed`, `evidence` |
| `benchmark.json` | Script or agent | Aggregated pass rates, timing, and tokens per configuration |

### Grading format

`grading.json` uses `assertion_results` array per the [docs](https://agentskills.io/skill-creation/evaluating-skills):

```json
{
  "assertion_results": [
    {"text": "Assertion text", "passed": true, "evidence": "Quote or reference from output"}
  ],
  "summary": {"passed": 4, "failed": 1, "total": 5, "pass_rate": 0.8}
}
```

### Eval execution steps (reproducible)

Follow these exact steps for each iteration. All tools used are listed so the process is consistent.

#### Step 1: Setup workspace (`Bash`)
```bash
# Create directories + generate eval_metadata.json from evals.json
mkdir -p run-development-commands-workspace/iteration-N/{eval-1-run-tests,...}/{with_skill/outputs,without_skill/outputs}
python3 -c "... generate eval_metadata.json from evals/evals.json ..."
```

#### Step 2: Spawn agents (`Agent`, model: sonnet)
For each eval, spawn two background agents:
- **with_skill**: Reads SKILL.md, answers the prompt, saves to `with_skill/outputs/response.md`
- **without_skill**: No skill access, answers with general knowledge, saves to `without_skill/outputs/response.md`

#### Step 3: Save timing data (`Bash` — python3 one-liner)
As each agent completes, capture `total_tokens` and `duration_ms` from the task notification.
Write to `{with_skill,without_skill}/timing.json` for each eval.

#### Step 4: Grade all responses (`Agent` x1)
Spawn a single grader agent that:
1. Reads all `response.md` files and their `eval_metadata.json` assertions
2. Grades each assertion (pass/fail with evidence)
3. Writes `grading.json` to each `{with_skill,without_skill}/` directory

#### Step 5: Build benchmark (`Write`)
Create `iteration-N/benchmark.json` with aggregated pass rates, timing, and tokens per configuration.

#### Step 6: Update EVAL-ITERATIONS.md (`Edit`)
Add the iteration row to the "Iteration history" table below.

#### Step 7 (optional): Launch eval viewer (`Bash`)
The `skill-creator` plugin includes a browser-based viewer for visual review. This is optional — all data is in `grading.json` and `benchmark.json`.

### Iteration history

| Iteration | Model | With Skill | Without Skill | Delta | WS Tokens (avg) | NS Tokens (avg) | Token Delta | Notes |
|-----------|-------|-----------|--------------|-------|-----------------|-----------------|-------------|------|
| 1 | sonnet | 100% (26/26) | 61.5% (16/26) | +38.5pp | 13,938 | 11,527 | +2,411 | Baseline run. Skill adds container-state detection and `uv add` usage. Without skill: hardcodes `run --rm`, uses `pip install`, skips confirmation on destructive ops. |
