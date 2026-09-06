# Live runtime compatibility

The live companion separates **runtime game version** from the pinned ruleset/source provenance.

## Reviewed source baseline

The canonical rules/content source remains `ninkjin/Battle-Brothers-Scripts` at commit
`162f498ac7c49b4c317bbf54718a595ecef6a65a`, whose script payload was decompiled from
Battle Brothers runtime 1.5.2.2. The corresponding BB-Agent ruleset identity and content
fingerprint remain unchanged.

## Runtime admission

Companion version 0.2.1 admits these runtime game versions:

- `1.5.2.2` — exact runtime version of the reviewed source baseline;
- `1.5.2.3` — admitted only so ticket #58 can perform the required real-game adapter oracle gate.

All other runtime versions fail closed with `game_version_mismatch`.

Battle Brothers 1.5.2.3 is a patch-level hotfix over 1.5.2.2. Published changes include an
Estoc crash fix, named-item recognition fixes for newly added weapons, an Executioner ending
fix, City State paint availability, a Mine Cave In marketplace fix, other minor fixes, and
binary signing. The current frozen M1 catalog contains only `actives.chop`, `actives.recover`,
`actives.reload_bolt`, and `weapon.hand_axe`; no catalog identity is changed by this runtime
admission.

This is **not** a claim that a new 1.5.2.3 decompiled source tree has been reviewed. Upstream
currently exposes the 1.5.2.2 source baseline. Runtime 1.5.2.3 therefore remains promotion-
gated by #58: native path shape/costs, command completeness, equipment, ammo/reload, previews,
transport behavior, no-cheat filtering, stale/duplicate handling, and replay must all pass the
real-game oracle before the adapter can receive `ADAPTER READY FOR SHADOW`.

If any 1.5.2.3 runtime behavior contradicts the frozen contracts, #58 returns
`ADAPTER NOT READY`; the mismatch must be diagnosed and fixed rather than widening the runtime
allowlist or ruleset by assumption.
