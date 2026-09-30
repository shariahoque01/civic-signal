/*
 * Civic Signal API layer
 * =======================
 * Every network call lives behind this one `api` object. Nothing else in the
 * app should call `fetch` directly. Flip MOCK_MODE to switch every endpoint
 * at once when the backend contract changes.
 *
 * Contract as documented in backend/CHANGES_AND_OVERVIEW_5pm.md (2026-09-30):
 *
 * POST /api/process
 *   body:   { url: string, platform: "tiktok"|"instagram", caption?: string }
 *        or { platform: "upload", file_path: string }
 *   returns: 201 Observation (see shape below)
 *   NOTE: there is no browser file-upload endpoint yet - a real "upload" call
 *   only works if file_path already exists in backend/uploads/. In this app,
 *   the file-picker is MOCK_MODE-only; it's disabled in real mode until a
 *   multipart upload endpoint exists (see api.processVideo below).
 *   Slow: 10-40s. Do not auto-retry on 500 (burns Gemini quota).
 *
 * GET /api/observations?status&borough&topic&type&limit&offset
 *   returns: { total: number, count: number, observations: Observation[] }
 *   (newest first)
 *
 * GET /api/observations/{id}
 *   returns: Observation, or 404 { error }
 *
 * PATCH /api/observations/{id}
 *   body: any of { status, final_agency, final_priority, reviewer_notes,
 *                  type, topic, borough, urgency, location_description }
 *   returns: updated Observation
 *
 * GET /api/signals -> { total, signals: Signal[] }
 * POST /api/signals/aggregate -> { message, signals_created, signals_updated, groups_found }
 *
 * Observation shape (backend-authoritative fields only):
 * {
 *   id, source_id,
 *   type: "issue"|"request"|"idea"|"praise"|"information"|"other",
 *   topic: one of TOPICS (see constants.py),
 *   summary: string,
 *   location: { description, borough, neighborhood, confidence, needs_review },
 *   agency_candidates: [{ name, confidence }],
 *   urgency: "low"|"medium"|"high"|null,
 *   language, confidence, evidence: { quote },
 *   status: "new"|"reviewed"|"rejected",
 *   reviewed_at, reviewer_notes,
 *   final_agency, final_priority: "low"|"medium"|"high"|null,
 *   created_at
 * }
 *
 * The backend does NOT return video metadata (handle, platform, views,
 * shares, post date, thumbnail). Case review / Inbox display those as
 * "display" fields that are UI-only and simply blank/absent when the data
 * comes from the real API - they are never sent back in a PATCH.
 *
 * Priority mapping: the design's P1-P4 has been collapsed to the backend's
 * own High/Medium/Low so there is no translation layer to keep in sync.
 */

const MOCK_MODE = true;
const API_BASE = "http://127.0.0.1:8000";

// ---- mock data ------------------------------------------------------------
// Shaped exactly like real Observations, plus a few UI-only "display" fields
// (handle, platform, views, shares, date) the backend does not provide.

let _mockIdSeq = 100;
const MOCK_OBSERVATIONS = [
  {
    id: "obs_1", source_id: "src_1", type: "issue", topic: "water",
    summary: "Water fountain broken at Maple Grove Park",
    location: { description: "Maple Grove Park, near the playground", borough: "Bronx", neighborhood: "Eastbrook", confidence: 0.91, needs_review: false },
    agency_candidates: [{ name: "NYC DEP", confidence: 0.8 }],
    urgency: "low", language: "en", confidence: 0.91,
    evidence: { quote: "the fountain has been dead all summer, kids are drinking from the hose" },
    status: "new", reviewed_at: null, reviewer_notes: null,
    final_agency: null, final_priority: null,
    created_at: "2026-09-21T12:00:00Z",
    display: { handle: "@park_parent_demo", platform: "tiktok", views: "42k", shares: "1.2k", date: "Sep 21", suggested_reply: "Thanks for flagging this. We've sent it to Parks to check the fountain." },
  },
  {
    id: "obs_2", source_id: "src_2", type: "issue", topic: "roads",
    summary: "Uncovered manhole near the Alder Street school crossing",
    location: { description: "Alder St crossing, by the school entrance", borough: "Manhattan", neighborhood: "Riverside", confidence: 0.88, needs_review: false },
    agency_candidates: [{ name: "NYC DOT", confidence: 0.85 }],
    urgency: "high", language: "es", confidence: 0.88,
    evidence: { quote: "hay una alcantarilla abierta donde cruzan los niños", quote_en: "there is an open manhole where the children cross" },
    status: "new", reviewed_at: null, reviewer_notes: null,
    final_agency: null, final_priority: null,
    created_at: "2026-09-24T12:00:00Z",
    display: { handle: "@vecina_demo", platform: "tiktok", views: "18k", shares: "640", date: "Sep 24", safety_flag: true, suggested_reply: "Gracias. Estamos enviando esto de inmediato al equipo de calles. (English draft included.)" },
  },
  {
    id: "obs_3", source_id: "src_3", type: "idea", topic: "rats",
    summary: "Redesign park trash cans with lids to stop rats",
    location: { description: "Parks citywide", borough: "Bronx", neighborhood: "Eastbrook", confidence: 0.84, needs_review: false },
    agency_candidates: [{ name: "NYC DOHMH", confidence: 0.7 }, { name: "NYC Parks", confidence: 0.6 }],
    urgency: null, language: "en", confidence: 0.84,
    evidence: { quote: "if the cans had lids the rats wouldn't win every night" },
    status: "reviewed", reviewed_at: "2026-09-20T09:00:00Z", reviewer_notes: null,
    final_agency: "NYC DOHMH", final_priority: "medium",
    created_at: "2026-09-19T12:00:00Z",
    display: { handle: "@rat_watch_demo", platform: "tiktok", views: "96k", shares: "5.4k", date: "Sep 19", who_benefits: "Park visitors, nearby homes, park staff", echo: "6 other videos, 212k total views", suggested_reply: "Great idea. We shared it with Sanitation and Parks. We'll tell you what they decide." },
  },
  {
    id: "obs_4", source_id: "src_4", type: "idea", topic: "transportation",
    summary: "Add shade structures at bus stops",
    location: { description: "Bus stops citywide", borough: "Queens", neighborhood: "Hillcrest", confidence: 0.86, needs_review: false },
    agency_candidates: [{ name: "NYC DOT", confidence: 0.75 }],
    urgency: null, language: "en", confidence: 0.86,
    evidence: { quote: "just give us some shade while we wait" },
    status: "new", reviewed_at: null, reviewer_notes: null,
    final_agency: null, final_priority: null,
    created_at: "2026-09-25T12:00:00Z",
    display: { handle: "@commuter_demo", platform: "instagram", views: "31k", shares: "900", date: "Sep 25", who_benefits: "Riders, older adults, kids", echo: "2 other videos", suggested_reply: "Thanks for the suggestion. We've passed it to Transportation." },
  },
  {
    id: "obs_5", source_id: "src_5", type: "issue", topic: "streetlights",
    summary: "Streetlight out on Finch Lane for two weeks",
    location: { description: "Finch Lane (two streets match; no cross street given)", borough: null, neighborhood: null, confidence: 0.46, needs_review: true },
    agency_candidates: [{ name: "NYC DOT", confidence: 0.4 }],
    urgency: "medium", language: "zh", confidence: 0.46,
    evidence: { quote: "Finch Lane 的路灯已经坏了两个星期", quote_en: "the streetlight on Finch Lane has been out for two weeks" },
    status: "new", reviewed_at: null, reviewer_notes: null,
    final_agency: null, final_priority: null,
    created_at: "2026-09-26T12:00:00Z",
    display: { handle: "@lane_demo", platform: "tiktok", views: "7k", shares: "80", date: "Sep 26", suggested_reply: "Draft paused until the location is confirmed." },
  },
  {
    id: "obs_6", source_id: "src_6", type: "other", topic: "roads",
    summary: "Thank you for fixing the crosswalk",
    location: { description: "Oak Ave crosswalk", borough: "Manhattan", neighborhood: "Riverside", confidence: 0.95, needs_review: false },
    agency_candidates: [],
    urgency: null, language: "en", confidence: 0.95,
    evidence: { quote: "they finally fixed the crosswalk, thank you" },
    status: "reviewed", reviewed_at: "2026-09-20T09:00:00Z", reviewer_notes: null,
    final_agency: null, final_priority: null,
    created_at: "2026-09-20T12:00:00Z",
    display: { handle: "@thankful_demo", platform: "tiktok", views: "12k", shares: "210", date: "Sep 20", suggested_reply: "Thank you! We'll pass your note to the crew." },
  },
];

function _mockDelay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function _real(path, options = {}) {
  const res = await fetch(API_BASE + path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  let body = null;
  try { body = await res.json(); } catch (_) { /* no body */ }
  if (!res.ok) {
    const message = (body && body.error) || `Request failed (${res.status})`;
    const err = new Error(message);
    err.status = res.status;
    err.details = body && body.details;
    throw err;
  }
  return body;
}

const api = {
  /**
   * Kick off extraction for a video.
   * @param {{ url?: string, platform: "tiktok"|"instagram"|"upload", file_path?: string }} input
   * @returns {Promise<Observation>}
   */
  async processVideo({ url, platform, file_path }) {
    if (MOCK_MODE) {
      await _mockDelay(1600);
      if (/error|fail/i.test(url || "")) {
        const err = new Error("We couldn't read this link");
        err.status = 400;
        throw err;
      }
      _mockIdSeq += 1;
      const fresh = {
        id: `obs_${_mockIdSeq}`, source_id: `src_${_mockIdSeq}`,
        type: "issue", topic: "other",
        summary: "New submission (mock draft) - AI would fill this in",
        location: { description: "Location not yet confirmed", borough: null, neighborhood: null, confidence: 0.6, needs_review: false },
        agency_candidates: [{ name: "NYC 311", confidence: 0.5 }],
        urgency: "medium", language: "en", confidence: 0.72,
        evidence: { quote: "(mock transcript excerpt would appear here)" },
        status: "new", reviewed_at: null, reviewer_notes: null,
        final_agency: null, final_priority: null,
        created_at: new Date().toISOString(),
        display: { handle: "@new_submission", platform, views: "0", shares: "0", date: "Just now", suggested_reply: "Thanks, we're looking into this." },
      };
      MOCK_OBSERVATIONS.unshift(fresh);
      return fresh;
    }
    if (platform === "upload") {
      const err = new Error("File upload isn't supported by the backend yet - paste a link instead.");
      err.status = 501;
      throw err;
    }
    return _real("/api/process", { method: "POST", body: JSON.stringify({ url, platform }) });
  },

  /**
   * List cases for the Inbox.
   * @param {{ status?, borough?, topic?, type?, limit?, offset? }} filters
   * @returns {Promise<{ total: number, count: number, observations: Observation[] }>}
   */
  async getCases(filters = {}) {
    if (MOCK_MODE) {
      await _mockDelay(200);
      let list = MOCK_OBSERVATIONS.slice();
      for (const key of ["status", "borough", "topic", "type"]) {
        if (filters[key]) list = list.filter((o) => (key === "borough" ? o.location.borough : o[key]) === filters[key]);
      }
      return { total: list.length, count: list.length, observations: list };
    }
    const params = new URLSearchParams(Object.entries(filters).filter(([, v]) => v != null));
    const qs = params.toString();
    return _real(`/api/observations${qs ? `?${qs}` : ""}`);
  },

  /**
   * Fetch a single case for the Case review screen.
   * @param {string} id
   * @returns {Promise<Observation>}
   */
  async getCase(id) {
    if (MOCK_MODE) {
      await _mockDelay(150);
      const found = MOCK_OBSERVATIONS.find((o) => o.id === id);
      if (!found) {
        const err = new Error("Case not found");
        err.status = 404;
        throw err;
      }
      return found;
    }
    return _real(`/api/observations/${encodeURIComponent(id)}`);
  },

  /**
   * Save a staff decision (priority, agency, status, notes, or a corrected
   * AI field) back to a case.
   * @param {string} id
   * @param {{ status?, final_agency?, final_priority?, reviewer_notes?, type?, topic?, borough?, urgency?, location_description? }} patch
   * @returns {Promise<Observation>}
   */
  async saveCase(id, patch) {
    if (MOCK_MODE) {
      await _mockDelay(250);
      const found = MOCK_OBSERVATIONS.find((o) => o.id === id);
      if (!found) {
        const err = new Error("Case not found");
        err.status = 404;
        throw err;
      }
      Object.assign(found, patch);
      if (patch.borough !== undefined) found.location.borough = patch.borough;
      if (patch.location_description !== undefined) found.location.description = patch.location_description;
      found.reviewed_at = new Date().toISOString();
      return found;
    }
    return _real(`/api/observations/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(patch) });
  },
};
