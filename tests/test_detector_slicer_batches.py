"""Check the Torch batch plan against the installed slicer's real callback groups."""
import pytest

np = pytest.importorskip("numpy")
sv = pytest.importorskip("supervision")

from app.tracking.detect import DetectorConfig  # noqa: E402


@pytest.mark.parametrize("width,height,tiles,overlap", [
    (4096, 1080, 4, .15), (3840, 1906, 4, .15), (1920, 1080, 4, .15),
    (3840, 2160, 6, .15), (6500, 1000, 4, .15), (1080, 1920, 4, .15),
    (1001, 701, 3, 0.), (1001, 701, 3, .25), (513, 257, 2, .5),
])
def test_automatic_torch_batch_has_at_most_one_padding_tile(width, height, tiles, overlap):
    cfg = DetectorConfig(tiles=tiles, tile_overlap=overlap)
    batch = cfg.torch_batch_size(width, height)
    columns, rows = cfg.tile_grid(width, height)
    tw, th = int(width / columns), int(height / rows)
    calls = []

    def callback(images):
        calls.append(len(images))
        return [sv.Detections.empty() for _ in images]

    slicer = sv.InferenceSlicer(callback=callback, slice_wh=(tw, th),
        overlap_wh=(int(tw * overlap), int(th * overlap)), batch_size=batch)
    slicer(np.zeros((height, width, 3), dtype=np.uint8))
    assert len(calls) <= 2
    assert len(calls) * batch - sum(calls) <= 1


def test_explicit_batch_and_unsliced_settings_are_preserved():
    assert DetectorConfig(tiles=4, batch_size=8).torch_batch_size(4096, 1080) == 8
    assert DetectorConfig(tiles=1).torch_batch_size(4096, 1080) == 1
    # ONNX keeps its previous batching profile until separately measured.
    assert DetectorConfig(tiles=4).effective_batch_size(4096, 1080) == 26
