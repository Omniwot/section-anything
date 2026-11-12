"""Free without an outline: levels follow the document's running section numbers (research finding F092).

A heading cannot close a numbered section that the next numbered heading shows to be still open: an unnumbered
heading between 3.2.1 and 3.2.2 is inside 3.2.1, whatever its type says, and "1." between 1.2 and 1.3 is a list
item, not chapter 1. "Chapter 3" over "3.1" is the numbering's top level. Sections, titles and offsets do not
change; only levels do."""

from __future__ import annotations

from section_anything.strategies.rules import _carries_on, _keep_sections_open, _label_number, _numbering_spine
from test_backmatter_levels import _ext, _free


def test_carries_on_counts_the_sections_left_open():
    assert _carries_on((3, 2, 1), (3, 2, 2)) == 2  # 3 and 3.2 stay open
    assert _carries_on((3, 1, 2), (3, 2)) == 1
    assert _carries_on((3,), (3, 1)) == 1
    assert _carries_on((3, 2), (3, 2, 1)) == 2
    assert _carries_on((3, 2), (3, 4)) == 1  # one missed heading is allowed
    assert _carries_on((3, 2), (3, 4), skip=0) == 0
    assert _carries_on((3, 2), (3, 3), skip=0) == 1
    assert _carries_on((3, 6), (4,)) == 0  # a new top-level section: nothing stays open
    assert _carries_on((3, 6), (4, 1)) == 0
    assert _carries_on((3, 2), (3, 2)) == 0  # the same number again (a contents line)
    assert _carries_on((3, 4), (3, 2)) == 0  # going back
    assert _carries_on((3, 2), (3, 9)) == 0  # too far ahead to be the same run
    assert _carries_on((1,), (2,)) == 0


def test_label_number_reads_chapter_labels_only():
    assert _label_number("Chapter 3") == ("chapter", 3)
    assert _label_number("CHAPTER IV") == ("chapter", 4)
    assert _label_number("Part 2") == ("part", 2)
    assert _label_number("Appendix A") is None  # appendices stand outside the running numbers
    assert _label_number("Schedule 2") is None
    assert _label_number("3.1") is None
    assert _label_number("Introduction") is None


def test_a_list_item_between_two_sections_of_one_chapter_is_not_a_chapter():
    nums = ["1", "1.1", "1.2", "1.", "2.", "1.3", "2", "2.1"]
    assert _numbering_spine(nums) == [(1,), (1, 1), (1, 2), None, None, (1, 3), (2,), (2, 1)]


def test_single_numbers_stand_when_the_numbering_moves_on():
    nums = ["1", "2", "2.1", "2.2", "3", "3.1", "4"]
    assert _numbering_spine(nums) == [(1,), (2,), (2, 1), (2, 2), (3,), (3, 1), (4,)]


def test_chapter_labels_are_the_top_level_when_the_numbers_under_them_say_so():
    nums = ["Chapter 1", "1.1", "1.2", "Chapter 2", "2.1", "Chapter 3", "", "Chapter 4", "4.1"]
    spine = _numbering_spine(nums)
    assert spine[0] == (1,) and spine[3] == (2,) and spine[7] == (4,)
    assert spine[5] is None  # no numbered section under it: its style decides


def test_labels_that_do_not_match_the_numbers_are_left_alone():
    # Parts over chapters: "Part II" is followed by 3.1, so Parts are not the numbering's top level.
    nums = ["Part I", "1", "1.1", "2", "2.1", "Part II", "3", "3.1", "Part III", "4", "4.1"]
    spine = _numbering_spine(nums)
    assert [spine[i] for i in (0, 5, 8)] == [None, None, None]
    assert spine[1] == (1,) and spine[6] == (3,)
    # One label is no pattern.
    assert _numbering_spine(["Chapter 1", "1.1", "1.2"])[0] is None


def test_a_heading_that_would_close_an_open_section_goes_under_the_one_before():
    #         3.2  3.2.1  ?  ?  3.2.2  3.3
    spine = [(3,), (3, 2), (3, 2, 1), None, None, (3, 2, 2), (3, 3)]
    levels = [1, 2, 3, 1, 5, 3, 2]
    _keep_sections_open(levels, spine, set())
    assert levels == [1, 2, 3, 4, 5, 3, 2]  # the level-1 heading is inside 3.2.1; the smaller one stays below it


def test_headings_keep_their_order_of_levels_when_moved():
    spine = [(2, 4), (2, 4, 1), None, None, None, (2, 4, 2)]
    levels = [2, 3, 2, 4, 2, 3]
    _keep_sections_open(levels, spine, set())
    assert levels == [2, 3, 4, 5, 4, 3]


def test_headings_stay_when_no_section_is_open_across_them():
    spine = [(3, 6), None, (4,), (4, 1), None, (4, 2)]
    levels = [2, 1, 1, 2, 2, 2]
    _keep_sections_open(levels, spine, set())
    assert levels == [2, 1, 1, 2, 2, 2]  # back matter between chapters; a sibling of 4.1 in its own style


def test_headings_stay_between_flat_numbers_with_no_section_above_them():
    # A statute's inserted sections 26.1 and 26.2, a regulation's 122.49 and 122.51: no heading numbered 26 or 122
    # was read, so nothing shows that these numbers nest, and a group heading between them keeps its level.
    spine = [(26, 1), None, (26, 2), (27, 1), None, (27, 2)]
    levels = [2, 1, 2, 2, 1, 2]
    _keep_sections_open(levels, spine, set())
    assert levels == [2, 1, 2, 2, 1, 2]


def test_headings_stay_where_labels_set_the_numbered_levels_otherwise():
    spine = [(6,), None, (6, 1)]
    levels = [2, 1, 5]  # Chapter at 2, "6.1" at 5: the levels do not follow the numbers, so nothing is concluded
    _keep_sections_open(levels, spine, set())
    assert levels == [2, 1, 5]


def test_a_style_shared_by_several_depths_is_unsure_and_goes_under_the_section_before():
    spine = [(2, 3), (2, 3, 1), None, (2, 3, 2)]
    levels = [2, 3, 3, 3]
    _keep_sections_open(levels, spine, set(), unsure={2})
    assert levels == [2, 3, 4, 3]
    # With a number skipped (4.5.2 then 4.5.4) the heading may be 4.5.3 with its number unread: it stays.
    spine = [(4, 5), (4, 5, 2), None, (4, 5, 4)]
    levels = [2, 3, 3, 3]
    _keep_sections_open(levels, spine, set(), unsure={2})
    assert levels == [2, 3, 3, 3]


THESIS = [("Contents", 24, True), ("Chapter 1 Introduction", 20, True), ("1.1 Motivation", 14, True),
          ("Key idea", 20, True), ("1. First list item", 10, True), ("2. Second list item", 10, True),
          ("1.2 Outline", 14, True), ("Chapter 2 Methods", 20, True), ("2.1 Data", 14, True),
          ("2.1.1 Sources", 12, True), ("Cleaning", 12, True), ("2.1.2 Splits", 12, True), ("2.2 Models", 14, True),
          ("Chapter 3 Results", 20, True), ("3.1 Main result", 14, True), ("3.2 Ablations", 14, True),
          ("References", 24, True)]


def test_a_thesis_nests_sections_under_chapters_and_stray_headings_under_sections():
    levels = _free(_ext(THESIS, per_page=2))
    assert levels["Chapter 1 Introduction"] == levels["Chapter 2 Methods"] == levels["Chapter 3 Results"] == 1, levels
    assert levels["Contents"] == levels["References"] == 1
    assert levels["1.1 Motivation"] == levels["2.2 Models"] == 2
    assert levels["2.1.1 Sources"] == 3
    assert levels["Key idea"] == 3  # set like a chapter title, but 1.2 follows: it is inside 1.1
    assert levels["1. First list item"] > 2 and levels["2. Second list item"] > 2  # not chapters 1 and 2
    assert levels["Cleaning"] == 3  # in the subsections' own style: beside them, as before


def test_a_paper_without_stray_headings_is_unchanged():
    paper = [("A Study of Sectioning", 18, True), ("1 Introduction", 12, True), ("2 Methods", 12, True),
             ("2.1 Data", 10, True), ("2.2 Models", 10, True), ("3 Results", 12, True), ("References", 12, True)]
    levels = _free(_ext(paper))
    assert [levels[t] for t in ("1 Introduction", "2 Methods", "2.1 Data", "2.2 Models", "3 Results", "References")] == [1, 1, 2, 2, 1, 1]
