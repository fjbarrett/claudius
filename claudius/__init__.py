"""claudius — a faithful, minimal recreation of mini-SWE-agent, the bash-only
SWE-agent scaffold used by ProgramBench (Yang et al., 2026)."""

from .agent import Agent, Submitted, LimitsExceeded, parse_action, render
from .environment import LocalEnvironment, DockerEnvironment, truncate_output
from .models import Model, ModelError

__version__ = "0.1.0"

__all__ = [
    "Agent", "Submitted", "LimitsExceeded", "parse_action", "render",
    "LocalEnvironment", "DockerEnvironment", "truncate_output",
    "Model", "ModelError",
]
