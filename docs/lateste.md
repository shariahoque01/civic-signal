# Civic Signal — One-Day Hackathon Plan

## 1. Project Overview

**Civic Signal** turns public social-media videos about New York City into structured civic observations that can be reviewed by humans and surfaced as recurring civic signals.

The product is designed as an additional public-engagement intake channel alongside 311, not as a replacement for 311.

### Core principle

> **AI suggests, staff decide.**

AI-generated information must remain clearly identifiable and editable. A human reviewer makes the final decisions about priority, agency, status, and notes.

---

## 2. The Problem

Residents may report city problems through TikTok or Instagram instead of submitting a formal 311 request.

Examples:

- A broken streetlight
- A damaged bus shelter
- Overflowing trash
- Rats around a park
- A dangerous sidewalk condition
- A suggested improvement to a public space

These posts can contain useful civic information, but the information is unstructured.

Civic Signal converts that unstructured public content into structured information that a city employee can review and act on.

---

## 3. One-Day MVP Goal

The goal is to demonstrate one complete vertical slice:

```text
Public video
     ↓
Video / URL intake
     ↓
AI processing
     ↓
Structured civic observation
     ↓
Human review
     ↓
Saved observation
     ↓
Inbox / tracker
     ↓
Recurring civic signal
     ↓
API-accessible data
```

The MVP should prioritize a reliable end-to-end demonstration rather than trying to build a complete production platform.

---

# 4. MVP Scope

## Build

- NYC-wide civic content
- Public TikTok/Instagram URL submission where technically accessible
- Video upload fallback
- Transcript extraction
- Language detection
- Civic classification
- Topic extraction
- Location extraction
- Agency candidates
- Confidence scores
- Evidence
- Human review
- Observation storage
- Basic recurring-signal aggregation
- Basic REST API
- Intake screen
- Case Review screen
- Inbox / Tracker screen

## Do Not Build

- Automated collection of every TikTok in NYC
- Automated collection of every Instagram Reel in NYC
- Private account access
- Private messages or DMs
- Citywide social-media firehose
- Automatic 311 submission
- Automatic agency action
- Fully automated agency routing
- Claims that an allegation is verified
- Advanced trend detection
- Advanced geographic mapping
- NYC 311 integration
- Reddit integration
- YouTube integration
- Agency notifications
- Authentication/API keys
- Public developer portal

These can be future features.

---

# 5. Product Flow

## Step 1 — Intake

A staff member can:

- Paste a public TikTok or Instagram URL
- Upload a video file

The system processes the submitted content.

---

## Step 2 — AI Processing

The system extracts:

- Summary
- Type
- Topic
- Location
- Borough
- Potential agency
- Urgency
- Language
- Confidence
- Evidence

The AI should not invent missing information.

If location or agency information is uncertain, the system should flag the item for human review.

---

## Step 3 — Case Review

The reviewer sees:

### Source information

- Video/source
- Platform
- Creator handle when necessary
- Transcript
- Relevant evidence

### AI-generated information

- Summary
- Type
- Topic
- Location
- Agency candidates
- Urgency
- Language
- Confidence

### Human decision

- Priority
- Final agency
- Status
- Notes

The reviewer can edit AI-generated fields before saving.

---

## Step 4 — Save Observation

After review, the case becomes a structured civic observation.

Example:

```json
{
  "id": "obs_001",
  "type": "issue",
  "summary": "Broken streetlight reported in Queens",
  "topic": "streetlights",
  "location": {
    "description": "Street intersection",
    "borough": "Queens",
    "confidence": 0.86
  },
  "agency_candidates": [
    {
      "name": "NYC DOT",
      "confidence": 0.89
    }
  ],
  "urgency": "medium",
  "language": "English",
  "confidence": 0.91,
  "status": "reviewed"
}
```

An observation represents an AI-extracted interpretation of one public source. It should not automatically be treated as a verified fact.

---

# 6. Classification

Use the following MVP categories:

| Type | Meaning |
|---|---|
| Issue | Something is broken, unsafe, missing, delayed, or damaged |
| Request | Resident explicitly asks government to take action |
| Idea | Resident proposes an improvement |
| Praise | Positive feedback about a service or action |
| Information | Informational civic content |
| Other | Does not fit another category |

The initial topic list should remain manageable:

- Transportation
- Public transit
- Roads
- Sidewalks
- Streetlights
- Sanitation
- Trash
- Rats / pests
- Parks
- Housing
- Public safety
- Water
- Noise
- Construction
- Accessibility
- Public facilities

---

# 7. Location Handling

Location is one of the most valuable pieces of information.

Possible location evidence includes:

- Spoken words
- Captions
- On-screen text
- Hashtags
- Neighborhood names
- Street names
- Intersections
- Landmarks
- Available public metadata

The system must not invent a location.

Example:

```text
Location:
Finch Lane

Confidence:
Low

Status:
Needs human review
```

When the location is ambiguous, the reviewer should be able to correct it.

---

# 8. Agency Mapping

Agency mapping should produce candidates rather than pretending the answer is always certain.

Example:

```text
Broken bus shelter
        ↓
NYC DOT — 0.89
```

Another example:

```text
Rats in a park
        ↓
NYC Parks — 0.81
DSNY      — 0.68
```

The human reviewer selects or adjusts the final agency.

---

# 9. Evidence and Confidence

Every important AI-generated claim should have supporting evidence where possible.

Example:

```text
Civic Observation
-----------------
Issue: Broken streetlight
Location: Queens
Agency: NYC DOT
Confidence: 91%

Evidence:
"The streetlight on this block has been out for two weeks."
```

The product should communicate:

```text
Public post
     ≠
Verified civic fact
```

Instead:

```text
Public post
     ↓
AI-extracted observation
     ↓
Evidence + confidence
     ↓
Human review
     ↓
Potential civic signal
```

---

# 10. Data Model

Keep the one-day database model simple.

## Source

Represents the original public social-media item.

Suggested fields:

```text
source_id
platform
post_url
created_at
caption
transcript
language
engagement
ingestion_timestamp
```

## Observation

Represents the structured interpretation of one source.

Suggested fields:

```text
observation_id
source_id
type
topic
summary
location
borough
location_confidence
agency_candidates
agency_confidence
urgency
language
confidence
evidence
status
created_at
```

## Civic Signal

Represents an aggregated pattern across related observations.

Suggested fields:

```text
signal_id
title
topic
agency_candidates
geography
observation_count
unique_source_count
estimated_reach
first_seen
last_seen
confidence
evidence_ids
```

---

# 11. Civic Signal Aggregation

Do not build advanced machine-learning clustering for the hackathon.

Use a simple approach based on related:

- Topic
- Borough
- Keywords

Example:

```text
Observation 1:
"Broken bus shelter"

Observation 2:
"The glass at this bus stop is damaged"

Observation 3:
"Another damaged bus shelter"

             ↓

Civic Signal:
"Damaged bus shelters — Queens"

3 observations
Potential agency: NYC DOT
```

The purpose is to demonstrate the concept, not to claim perfect clustering.

---

# 12. User Interface

The MVP should have three main screens.

## Screen 1 — Intake

```text
CIVIC SIGNAL

Turn public voices into civic intelligence.

[ Public TikTok / Instagram URL ]

OR

[ Upload Video ]

[ Process with AI ]
```

Include useful processing states:

```text
Loading
Transcript extracted
Finding location
Finding agency
Classifying civic content
Preparing review
```

Include basic errors:

```text
Private/deleted/unreadable post
Unsupported URL
Processing failure
```

---

## Screen 2 — Case Review

The Case Review screen is the main demo screen.

Show:

```text
Source / Video
Transcript
AI Summary
Type
Topic
Location
Agency Candidates
Urgency
Language
Confidence
Evidence
```

Then show:

```text
Human Decision

Priority
Final Agency
Status
Notes

[ Save Observation ]
```

Clearly distinguish AI suggestions from human decisions.

---

## Screen 3 — Inbox / Tracker

Show summary information such as:

```text
New Cases
Needs Review
Issues
Ideas
```

Then a table:

```text
Case                  Borough    Agency    Status
---------------------------------------------------
Broken streetlight    Queens     DOT       Reviewed
Overflowing trash     Brooklyn   DSNY      New
Damaged bus shelter   Queens     DOT       Review
```

Show recurring civic signals:

```text
Streetlights — Queens
5 observations

Trash / sanitation — Brooklyn
4 observations

Bus shelters — Queens
3 observations
```

---

# 13. API Scope

Keep the API small.

### Endpoints

```http
POST /api/process
GET /api/observations
GET /api/observations/{id}
PATCH /api/observations/{id}
GET /api/signals
```

The API should expose structured civic information rather than requiring consumers to process the original social-media content themselves.

Example:

```http
GET /api/observations
```

Example response:

```json
{
  "observations": [
    {
      "id": "obs_001",
      "type": "issue",
      "topic": "streetlights",
      "borough": "Queens",
      "agency": "NYC DOT",
      "urgency": "medium",
      "confidence": 0.91,
      "status": "reviewed"
    }
  ]
}
```

---

# 14. Backend / Frontend Work Split

## Backend

Build:

- Video/file intake
- AI processing
- Structured extraction
- Validation
- Agency mapping
- Observation storage
- Observation API
- Human-review update API
- Basic Civic Signal aggregation

## Frontend

Build:

- Intake screen
- Processing state
- Case Review
- Human decision controls
- Inbox
- Civic Signal summary
- API integration

## Shared

Agree on the API response schema before building the UI.

---

# 15. Demo Data

Prepare a small curated collection before the hackathon.

Aim for approximately:

- 5–10 videos for the live demo
- Multiple civic topics
- Multiple NYC boroughs
- At least one Issue
- At least one Request
- At least one Idea
- At least one low-confidence example
- At least one non-English example
- At least one example that can contribute to a recurring signal

Do not make live social-media discovery a dependency for the demo.

Use downloaded/curated public clips or uploaded files if necessary.

---

# 16. One-Day Execution Plan

Assuming approximately eight hours:

## Hour 0–0.5 — Setup

- Create shared repository
- Agree on API contract
- Confirm demo data
- Confirm three-screen UI
- Create basic project structure

## Hour 0.5–1.5 — AI Contract

- Define structured observation schema
- Create AI prompt
- Test one video
- Validate structured output
- Handle missing/uncertain fields

## Hour 1.5–2.5 — Processing Pipeline

Build:

```text
Video
 ↓
Transcript / content
 ↓
AI extraction
 ↓
Structured observation
```

Test multiple examples.

## Hour 2.5–3.5 — API

Build:

```text
POST /api/process
GET /api/observations
GET /api/observations/{id}
PATCH /api/observations/{id}
GET /api/signals
```

## Hour 3.5–4.5 — Storage

Connect:

```text
AI result
 ↓
Observation
 ↓
Database
```

Verify that observations can be retrieved and updated.

## Hour 4.5–5.5 — Frontend Integration

Connect the Intake and Case Review screens to the backend.

## Hour 5.5–6.5 — Inbox

Display:

- Saved observations
- Status
- Agency
- Borough
- Topic
- Recurring signals

## Hour 6.5–7.0 — Aggregation

Add simple grouping for recurring topics/signals.

## Hour 7.0–7.5 — Polish

Focus on:

- Loading states
- Error states
- Confidence display
- AI vs human distinction
- Clean visual presentation

## Hour 7.5–8.0 — Demo Rehearsal

Run the complete flow from beginning to end.

---

# 17. Feature Priority

If time becomes limited, use this order:

### P0 — Must Work

1. Video upload
2. AI extraction
3. Structured observation
4. Case Review
5. Human editing
6. Save observation
7. Inbox

### P1 — Strongly Recommended

8. URL processing
9. Evidence
10. Confidence
11. Agency candidates
12. Basic Civic Signal aggregation
13. API

### P2 — Only If Everything Works

14. Map
15. Advanced clustering
16. Trend detection
17. Voice-gap analysis
18. Additional source types

---

# 18. Failure Strategy

If URL retrieval becomes unreliable:

```text
Use uploaded MP4 files.
```

If advanced aggregation takes too long:

```text
Group by topic + borough.
```

If maps take too long:

```text
Use borough labels instead.
```

If the API needs more time:

```text
Prioritize the core processing and review flow.
```

The demo should never depend on a fragile external social-media scraping workflow.

---

# 19. Demo Story

The demo should tell one simple story.

### Step 1

A resident posts a video about a city problem.

### Step 2

The staff member submits the public video to Civic Signal.

### Step 3

Civic Signal processes the video.

### Step 4

AI extracts:

```text
Issue
Topic
Location
Agency
Urgency
Language
Confidence
Evidence
```

### Step 5

A staff member reviews the AI output.

### Step 6

The staff member corrects or confirms the information.

### Step 7

The observation is saved.

### Step 8

The observation appears in the Inbox.

### Step 9

Several related observations appear as a recurring Civic Signal.

### Step 10

The structured information is available through the API.

---

# 20. Product Positioning

The project should not be presented as:

> "An AI tool that scrapes TikTok."

Instead:

> **Civic Signal turns public NYC social-media posts into structured civic observations and emerging signals that can be reviewed by humans and accessed through an API.**

The important transformation is:

```text
Messy public information
          ↓
Structured civic observation
          ↓
Human review
          ↓
Recurring civic signal
```

---

# 21. Privacy and Safety

The system should:

- Process public content only
- Avoid private messages
- Avoid unnecessary personal-profile information
- Minimize creator identifiers
- Keep evidence traceable
- Clearly label AI-generated fields
- Store confidence values
- Require human review for uncertain routing
- Avoid claiming allegations are verified facts
- Avoid treating engagement/views as proof of accuracy

The product should be positioned as a way to surface public feedback for service delivery, not as surveillance.

---

# 22. Definition of Done

The MVP is complete when the team can successfully demonstrate:

```text
✓ Submit a video
        ↓
✓ Process it
        ↓
✓ Extract civic information
        ↓
✓ Display structured AI results
        ↓
✓ Human edits/approves the result
        ↓
✓ Save the observation
        ↓
✓ Display it in the Inbox
        ↓
✓ Group related observations
        ↓
✓ Display a Civic Signal
        ↓
✓ Retrieve the data through the API
```

If all of these work, stop adding features and focus on demo quality.

---

# 23. Future Direction

After the hackathon, Civic Signal can expand to:

- Automated source discovery
- Additional public platforms
- NYC 311 integration
- Advanced semantic clustering
- Trend detection
- Geographic signal maps
- Agency notifications
- Additional public datasets
- Public developer access

The long-term concept is a reusable civic-information layer that can accept multiple public data sources without redesigning the core observation model.

---

# 24. Final Project Statement

> **Civic Signal turns public NYC social-media posts into structured civic observations and emerging signals that can be reviewed by humans and accessed through an API.**

The one-day hackathon should focus on proving this end-to-end workflow rather than building the entire future platform.
