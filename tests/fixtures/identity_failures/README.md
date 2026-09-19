# Known identity failure fixtures

These are development diagnostic inputs, not independent control data.
Gzip contains JSON with all pitch-eligible raw detections from order zero to
the end of each short evidence window. No source images, private identities,
model weights or predicted tracker IDs are fixture inputs.

Source detector cache, source video and previously frozen manual endpoint-label
SHA-256 values are embedded. Endpoint matching uses the exact source box and
raw index. The fragment/support annotations were inspected in the original
frames: white_turn 298 (18/17), blue_referee 458 (24/14). These manual annotations
are oracle interventions; they must never become a frame-index production rule.

`audit_identity_failures --prepare-fixtures` creates fixtures once and refuses
overwrite. `load_fixture` verifies full warmup, cadence, unique source rows and
annotation coverage. SHA-256 values of compressed files are in the audit report.

Tests characterize existing failures and isolate their causes. Passing this
suite does not mean the production identity accuracy has been fixed. The default
tracker and all previously frozen accuracy decisions are unchanged.
