"""Round 2 (Demo Round) deck: 9 talk slides + 2 backup slides, 7 minutes, own design in a One UI style.

Order follows the mentor's brief: problem + caveats (Abhinav), core architecture + core modules (Abhishek),
demo video, extension for Samsung (Ayushi), scalability + close (Ketki). Speaker notes hold each presenter's script.
Every number on the slides comes from metrics.md, eval/runs/scale.md or the code itself.

Run from the repo root:  .venv/Scripts/python docs/deck_src/build_round2_deck.py
Needs the UI screenshots and icons in .tmp/round2v2/ (shots/*.png from the offline demo UI at 2x, icons/*.png).
"""
from pathlib import Path

from lxml import etree
from PIL import Image, ImageDraw
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / ".tmp" / "round2v2"
SHOTS, ICONS = WORK / "shots", WORK / "icons"
OUT = ROOT / "docs" / "round2" / "SRMIST_QueueQueueing_Round2.pptx"

# One UI-like palette: grey canvas, white cards, black type, one blue accent; chip colours match the demo UI
BG, CARD, INK, SUB, LINE = "F2F3F5", "FFFFFF", "111318", "5F6570", "DADDE3"
BLUE, BLUE_SOFT, NAVY, NAVY_SUB = "1F5FD6", "E4ECFC", "1428A0", "C8D2F5"
GREEN, GREEN_SOFT = "13805B", "DFF2EA"
AMBER, AMBER_SOFT = "8F5600", "F8EBD6"
RED, RED_SOFT = "B2261E", "FBE5E3"
F, FS, FB = "Segoe UI", "Segoe UI Semibold", "Segoe UI Bold"
TALK = 9


def rgb(h):
    return RGBColor.from_string(h)


prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]


def slide(bg=BG):
    s = prs.slides.add_slide(BLANK)
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = rgb(bg)
    return s


def text(s, x, y, w, h, content, size=16, color=INK, font=F, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, space=4, line=1.1):
    """content: str, or list of paragraphs; a paragraph is str or list of (text, {color, size, font}) runs."""
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    paras = content if isinstance(content, list) else [content]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space)
        p.line_spacing = line
        for t, st in (para if isinstance(para, list) else [(para, {})]):
            r = p.add_run()
            r.text = t
            r.font.size = Pt(st.get("size", size))
            r.font.name = st.get("font", font)
            r.font.color.rgb = rgb(st.get("color", color))
    return tb


def box(s, x, y, w, h, fill=CARD, radius=0.22, line=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE):
    """Flat card; radius in inches (One UI uses large, soft corners)."""
    sh = s.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    sh.fill.solid()
    sh.fill.fore_color.rgb = rgb(fill)
    if line:
        sh.line.color.rgb = rgb(line)
        sh.line.width = Pt(1)
    else:
        sh.line.fill.background()
    sh.shadow.inherit = False
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        sh.adjustments[0] = min(0.5, radius / min(w, h))
    return sh


def pill(s, x, y, label, fill, color, size=12, h=0.32, pad=0.16, w=None):
    """Chip with centred text; width from the label length unless given."""
    w = w or pad * 2 + len(label) * size * 0.0071
    box(s, x, y, w, h, fill, radius=h / 2)
    text(s, x, y, w, h, label, size=size, color=color, font=FS, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    return w


def icon(s, x, y, name, fill=BLUE, size=0.62):
    """White icon on a coloured squircle tile, like a One UI app icon."""
    box(s, x, y, size, size, fill, radius=size * 0.3)
    pad = size * 0.2
    s.shapes.add_picture(str(ICONS / f"{name}.png"), Inches(x + pad), Inches(y + pad), Inches(size - 2 * pad), Inches(size - 2 * pad))


def arrow(s, x1, y1, x2, y2, color=SUB, width=1.75, dash=False):
    c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = rgb(color)
    c.line.width = Pt(width)
    ln = c.line._get_or_add_ln()
    if dash:
        etree.SubElement(ln, qn("a:prstDash")).set("val", "dash")
    tail = etree.SubElement(ln, qn("a:tailEnd"))
    for k, v in (("type", "triangle"), ("w", "med"), ("h", "med")):
        tail.set(k, v)
    return c


def frame(s, n, title, section, backup=False):
    """Section chip and title at the top; product, team and slide number at the bottom."""
    pill(s, 0.6, 0.42, section, BLUE_SOFT if not backup else "E6E8EC", BLUE if not backup else SUB, size=12)
    text(s, 0.6, 0.88, 12.1, 0.7, title, size=32, font=FS, line=1.0)
    text(s, 0.6, 7.02, 6, 0.25, "FixFlow  ·  Team SRMIST_QueueQueueing", size=10, color=SUB)
    label = f"{n} / {TALK}" if not backup else f"Backup {n}"
    text(s, 10.73, 7.02, 2.0, 0.25, label, size=10, color=SUB, align=PP_ALIGN.RIGHT)


def notes(s, who, script):
    s.notes_slide.notes_text_frame.text = f"{who}\n\n{script}"


def rounded_png(src, crop, radius_px, out_name):
    """Crops a screenshot and makes the corners outside a rounded rectangle transparent."""
    im = Image.open(SHOTS / src).convert("RGBA").crop(crop)
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.size[0] - 1, im.size[1] - 1), radius=radius_px, fill=255)
    im.putalpha(mask)
    out = WORK / out_name
    im.save(out)
    return out


def phone_png(src, height_px, out_name):
    """The phone mock-up from the demo UI (bezel included), cut at height_px so it can run off the slide edge."""
    return rounded_png(src, (248, 218, 1188, 218 + height_px), 80, out_name)


def picture(s, path, x, y, w=None, h=None):
    return s.shapes.add_picture(str(path), Inches(x), Inches(y), Inches(w) if w else None, Inches(h) if h else None)


# ======================================================================================== 1. title
s = slide(NAVY)
text(s, 0.7, 0.6, 7.4, 0.3, "Samsung PRISM GenAI Hackathon 2026   ·   Theme 02   ·   Demo round", size=13, color=NAVY_SUB, font=FS)
text(s, 0.7, 1.55, 7.4, 1.2, "FixFlow", size=72, color="FFFFFF", font=FB)
text(s, 0.7, 2.8, 7.4, 0.5, "Smart Guided Troubleshooting Engine", size=24, color=NAVY_SUB)
text(s, 0.7, 3.55, 7.0, 1.2, "A phone complaint in the user's own words goes in. A short, ordered fix plan comes out, "
     "with one-tap links into Settings, built only from the support article.", size=18, color="FFFFFF", line=1.2)
text(s, 0.7, 5.45, 7.4, 1.2, [
    [("Team SRMIST_QueueQueueing", {"font": FS, "size": 16, "color": "FFFFFF"})],
    [("SRM Institute of Science and Technology", {"size": 14, "color": NAVY_SUB})],
    [("Abhinav Kumar  ·  Abhishek Verma  ·  Ayushi Paul  ·  Ketki Gonnade", {"size": 14, "color": NAVY_SUB})],
], space=5)
picture(s, phone_png("verify.png", 1530, "phone_title.png"), 8.55, 0.75, w=4.15)
notes(s, "ABHINAV (about 10 s)",
      "Good morning. We are team SRMIST_QueueQueueing from SRM, and this is FixFlow, our engine for Theme 02. "
      "You describe a phone problem in your own words, and FixFlow returns a short, ordered fix plan with one-tap links into Settings, "
      "built only from the support article.")

# ======================================================================================== 2. problem
s = slide()
frame(s, 2, "Turn a vague complaint into a fix the user can tap", "Understanding the problem")
box(s, 0.6, 1.85, 4.35, 4.15)
text(s, 0.9, 2.1, 3.8, 0.3, "WHAT COMES IN", size=11, color=SUB, font=FS)
text(s, 0.9, 2.5, 3.8, 1.5, "“My Nexa X1 screen inputs are delayed and the touch responsiveness is laggy, "
     "causing a noticeable delay when I try to interact with the device.”", size=15, line=1.15)
text(s, 0.9, 3.95, 3.8, 0.3, "Official kit, complaint 19", size=11, color=SUB)
for i, (ic, t) in enumerate((("article", "Its support article (SIIS text)"), ("link", "A catalog of 578 Settings deeplinks"))):
    icon(s, 0.9, 4.5 + i * 0.68, ic, size=0.48)
    text(s, 1.55, 4.5 + i * 0.68, 3.3, 0.48, t, size=14, anchor=MSO_ANCHOR.MIDDLE)

# FixFlow in the middle
arrow(s, 5.1, 3.92, 5.95, 3.92, BLUE, 2.25)
box(s, 6.0, 3.5, 1.3, 0.84, BLUE, radius=0.42)
text(s, 6.0, 3.5, 1.3, 0.84, "FixFlow", size=16, color="FFFFFF", font=FS, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
arrow(s, 7.35, 3.92, 8.2, 3.92, BLUE, 2.25)

box(s, 8.3, 1.85, 4.43, 4.15)
text(s, 8.6, 2.1, 3.9, 0.3, "WHAT MUST GO OUT", size=11, color=SUB, font=FS)
text(s, 8.6, 2.45, 3.9, 0.4, "Touchscreen response issues", size=16, font=FS)
plan = [("Enable Touch Sensitivity", "One tap"), ("Open Navigation Bar Settings", "One tap"), ("Check Screen Protectors", "By hand"),
        ("Check Usage and Moisture", "By hand"), ("Check Charger", "By hand"), ("Restart Your Device", "Last resort")]
chip = {"One tap": (BLUE_SOFT, BLUE), "By hand": (AMBER_SOFT, AMBER), "Last resort": (RED_SOFT, RED)}
for i, (name, cat) in enumerate(plan):
    y = 3.0 + i * 0.47
    text(s, 8.6, y, 0.3, 0.32, str(i + 1), size=13, color=SUB, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 8.9, y, 2.6, 0.32, name, size=13, anchor=MSO_ANCHOR.MIDDLE)
    pill(s, 11.42, y + 0.02, cat, *chip[cat], size=10, h=0.28, w=1.06)

rules = ["Pure JSON, official schema", "Catalog deeplinks only", "Restart and reset always last",
         "No fix in the article: no_match", "Repeat < 300 ms, new < 8 s"]
for i, r in enumerate(rules):
    pill(s, 0.6 + i * 2.454, 6.3, r, CARD, INK, size=11.5, h=0.4, w=2.33)
notes(s, "ABHINAV (about 30 s)",
      'Here is the task as we understood it. In: a complaint like this official one, its support article, and a catalog of 578 Settings deeplinks. Out: a strict JSON plan. Settings fixes first, each with a one-tap deeplink from the catalog, then checks by hand, and restart always last. This is the real plan FixFlow returns for this complaint. And if the article has no fix, we must say no_match, never guess.')

# ======================================================================================== 3. caveats
s = slide()
frame(s, 3, "Six catches we found in the official kit", "Caveats identified")
caveats = [
    ("The article may not fit", "Complaint 6 is about a tablet's dark screen; its article is about multi-window. A plan here would be invented.", "Extract: relevance check"),
    ("AI models invent steps", "An LLM adds tips, settings and web links that the article never mentions.", "Extract: citation check"),
    ("Deeplinks are masked codes", "Only the descriptions can be matched, and 138 switches come as on/off twins. The wrong twin undoes the fix.", "Deeplinks: action-aware search"),
    ("One line, several problems", "Complaint 17 holds three complaints in one line. Each needs its own plan.", "Understand: problem split"),
    ("Many wordings, one plan", "Rewordings and Hinglish must get the same plan, and a repeat must answer in under 300 ms.", "Language + Memory"),
    ("The sample breaks the spec", "The kit's sample output has 8- and 12-word descriptions; the spec says 5 to 7, starting “It will”.", "Contract gate: we follow the spec"),
]
for i, (h, d, fix) in enumerate(caveats):
    x, y = 0.6 + (i % 3) * 4.1, 1.85 + (i // 3) * 2.5
    box(s, x, y, 3.88, 2.3)
    box(s, x + 0.28, y + 0.28, 0.42, 0.42, BLUE_SOFT, radius=0.21)
    text(s, x + 0.28, y + 0.28, 0.42, 0.42, str(i + 1), size=14, color=BLUE, font=FS, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    text(s, x + 0.85, y + 0.3, 2.85, 0.4, h, size=16, font=FS, anchor=MSO_ANCHOR.MIDDLE)
    text(s, x + 0.28, y + 0.88, 3.35, 0.9, d, size=13, color=SUB, line=1.12)
    pill(s, x + 0.28, y + 1.8, fix, GREEN_SOFT, GREEN, size=10.5, h=0.28, pad=0.13)
notes(s, "ABHINAV (about 35 s)",
      "Reading the kit closely, we found six catches. Complaint 6 comes with an article that does not fit, so any plan would be invented. LLMs add steps the article never mentions. Deeplinks are masked codes, and 138 switches have on and off twins. Complaint 17 holds three problems in one line. One problem comes in many wordings, even Hinglish. And the kit's own sample breaks the five-to-seven word rule, so we follow the spec. The green tag on each card is the module that handles it. Over to Abhishek.")

# ======================================================================================== 4. architecture
s = slide()
frame(s, 4, "Memory first. A new problem passes four checked stages", "Core architecture")
W, H = 2.2, 1.4
X = [0.6, 3.17, 5.74, 8.31, 10.53]


def node(x, y, title, sub, tag, tag_fill, tag_color, w=W, fill=CARD, title_color=INK):
    box(s, x, y, w, H, fill)
    text(s, x + 0.2, y + 0.16, w - 0.4, 0.32, title, size=15, font=FS, color=title_color)
    text(s, x + 0.2, y + 0.5, w - 0.4, 0.45, sub, size=11.5, color=SUB, line=1.05)
    pill(s, x + 0.2, y + H - 0.4, tag, tag_fill, tag_color, size=9.5, h=0.25, pad=0.11)


AI, CODE = ("LLM or rules", "EEE6FB", "5B3DB8"), ("code, no LLM", "E6E8EC", SUB)
Y1, Y2 = 1.9, 4.2
node(X[0], Y1, "Complaint", "typed or spoken, English or Hinglish", "input", BLUE_SOFT, BLUE)
node(X[1], Y1, "Language", "Hinglish to English, offline rules", *CODE)
node(X[2], Y1, "Memory", "exact or same-meaning match, symptom guard", *CODE)
box(s, X[4], Y1, W, H, GREEN_SOFT)
text(s, X[4] + 0.2, Y1 + 0.16, W - 0.4, 0.32, "Answer", size=15, font=FS, color=GREEN)
text(s, X[4] + 0.2, Y1 + 0.5, W - 0.4, 0.7, "pure JSON plan, then saved to memory", size=11.5, color=INK, line=1.05)
node(X[0], Y2, "1  Understand", "normalise, split problems, 8 to 10 rewordings", *AI)
node(X[1], Y2, "2  Extract", "steps from the article, each citing its sentence", *AI)
node(X[2], Y2, "3  Deeplinks", "hybrid search over the 578-entry catalog", *CODE)
node(X[3] - 0.15, Y2, "4  Contract gate", "every rule checked in code", *CODE, w=W + 0.15)
arrow(s, X[0] + W, Y1 + H / 2, X[1], Y1 + H / 2)
arrow(s, X[1] + W, Y1 + H / 2, X[2], Y1 + H / 2)
arrow(s, X[2] + W, Y1 + H / 2, X[4], Y1 + H / 2, BLUE, 2.5)
text(s, X[2] + W + 0.2, Y1 + 0.1, 2.3, 0.55, [[("Seen before", {"font": FS, "color": BLUE})], [("1 to 82 ms, $0, no LLM", {"color": BLUE, "size": 12})]], size=13, space=0)
# miss: down from Memory, back to the start of the second row, then along it and up into Answer
arrow(s, X[2] + W / 2, Y1 + H, X[2] + W / 2, Y1 + H + 0.45, SUB)
text(s, X[2] + W / 2 + 0.12, Y1 + H + 0.08, 1.6, 0.3, "new problem", size=12, color=SUB)
c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(X[0] + W / 2), Inches(Y1 + H + 0.45), Inches(X[2] + W / 2), Inches(Y1 + H + 0.45))
c.line.color.rgb, c.line.width = rgb(SUB), Pt(1.75)
arrow(s, X[0] + W / 2, Y1 + H + 0.45, X[0] + W / 2, Y2, SUB)
arrow(s, X[0] + W, Y2 + H / 2, X[1], Y2 + H / 2)
arrow(s, X[1] + W, Y2 + H / 2, X[2], Y2 + H / 2)
arrow(s, X[2] + W, Y2 + H / 2, X[3] - 0.15, Y2 + H / 2)
c =s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(X[3] + W), Inches(Y2 + H / 2), Inches(X[4] + W / 2), Inches(Y2 + H / 2))
c.line.color.rgb, c.line.width = rgb(SUB), Pt(1.75)
arrow(s, X[4] + W / 2, Y2 + H / 2, X[4] + W / 2, Y1 + H, SUB)
facts = [("offline", "Runs with no AI key", "Every LLM stage has a rules path. CPU only, one Docker image."),
         ("bolt", "Gemini is optional", "Flash-Lite with a model fallback chain and a 7 s budget per call, then rules."),
         ("rule", "Same meaning, same plan", "Temperature 0, fixed seed, and memory return identical plans.")]
for i, (ic, h, d) in enumerate(facts):
    x = 0.6 + i * 4.1
    icon(s, x, 5.95, ic, fill=NAVY, size=0.56)
    text(s, x + 0.75, 5.9, 3.2, 0.9, [[(h, {"font": FS, "size": 14.5})], [(d, {"size": 12, "color": SUB})]], space=2, line=1.08)
notes(s, "ABHISHEK (about 45 s)",
      "A complaint first goes through Language, where Hinglish becomes English, then Memory. If we have seen the problem before, in any wording, "
      "we answer in 1 to 82 milliseconds, at zero cost, with no LLM. That is the blue path.\n"
      "A new problem passes four stages: Understand, Extract, Deeplinks, and a contract gate that checks every rule in code. Then the plan is saved to memory.\n"
      "Purple stages can use the LLM; grey ones are plain code. Every LLM stage also has a rules path, so FixFlow runs with no AI key, "
      "and if Gemini is slow we fall back within the time budget.")

# ======================================================================================== 5. core modules
s = slide()
frame(s, 5, "Three core modules keep every answer grounded", "Core technology modules")
mods = [
    ("article", "Grounded extraction", "The article is split into numbered sentences. Every step must cite them, and code deletes "
     "any step whose words are not in the sentences it cites.", "2.60 / 3", "step accuracy on the official lines; 2.73 on held-out scenarios", BLUE),
    ("link", "Deeplink mapper", "Keyword (BM25) plus meaning search over catalog descriptions, never the masked code. It picks on vs off "
     "and the exact screen, then copies the entry verbatim.", "100%", "link precision. LLM picking links: 75%, keyword rules: 58%", GREEN),
    ("memory", "Guarded memory", "Each plan is stored with its complaint and 8 to 10 rewordings. A hit needs close meaning and the same symptom, "
     "so a flicker complaint never gets the cracked-screen plan.", "87.5%", "of held-out rewordings get the same plan; 0 wrong hits", AMBER),
]
for i, (ic, h, d, big, small, col) in enumerate(mods):
    y = 1.85 + i * 1.5
    box(s, 0.6, y, 12.13, 1.32)
    icon(s, 0.88, y + 0.35, ic, fill=col, size=0.62)
    text(s, 1.8, y + 0.2, 2.6, 0.9, h, size=17, font=FS, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 4.35, y + 0.2, 4.9, 0.95, d, size=13, color=SUB, line=1.12, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 9.55, y + 0.14, 2.95, 0.6, big, size=30, font=FB, color=col)
    text(s, 9.55, y + 0.74, 3.0, 0.5, small, size=11.5, color=INK, line=1.05)
box(s, 0.6, 6.33, 12.13, 0.5, BLUE_SOFT, radius=0.25)
text(s, 0.9, 6.33, 11.6, 0.5, [[("Contract gate in code:  ", {"font": FS, "color": BLUE}),
                                ("100% schema-valid, 100% rule compliance and 0 web links on the official, dev and held-out sets", {"color": INK})]],
     size=13.5, anchor=MSO_ANCHOR.MIDDLE)
notes(s, "ABHISHEK (about 40 s)",
      "Three modules keep answers grounded. Grounded extraction: every step must cite article sentences, and code deletes any step that is not really there. "
      "Step accuracy is 2.6 out of 3.\n"
      "The deeplink mapper is search, not the LLM: it picks on versus off and the exact screen. 100 percent precision, against 75 when the LLM picked links.\n"
      "Guarded memory reuses a plan only for the same symptom: 87.5 percent of held-out rewordings get the same plan, with no wrong hits. "
      "Let's see it working.")

# ======================================================================================== 6. demo video
s = slide(NAVY)
text(s, 0.6, 0.42, 6, 0.3, "Demo video", size=13, color=NAVY_SUB, font=FS)
text(s, 0.6, 0.85, 12, 0.7, "FixFlow in under two minutes", size=32, color="FFFFFF", font=FS)
box(s, 0.6, 1.85, 7.82, 4.4, "0B1550", radius=0.22)
icon(s, 4.21, 3.62, "play", fill="2E45C0", size=0.85)
text(s, 0.6, 4.6, 7.82, 0.4, "Demo video plays here", size=13, color=NAVY_SUB, align=PP_ALIGN.CENTER)
scenes = [("0:00", "An official complaint becomes a 6-step plan. One tap opens the setting, and its check confirms it."),
          ("0:30", "The same problem in new words: same plan, from memory, in about 20 ms."),
          ("0:50", "A Hinglish complaint, shown as “Understood as”, gets the same plan."),
          ("1:10", "An article that does not fit: no_match, nothing invented."),
          ("1:25", "A new problem is taught with one article; a rewording is then answered from memory.")]
text(s, 8.85, 1.85, 3.9, 0.35, "IN THE VIDEO", size=11, color=NAVY_SUB, font=FS)
for i, (t, d) in enumerate(scenes):
    y = 2.3 + i * 0.82
    text(s, 8.85, y, 0.7, 0.3, t, size=12, color=NAVY_SUB, font=FS)
    text(s, 9.55, y, 3.2, 0.8, d, size=12.5, color="FFFFFF", line=1.08)
text(s, 0.6, 7.02, 6, 0.25, "FixFlow  ·  Team SRMIST_QueueQueueing", size=10, color=NAVY_SUB)
text(s, 10.73, 7.02, 2.0, 0.25, f"6 / {TALK}", size=10, color=NAVY_SUB, align=PP_ALIGN.RIGHT)
notes(s, "VIDEO (about 1 min 50 s, with its own voice-over)",
      "Abhishek: 'Here is FixFlow working.' Click the video (insert it over the dark frame: Insert, Video, This Device; set it to start on click). "
      "In Teams, share the screen with 'Include sound' on.\n"
      "If the video fails, describe it: an official complaint becomes a six-step plan and one tap applies a setting and checks it; "
      "a reworded complaint and a Hinglish one get the same plan from memory in milliseconds; an article that does not fit gives no_match; "
      "and a new problem is taught with one article and no code. Then hand over to Ayushi.")

# ======================================================================================== 7. Samsung extension
s = slide()
frame(s, 7, "Built for the way Samsung users in India ask for help", "Extension for Samsung")
picture(s, rounded_png("hinglish.png", (248, 218, 1188, 1418), 80, "phone_hinglish.png"), 0.6, 1.8, w=3.35)
box(s, 0.6, 6.3, 3.35, 0.5, CARD, radius=0.25)
text(s, 0.6, 6.3, 3.35, 0.5, "Hinglish in, same plan out, 27 ms", size=12, color=INK, font=FS, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
rows = [
    ("translate", BLUE, "Hinglish, understood offline",
     "“mera phone ka touch bahut slow hai” is read as English and gets the touchscreen plan. Our Hinglish set: right plan 3 of 15 before, 11 of 15 now, 0 wrong. "
     "Devanagari Hindi goes through Gemini."),
    ("tap", GREEN, "Tap the fix, then verify it",
     "One-tap steps carry the catalog's deeplink plus its validation deeplink (570 of 578 entries have one), so the device can open the screen and confirm the change. "
     "The demo UI simulates the device."),
    ("mic", AMBER, "Voice and step-by-step guidance",
     "The complaint can be spoken (browser speech), and “Guide me step by step” walks through one step at a time until it is fixed."),
    ("offline", NAVY, "No complaint text has to leave the server",
     "Rules mode needs no API key and no GPU: one Docker image on a CPU. Outputs stay brand-neutral, checked by a test."),
]
for i, (ic, col, h, d) in enumerate(rows):
    y = 1.8 + i * 1.27
    box(s, 4.35, y, 8.38, 1.12)
    icon(s, 4.6, y + 0.25, ic, fill=col, size=0.6)
    text(s, 5.45, y + 0.14, 7.1, 0.35, h, size=15.5, font=FS)
    text(s, 5.45, y + 0.48, 7.1, 0.62, d, size=11.5, color=SUB, line=1.08)
notes(s, "AYUSHI (about 45 s)",
      "What this means for Samsung, using only what we have built. First, Hinglish: 'mera phone ka touch bahut slow hai' is read as English offline and answered from memory in 27 milliseconds. On our Hinglish set, right plans went from 3 of 15 to 11 of 15, with no wrong answers.\nSecond, tap and verify: one-tap steps carry the catalog's deeplink and its validation link, so the device can confirm the fix. Our demo simulates the device.\nThird, voice input and a step-by-step guided mode. Fourth, in rules mode no complaint text leaves the server: no API key, no GPU, one Docker image.\n(Only if asked, as ideas, not built: the API could sit behind Bixby or Samsung Members, verify results could reorder plans by what really fixes problems, and the catalog already has SmartThings appliance entries. Also: 0 of 183 English test texts were misread as Hinglish.)")

# ======================================================================================== 8. scalability
s = slide()
frame(s, 8, "A new problem needs one article and zero code", "Scalability")
steps = [("article", "Add the support article", "No code, no retraining"),
         ("bolt", "Compile it once", "Rules 0.3 s, $0. Gemini 2.6 s, $0.0004"),
         ("memory", "Answer every rewording", "From memory, P95 under 50 ms, $0")]
for i, (ic, h, d) in enumerate(steps):
    x = 0.6 + i * 4.1
    box(s, x, 1.85, 3.88, 1.05)
    icon(s, x + 0.25, 2.08, ic, size=0.6)
    text(s, x + 1.05, 2.0, 2.75, 0.8, [[(h, {"font": FS, "size": 15})], [(d, {"size": 12, "color": SUB})]], space=2, anchor=MSO_ANCHOR.MIDDLE)
    if i < 2:
        arrow(s, x + 3.9, 2.375, x + 4.08, 2.375, BLUE, 2)
# chart: memory lookup time as the cache grows
box(s, 0.6, 3.15, 5.6, 3.65)
text(s, 0.9, 3.35, 5.0, 0.35, "Memory lookup stays fast as it grows", size=15, font=FS)
text(s, 0.9, 3.7, 5.0, 0.3, "P95 lookup time (ms) by number of stored problems", size=11.5, color=SUB)
cd = CategoryChartData()
cd.categories = ["1,256", "10,256", "100,256"]
cd.add_series("P95 ms", (21.6, 21.6, 39.2))
gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.9), Inches(4.05), Inches(5.0), Inches(2.6), cd)
ch = gf.chart
ch.has_legend = False
ch.has_title = False
ch.font.name, ch.font.size, ch.font.color.rgb = F, Pt(12), rgb(SUB)
plot = ch.plots[0]
plot.gap_width = 90
plot.has_data_labels = True
dl = plot.data_labels
dl.number_format, dl.number_format_is_linked = '0.0" ms"', False
dl.position = XL_LABEL_POSITION.OUTSIDE_END
dl.font.size, dl.font.color.rgb, dl.font.name = Pt(13), rgb(INK), FS
plot.series[0].format.fill.solid()
plot.series[0].format.fill.fore_color.rgb = rgb(BLUE)
va = ch.value_axis
va.visible = False
va.has_major_gridlines = False
va.maximum_scale = 50
ch.category_axis.format.line.color.rgb = rgb(LINE)
ch.category_axis.tick_labels.font.size = Pt(12)
tiles = [("8 / 8", "new problem types got a plan with 0 code changes (battery, charging, Bluetooth, camera)"),
         ("7 / 8", "rewordings of the new problems got the right plan; 0 false hits on 5 unrelated"),
         ("555 / 556", "phone Settings screens in the catalog reached by search, 0 wrong"),
         ("98 req/s", "with 50 users at once, 0 errors, P95 642 ms, one CPU worker")]
for i, (big, small) in enumerate(tiles):
    x, y = 6.5 + (i % 2) * 3.17, 3.15 + (i // 2) * 1.88
    box(s, x, y, 3.06, 1.77)
    text(s, x + 0.25, y + 0.18, 2.6, 0.6, big, size=27, font=FB, color=BLUE)
    text(s, x + 0.25, y + 0.85, 2.62, 0.85, small, size=11.5, color=INK, line=1.08)
notes(s, "KETKI (about 45 s)",
      'How easy is it to cover new scenarios? One article, zero code. We added eight new problem types, like battery, charging, Bluetooth and camera, without touching the code. Each article is compiled once, in 0.3 seconds with rules or 2.6 seconds with Gemini, and every rewording is then answered from memory in under 50 milliseconds. Seven of eight rewordings got the right plan, with no false hits.\nSearch reaches 555 of 556 phone Settings screens. Lookup stays at 39 milliseconds with a hundred thousand stored problems, and one CPU worker served 50 users at once at about 98 requests per second, with zero errors.')

# ======================================================================================== 9. close
s = slide(NAVY)
text(s, 0.7, 0.9, 8, 1.1, "Thank you", size=60, color="FFFFFF", font=FB)
text(s, 0.7, 2.1, 8, 0.5, "We are happy to take your questions.", size=22, color=NAVY_SUB)
recap = [("Grounded", "every step cites the support article"), ("Exact", "every deeplink is copied from the catalog"),
         ("Fast", "repeats come from memory in milliseconds, at $0"), ("Scalable", "a new problem is one article, no code")]
for i, (h, d) in enumerate(recap):
    y = 3.3 + i * 0.62
    box(s, 0.7, y + 0.13, 0.2, 0.2, "5C79E0", radius=0.1)
    text(s, 1.15, y, 7, 0.45, [[(h + "  ", {"font": FS, "color": "FFFFFF"}), (d, {"color": NAVY_SUB})]], size=17, anchor=MSO_ANCHOR.MIDDLE)
text(s, 0.7, 6.2, 8.5, 0.6, [[("Team SRMIST_QueueQueueing", {"font": FS, "color": "FFFFFF"})],
                             [("Abhinav Kumar  ·  Abhishek Verma  ·  Ayushi Paul  ·  Ketki Gonnade", {"color": NAVY_SUB})]], size=13, space=3)
picture(s, phone_png("teach.png", 1530, "phone_close.png"), 8.55, 0.75, w=4.15)
notes(s, "KETKI (about 10 s)",
      "To sum up: grounded, exact, fast and scalable. Thank you, and we are happy to take your questions.")

# ======================================================================================== backup 1. results
s = slide()
frame(s, 1, "Results on the official and held-out sets", "Backup for Q&A", backup=True)
rows = [("Metric (target)", "Official D1", "Held-out D2b"),
        ("Schema-valid / rule compliance (99% / 95%)", "100% / 100%", "100% / 100%"),
        ("Web links in output (0)", "0", "0"),
        ("Settings steps with a catalog deeplink (90%)", "100%", "100%"),
        ("Step accuracy, gold proxy (0 to 3)", "2.60", "2.73"),
        ("Step accuracy, LLM judge (0 to 3)", "1.94", "2.06"),
        ("Deeplink relevance (0 to 2) / precision", "2.00 / 100%", "1.82 / 91%"),
        ("Says no_match at the right time", "95%", "90%")]
box(s, 0.6, 1.85, 7.4, 4.95)
for i, (a, b, c_) in enumerate(rows):
    y = 2.05 + i * 0.58
    st = {"font": FS, "color": SUB, "size": 12} if i == 0 else {}
    text(s, 0.9, y, 4.2, 0.45, [[(a, st)]], size=13.5, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 5.1, y, 1.3, 0.45, [[(b, st)]], size=13.5, font=FS, align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 6.45, y, 1.3, 0.45, [[(c_, st)]], size=13.5, font=FS, align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)
    if i:
        box(s, 0.9, y - 0.07, 6.85, 0.012, "E3E6EA", shape=MSO_SHAPE.RECTANGLE)
box(s, 8.3, 1.85, 4.43, 4.95)
text(s, 8.6, 2.1, 3.9, 0.35, "Deeplink mapping ablation", size=15, font=FS)
text(s, 8.6, 2.45, 3.9, 0.5, "Same extraction, only the mapper changes (D1 + D2, on gold)", size=11.5, color=SUB)
abl = [("Hybrid BM25 + dense (ours)", "100%", "1.88", "$0", BLUE), ("Full-LLM mapping", "75%", "1.76", "$0.00125", SUB), ("Keyword rules", "58%", "1.29", "$0", SUB)]
for i, (n, p, r, cost, col) in enumerate(abl):
    y = 3.15 + i * 1.15
    text(s, 8.6, y, 3.9, 0.3, n, size=13.5, font=FS, color=INK)
    text(s, 8.6, y + 0.36, 3.9, 0.5, [[(p, {"font": FB, "size": 22, "color": col}), ("  precision    ", {"size": 11.5, "color": SUB}),
                                       (f"relevance {r}   cost {cost}", {"size": 11.5, "color": SUB})]], size=13)
notes(s, "BACKUP (show only if asked)",
      "Numbers from metrics.md (3 Oct compile, shipped cache). D1 = the 20 official lines; D2b = 10 held-out scenarios written before the final changes and never tuned on.\n"
      "Gold labels for D1 are AI-assisted with a human spot-check pending, which is why we also report an independent LLM judge (a stronger Gemini model that never sees the gold labels).\n"
      "Ablation: eval/ablation.py, extraction held fixed so only the deeplink mapper changes.")

# ======================================================================================== backup 2. limits
s = slide()
frame(s, 2, "Known limits, and what the engine does about them", "Backup for Q&A", backup=True)
limits = [
    ("Hardest unseen rewordings: 75% hits", "On the final never-tuned set D3c, 75% hits and 62.5% right plan (target 80%). Two look-alike black-screen complaints got the flicker plan. "
     "Reported as is; the held-out set D3b reaches 91.7% / 87.5%."),
    ("Gemini free tier is often overloaded", "503 and 429 errors are common. The adapter tries other models, then the rules path answers inside the budget. "
     "Every request still returns a valid plan (14 of 32 cold runs used the LLM)."),
    ("Answer key is AI-assisted", "Gold labels for the official lines were written with AI help; a human check is pending. An independent LLM judge is reported next to them."),
    ("Some article mismatches slip through", "One official line pairs a TV aspect-ratio article with a phone complaint; the LLM still builds a plan there."),
]
for i, (h, d) in enumerate(limits):
    x, y = 0.6 + (i % 2) * 6.13, 1.85 + (i // 2) * 2.5
    box(s, x, y, 6.0, 2.3)
    pill(s, x + 0.3, y + 0.3, "Limit", RED_SOFT, RED, size=10.5, h=0.28)
    text(s, x + 0.3, y + 0.75, 5.4, 0.4, h, size=16, font=FS)
    text(s, x + 0.3, y + 1.2, 5.4, 1.0, d, size=12.5, color=SUB, line=1.1)
notes(s, "BACKUP (show only if asked)",
      "Likely questions and short answers:\n"
      "Why not let the LLM pick deeplinks? The ablation: 75% precision and it costs money; our search reaches 100% at $0, and links are copied verbatim, never generated.\n"
      "What if the LLM is down? Every LLM stage has a rules path; the service never returns a non-JSON error. With LLM_PROVIDER=off it runs fully offline.\n"
      "How does it scale to 10k scenarios? Compile each article once (batch), then serve rewordings from memory; lookup is 39 ms P95 at 100k stored problems.\n"
      "How do you stop wrong cache hits? Similarity threshold plus a symptom guard plus the article hash when an article is sent; 0 false hits on unrelated complaints.\n"
      "Why is D3c below target? We wrote it before the last changes and did not tune on it after seeing the result.")

OUT.parent.mkdir(parents=True, exist_ok=True)
prs.save(OUT)
print(f"wrote {OUT} ({len(prs.slides)} slides)")
