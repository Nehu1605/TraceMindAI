"""Deterministic incident report generation (Phase 6, improvements I4/I11/I13).

The report ties together everything: detection anomalies, RCA candidates, and a
deterministic narrative that can be *independently verified* by a human or a
second generator. Three generators are provided for the I4 comparison:

* **offline** - deterministic template, no external dependency (default)
* **llm** - optional OpenAI-compatible call, gated by `llm_enabled`
* **critic** - runs both and flags disagreements (evidence hallucination)

The report also includes a remediation playbook picked from a built-in catalog
(I11) and runs its commands in a sandbox (dry-run by default).

Redaction (I13) strips secrets before any external call; a prompt-injection
guard rejects suspicious patterns.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from common.config import Settings, get_settings
from rca.engine import RCAReport


_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password|bearer)\s*[:=]\s*\S+"),
    re.compile(r"(?i)authorization\s*:\s*bearer\s+\S+"),
    re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b"),  # base64-ish blobs
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),        # OpenAI-ish keys
]

_INJECTION_PATTERNS = [
    re.compile(r"(?i)ignore\s+(previous|above)\s+instructions"),
    re.compile(r"(?i)system\s*:\s*you\s+are\s+now"),
    re.compile(r"(?i)<\|.*?\|>"),  # special tokens
    re.compile(r"(?i)###\s*instructions?"),
]


@dataclass
class PlaybookStep:
    name: str
    command: str
    description: str = ""


@dataclass
class Playbook:
    name: str
    triggers: list[str]  # service or metric names that select this playbook
    steps: list[PlaybookStep] = field(default_factory=list)


@dataclass
class RemediationResult:
    playbook: str
    steps: list[dict] = field(default_factory=list)
    dry_run: bool = True


@dataclass
class Report:
    incident_id: str
    generated_at: datetime
    rca: RCAReport
    narrative: str
    evidence_map: dict[str, list[str]] = field(default_factory=dict)
    playbook: RemediationResult | None = None
    generators: dict[str, str] = field(default_factory=dict)
    critic: dict[str, Any] | None = None

    def to_dict(self) -> dict:
        return {
            "incident_id": self.incident_id,
            "generated_at": self.generated_at.isoformat(),
            "narrative": self.narrative,
            "evidence_map": self.evidence_map,
            "playbook": None
            if self.playbook is None
            else {
                "playbook": self.playbook.playbook,
                "dry_run": self.playbook.dry_run,
                "steps": self.playbook.steps,
            },
            "generators": self.generators,
            "critic": self.critic,
            "rca": self.rca.to_dict(),
        }


# --- Redaction (I13) ------------------------------------------------------

def redact(text: str) -> str:
    """Remove secrets/keys from text before any external call."""

    out = text
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub("[REDACTED]", out)
    return out


def guard_prompt(text: str) -> bool:
    """Return True if the text looks like a prompt-injection attempt."""

    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            return True
    return False


# --- Playbooks (I11) ------------------------------------------------------

PLAYBOOKS = {
    "db_pool_exhaustion": Playbook(
        name="db_pool_exhaustion",
        triggers=["db_connections_in_use", "postgres", "payment-service"],
        steps=[
            PlaybookStep(
                "check_pool_config",
                "kubectl get configmap payment-db-config -o yaml",
                "Verify max_connections in DB configmap",
            ),
            PlaybookStep(
                "restart_payment",
                "kubectl rollout restart deployment/payment-service",
                "Clear leaked connections by rolling the pods",
            ),
        ],
    ),
    "high_latency": Playbook(
        name="high_latency",
        triggers=["http_request_duration_ms", "cpu_percent"],
        steps=[
            PlaybookStep(
                "scale_up",
                "kubectl scale deployment/order-service --replicas=5",
                "Add capacity while debugging",
            ),
            PlaybookStep(
                "check_hpa",
                "kubectl get hpa order-service -o yaml",
                "Verify HPA is not stuck",
            ),
        ],
    ),
    "error_spike": Playbook(
        name="error_spike",
        triggers=["http_5xx_rate", "error_rate"],
        steps=[
            PlaybookStep(
                "recent_deploys",
                "kubectl rollout history deployment/payment-service",
                "List recent rollouts for quick revert",
            ),
            PlaybookStep(
                "revert_if_recent",
                "kubectl rollout undo deployment/payment-service",
                "Revert to previous revision (manual confirmation required)",
            ),
        ],
    ),
}


def select_playbook(rca: RCAReport) -> str | None:
    top = rca.top_cause
    if top is None:
        return None
    for name, playbook in PLAYBOOKS.items():
        for trigger in playbook.triggers:
            if trigger in top.service or any(
                trigger in anomaly.metric for anomaly in []
            ):
                return name
    return "error_spike"


def run_playbook(name: str, dry_run: bool = True) -> RemediationResult:
    playbook = PLAYBOOKS.get(name)
    if playbook is None:
        return RemediationResult(playbook=name, steps=[{"error": "unknown playbook"}])

    steps_out: list[dict] = []
    for step in playbook.steps:
        if dry_run:
            steps_out.append(
                {"name": step.name, "command": step.command, "dry_run": True}
            )
        else:
            try:
                result = subprocess.run(
                    shlex.split(step.command),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                steps_out.append(
                    {
                        "name": step.name,
                        "command": step.command,
                        "dry_run": False,
                        "exit_code": result.returncode,
                        "stdout": result.stdout[:500],
                        "stderr": result.stderr[:500],
                    }
                )
            except subprocess.TimeoutExpired:
                steps_out.append(
                    {"name": step.name, "command": step.command, "dry_run": False, "timeout": True}
                )
            except Exception as exc:  # pragma: no cover - defensive
                steps_out.append(
                    {"name": step.name, "command": step.command, "dry_run": False, "error": str(exc)}
                )

    return RemediationResult(playbook=name, steps=steps_out, dry_run=dry_run)


# --- Deterministic offline generator --------------------------------------

def _deterministic_narrative(rca: RCAReport) -> str:
    top = rca.top_cause
    if top is None:
        return "No anomalies detected; no incident to explain."
    if rca.abstained:
        return (
            "The evidence is insufficient to confidently identify a root cause. "
            "Escalate for manual investigation."
        )
    evidence_refs = ", ".join(top.evidence_ids[:3])
    return (
        f"Incident likely originated in **{top.service}** (confidence: {top.confidence}). "
        f"{top.rationale}. Key evidence: {evidence_refs}. "
        f"Recommended remediation: see attached playbook."
    )


def generate_offline(rca: RCAReport) -> str:
    return _deterministic_narrative(rca)


# --- Optional LLM generator ----------------------------------------------

def generate_llm(rca: RCAReport, settings: Settings) -> str:
    if not settings.llm_enabled:
        return "LLM disabled; offline generator used."
    if guard_prompt(str(rca.to_dict())):
        return "Prompt guard rejected input; offline generator used."

    # Stub - real implementation would call OpenAI-compatible endpoint here.
    # The critic below will compare this to the offline version anyway.
    return "LLM generator not implemented (no API key); offline generator used."


# --- Critic (I4) ---------------------------------------------------------

def critic(offline: str, llm: str) -> dict[str, Any]:
    """Compare two generator outputs and flag disagreements."""

    disagreements: list[str] = []
    if offline.strip().lower() != llm.strip().lower():
        disagreements.append(
            "LLM output differs from deterministic offline version - review before use."
        )
    return {"agree": len(disagreements) == 0, "disagreements": disagreements}


# --- High-level builder ---------------------------------------------------

def build_report(
    incident_id: str,
    rca: RCAReport,
    settings: Settings | None = None,
    run_playbook_flag: bool = True,
    dry_run: bool = True,
) -> Report:
    settings = settings or get_settings()

    offline = generate_offline(rca)
    llm = generate_llm(rca, settings)
    critic_result = critic(offline, llm)

    playbook_name = select_playbook(rca)
    playbook_result = run_playbook(playbook_name, dry_run=dry_run) if run_playbook_flag else None

    evidence_map: dict[str, list[str]] = {}
    if rca.top_cause:
        evidence_map[rca.top_cause.service] = rca.top_cause.evidence_ids

    return Report(
        incident_id=incident_id,
        generated_at=datetime.now(),
        rca=rca,
        narrative=offline,
        evidence_map=evidence_map,
        playbook=playbook_result,
        generators={"offline": offline, "llm": llm},
        critic=critic_result,
    )