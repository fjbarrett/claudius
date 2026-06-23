"""The agent loop — a faithful, minimal recreation of mini-SWE-agent's
DefaultAgent.

Control flow is driven by exceptions (the mini-SWE-agent pattern):
- a malformed response re-prompts the model with a format error (recoverable),
- `Submitted` ends the run cleanly,
- `LimitsExceeded` ends the run on the step/time budget.

Exactly one bash command is executed per step. There are no bespoke tools.
"""
from __future__ import annotations

import re
import time

# Accept ```bash or ```sh fenced blocks.
_BLOCK_RE = re.compile(r"```(?:bash|sh)\s*\n(.*?)```", re.DOTALL)


class Submitted(Exception):
    """Terminating: the agent declared the task complete."""


class LimitsExceeded(Exception):
    """Terminating: the step or time budget was exhausted."""


class _FormatError(Exception):
    """Recoverable: the response didn't contain exactly one command."""


def render(template: str, **values) -> str:
    """Tiny `{{var}}` substitution — keeps the package dependency-free."""
    out = template
    for key, value in values.items():
        out = out.replace("{{" + key + "}}", str(value))
    return out


def parse_action(response: str) -> str:
    """Return the single command, or raise _FormatError if not exactly one."""
    blocks = _BLOCK_RE.findall(response)
    if len(blocks) != 1:
        raise _FormatError(len(blocks))
    return blocks[0].strip()


class Agent:
    def __init__(self, model, env, config: dict, *, logger=None):
        self.model = model
        self.env = env
        self.cfg = config
        self.log = logger or (lambda *_: None)
        self.messages: list[dict] = []
        self.step_count = 0
        self.started_at = 0.0

    def add(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})

    # ── main loop ────────────────────────────────────────────────────────────
    def run(self, task: str) -> dict:
        a, e, t = self.cfg["agent"], self.cfg["environment"], self.cfg["templates"]
        self.started_at = time.time()
        system = render(
            t["system"],
            submit_sentinel=a["submit_sentinel"],
            action_timeout_min=round(e["action_timeout_sec"] / 60),
            output_char_limit=e["output_char_limit"],
        )
        self.add("system", system)
        self.add("user", render(t["instance"], task=task))

        while True:
            try:
                self.step()
            except Submitted as exc:
                return self._result("submitted", str(exc))
            except LimitsExceeded as exc:
                return self._result("limits_exceeded", str(exc))

    def step(self) -> None:
        a, t = self.cfg["agent"], self.cfg["templates"]

        # Hard limits (terminating) checked before spending another model call.
        elapsed = time.time() - self.started_at
        if self.step_count >= a["step_limit"]:
            raise LimitsExceeded(f"step limit ({a['step_limit']}) reached")
        if elapsed >= a["time_limit_sec"]:
            raise LimitsExceeded(f"time limit ({a['time_limit_sec']}s) reached")

        self.step_count += 1
        response = self.model.query(self.messages)["content"]
        self.add("assistant", response)
        self.log("assistant", self.step_count, response)

        try:
            action = parse_action(response)
        except _FormatError:
            self.add("user", t["format_error"])
            self.log("format_error", self.step_count, "")
            return

        self.log("action", self.step_count, action)
        result = self.env.execute(action)

        # Submission: the model ran `echo <sentinel>`; the marker shows up in the
        # command output, which is how we detect a clean finish.
        if a["submit_sentinel"] in result["output"]:
            raise Submitted(response)

        observation = render(
            t["action_observation"],
            returncode=result["returncode"],
            output=result["output"],
        )
        warning = self._budget_warning()
        if warning:
            observation = f"{observation}\n\n{warning}"
        self.add("user", observation)
        self.log("observation", self.step_count, observation)

    # ── helpers ──────────────────────────────────────────────────────────────
    def _budget_warning(self) -> str:
        a, t = self.cfg["agent"], self.cfg["templates"]
        steps_left = a["step_limit"] - self.step_count
        mins_left = (a["time_limit_sec"] - (time.time() - self.started_at)) / 60
        reasons = []
        if steps_left < a["warn_steps_remaining"]:
            reasons.append(f"Only {steps_left} step(s) remain.")
        if mins_left < a["warn_minutes_remaining"]:
            reasons.append(f"Only {mins_left:.0f} minute(s) remain.")
        if not reasons:
            return ""
        return render(
            t["step_warning"],
            reason=" ".join(reasons),
            submit_sentinel=a["submit_sentinel"],
        )

    def _result(self, status: str, detail: str) -> dict:
        return {
            "status": status,
            "detail": detail,
            "steps": self.step_count,
            "messages": self.messages,
            "usage": {
                "calls": self.model.n_calls,
                "prompt_tokens": self.model.prompt_tokens,
                "completion_tokens": self.model.completion_tokens,
            },
        }
