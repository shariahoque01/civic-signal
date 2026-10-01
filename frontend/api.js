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

// Served by the backend at /ui/, so the API is same-origin. Set MOCK_MODE = true to
// demo without a backend (mock data below), or open ?mock=1.
const MOCK_MODE = /[?&]mock=1/.test(location.search);
// Static snapshot (built by backend/scripts/export_static.py for Vercel): read data/*.json, no writes.
const SNAPSHOT = window.CIVIC_SNAPSHOT || null;
const _snapCache = {};
function _snap(name) {
  if (!_snapCache[name]) _snapCache[name] = fetch("data/" + name + ".json").then((r) => {
    if (!r.ok) throw new Error("Snapshot data missing: " + name);
    return r.json();
  });
  return _snapCache[name];
}
function _readOnly() {
  const err = new Error("This is a read-only snapshot. Run the app locally to edit or add videos.");
  err.status = 403;
  return Promise.reject(err);
}
const API_BASE = location.protocol === "file:" ? "http://127.0.0.1:8000" : "";

/*
 * Added endpoints (backend/app/videos.py, backend/app/main.py):
 *   GET  /api/videos?days=7          -> { total, days, videos: Video[] }  every ingested video, 311 or not
 *   GET  /api/cases                  -> { cases: [{ observation, source, service_request }] }
 *   POST /api/workflow/run {urls[]}  -> { counts, results[] }  fetch + filter + extract + 311 draft
 *   PATCH /api/service-requests/{id} {status, sr_number, ...} -> case
 * `_toObservation` folds source metadata into the `display` field the screens already read,
 * and attaches `service_request` (null when no 311 was drafted).
 */
function _fmtCount(n) { return n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1e3 ? Math.round(n / 1e3) + "k" : String(n || 0); }
function _toObservation(c) {
  var s = c.source, o = c.observation;
  o.display = {
    handle: s.handle ? "@" + s.handle : null, platform: s.platform, url: s.url,
    views: _fmtCount(s.views), shares: null, likes: _fmtCount(s.likes),
    date: s.posted_at ? new Date(s.posted_at).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "",
    caption: s.caption, transcript: s.transcript, note: o.evidence && o.evidence.note,
  };
  o.service_request = c.service_request;
  return o;
}

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
    if (SNAPSHOT) return _readOnly();
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
    // The workflow endpoint also captures post metadata and drafts the 311, and works without a Gemini key.
    const run = await _real("/api/workflow/run", { method: "POST", body: JSON.stringify({ urls: [url], window_days: 60 }) });
    const r = run.results[0];
    if (r.status === "error") { const err = new Error(r.reason); err.status = 400; throw err; }
    if (r.status === "skipped" && r.reason !== "already processed") { const err = new Error("Not added: " + r.reason); err.status = 422; throw err; }
    if (!r.observation_id) {
      const all = await this.getCases();
      const hit = all.observations.find((o) => o.display.url && url.indexOf(o.display.url) === 0);
      if (!hit) { const err = new Error("Saved, but it isn't a fix request, so there's no case to review (see This week's videos)."); err.status = 422; throw err; }
      return hit;
    }
    return this.getCase(r.observation_id);
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
    const res = SNAPSHOT ? await _snap("cases") : await _real("/api/cases");
    let list = res.cases.map(_toObservation);
    for (const key of ["status", "borough", "topic", "type"]) {
      if (filters[key]) list = list.filter((o) => (key === "borough" ? o.location.borough : o[key]) === filters[key]);
    }
    if (filters.limit) list = list.slice(0, filters.limit);
    return { total: res.total, count: list.length, observations: list, portal_url: res.portal_url };
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
    const all = await this.getCases();
    const found = all.observations.find((o) => o.id === id);
    if (!found) { const err = new Error("Case not found"); err.status = 404; throw err; }
    return found;
  },

  /**
   * Save a staff decision (priority, agency, status, notes, or a corrected
   * AI field) back to a case.
   * @param {string} id
   * @param {{ status?, final_agency?, final_priority?, reviewer_notes?, type?, topic?, borough?, urgency?, location_description? }} patch
   * @returns {Promise<Observation>}
   */
  async saveCase(id, patch) {
    if (SNAPSHOT) return _readOnly();
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

  /** Full transcript-analysis payload (backend/app/insights.py): sentiment, blind_spots, engagement_plan, ... Cached per page load. */
  async getInsights() {
    if (MOCK_MODE) { const err = new Error("Insights need the live backend."); err.status = 501; throw err; }
    if (!this._insights) this._insights = (SNAPSHOT ? _snap("insights") : _real("/api/insights")).catch((e) => { this._insights = null; throw e; });
    return this._insights;
  },

  /** Every ingested video in the last `days` days, 311 case or not. */
  async getVideos(days = 7) {
    if (MOCK_MODE) {
      await _mockDelay(150);
      return { total: MOCK_OBSERVATIONS.length, days, videos: MOCK_OBSERVATIONS.map((o) => ({
        id: o.source_id, platform: o.display.platform, url: null, handle: (o.display.handle || "").replace("@", ""),
        posted_at: o.created_at, views: 0, likes: 0, caption: o.summary, hashtags: [], relevance: "fix_request",
        transcript: o.evidence.quote, observation: { id: o.id, type: o.type, topic: o.topic, summary: o.summary, quote: o.evidence.quote },
        service_request: null,
      })) };
    }
    if (SNAPSHOT) {
      const all = await _snap("videos");
      const cutoff = new Date(SNAPSHOT.exported_at).getTime() - days * 864e5;  // window relative to export time
      const videos = all.videos.filter((v) => v.posted_at && new Date(v.posted_at).getTime() >= cutoff);
      return { total: videos.length, days, videos };
    }
    return _real(`/api/videos?days=${days}`);
  },

  /** Update a drafted 311 request: status (draft|approved|filed|declined), sr_number, or edited fields. */
  async updateServiceRequest(id, patch) {
    if (SNAPSHOT) return _readOnly();
    if (MOCK_MODE) { await _mockDelay(150); return null; }
    return _real(`/api/service-requests/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(patch) });
  },
};
