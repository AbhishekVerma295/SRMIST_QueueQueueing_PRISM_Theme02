# Starter kit: where these files came from

We never received the official Theme 02 kit. These files are the version that most public participant repos agree on,
compared byte for byte (SHA-256) across 16 cloned repos on 26 Sep 2026.

| File | SHA-256 (first 12) | Repos with identical copy | Outliers |
|---|---|---|---|
| deeplinks.json | 2b2c7f75e520 | 6 (FixRoute, OneClick, SWARNAVA, Pallavi-kr6, KrishnaKapoor612, Nexusnode1) | 4 modified copies |
| siis_responses.json | 4715c5313662 | 6 (same six) | 3 modified copies |
| input.txt | f0ccfee5897b | 7 (same six + aush5895, identical except line endings) | 1 (device names anonymised) |
| sample_output.json | b6af90fa3c58 | 6 (same six) | 1 |
| schema.py | 833e54d26e32 | 9 (incl. TapFix, Aadi546/data, aush5895 except line endings) | edited variants |

Copied from `Sidd2465/FixRoute/student_kit/`. `schema.py` matches Appendix A of the Theme 2 PDF.

## Facts checked
- deeplinks.json: 578 entries, 578 unique URIs. originalType: onClickURL 254, onURL 138, offURL 138, updateURL 36, null 11, placeholder 1.
  - `DL-DUMMY` = `bixby://dummy_positive` (the generic placeholder).
  - `DL-0474/0475/0476` are "Diagnose Battery Drain / Slow Performance / Overheating" (null originalType).
  - A few entries are SmartThings appliances (air conditioner, refrigerator), so they are noise for phone troubleshooting.
- siis_responses.json: 20 rows (row_6 and row_18 absent), `{id, original_query, siis_response:{title, content}}`.
- input.txt: **20 lines**, not 22. Line 17 packs 3 complaints into one line ("1. … 2. … 3. …"). It is matched by SIIS `row_19` ("Cracked or bleeding screen"), so treat it as a multi-intent query. Line 16 also starts with "1." (single complaint).
- Some `original_query` strings differ slightly from input.txt (a "1. " prefix, quotes, an encoding glitch in row_11). Match queries to SIIS with fuzzy/normalised matching, not exact equality.

## To do
Swap in the official kit if it ever arrives, then re-run the hashes. If they differ, the official copy wins.
