import numpy as np

from app.tracking.person_parts import full_body_contacts, nested_person_mask


def test_parts_require_retained_body_and_leave_overlapping_opponent():
    boxes = np.array([[10, 10, 40, 90], [12, 10, 35, 35], [12, 65, 36, 90],
                      [25, 12, 55, 88]], dtype=float)
    original = boxes.copy()
    keep, parents = nested_person_mask(boxes)
    assert keep.tolist() == [True, False, False, True]
    assert parents == {1: 0, 2: 0}
    np.testing.assert_array_equal(boxes, original)
    assert full_body_contacts(boxes[keep]) == [True, True]


def test_similar_people_and_small_distant_person_survive():
    boxes = np.array([[0, 0, 30, 80], [2, 1, 33, 81], [60, 0, 68, 20]])
    keep, parents = nested_person_mask(boxes)
    assert keep.all() and not parents
    assert full_body_contacts(boxes) == [True, True, False]


def test_no_body_no_suppression_and_empty_mask_can_index():
    assert nested_person_mask(np.array([[0, 0, 10, 20]]))[0].all()
    boxes = np.empty((0, 4))
    mask, parents = nested_person_mask(boxes)
    assert boxes[mask].shape == (0, 4) and parents == {}
    assert full_body_contacts(boxes) == []


def test_invalid_boxes_do_not_erase_valid_person():
    boxes = np.array([[0, 0, 10, 40], [0, 0, np.inf, 100], [0, 0, 0, 0]])
    assert nested_person_mask(boxes)[0].all()


def test_nested_chain_resolves_to_surviving_body():
    boxes = np.array([[0, 0, 40, 160], [0, 0, 25, 70], [0, 0, 15, 25]])
    keep, parents = nested_person_mask(boxes)
    assert keep.tolist() == [True, False, False]
    assert parents == {1: 0, 2: 0}
