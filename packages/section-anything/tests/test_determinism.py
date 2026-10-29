"""Layout analysis gives the same reading order on every run (research finding F029).

pdfminer breaks ties between equally distant text boxes by `id()`, so table cells could come out
in a different order in each process. `extract` uses a copy of its grouping that breaks ties by
the boxes' order instead."""

from __future__ import annotations

from types import SimpleNamespace

from pdfminer.layout import LTTextBoxHorizontal, LTTextGroup

from section_anything.extract import _stable_group_textboxes, extract

# A 3 x 3 table: equal cells, equal gaps, so many box pairs are exactly as far apart.
CELLS = [(72 + 100 * c, 600 - 30 * r, 72 + 100 * c + 80, 600 - 30 * r + 12) for r in range(3) for c in range(3)]
PAGE = SimpleNamespace(bbox=(0, 0, 612, 792))


def _leaves(obj) -> list[tuple]:
    if isinstance(obj, LTTextGroup):
        return [leaf for child in obj for leaf in _leaves(child)]
    return [obj.bbox]


def _grouped(allocation_order: list[int]) -> list[tuple]:
    """Group the table's boxes, given to the function in table order but created in another order
    (so their ids, which pdfminer uses for ties, are in another order too)."""
    made = {}
    for k in allocation_order:
        box = LTTextBoxHorizontal()
        box.set_bbox(CELLS[k])
        made[k] = box
    groups = _stable_group_textboxes(PAGE, None, [made[k] for k in range(len(CELLS))])
    assert len(groups) == 1
    return _leaves(groups[0])


def test_ties_do_not_depend_on_object_ids():
    forward = _grouped(list(range(9)))
    assert sorted(forward) == sorted(CELLS)
    assert _grouped(list(reversed(range(9)))) == forward
    assert _grouped([4, 0, 8, 2, 6, 1, 7, 3, 5]) == forward


def test_extraction_is_repeatable(table_pdf):
    first = extract(table_pdf)
    assert first.text.startswith("Results")
    assert all(extract(table_pdf).text == first.text for _ in range(3))
