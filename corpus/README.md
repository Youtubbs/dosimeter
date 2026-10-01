# Dosimeter regulatory corpus

This directory contains excerpts of federal public-domain material — 10 CFR Parts 20, 30 and 34, and two Federal Register preambles — reproduced as a training artifact for the Dosimeter exercise.

**It is not a current or authoritative source, and it is not radiation safety, health physics or legal guidance.** Sections have been excerpted out of their surrounding text, and the material is fixed at its 11 September 2026 retrieval date. Anyone with an actual radiation protection question must consult the published sources, which are linked per document in [MANIFEST.md](MANIFEST.md).

The exposure packets the system analyses are fictional. Ostrander Inspection Group does not exist.

## Layout

| Path | What it is |
|---|---|
| `pdf/` | The excerpted PDFs. These are what the ingestion pipeline cracks. |
| `text/` | Plain-text extraction of each PDF, committed so a diff reveals when an upstream source has changed. |
| `sources.json` | The URL manifest: source addresses, section lists, page ranges, and the declared topic lists. Everything project-specific lives here. |
| `fetch_corpus.py` | Rebuilds `pdf/` and `text/` from `sources.json`. Identical across every project in the cohort. |
| `MANIFEST.md` | Per-document provenance, the recorded cross-references, the retrieval distractors, and the declared out-of-corpus topic list. |

## Rebuilding

```bash
pip install requests "pypdf[crypto]" reportlab
python fetch_corpus.py                  # all six documents, then verify
python fetch_corpus.py CFR-20-REPORTS   # one document, no verification
```

The `[crypto]` extra is the cohort-wide dependency set. No document in this corpus needs it, but agencies serve some forms as AES-encrypted PDFs, and `pypdf` raises `DependencyError` on those without `cryptography` installed.

Raw upstream downloads are cached in `.cache/`, which is not committed. Delete it to force a fresh pull.

Rebuilds are byte-reproducible: given the same upstream bytes, a rebuild produces the same PDFs and text files, so a clean run leaves no git diff. A diff means an upstream source moved — or that your renderer differs from the one that built the committed files. The PDFs here were produced with **reportlab 5.0.1** and **pypdf 6.18.0**; font metrics and stream layout are version-dependent, so a different reportlab rewrites every PDF and can shift page counts on documents you did not touch. Before changing `sources.json`, rebuild unchanged and confirm `git status` is clean. If it is not, your versions differ and the diff is yours, not the agency's.

A full rebuild ends with a verification pass over the extracted text. Every topic declared out-of-corpus in `sources.json`'s `verification` block must have zero occurrences and every near-miss topic must have at least one; the build fails otherwise, and distractor counts are printed for transcription into the manifest. `MANIFEST.md` transcribes those same lists for a human reader — the build does not read it, so an edit there that is not mirrored into `sources.json` changes nothing but the claim.

Upstream sources move. The four eCFR documents are pinned to issue date 2026-08-04 and will reproduce exactly; the two govinfo PDFs are served without version pinning, so if a rebuild produces different page counts, compare against `text/` to see what shifted before assuming the excerpt ranges in `sources.json` are still correct.

## Two things to read MANIFEST.md for before you start

**Both Federal Register documents in this corpus are proposed rules, not final ones.** They are long, on-topic and highly responsive to exactly the queries this project generates — and they are not the law. Carrying that distinction in your chunk metadata is a requirement, not a nicety. See *The proposed-rule hazard*.

**Appendix C to Part 20 is not in this corpus**, because appendices are not reachable through the eCFR structural API. § 20.2201's lost-material thresholds are expressed as multiples of it, so a question about them must return `insufficient_data` naming the missing input — not an answer, and not a refusal. See *What this corpus deliberately does not contain*.
