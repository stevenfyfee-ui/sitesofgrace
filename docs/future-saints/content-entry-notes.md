# Future Saints: content-entry notes for editors

For anyone entering a learning page in the Wagtail admin. Every learning page with real content goes
through the "Future Saints editorial review" workflow before it's published, never through a
shell command.

## Lengths (the layout is built for these)

| field | Explorer (Grades 2–3) | Researcher (Grades 4–5) |
|---|---|---|
| Intro (beside Quick Facts) | **40–70 words** | **60–100 words** |
| Story (full section below) | 150–250 words | 300–500 words |

**Keep the two intros close in length.** Both share one box so switching the reading level never
moves the page; if one is much longer, the shorter one leaves a gap under it. If only one level is
written, the Grades 2–3 / 4–5 switch is hidden and that level is shown.

Other short fields: subtitle one line; Think About It one question; reflection one question;
fun facts and timeline lines one or two short sentences each.

## Quick Facts

- Prefer **Inherit** for anything the canonical page already holds (dates, feast day, place, Church
  status). Inherited values are read live from the adult page and are never copied, so a correction
  there shows here.
- Type a value only for facts the canonical page doesn't hold (e.g. "Known for"). A fact with a
  label but no value or inherit choice won't save.
- Saint pages can inherit saint fields only; the other four types can inherit site fields only.

## Quiz

- Exactly **five questions** to publish (drafts can have fewer).
- Each question: **3 or 4 choices, exactly one marked correct**, and a kind explanation that teaches
  rather than scolds.

## Pictures

- A picture appears only when **both the image and its credit** are filled. With no credit, the page
  shows the placeholder frame. Canonical (adult) images are never used unless they have a credit.
- Alt text describes what's in the picture for a child who can't see it.
- Sizes and ratios: see `art-manifest.md` (hero 3:4, context scene 2:3, index thumbnail 4:3).

## Accuracy and wording

- No invented facts; every claim should trace to a listed source. Add sources under Sources.
- **Marian:** the Church-status line comes from the canonical page; the note explains what that
  judgment means and what it does **not** claim. Never imply every apparition has the same approval.
- **Eucharistic:** describe what was reported as a historical claim; don't present scientific claims
  as definitive.
- **Holy Land:** link Bible passages to a reputable Catholic Scripture source. Separate what's known
  from what tradition says. No travel information.
- **Missions:** set the founding number and date only with a source in the source note; the Mission
  Trail's stop order is geography, never founding order. Link the current trail page, never the older
  duplicates (1144, 1126 in production). Name Native communities only from cited sources, and tell the
  difficult history honestly at the children's level.

## Samples

Anything with "(sample)" in its title or "[SAMPLE" in its text was made by
`future_saints_dev_sample` for local layout review. It must never be entered in production.
