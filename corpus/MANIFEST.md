# Corpus manifest

Six documents, 69 pages, all federal public-domain material excerpted from `ecfr.gov` and `govinfo.gov`. Retrieved **11 September 2026**; eCFR issue date **4 August 2026**.

`pdf/` holds the excerpted PDFs the ingestion pipeline cracks. `text/` holds a plain-text extraction of each, committed so that a diff shows when an upstream source has moved under you. `python fetch_corpus.py` rebuilds both from `sources.json` on a clean clone.

---

## Documents

### `CFR-20-LIMITS` — 10 CFR Part 20 Subparts C and D, Occupational Dose Limits

| | |
|---|---|
| `doc_type` | `regulation` |
| Source | https://www.ecfr.gov/current/title-10/chapter-I/part-20 |
| API | `https://www.ecfr.gov/api/versioner/v1/full/2026-08-04/title-10.xml?part=20` |
| Excerpted | §§ 20.1003, 20.1201, 20.1206, 20.1207, 20.1208, 20.1301, 20.1502 — each in full |
| Pages | 15 |
| Anchor | Section number and paragraph designation. |
| Backs | R3, R4 |

§ 20.1003 the definitions — the largest section here and the only place *total effective dose equivalent*, *lens dose equivalent*, *shallow-dose equivalent*, *deep-dose equivalent* and *annual limit on intake* are defined. § 20.1201 the adult occupational limits, § 20.1206 **planned special exposures**, § 20.1207 minors, § 20.1208 the embryo/fetus of a declared pregnant woman, § 20.1301 members of the public, § 20.1502 when monitoring is required.

**Three different dose quantities carry three different limits, and they are not interchangeable:**

| Quantity | Annual limit (§ 20.1201) |
|---|---|
| Total effective dose equivalent | 5 rem (0.05 Sv) |
| Lens dose equivalent | 15 rem (0.15 Sv) |
| Shallow-dose equivalent, skin or extremity | 50 rem (0.5 Sv) |

A 20 rem lens dose is under the 25 rem *total effective dose equivalent* threshold for immediate notification and over the 15 rem *lens* threshold for the 24-hour one. A system that flattens "dose" into a single number will be wrong in both directions at once, and the packets are built to expose it.

> **§ 20.1206 is the exception the architecture exists to get right.** § 20.1201(a) applies its limits "**except for planned special exposures under § 20.1206**". A planned special exposure is a dose deliberately authorised in addition to, and accounted for separately from, the ordinary limits — and it is valid only if **all seven** conditions in § 20.1206(a)–(g) are satisfied, including written authorisation *before the exposure occurs* and a lifetime cap of five times the annual limits. A dose above 5 rem that is a valid planned special exposure is **not** a dose "in excess of the § 20.1201 limits", so § 20.2203(a)(2)(i) never fires.

### `CFR-20-REPORTS` — 10 CFR Part 20 Subpart M, Notifications and Reports

| | |
|---|---|
| `doc_type` | `regulation` |
| Source | https://www.ecfr.gov/current/title-10/chapter-I/part-20/subpart-M |
| Excerpted | §§ 20.2201, 20.2202, 20.2203, 20.2204, 20.2206 — each in full |
| Pages | 6 |
| Anchor | Section number and paragraph designation. |
| Backs | R1, R2, R3, R4 |

The smallest document that carries the most weight. Four duties on three clocks, with different thresholds and different recipients:

| Duty | Clock | Trigger | Goes to |
|---|---|---|---|
| § 20.2202(a) immediate notification | Immediately | TEDE ≥ 25 rem · lens ≥ 75 rem · shallow ≥ 250 rad · release ≥ 5× ALI | NRC Operations Center |
| § 20.2202(b) 24-hour notification | 24 h from discovery | **Loss of control** *and* TEDE > 5 rem · lens > 15 rem · shallow > 50 rem · release > 1× ALI | NRC Operations Center |
| § 20.2203 written report | 30 days | Any § 20.2202 incident, or a dose exceeding a § 20.1201/.1207/.1208/.1301 limit | NRC |
| § 20.2204 planned-exposure report | 30 days | Any planned special exposure conducted under § 20.1206 | **NRC Regional Office** |

> **§ 20.2202(b) is conjunctive and easy to misread.** The 24-hour duty requires an event "**involving loss of control of licensed material**" *and* one of the dose conditions. A dose over 5 rem with no loss of control does not trigger it — but it does exceed the § 20.1201 annual limit, so the 30-day written report is owed anyway. The phrase `loss of control` appears **exactly once in the entire corpus**, in this paragraph. Everything turns on it.

### `CFR-30` — 10 CFR 30.70–30.72, Schedules A, B and C

| | |
|---|---|
| `doc_type` | `regulation` |
| Source | https://www.ecfr.gov/current/title-10/chapter-I/part-30 |
| Excerpted | §§ 30.70, 30.71, 30.72 — each in full |
| Pages | 9 |
| Anchor | Schedule letter and radionuclide row. |
| Backs | — (no rule; grounds quantity questions) |

**The only documents in the corpus carrying column-aligned numeric tables**, and the reason table extraction matters here. Schedule A exempt concentrations (164 rows), Schedule B exempt quantities (187 rows), Schedule C quantities requiring consideration of an emergency plan (99 rows, with a release-fraction column alongside the curie quantity).

These are *sections*, not appendices, which is why they are reachable at all — see **What this corpus deliberately does not contain** below.

> Header cells wrap across several lines because the radionuclide column is wide; the data rows do not. An extraction that loses the header but keeps the columns is still usable. One that misaligns the data rows is not — a release fraction read as a quantity is off by orders of magnitude. Check this explicitly against Textract's Tables output.

### `CFR-34` — 10 CFR Part 34, Industrial Radiography

| | |
|---|---|
| `doc_type` | `regulation` |
| Source | https://www.ecfr.gov/current/title-10/chapter-I/part-34 |
| Excerpted | §§ 34.1, 34.13, 34.71, 34.83, 34.101 — each in full |
| Pages | 5 |
| Anchor | Section number. |
| Backs | — (grounds the equipment-failure duty) |

The licensee-specific layer. § 34.101 requires a **written report within 30 days** for three named equipment failures — an unintentional disconnection of the source assembly from the control cable, an inability to retract the source assembly to its fully shielded position, and the failure of any component critical to safe operation.

**This duty is independent of dose.** A source that cannot be retracted is reportable under § 34.101 even if nobody received any measurable exposure at all, and § 34.101(b) additionally shapes the contents of any § 20.2203 overexposure report that involves a safety-component failure. A dossier that reports only the dose consequences of a stuck source has missed a duty that exists regardless of them.

### `FR-DOSE` — 91 FR 43456, Reforming and Modernizing the NRC's Radiation Protection Framework

| | |
|---|---|
| `doc_type` | `preamble` |
| Source | https://www.federalregister.gov/documents/2026/07/15/2026-14208 |
| PDF | https://www.govinfo.gov/content/pkg/FR-2026-07-15/pdf/2026-14208.pdf |
| Published | 15 July 2026 |
| **Status** | **PROPOSED RULE — not law** |
| Excerpted | § III.B *Occupational dose limits and the planned special exposure provisions* (printed pp. 43469–43476) · § III.E *Planned special exposures and the reporting interface* (pp. 43483–43485) · § IV.C *Reporting of doses in excess of the limits* (pp. 43494–43498) |
| Pages | 16 |
| Anchor | Printed Federal Register page. Printed page *n* is PDF page *n − 43455*. |
| Backs | R3, R4 |

The NRC's own extended reasoning about what the dose limits are for and how planned special exposures interact with the reporting duties.

> **This is a proposed rule, and that is deliberate.** It describes what the NRC has *suggested* the framework might become, not what it currently requires. A determination grounded in this document rather than in Part 20 is wrong even when it is well cited and internally coherent — and that is one of the hardest failures to see in review, because the citation resolves and the prose is authoritative. See **The proposed-rule hazard** below.

### `FR-MATERIALS` — 91 FR 28916, Modernizing NRC Regulations for Byproduct Material Use

| | |
|---|---|
| `doc_type` | `preamble` |
| Source | https://www.federalregister.gov/documents/2026/05/18/2026-09877 |
| PDF | https://www.govinfo.gov/content/pkg/FR-2026-05-18/pdf/2026-09877.pdf |
| Published | 18 May 2026 |
| **Status** | **PROPOSED RULE — not law** |
| Excerpted | § II.D *Radiography licensee obligations and equipment-failure notification* (printed pp. 28924–28930) · § III.A *Event notification and the reporting interface* (pp. 28932–28942) |
| Pages | 18 |
| Anchor | Printed Federal Register page. Printed page *n* is PDF page *n − 28915*. |
| Backs | R1, R2 |

Discussion of the licensing and notification framework for byproduct material users, including radiography. Same caution as `FR-DOSE`: **proposed, not in force.**

---

## The proposed-rule hazard

**Both preambles in this corpus are proposed rules.** No other project in this cohort has that property, and it exists here on purpose.

A worker retrieving on "occupational dose limit" or "planned special exposure" will find `FR-DOSE` extremely responsive — it is long, on-topic, written in confident regulatory prose, and discusses exactly the provisions at issue. It is also **not the law**, and a determination resting on it is wrong in a way that passes every shallow check: the citation resolves, the chunk genuinely supports the sentence, and the reasoning reads well.

Three consequences for the build:

1. **`doc_type` alone is not enough.** A preamble to a *final* rule construes text that is in force; a preamble to a *proposed* rule describes text that is not. Carry the distinction in your chunk metadata and make it filterable — `status: proposed` is the minimum.
2. **The output guardrail must check it.** A dossier asserting a threshold or a duty whose only supporting citation is a proposed rule should be blocked, not merely flagged.
3. **One golden case must be built on it**, and one adversarial case: a question whose most semantically similar chunk lives in `FR-DOSE` but whose correct answer is in Part 20.

---

## Cross-references — the multi-hop chains

| # | Hop 1 | Hop 2 | Why it matters |
|---|---|---|---|
| 1 | `CFR-20-REPORTS` § 20.2203(a)(2)(i) dose in excess of the limits | `CFR-20-LIMITS` § 20.1201(a) "except for planned special exposures" | The duty names a limit; the limit carves out a class of doses the duty therefore never reaches. |
| 2 | `CFR-20-LIMITS` § 20.1201(a) exception | `CFR-20-LIMITS` § 20.1206(a)–(g) seven conditions | An exception asserted without checking all seven is a guess. |
| 3 | `CFR-20-LIMITS` § 20.1206(f) | `CFR-20-REPORTS` § 20.2204 | An excepted exposure still owes a report — to a different office, on the same 30-day clock. |
| 4 | `CFR-20-REPORTS` § 20.2202(b) dose thresholds | `CFR-20-REPORTS` § 20.2202(b) opening words | The thresholds are conditional on loss of control, three lines above them. |
| 5 | `CFR-20-REPORTS` § 20.2203(b) contents | `CFR-34` § 34.101(b) | A radiography overexposure report has extra required contents that live in a different Part. |
| 6 | `CFR-34` § 34.101(a) equipment failures | `CFR-20-REPORTS` § 20.2202 | Two independent duties on one event; neither substitutes for the other. |

---

## Retrieval distractors

Counts measured from the committed `text/` extraction.

| Term | Occurrences | Where | The confusion it creates |
|---|---|---|---|
| `planned special exposure` | 47 | FR-DOSE 24, CFR-20-LIMITS 17, CFR-20-REPORTS 6 | **Most occurrences are in a proposed rule.** The operative conditions are the 17 in Part 20; the 24 in `FR-DOSE` describe a framework that is not in force. |
| `total effective dose equivalent` | 13 | FR-DOSE 6, CFR-20-LIMITS 4, CFR-20-REPORTS 3 | One of three dose quantities, each with its own threshold at each tier. Never interchangeable with the other two. |
| `shallow-dose equivalent` | 9 | CFR-20-LIMITS 4, FR-DOSE 3, CFR-20-REPORTS 2 | Measured in **rads/gray** at the immediate tier (250 rad) and **rem** at the annual limit (50 rem). Two units for one quantity. |
| `lens dose equivalent` | 7 | CFR-20-LIMITS 3, FR-DOSE 2, CFR-20-REPORTS 2 | 15 rem annual, 15 rem at 24-hour, 75 rem immediate — a number that repeats across tiers with different meanings. |
| `annual limit on intake` | 7 | CFR-20-LIMITS 3, FR-DOSE 2, CFR-20-REPORTS 2 | An *intake* threshold for releases, not an external dose. Appears at 5× and 1× in the two notification tiers. |
| `loss of control` | 1 | CFR-20-REPORTS 1 | **Appears exactly once in the corpus**, and gates the entire 24-hour notification duty. A retrieval that misses this chunk cannot get R2 right. |

**Build golden cases on the first and last.** The first is where a proposed rule out-competes the regulation on similarity; the last is a single decisive phrase that any chunking mistake can bury.

---

## Out-of-corpus topics

Declared absent, and verified absent by `fetch_corpus.py` on every full build.

- `reactor pressure vessel`
- `spent fuel pool`
- `emergency core cooling`
- `steam generator tube`

More broadly out of corpus: everything about power reactors (Parts 50, 52, 53), reactor event notification under § 50.72 and § 50.73, transport packaging under Part 71, waste disposal under Part 61, security and safeguards under Parts 73 and 74, medical use under Part 35, and every Agreement State programme. A question about any of these must be refused with the corpus gap named.

## Near-miss topics

Declared present, and verified present on every full build. These must **not** be refused.

- `planned special exposure`
- `lens dose equivalent`
- `annual limit on intake`
- `declared pregnant woman`

---

## What this corpus deliberately does not contain

**Appendices B, C and E to Part 20 are not here**, and neither is Appendix B to Part 30. They are appendices rather than sections, and are not reachable through the eCFR structural API at the part path — the same limitation every project in this cohort hits.

The consequence is a designed gap the packets are built around. **§ 20.2201 requires a telephone report for lost or stolen material at 1,000 times "the quantity specified in appendix C to part 20", and a 30-day report at 10 times that quantity — and Appendix C is not in this corpus.** So:

- A question asking whether a specific missing quantity crosses the § 20.2201 threshold must return **`insufficient_data`, naming Appendix C as the missing input** — not a refusal, and certainly not a guess. This is the one place in the project where the correct behaviour is neither an answer nor a refusal, and a golden case must assert it.
- A question about the Schedule A, B or C quantities in Part 30 **is** fully answerable, because those are sections.

Two similar-looking tables, one reachable and one not, is the sharpest test in the corpus of whether a system knows what it actually has.

---

## Rebuilding

```
python fetch_corpus.py                  # rebuild all six, then verify
python fetch_corpus.py CFR-20-REPORTS   # rebuild one, skip verification
```

Requires `requests`, `pypdf`, `reportlab`. Upstream downloads cache under `.cache/`; delete it to force a fresh pull. A full run ends by checking every distractor, out-of-corpus and near-miss term above and printing the counts to transcribe back into this file.

**If a rebuild reports different counts than the table above, the upstream source has changed.** Diff `text/` against the committed version before assuming your retrieval broke.
