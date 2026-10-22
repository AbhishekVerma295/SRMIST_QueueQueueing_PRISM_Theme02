# FixFlow demo video (Round 2): shot list and narration
Target **1:50** (hard limit 2:00). One continuous screen recording of the demo UI, browser at 100% zoom, light mode, 1440 × 900 or larger.
The timestamps match the "In the video" list on slide 6 of `SRMIST_QueueQueueing_Round2.pptx`.

## Before recording
Run the offline demo server (no LLM, so every answer is fast and repeatable; it uses a scratch copy of the cache, never the shipped one):

```bash
cmd /c "set CACHE_DB=.tmp\ui_cache.sqlite&& set LLM_PROVIDER=off&& .venv\Scripts\python.exe -m uvicorn app.main:app --port 8766"
```

Open these four tabs in order, and do one dry run so every page has loaded once:
1. `http://localhost:8766/?sample=18&verify=1`
2. `http://localhost:8766/`
3. `http://localhost:8766/?sample=5`
4. `http://localhost:8766/?teach=1`

All five scenes were checked on 22 Oct against this server: each complaint below returns the plan described.

## Shots
| Time | Tab | What to do on screen | Narration (one voice) |
|---|---|---|---|
| 0:00–0:30 | 1 | Let the page load. The touchscreen plan appears; the first card shows "Open setting" and "Check it worked" with the green "Confirmed on the device" line. Move the pointer slowly along the signal path on the right. | "This is an official complaint from the kit: the touchscreen is laggy. FixFlow returns six steps, gentlest first. Two are one-tap Settings fixes with deeplinks from the catalog, three are checks by hand, and restart comes last. One tap opens the setting, and its validation link confirms it. On the right you can see how it answered: from memory, in about a millisecond, at no cost." |
| 0:30–0:50 | 2 | Type `my taps take ages to register on the touchscreen` and press **Find fix**. Point at the time (about 20 ms) and "Found by meaning". | "Now the same problem in completely different words. Same plan, found by meaning, in about twenty milliseconds, with no AI call." |
| 0:50–1:10 | 2 | Clear the box, type `mera phone ka touch bahut slow hai, der se respond karta hai`, press **Find fix**. Point at "Understood as". | "Many users in India write in Hinglish. FixFlow turns it into English offline, shows what it understood, and gives the same touchscreen plan." |
| 1:10–1:25 | 3 | The tablet complaint loads with its multi-window article. Point at "The support article doesn't cover this problem… Nothing is made up" and the orange no_match dot. | "Here the article does not fit the complaint. FixFlow says so and returns no_match instead of inventing steps." |
| 1:25–1:50 | 4 | The Teach panel fills in the brightness article and teaches it ("Learned a 3-step plan…"), then asks "the screen is too dim to see outdoors in bright sun" on the phone. Point at the brightness plan and "Found by meaning". | "Finally, a problem FixFlow has never seen. We give it one support article, with no code changes. It learns the plan once, and a differently worded complaint is answered from memory straight away. That is how FixFlow scales to new scenarios." |

## Tips
- Record with system sound off; add the narration as a separate track or record it live in one take.
- Keep the pointer still while the narration explains a number.
- Export as MP4 (H.264), then in PowerPoint: slide 6, **Insert → Video → This Device**, place it over the dark frame, and set **Start: On click**.
- In Teams, share the screen with **Include sound** switched on.
