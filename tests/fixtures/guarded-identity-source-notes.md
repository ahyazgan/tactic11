# Previous identity boundary fixtures

`guarded-identity-old-boundaries.json.gz` contains seven per-track projections
from the completed 19-clip development replay: six previously accepted identity
boundaries and the rejected daylight white-6 lighting boundary. Each projection
keeps the complete available baseline history, sample positions, exact source
boxes/confidences/colors, per-observation teams and the independent tracker rows
on those exact boxes. Unrelated tracks are omitted; this tests partitioning,
not detector inference or a tracker initialized at a known failure.

Fixed palette anchors and the **original baseline's fitted centers** are separate
fields. The latter are fitted from the full unchanged baseline color history and
eligible tracks before projection; their team assignment is checked against every
baseline observation. Refitting after candidate identity changes is not allowed.

Raw caches, complete baseline/secondary outputs, palette anchors and historical
boundary decisions have recorded SHA256 hashes. The producing replay's hash is
also included. It is the first, completed development replay whose incorrectly
shared palette parameter was rejected; its unchanged source and independent
tracker outputs remain valid evidence for the regression. The original boundary
labels were not rewritten. Gzip timestamps are zero.

These are already-consumed, single-AI development observations, not new control
labels or independent human player-identity ground truth.
