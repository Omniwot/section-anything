# Venue fit for the Section Anything report

Checked 21 Oct 2026 against official pages (read-only; nothing submitted, registered or posted).
"Verified" means the fact was read on the linked official page on that date. Re-check every date
before acting: two of them already conflict.

## The paper in one line

A text-layer method (pdfminer text plus typography, bookmarks and TOC, with optional small-model
review) for heading hierarchies in born-digital PDFs. It uses no page images and no OCR. Main
evidence is READoc (held-out arXiv), a 118-document multi-genre corpus and a small RAG pilot. Open
items: Qasper RAG experiment, held-out README evaluation, local-model numbers, Marker and
PageIndex baselines.

## Comparison

| | VisionDocs @ WACV 2027 | ICDAR 2027 | ACM DocEng 2027 | arXiv |
|---|---|---|---|---|
| What it is | 4th Workshop on Computer Vision Systems for Document Analysis and Recognition | 21st Int. Conf. on Document Analysis and Recognition | 27th ACM Symposium on Document Engineering | Preprint server |
| When / where | Workshop 4 or 5 Jan 2027; WACV 4–8 Jan 2027, Disney Springs, Buena Vista, FL | 18–22 Aug 2027, Kuala Lumpur | 2027 in Calgary; dates not announced | Any time |
| Deadline | Short papers 12 Nov 2026 (regular papers closed 18 Oct 2026) | Abstract 31 Jan 2027, full paper 20 Feb 2027 on the CFP page; the Important Dates page says 28 Feb. Plan for 20 Feb | CFP not out. 2026 precedent: full-paper abstract 21 Apr, paper 5 May; short papers 9/16 Jun | None |
| Length / template | Short: 4 pages + references (regular: 8), WACV template | At most 17 pages including figures and references, Springer LNCS | 2026 precedent: full up to 10 pages, short up to 4, demos 2; `acmart` `sigconf` | Free |
| Archival | **No** for short papers (workshop website only); regular papers go to the WACV workshop proceedings (IEEE) | Yes, Springer LNCS | Yes, ACM Digital Library | Yes (preprint) |
| Review | Double-blind | Double-blind with rebuttal | 2026: **single-blind** (author names visible) | Moderation, not peer review |
| Attendance | In person required | TODO (check registration rule) | 2026: at least one author registers | — |
| Fit with a text-only method | Weak to moderate: vision-focused title; topic list is "not limited to" and includes datasets and benchmarks, extracting document semantics, logical layout analysis, retrieval-augmented systems | Strong: document structure and benchmarks are core ICDAR material (TODO: quote the 2027 topic list) | Strong: practical document systems, structure, cost | Good for visibility; needs endorsement |
| Preprint policy | WACV main conference: arXiv posting allowed and not a prior publication; VisionDocs page silent | arXiv posting allowed, no embargo; parallel submission to other venues prohibited | 2026: work must be unpublished and not under review elsewhere; ACM reportedly allows arXiv preprints (unverified, page returned 403) | — |

Sources:
- VisionDocs: https://sites.google.com/view/avml-lab-visiondocs-wacv2027/ (types, deadlines,
  archival status, double-blind, in-person rule, topic list). WACV dates:
  https://wacv.thecvf.com/Conferences/2027. WACV preprint FAQ:
  https://wacv.thecvf.com/Conferences/2027/AuthorGuides. Proceedings to IEEE:
  https://wacv.thecvf.com/Conferences/2027/CallForWorkshops.
- ICDAR 2027: https://icdar2027.org, https://icdar2027.org/call-for-papers,
  https://icdar2027.org/important-dates, https://icdar2027.org/paper-submission-instruction,
  https://icdar2027.org/call-for-competitions. Competition proposals close 25 Oct 2026 (open now,
  but too soon for us). The submission page's contact link points to an icdar2026.org address, so
  check contacts before writing to anyone.
- DocEng: https://doceng.org/doceng2026/ (2027 in Calgary), https://doceng.org/doceng2026/cfp and
  https://doceng.org/doceng2026/submission (2026 precedent). Unverified: whether 2026 page limits
  include references, and the "application note" category.
- arXiv endorsement: https://blog.arxiv.org/2026/01/21/attention-authors-updated-endorsement-policy
  and https://info.arxiv.org/help/endorsement.html. Review and position papers in cs:
  https://blog.arxiv.org/2025/10/31/attention-authors-updated-practice-for-review-articles-and-position-papers-in-arxiv-cs-category/.
  Rate limit: https://blog.arxiv.org/2026/10/01/updated-rate-limit-policy/.

## arXiv: what the endorsement change means for us

- **The note in our plan was too narrow.** The 21 Jan 2026 change applies to new submitters in
  **all categories**, not only cs.CL or cs.IR. Since then an institutional email address alone no
  longer qualifies a new author. Two routes remain:
  - an institutional address from an academic or research institution **plus** prior authorship of
    an accepted paper in that endorsement domain; or
  - a personal endorsement from an established arXiv author in the same domain.
- Authors already endorsed in a category stay endorsed.
- The help page says most high-level subject areas are one endorsement domain. That suggests all of
  cs is one domain (cs.CL, cs.IR and cs.CV would share an endorsement), but this is our inference.
- **The Oct 2025 cs rule does not apply.** It requires peer review only for review articles and
  position papers; original research papers are exempt, and this report is original research.
- Since 1 Oct 2026, a submitter may make at most two submissions per calendar month, with at most
  three active at once.
- Likely categories: cs.CL primary with cs.IR (RAG) and cs.CV or cs.DL cross-lists. TODO: confirm
  that cs.DL fits.
- Endorsement needs a named author and an endorser. That is an owner decision and takes time, so
  start early.

## Recommendation

1. **Primary target: ICDAR 2027 main track (full paper due 20 Feb 2027).** It has the best topical
   fit. The main text is about 8,200 words (about 7,200 of prose plus 9 tables), roughly 8 pages in
   ACM two-column format. That is over 17 LNCS pages once references are added, so expect to cut
   about 20% and move Appendices A–D to supplementary material (TODO: check ICDAR's
   supplementary-material rule).
   Four months is enough to close the open items: Qasper, held-out READMEs, local models, Marker and
   PageIndex, and repeat runs. It is double-blind, so the anonymous draft works as is.
2. **arXiv: post once the results are final, ideally at or after the ICDAR submission.** ICDAR
   allows it. Start the endorsement route now, because it needs a named author.
3. **Fallback: DocEng 2027 (Calgary), when its CFP appears.** The fit is good, and a short or
   application-style paper suits the systems angle. Two cautions:
   - DocEng was single-blind in 2026, so author names would be needed at submission.
   - Dual submission is barred. If its 2027 dates follow 2026, the full-paper deadline (early May)
     falls before ICDAR's decisions (15 May 2027), so DocEng is a fallback only through its later
     short-paper track, or as an alternative chosen instead of ICDAR.
4. **Skip VisionDocs, unless an early in-person talk in Florida in January is wanted.**
   - Only the 4-page non-archival short track is still open (due 12 Nov 2026).
   - The workshop is vision-focused, and our method deliberately avoids vision.
   - In-person presentation is required.
   - A non-archival paper would not block ICDAR under WACV's rules, but check ICDAR's view of prior
     workshop papers first.

## Before any submission

- Author names, affiliations and contact details are an owner decision; the draft is anonymous.
- Close or remove every TODO in `paper.md`, especially the licence checks: OpenStax, READoc
  documents sent to providers, and the FinanceBench licence.
- Re-verify both ICDAR deadlines, and the DocEng 2027 CFP when it is out.
