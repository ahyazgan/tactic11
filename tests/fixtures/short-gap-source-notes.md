# Short-gap source fixtures

These are compressed JSON excerpts from already consumed development sources,
not synthetic detector boxes or newly independent controls. Each file includes
the original raw-cache path and SHA256, source configuration, sample time/frame
metadata and an explicit projection description.

- `short-gap-night84.json.gz`: all pitch-eligible detector rows in the first
  239 sampled observations of night segment 84. Includes six recorded secondary
  observations around the later blue-to-white transfer. The test replays the
  complete warmup before the missing detection; it does not initialize a tracker
  at the failure with oracle velocity. Real team scoring belongs to the full
  development replay; this small test uses dummy team values only to check evidence
  preservation.
- `short-gap-night3-crowd.json.gz`: all pitch-eligible detector rows in the first
  152 sampled observations of old night segment 3. The test requires the candidate
  to leave this crowded prefix exactly equal to baseline. This is a conservative
  no-change requirement, not a claim of independently adjudicated player identity.

Projection used `PitchCalibration.from_dict(raw['calibration']).is_on_pitch`
with the raw configuration's `pitch_margin_m`, matching the existing replay
filter. Box, confidence and color values were copied without rounding or model
inference. Source videos and original raw caches remain untouched. Gzip timestamps
are zero for reproducible fixture bytes.
