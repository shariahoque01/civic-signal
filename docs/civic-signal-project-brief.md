# Civic Signal — Project Brief
*State Capacity AI Hackathon · Public Engagement, Public Voice At Scale*

Placeholder name: **Civic Signal**

## 1. The idea

Residents often speak up about city issues on TikTok and Instagram — tagging or addressing the mayor directly — rather than filing a 311 request. This is especially true for historically underheard groups: non-English speakers, people who distrust official channels, and people who just prefer video over a form.

Civic Signal turns those public videos into structured, triage-ready case records for a city employee in the mayor's office, so that social media becomes a second, more inclusive intake channel alongside 311 — not a replacement for it.

Feedback comes in more than one shape, and the product treats both as first-class:
- **Issues** — something broken or unsafe (a broken water fountain, an open manhole)
- **Ideas** — a suggested improvement (redesigned trash cans, shade at bus stops)
- **Other** — praise, questions, or anything not actionable

**Core principle: AI suggests, staff decide.** Every AI-generated field is editable and clearly labeled, and a human sets the final priority, agency assignment, and status.

## 2. User flow

1. Staff member pastes a public TikTok/Instagram link, or uploads a video file.
2. AI processes the video (visual + audio) and drafts a structured case: summary, type, likely agency, location, urgency, language, sentiment, confidence score, and a suggested public reply.
3. Staff review the draft on the case card, edit anything that's off, and set priority, assigned agency, status, and notes.
4. The case is saved to the tracker (Inbox), where all cases live as a triage queue with filters, recurring-theme clustering, and a map view.
5. (Stretch) A voice-gap view compares social-post volume with 311 volume by neighborhood, to surface where formal channels are under-reporting real complaints.

## 3. Screens (from the design concept)

Source file: `civic-signal.html` — a clickable, mock-data-only design proof of concept (no real video processing; all content is illustrative).

1. **Intake** — paste-a-link / upload-a-file input, plus explicit loading, empty, and error states shown side by side for design review.
2. **Case review** — the core screen. Left: video placeholder, creator handle, platform, views/shares, transcript with key quote highlighted. Right: AI draft fields (purple/dashed = AI suggestion) and a staff decision section (green = staff-set): priority (P1–P4), assigned agency, status, notes, and action buttons (Save to tracker / Route to agency / Decline). Includes variants for an Issue card, an Idea card (swaps urgency for "who benefits" + "how many others are saying this"), and a low-confidence card with a "needs human review" flag.
3. **Inbox / Tracker** — summary tiles (new this week, Issues vs Ideas split, needs review, avg time to triage), a filterable/sortable case table, a recurring-themes panel (e.g. "Trash cans and rats — 6 videos, 212k views"), and a map with pins colored by type.
4. **Voice-gap view** (secondary/stretch) — neighborhood-level comparison of social mentions vs 311 volume, plus a language breakdown.

## 4. Suggested tech stack (zero/low-cost)

| Layer | Choice | Notes |
|---|---|---|
| Frontend | Streamlit (or Next.js) | Simple input UI: upload a file or paste a URL |
| Video retrieval | `yt-dlp` | Open-source; downloads public video to temp storage, no paid platform API keys |
| AI processing | Gemini 2.5 Flash (Google AI Studio) | Multimodal — processes visual frames + native audio in one free request |
| Extraction schema | Structured system prompt + Pydantic schema | Forces consistent JSON output: summary, type, location cues, category, etc. |
| Agency mapping | Deterministic Python lookup matrix | Maps Gemini's category output to real municipal agency codes (e.g. NYC: DOT for streets, DSNY for sanitation, Parks for tree/park issues) |
| Data store | Google Sheets (or local table) | Acts as the tracker; matches how staff already work with spreadsheets |
| Output | Rendered triage ticket / dashboard | The case review + inbox screens in the design concept |

**Pipeline in one line:** video (upload or URL via `yt-dlp`) → Gemini 2.5 Flash (multimodal extraction) → Python agency-lookup matrix → structured ticket written to Sheets/dashboard.

## 5. Build approach (given a ~3–4 hour window)

- Treat the HTML file as the target UI/UX reference — it already defines the fields, states, and visual language to implement or approximate.
- Priority order if time is short:
  1. Reliable Gemini extraction (the core value — get the JSON schema solid first)
  2. Case review screen with editable AI fields + staff decision fields
  3. Inbox/tracker table with filters
  4. Recurring-themes clustering and map view
  5. Voice-gap comparison (cut first if time runs out)
- Use a small curated set of real public videos (or `yt-dlp`-downloaded clips) rather than live scraping during the demo — treat live scraping as future-architecture, not a live dependency.

## 6. Source files

- `civic-signal.html` — clickable design concept (mock data only, no live functionality). Screens: Intake, Case review, Inbox/Tracker. Useful as the UI spec for whatever framework is actually built (Streamlit/Next.js).

## 7. Open items / things to decide before starting

- [ ] Pick the target city (determines the real 311 agency taxonomy and open-data source for the voice-gap comparison)
- [ ] Confirm final frontend framework: Streamlit (faster to wire to Python/Gemini) vs Next.js (closer to the HTML design concept)
- [ ] Decide whether Sheets API integration is worth the setup time vs. a simple local table/CSV for the demo
- [ ] Curate the demo video set in advance (mix of Issue/Idea/Other, at least one low-confidence/needs-review example, at least one non-English example)
- [ ] Draft and test the Gemini structured-output prompt/schema against the curated videos before building UI around it

## 8. Ethics / privacy notes

- Only public post details are used — no private messages or DMs.
- Store minimal creator info (handle only, not personal profile data).
- Be explicit in the pitch that this surfaces public feedback for service delivery, not surveillance.
- Flag AI location/category uncertainty rather than presenting guesses as fact (the "needs human review" pattern in the design concept).
