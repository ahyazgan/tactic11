# Third-party provenance

Source: https://github.com/GerardMaggiolino/Deep-OC-SORT
Commit: `6bb51d027b137233f5c520b6fcc4f2ae387a6ba9`.

`ocsort.py`, `association.py`, `kalmanfilter.py`: integrated_ocsort_embedding,
copyright Gerard Maggiolino 2023, MIT. The Kalman file retains its original
FilterPy attribution and MIT license in its header. `osnet_ain.py`: bundled
deep-person-reid, copyright Kaiyang Zhou 2018, MIT. Full licenses included.
Original/adapted LF hashes and paths are in `provenance.json`.

Local changes: inject the OSNet embedder; disable unsupported camera motion
compensation and upstream pickle caches; remove unused Torch imports; use an
instance-local ID counter; propagate the original detection index through both
assignment rounds and births into a sixth output column; empty output is Nx6;
pin SciPy's Hungarian solver instead of switching when optional lap is installed.
Trailing whitespace was removed. Association/Kalman equations and OSNet
architecture are otherwise unchanged.

Weights are not redistributed. The upstream authors' linked public weights
folder supplies osnet_ain_ms_d_c.pth.tar. Its pinned digest, preprocessing,
download instructions and measured limitations are documented separately.
