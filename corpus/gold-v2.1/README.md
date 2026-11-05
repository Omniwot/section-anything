# Answer keys v2.1 (research finding F063)

Written by `gold_v21.py` (Section Anything, branch fix/match-failures, `corpus/tools/match_audit/`) from the
v2 keys in `../gold-v2/` (F058), which stay as they were, as do the originals in `../gold/`. One more documented
rule changes pages, applied to every document without looking at any system's output:

- **R3, mention copy to printed heading.** A heading whose title, on its key page and the pages either side, is
  printed only as a mention -- a list item, a quotation, part of a sentence, a figure or table label, a contents
  entry whose leaders were cut, a contents list under a printed "Contents" title holding three or more key
  headings, or (in documents that print their headings' numbers) a copy without the heading's number -- moves to
  the first later page where it is printed as a heading line of its own: R1's acceptance test, with the title's
  number when it has one, outside contents lists and running headers, at least 2 pages after the key page, not
  before the previous heading's page and not after the next correctly placed heading's page (+1). Without such
  a copy it is left as it was.

`CHANGES.jsonl` lists every change (176 lines), with the old and new page, why the key page's copy is a mention,
and the text of the printed copy. Titles are not edited.
