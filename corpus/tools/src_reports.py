"""Long institutional reports from different countries and publishers, so
house styles differ (numbered chapters, boxes, executive summaries, key
messages, annexes). No compliance documents or financial filings. Gold
from bookmarks, removed from the test copy; candidates without usable
bookmarks or that fail to download are skipped.

Tried and rejected (Oct 2026): IPCC AR6 SYR and ISRO annual report (no
bookmarks); Canada's Changing Climate Report (junk tagged-layout outline);
WHO, UNEP, FAO, NZ MfE (HTML instead of PDF); Eurostat, Australian PC,
ESA, UNESCO (404); CDC, CRS (403 to scripts)."""

from __future__ import annotations

from common import Entry, built, fetch, from_bookmarks, unregister

US_PD = "Public domain (US government work)"
OPEN = "Publisher's open-access terms; local testing only"

# (id suffix, url, title, publisher / country, licence, from_bookmarks kwargs)
CANDIDATES = [
    ("nasa-se-handbook", "https://www.nasa.gov/wp-content/uploads/2018/09/nasa_systems_engineering_handbook_0.pdf",
     "NASA Systems Engineering Handbook (Rev 2)", "NASA, US", US_PD, {"max_pages": 300}),
    ("undp-hdr-2023", "https://hdr.undp.org/system/files/documents/global-report-document/hdr2023-24reporten.pdf",
     "Human Development Report 2023/2024", "UNDP", "CC BY 3.0 IGO", {"max_pages": 300}),
    ("usgs-mcs-2024", "https://pubs.usgs.gov/periodicals/mcs2024/mcs2024.pdf",
     "Mineral Commodity Summaries 2024", "USGS, US", US_PD, {"max_pages": 250}),
    ("nist-sp1270", "https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.1270.pdf",
     "Towards a Standard for Identifying and Managing Bias in AI", "NIST, US", US_PD, {}),
    ("niti-ai-strategy", "https://www.niti.gov.in/sites/default/files/2023-03/National-Strategy-for-Artificial-Intelligence.pdf",
     "National Strategy for Artificial Intelligence", "NITI Aayog, India", OPEN, {}),
    ("noaa-arctic-report-card-2023",
     "https://arctic.noaa.gov/wp-content/uploads/2023/12/ArcticReportCard_full_report2023.pdf",
     "Arctic Report Card 2023", "NOAA, US", US_PD, {}),
    ("nrel-wind-market-2023", "https://www.energy.gov/sites/default/files/2023-08/land-based-wind-market-report-2023-edition.pdf",
     "Land-Based Wind Market Report 2023", "US DOE", US_PD, {}),
    ("nasa-artemis-plan", "https://www.nasa.gov/wp-content/uploads/2020/12/artemis_plan-20200921.pdf",
     "NASA's Lunar Exploration Program Overview (Artemis Plan)", "NASA, US", US_PD, {}),
    ("eia-aeo-2023", "https://www.eia.gov/outlooks/aeo/pdf/AEO2023_Narrative.pdf",
     "Annual Energy Outlook 2023, Narrative", "EIA, US", US_PD, {}),
    ("uk-ccc-progress-2023",
     "https://www.theccc.org.uk/wp-content/uploads/2023/06/Progress-in-reducing-UK-emissions-2023-Report-to-Parliament-1.pdf",
     "Progress in Reducing UK Emissions: 2023 Report to Parliament", "Climate Change Committee, UK", OPEN,
     {"max_pages": 300}),
    ("ie-epa-environment-2020",
     "https://www.epa.ie/publications/monitoring--assessment/assessment/state-of-the-environment/EPA_Irelands_Environment_2020.pdf",
     "Ireland's Environment: An Integrated Assessment 2020", "EPA, Ireland", OPEN, {}),
    ("nist-ir8312", "https://nvlpubs.nist.gov/nistpubs/ir/2021/NIST.IR.8312.pdf",
     "Four Principles of Explainable Artificial Intelligence", "NIST, US", US_PD, {}),
    ("nasa-hidh", "https://www.nasa.gov/wp-content/uploads/2015/03/human_integration_design_handbook_revision_1.pdf",
     "Human Integration Design Handbook, Revision 1", "NASA, US", US_PD, {"max_pages": 300}),
    ("usgs-circ1405", "https://pubs.usgs.gov/circ/1405/pdf/circ1405.pdf",
     "Estimated Use of Water in the United States in 2010", "USGS, US", US_PD, {}),
]
WANT = 12
DROPPED = ["canada-changing-climate"]


def build(force: bool = False) -> None:
    for key in DROPPED:
        unregister(f"report-{key}")
    have = 0
    for key, url, title, who, licence, kw in CANDIDATES:
        if have >= WANT:
            break
        eid = f"report-{key}"
        if built(eid) and not force:
            have += 1
            continue
        try:
            src = fetch(url, f"reports/{key}.pdf", timeout=900)
        except Exception as e:  # noqa: BLE001 — a dead link just skips the candidate
            print(f"  ✗ {eid}: {e}")
            continue
        if from_bookmarks(
            Entry(id=eid, category="reports", title=title, source_url=url, license=licence,
                  gold_source="bookmarks", complete=False, variant=who),
            src, **kw,
        ):
            have += 1
