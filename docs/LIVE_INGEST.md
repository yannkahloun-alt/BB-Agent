# Post-M1 live-envelope ingest

Ticket #56 implements the external, fail-closed half of the frozen post-M1
structured-log transport from #50/#51/#54. It does **not** implement Battle
Brothers capture, canonical projection, shadow UX, or command execution.

## Wire frame

One Battle Brothers log message contains exactly one ASCII frame:

```text
BBAGENT1|<decoded-byte-length>|<sha256>|<base64url(canonical-json)>
```

The decoder rejects the whole frame if the prefix, encoded/decoded size bounds,
base64, JSON shape, byte length, SHA-256, record schema, or compatibility
identities do not validate. There is no partial canonical-object recovery.

The initial safety limits are 2 MiB decoded and 3 MiB encoded. V1 does not
fragment records.

## Record types

`STREAM_START` establishes a new host-side capture stream. The producer carries
its companion/runtime/ruleset/mod stack and the closed-M1 kernel compatibility
identity. The external process creates the random/UUID `capture_stream_id`; the
game-side component never consumes Battle Brothers gameplay RNG to mint IDs.

`DECISION_READY` carries `battle_sequence`, `source_generation`, the deterministic
`raw_source_fingerprint`, an explicit information profile, and one canonical
payload. The external process computes:

```text
raw_capture_id = sha256(
  capture_stream_id,
  battle_sequence,
  source_generation,
  raw_source_fingerprint
)
```

An exact repeated READY is idempotent. The same identity with a different raw
fingerprint or payload digest is a protocol conflict and clears current advice.
After an INVALIDATED edge, the same generation may become READY again only when
it exactly reproduces the previously known READY identity/payload, matching the
#51 cancel/reopen rule. Otherwise a strictly newer generation is required.

`DECISION_INVALIDATED` immediately clears externally usable recommendation
eligibility. Older invalidations cannot erase a newer decision.

`omniscient_debug` READY records are rejected unless the receiver is explicitly
configured to allow them.

## Compatibility identity

Every record carries the expected closed-M1 compatibility surface: M1 spec,
information policy, tactical-state and action-affordance contracts, evaluation
and uncertainty contracts, trace contract/schema, evaluator model, evaluation
config, mechanics manifest, and outcome model. A stale companion/kernel pairing
fails before a decision payload is exposed.

Game/ruleset/content fingerprint, optional exact mod stack, companion version,
and runtime game version are checked independently.

## Durable tailing and restart

`LiveLogTailer` advances a byte cursor only past complete HTML `<div class="text">`
records. A partial trailing div is left pending. Persisted state contains:

- log file identity;
- byte offset;
- a SHA-256 anchor over bytes immediately preceding that offset;
- host capture-stream ID;
- last battle/source generation;
- last READY raw-capture/payload identity and record type.

State is written to a temporary file, `fsync`ed, and atomically replaced.

On first attachment, historical records are scanned but only events from the
latest valid `STREAM_START` are surfaced. On ordinary parser restart, the same
validated cursor and host stream ID resume without replaying the log. The actual
READY payload is deliberately not persisted; an exact READY re-emission restores
it idempotently.

If the log disappears, is replaced, shrinks behind the cursor, or no longer
matches the persisted anchor, current readiness is cleared and the parser moves
to current EOF. No future READY is accepted until a fresh `STREAM_START` arrives.
This deliberately prefers lost advice to advice attached to an ambiguous game
session.

## Diagnostics

Events produced while tailing include monotonic `frame_observed_ns` and
`canonical_available_ns` timestamps plus their processing latency. These measure
external decode/order overhead only. They are not cross-process Battle Brothers
capture-to-host latency; #58 measures the real `logInfo` flush and end-to-end
latency on the game host.

## Security and scope

The log is untrusted external input. The parser uses strict JSON/base64 schemas,
never `eval`, never executes payload code, and never accepts payload-controlled
output paths. SHA-256 detects corruption; it is not authentication.

This module has no mouse/keyboard/game-command path and no Battle Brothers
runtime dependency. It is safe for later #57 canonical integration but does not
by itself authorize shadow promotion; #58 remains the real-game smoke/oracle
gate.
