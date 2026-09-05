"""Authoritative identifiers for frozen contracts and ranking-affecting models."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Final

# Trusted-head round trip for issue #23; removed in the next commit.

@dataclass(frozen=True, slots=True)
class ContractVersions:
    """Identifiers that must accompany future decision and replay artifacts."""

    m1_spec: str
    information_policy: str
    tactical_state: str
    action_affordance: str
    evaluation: str
    uncertainty: str
    decision_trace: str
    mechanics_manifest: str
    outcome_model: str
    evaluation_config: str
    fixture: str

    def as_mapping(self) -> Mapping[str, str]:
        """Return a read-only, serialization-friendly registry view."""
        return MappingProxyType(asdict(self))


CURRENT_VERSIONS: Final = ContractVersions(
    m1_spec="issues-1-through-13.freeze-1",
    information_policy="issue-2.amended-by-13",
    tactical_state="issue-3.amended-by-13.contingent-reactions-19.identity-40",
    action_affordance="issue-4.amended-by-13.contingent-reactions-19.identity-40",
    evaluation="issue-5.amended-by-13",
    uncertainty="issue-6.amended-by-13",
    decision_trace="issue-7.amended-by-13",
    mechanics_manifest="bb-agent-mechanics-manifest.v1",
    outcome_model="ordinary-attack.v1",
    evaluation_config="m1-evaluation-profile.v1",
    fixture="bb-agent-fixture.v1",
)
