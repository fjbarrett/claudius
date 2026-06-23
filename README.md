# claudius

A faithful, **minimal** recreation of [mini-SWE-agent](https://mini-swe-agent.com) —
the agent scaffold used by **ProgramBench** (Yang et al., 2026) to both construct
tasks and evaluate 9 frontier models.

The whole identity of this harness is *minimalism*: the model's entire interface
to the world is **a single bash command per turn**. There are no bespoke tools,
no special-cased prompts, and no guardrails — which, in ProgramBench's words, is
the point: it "reduces confounds between model capability and harness design."

It is the deliberate opposite of a rich agent like [claudette](../claudette)
(9 structured tools + verification gate + anti-flailing nudges). claudius exists
as the *control* in that comparison.

## What it is

```
config/default.yaml     the whole agent, declaratively (limits + prompt templates)
claudius/
  agent.py              the loop: query → parse one bash block → execute → observe
  environment.py        LocalEnvironment / DockerEnvironment (bash, timeout, truncation)
  models.py             dependency-free OpenAI-compatible client (OpenRouter/OpenAI/…)
  cli.py                argparse entrypoint, .env loading, trajectory saving
run.py                  `python3 run.py --task ...`
tests/test_core.py      offline unit tests (no model calls)
examples/               sample tasks
```

## Fidelity to the paper (§B.1)

The operational limits are copied straight from ProgramBench's configuration and
live in `config/default.yaml`:

| Parameter | Paper | `default.yaml` |
|---|---|---|
| Action interface | single bash command/turn | ✅ |
| Per-action timeout | 3 minutes | `action_timeout_sec: 180` |
| Output truncation | 10,000 chars → first+last 5,000 | `output_char_limit: 10000`, `output_keep_each_side: 5000` |
| Soft "wrap up" warning | < 20 steps **or** < 10 min remaining | `warn_steps_remaining: 20`, `warn_minutes_remaining: 10` |
| Step cap | 1,000 steps | `step_limit: 1000` |
| Wall-clock cap | 6 hours | `time_limit_sec: 21600` |
| Cost limit | none | (none) |
| Sandbox | Docker `ubuntu:22.04`, `--network none` | `DockerEnvironment` (`--env docker`) |
| Hyperparameters | vendor defaults | `temperature: 0.0` |

Control flow mirrors mini-SWE-agent's `DefaultAgent`: exceptions drive
termination (`Submitted`, `LimitsExceeded`), a malformed response re-prompts with
a format error, and the model finishes by running `echo <sentinel>`.

### Deliberate differences

- **Local by default.** `LocalEnvironment` runs on the host (fast to try);
  `DockerEnvironment` reproduces the no-internet sandbox but needs a Docker
  daemon and is not exercised by the tests here.
- **Dependency-free model client.** Upstream uses `litellm`; this uses stdlib
  `urllib` against any OpenAI-compatible endpoint. PyYAML is the only dep.
- Not bundled: ProgramBench's *benchmark* pipeline (binary stripping, fuzzed
  behavioral-test generation, the assertion linter, the cheat-detection judge).
  This repo is the **scaffold** only — the mini-SWE-agent half.

## Quickstart

```bash
pip install -r requirements.txt          # just PyYAML

# Put OPENROUTER_API_KEY in .env (or rely on the ../claudette/.env fallback).
cp .env.example .env

python3 run.py --task "Create hello.txt containing exactly: hi from claudius" -v
python3 run.py --task-file examples/reverse-a-file.md -m anthropic/claude-3.5-haiku -v
```

The agent works inside `workspace/` (gitignored). Each run saves its full message
trajectory to `runs/<timestamp>.json` — the same kind of trace the paper mines
for its action-type analysis (read / write / probe / execute).

### Configuration

Everything is in `config/default.yaml`; CLI flags (`-m/--model`, `--env`,
`--step-limit`, `--cwd`) override per run. Point `model.base_url` /
`model.api_key_env` at any OpenAI-compatible provider.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Covers output truncation, the single-command parser, and the local environment
(exec, fixed cwd, timeout) — no API calls.

## Provenance

Recreated from the method description in *ProgramBench: Can Language Models
Rebuild Programs From Scratch?* (Yang, Lieret, et al., 2026), which uses
mini-SWE-agent as its scaffold. mini-SWE-agent is by the SWE-agent / SWE-bench
team (Yang et al., 2024).
