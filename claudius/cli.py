"""Command-line entry point.

  python3 run.py --task "create hello.txt containing 'hi'" --verbose
  python3 run.py --task-file examples/reverse-a-file.md -m anthropic/claude-3.5-haiku

Loads .env (this repo's, then the sibling claudette/.env as a fallback), builds
the model + environment + agent from a YAML config, runs one task, and saves the
trajectory under runs/.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

import yaml

from .agent import Agent
from .environment import DockerEnvironment, LocalEnvironment
from .models import Model, ModelError

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_dotenv() -> None:
    """Populate os.environ from this repo's .env, then ../claudette/.env, for any
    key not already set. A tiny KEY=VALUE parser — no python-dotenv dependency."""
    import os

    candidates = [REPO_ROOT / ".env", REPO_ROOT.parent / "claudette" / ".env"]
    for path in candidates:
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def parse_args(argv):
    p = argparse.ArgumentParser(prog="claudius", description="Minimal bash-only SWE-agent (mini-SWE-agent clone)")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("-t", "--task", help="task description (string)")
    src.add_argument("--task-file", help="path to a file containing the task")
    p.add_argument("-m", "--model", help="model slug (overrides config)")
    p.add_argument("-c", "--config", help="config YAML (default: config/default.yaml)")
    p.add_argument("--cwd", help="working dir the agent operates in (default: workspace/)")
    p.add_argument("--env", choices=["local", "docker"], help="execution environment")
    p.add_argument("--image", help="docker image (when --env docker)")
    p.add_argument("--step-limit", type=int, help="override agent.step_limit")
    p.add_argument("-o", "--output", help="trajectory output path (default: runs/<ts>.json)")
    p.add_argument("-v", "--verbose", action="store_true", help="stream thoughts/commands/output")
    return p.parse_args(argv)


def load_config(path: str | None) -> dict:
    cfg_path = pathlib.Path(path) if path else REPO_ROOT / "config" / "default.yaml"
    return yaml.safe_load(cfg_path.read_text(encoding="utf-8"))


def make_logger(verbose: bool):
    if not verbose:
        return None

    def log(kind: str, step: int, text: str) -> None:
        if kind == "assistant":
            print(f"\n── step {step} · model ──\n{text.strip()}")
        elif kind == "action":
            print(f"\n$ {text}")
        elif kind == "observation":
            print(text.strip())
        elif kind == "format_error":
            print(f"\n[step {step}] format error — re-prompting")

    return log


def main(argv=None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    load_dotenv()
    cfg = load_config(args.config)

    if args.model:
        cfg["model"]["name"] = args.model
    if args.env:
        cfg["environment"]["kind"] = args.env
    if args.image:
        cfg["environment"]["docker_image"] = args.image
    if args.step_limit:
        cfg["agent"]["step_limit"] = args.step_limit

    task = args.task if args.task else pathlib.Path(args.task_file).read_text(encoding="utf-8")
    cwd = args.cwd or str(REPO_ROOT / "workspace")

    try:
        model = Model(**cfg["model"])
    except ModelError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    env_cfg = cfg["environment"]
    if env_cfg["kind"] == "docker":
        env = DockerEnvironment(
            image=env_cfg["docker_image"],
            network=env_cfg["docker_network"],
            timeout=env_cfg["action_timeout_sec"],
            output_char_limit=env_cfg["output_char_limit"],
            output_keep_each_side=env_cfg["output_keep_each_side"],
        )
    else:
        env = LocalEnvironment(
            cwd,
            timeout=env_cfg["action_timeout_sec"],
            output_char_limit=env_cfg["output_char_limit"],
            output_keep_each_side=env_cfg["output_keep_each_side"],
        )

    agent = Agent(model, env, cfg, logger=make_logger(args.verbose))
    print(f"claudius · model={cfg['model']['name']} · env={env_cfg['kind']} · step_limit={cfg['agent']['step_limit']}")
    started = time.time()
    try:
        result = agent.run(task)
    finally:
        env.cleanup()
    elapsed = time.time() - started

    out_path = pathlib.Path(args.output) if args.output else REPO_ROOT / "runs" / f"{int(started)}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({**result, "elapsed_sec": round(elapsed, 1),
                                    "model": cfg["model"]["name"]}, indent=2), encoding="utf-8")

    u = result["usage"]
    print(f"\n── {result['status']} after {result['steps']} step(s), {elapsed:.0f}s "
          f"({u['calls']} calls, {u['prompt_tokens']}+{u['completion_tokens']} tok) ──")
    print(f"trajectory: {out_path.relative_to(REPO_ROOT)}")
    return 0 if result["status"] == "submitted" else 1
