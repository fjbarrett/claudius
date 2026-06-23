"""Execution environments.

Everything the agent does is a bash command that runs here — there are no
bespoke tools. This mirrors mini-SWE-agent: the model's entire interface to the
world is the shell.

`LocalEnvironment` runs commands on the host in a fixed working directory.
`DockerEnvironment` mirrors the paper's setup: an ubuntu:22.04 container started
with `--network none` (no internet), with each command run via `docker exec`.

In both, every command runs in a FRESH shell with a FIXED cwd — state does not
persist between commands (just like mini-SWE-agent's default). The system prompt
tells the model this so it chains with `&&` / uses absolute paths.
"""
from __future__ import annotations

import os
import subprocess
import uuid


def truncate_output(text: str, limit: int, keep_each_side: int) -> str:
    """Keep the first and last `keep_each_side` chars of an over-long output,
    with an elision notice in the middle (paper §B.1: 10k cap → first+last 5k)."""
    if len(text) <= limit:
        return text
    head = text[:keep_each_side]
    tail = text[-keep_each_side:]
    elided = len(text) - len(head) - len(tail)
    return f"{head}\n\n[... {elided} characters elided ...]\n\n{tail}"


class LocalEnvironment:
    def __init__(self, cwd: str, *, timeout: int, output_char_limit: int,
                 output_keep_each_side: int):
        self.cwd = os.path.abspath(cwd)
        os.makedirs(self.cwd, exist_ok=True)
        self.timeout = timeout
        self.output_char_limit = output_char_limit
        self.output_keep_each_side = output_keep_each_side

    def execute(self, command: str) -> dict:
        try:
            proc = subprocess.run(
                ["bash", "-c", command],
                cwd=self.cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            output = (proc.stdout or "") + (proc.stderr or "")
            returncode = proc.returncode
        except subprocess.TimeoutExpired as exc:
            partial = (exc.stdout or "") + (exc.stderr or "")
            if isinstance(partial, bytes):
                partial = partial.decode("utf-8", "replace")
            output = partial + f"\n[command timed out after {self.timeout}s]"
            returncode = 124
        output = truncate_output(
            output, self.output_char_limit, self.output_keep_each_side
        )
        return {"output": output, "returncode": returncode}

    def cleanup(self) -> None:  # symmetry with DockerEnvironment
        pass


class DockerEnvironment:
    """Run each command inside a long-lived container. Faithful to the paper's
    no-internet sandbox. Untested in this repo's CI — requires a Docker daemon."""

    def __init__(self, *, image: str, network: str, timeout: int,
                 output_char_limit: int, output_keep_each_side: int,
                 workdir: str = "/workspace"):
        self.image = image
        self.timeout = timeout
        self.output_char_limit = output_char_limit
        self.output_keep_each_side = output_keep_each_side
        self.workdir = workdir
        self.container = f"claudius-{uuid.uuid4().hex[:12]}"
        subprocess.run(
            ["docker", "run", "-d", "--rm",
             "--name", self.container,
             f"--network={network}",
             "-w", workdir, image,
             "sleep", "infinity"],
            check=True, capture_output=True, text=True,
        )

    def execute(self, command: str) -> dict:
        try:
            proc = subprocess.run(
                ["docker", "exec", "-w", self.workdir, self.container,
                 "bash", "-c", command],
                capture_output=True, text=True, timeout=self.timeout,
            )
            output = (proc.stdout or "") + (proc.stderr or "")
            returncode = proc.returncode
        except subprocess.TimeoutExpired:
            output = f"[command timed out after {self.timeout}s]"
            returncode = 124
        output = truncate_output(
            output, self.output_char_limit, self.output_keep_each_side
        )
        return {"output": output, "returncode": returncode}

    def cleanup(self) -> None:
        subprocess.run(["docker", "rm", "-f", self.container],
                       capture_output=True, text=True)
