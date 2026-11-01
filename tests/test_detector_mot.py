"""MOT dedektör değerlendirmesi ve veri seti dilimleme."""
import numpy as np

from scripts.soccertrack_v2.build_mot_dataset import grid, read_mot, tile_boxes
from scripts.soccertrack_v2.evaluate_detector_mot import match


def test_read_mot_skips_degenerate_boxes(tmp_path) -> None:
    path = tmp_path / "m.txt"
    path.write_text("0,1,10,20,5,12,-1,-1,-1,-1\n0,2,1,1,0.5,9,-1,-1,-1,-1\n3,1,4,5,6,7,-1,-1,-1,-1\n", encoding="utf-8")
    gt = read_mot(path)
    assert gt[0] == [(10.0, 20.0, 5.0, 12.0)] and gt[3] == [(4.0, 5.0, 6.0, 7.0)]


def test_tile_boxes_keep_centred_and_clip() -> None:
    boxes = [(85.0, 10.0, 20.0, 40.0), (150.0, 10.0, 10.0, 10.0), (90.0, 50.0, 20.0, 10.0)]
    # merkezi dilimde olan kırpılır; merkezi dışarıda (155) ya da sınırda (100) olan alınmaz
    assert tile_boxes(boxes, 0, 0, 100, 100) == [(85.0, 10.0, 15.0, 40.0)]


def test_grid_matches_inference_rule() -> None:
    assert grid(4096, 1080, 3, 16 / 9) == (6, 3)
    assert grid(3840, 1906, 4, 16 / 9) == (5, 4)


def test_foot_matching_ignores_box_width_convention() -> None:
    gt = np.array([[100.0, 100.0, 120.0, 140.0]])          # dar MOT kutusu
    wide = np.array([[90.0, 95.0, 130.0, 142.0]])         # aynı oyuncu, geniş çizim
    assert match(wide, gt, 0.5, "foot") == [(0, 0)]
    assert match(wide, gt, 0.5, "iou") == []              # IoU 0,41: biçim farkı eşleşmeyi bozar
