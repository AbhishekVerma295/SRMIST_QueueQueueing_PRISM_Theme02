# Starter kit: provenance

## `Theme 2/` — OFFICIAL kit (in use since 28 Sep 2026)
Received from the organisers. `app/config.py` points `KIT_DIR` here. **Never edit these files.**

| File | SHA-256 (first 12) | Notes |
|---|---|---|
| deeplinks.json | 5b49ec7c66b1 | 578 entries, scheme `voiceassist://masked/act/…`; placeholder `DL-DUMMY` = `voiceassist://dummy_positive` |
| siis_responses.json | 5513880c11d3 | 20 rows (row_6, row_18 absent), `{id, original_query, siis_response:{title, content}}` |
| input.txt | 0b025b78102e | 20 lines; line 17 holds 3 complaints (multi-intent) |
| sample_output.json | eebe94e11943 | 1 example; its descriptions are 8 and 12 words (the spec says 5–7, and we follow the spec) |
| schema.py | 833e54d26e32 | identical to Appendix A of the Theme 2 PDF |

What changed vs the public copy we built Phase 1 on (same structure, same DL-xxxx ids, same text apart from names):
- URI scheme `bixby://` → `voiceassist://`, including the placeholder.
- Brand-neutral names: Samsung → TechCorp, Galaxy models → "Nexa X1 / Nexa Fold X1 / Nexa A14", Smart Switch → Data Transfer, Bixby → VoiceAssist, "Samsung Support" → "Customer Support", S Pen → stylus.
- The `DL-DUMMY` entry now says: write the placeholder's description and message yourself, 5–7 words, naming the concrete screen from the steps. The engine does this.
- The official hashes match only one public repo (Aadi546/prism_project). The six-repo "majority" copy was an earlier, branded version.

## `_unofficial_public_copy/` — superseded
The majority copy from 16 public participant repos (26 Sep), kept only for reference. It is gitignored and not used by the code.
