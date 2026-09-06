import json

from bb_agent.live_ingest import current_live_kernel_identity


def test_print_issue57_kernel_identity() -> None:
    value = current_live_kernel_identity().to_wire_dict()
    raise AssertionError(json.dumps(value, sort_keys=True, separators=(",", ":")))
