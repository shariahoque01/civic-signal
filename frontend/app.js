// Civic Signal frontend - nav, rendering, and wiring to the `api` layer (api.js).
// Visual design (classes, CSS vars, purple/dashed = AI, green = staff) is
// unchanged from civic-signal.html; this file only adds real behavior.

var $ = function (id) { return document.getElementById(id); };

var ICONS = {
  issue: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.3 3.6 1.9 18a1.6 1.6 0 0 0 1.4 2.4h17.4a1.6 1.6 0 0 0 1.4-2.4L13.7 3.6a1.6 1.6 0 0 0-2.8 0Z"/><path d="M12 9v4"/><path d="M12 16.5v.01"/></svg>',
  idea: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18h6"/><path d="M10 21h4"/><path d="M12 3a6 6 0 0 0-4 10.5c.7.6 1 1.4 1 2.3v.2h6v-.2c0-.9.3-1.7 1-2.3A6 6 0 0 0 12 3Z"/></svg>',
  other: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>',
};
function iconFor(type) { return ICONS[type] || ICONS.other; }
function typeLabel(type) { return type ? type.charAt(0).toUpperCase() + type.slice(1) : "Other"; }
function tag(type) { return '<span class="type ' + type + '">' + iconFor(type) + typeLabel(type) + '</span>'; }
function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }

// ---- nav --------------------------------------------------------------
function go(screen, id) {
  document.querySelectorAll("section").forEach(function (e) { e.classList.toggle("on", e.id === screen); });
  document.querySelectorAll("#nav button").forEach(function (b) { b.setAttribute("aria-current", b.dataset.s === screen); });
  if (screen === "home") renderHome();
  if (screen === "videos") renderVideos();
  if (PAGE_RENDERERS[screen]) PAGE_RENDERERS[screen]();
  if (screen === "review") {
    if (!id && !lastReviewId) { $("rv").innerHTML = '<div class="card"><p class="mu">Pick a case from <a href="#" onclick="go(\'inbox\');return false">311 cases</a> to review it.</p></div>'; }
    else renderReview(id || lastReviewId);
  }
  if (screen === "inbox") renderInbox();
  window.scrollTo(0, 0);
}
document.querySelectorAll("#nav button").forEach(function (b) { b.onclick = function () { go(b.dataset.s); }; });

// ======================= INTAKE =========================================
var intakeState = { phase: "empty", errorMessage: "" }; // empty | loading | error

function renderIntakeState() {
  var frame = $("intakeState");
  if (intakeState.phase === "loading") {
    frame.innerHTML =
      '<b>Working</b><p><span class="spin" role="img" aria-label="Working"></span> Watching video, transcribing, extracting details&hellip;</p>' +
      '<ul class="r"><li>Video received <span class="tag staff">Done</span></li>' +
      '<li>Transcript &amp; extraction <span class="tag ai">In progress</span></li></ul>';
  } else if (intakeState.phase === "error") {
    frame.innerHTML =
      '<b>Error</b><p class="alert">' + esc(intakeState.errorMessage || "We couldn’t read this link") + '</p>' +
      '<p class="mu">The post may be private or deleted. Check that the link opens in a browser, then try again, or upload the video file instead.</p>' +
      '<button class="btn o" id="retryBtn">Try again</button>';
    $("retryBtn").onclick = function () { intakeState.phase = "empty"; renderIntakeState(); };
  } else {
    frame.innerHTML =
      '<b>Ready</b><p><strong>No video yet.</strong></p>' +
      '<p class="mu">Paste a link above or choose a video file below. We accept TikTok, Instagram Reels, and MP4.</p>';
  }
}

function renderRecent() {
  api.getCases({ limit: 4 }).then(function (res) {
    $("recent").innerHTML = res.observations.slice(0, 4).map(function (c) {
      return '<li><span>' + tag(c.type) + ' ' + esc(c.summary) + '</span><small>' +
        esc((c.display && c.display.date) || "") + ' · ' + esc(c.status) + '</small></li>';
    }).join("") || '<li><span class="mu">No submissions yet.</span></li>';
  }).catch(function (err) {
    $("recent").innerHTML = '<li><span class="alert">Couldn’t load recent submissions: ' + esc(err.message) + '</span></li>';
  });
}

function wireIntakeForm() {
  var linkInput = $("videoUrl");
  var fileInput = $("videoFile");
  var submitBtn = $("submitBtn");

  fileInput.disabled = !MOCK_MODE;
  $("fileHint").classList.toggle("hidden", MOCK_MODE);

  submitBtn.onclick = function () {
    var url = linkInput.value.trim();
    var file = fileInput.files && fileInput.files[0];

    if (!file && !url) {
      intakeState.phase = "error";
      intakeState.errorMessage = "Paste a link or choose a file first.";
      renderIntakeState();
      return;
    }

    intakeState.phase = "loading";
    renderIntakeState();
    submitBtn.disabled = true;

    var platform = url.indexOf("instagram.com") !== -1 ? "instagram" : "tiktok";
    var req = file
      ? { platform: "upload", file_path: file.name }
      : { platform: platform, url: url };

    api.processVideo(req).then(function (observation) {
      intakeState.phase = "empty";
      submitBtn.disabled = false;
      renderIntakeState();
      renderRecent();
      go("review", observation.id);
    }).catch(function (err) {
      submitBtn.disabled = false;
      intakeState.phase = "error";
      intakeState.errorMessage = err.message;
      renderIntakeState();
    });
  };
}

// ======================= CASE REVIEW ====================================
var reviewDraft = {}; // in-memory staff decision, keyed by observation id
var lastReviewId = null;

function fld(label, value, kind) {
  var badge = kind === "ai" ? ' <span class="tag ai">AI suggested</span>' : "";
  return '<div class="f"><label>' + label + badge + '</label><div>' + value + '</div></div>';
}

function renderReview(id) {
  $("rv").innerHTML = '<p class="mu"><span class="spin" role="img" aria-label="Loading"></span> Loading case&hellip;</p>';
  $("vars").innerHTML = "";

  lastReviewId = id;
  api.getCase(id).then(function (c) {
    reviewDraft[c.id] = reviewDraft[c.id] || {
      type: c.type,
      final_priority: c.final_priority || "medium",
      final_agency: c.final_agency || (c.agency_candidates[0] && c.agency_candidates[0].name) || "",
      status: c.status,
      reviewer_notes: c.reviewer_notes || "",
    };
    paintReview(c, reviewDraft[c.id]);
  }).catch(function (err) {
    $("rv").innerHTML = '<div class="card"><p class="alert">Couldn’t load this case</p><p class="mu">' + esc(err.message) + '</p></div>';
  });
}

function paintReview(c, draft) {
  var d = c.display || {};
  var lowConf = c.location.needs_review;

  var typeSeg = ["issue", "request", "idea", "other"].map(function (t) {
    return '<span class="' + (t === draft.type ? "a" : "") + '" data-set="type" data-val="' + t + '">' + typeLabel(t) + '</span>';
  }).join("");

  var prioritySeg = ["high", "medium", "low"].map(function (p) {
    return '<span class="' + (p === draft.final_priority ? "s" : "") + '" data-set="final_priority" data-val="' + p + '">' + typeLabel(p) + '</span>';
  }).join("");

  var statusSeg = ["new", "reviewed", "rejected"].map(function (s) {
    return '<span class="' + (s === draft.status ? "s" : "") + '" data-set="status" data-val="' + s + '">' + typeLabel(s) + '</span>';
  }).join("");

  var agencyName = (c.agency_candidates[0] && c.agency_candidates[0].name) || "No agency suggested";
  var locationText = esc(c.location.description || "Not extracted");
  var boroughText = c.location.borough ? " · " + esc(c.location.borough) : "";

  var h = '<div class="grid g2"><div>';
  h += d.url
    ? '<a class="vid" href="' + esc(d.url) + '" target="_blank" rel="noopener" style="text-decoration:none"><i>▶</i><span>Open on ' + esc(d.platform) + (d.date ? " · " + esc(d.date) : "") + '</span></a>'
    : '<div class="vid"><i>▶</i><span>Video placeholder' + (d.date ? " · " + esc(d.date) : "") + '</span></div>';
  h += '<p style="margin:10px 0 0"><b>' + esc(d.handle || "unknown creator") + '</b> · ' + esc(d.platform || "—") +
    '<br><small>' + esc(d.views || "?") + ' views · ' + esc(d.likes || d.shares || "?") + (d.likes ? ' likes' : ' shares') + '</small></p>' +
    (d.caption ? '<p class="mu" style="overflow-wrap:anywhere">' + esc(d.caption) + '</p>' : '');
  if (c.language && c.language !== "en") {
    h += '<p><span class="alert">Translation needed</span> <small>' + esc(c.language) + '</small></p>';
  }
  h += '<details open><summary>Transcript</summary><p><mark>' + esc(c.evidence.quote || "(no transcript captured)") + '</mark></p>';
  if (c.evidence.quote_en) h += '<p class="mu">English: ' + esc(c.evidence.quote_en) + '</p>';
  if (d.transcript) h += '<p class="mu" style="white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px">' + esc(d.transcript) + '</p>';
  h += '</details>';
  h += srPanel(c);
  h += '</div>';

  h += '<div class="card"><div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap"><h3>AI draft</h3>' +
    '<span><span class="meter" role="img" aria-label="AI confidence"><i style="width:' + Math.round(c.confidence * 100) + '%"></i></span> ' +
    Math.round(c.confidence * 100) + '%' + (lowConf ? ' <span class="alert">Needs human review</span>' : '') + '</span></div>';

  if (lowConf) h += '<p class="alert" style="margin-top:10px;white-space:normal">We’re not sure where this is. Confirm the location before routing.</p>';

  h += fld("Type", '<div class="seg">' + typeSeg + '</div>', "ai");
  h += fld("Summary", '<div class="ed">' + esc(c.summary) + '</div>', "ai");
  h += fld("Agency", '<div class="ed">' + esc(agencyName) + ' <small>(likely)</small></div>', "ai");
  h += fld("Location", '<div class="ed">' + locationText + boroughText + '</div><small>Location confidence: <b>' + Math.round(c.location.confidence * 100) + '%</b></small>', "ai");

  if (c.type === "idea") {
    h += fld("Who benefits", '<div class="ed">' + esc(d.who_benefits || "—") + '</div>', "ai");
    h += fld("Others saying this", '<div class="ed">' + esc(d.echo || "No others yet") + '</div>', "ai");
  } else if (c.type === "issue") {
    h += fld("Urgency", '<div class="ed">' + esc(typeLabel(c.urgency)) + (d.safety_flag ? ' &nbsp;<span class="alert">⚑ Safety risk</span>' : '') + '</div>', "ai");
  }

  h += fld("Language", '<div class="ed">' + esc(c.language) + (c.language !== "en" ? ' · translation needed' : ' · no translation needed') + '</div>', "ai");
  h += fld("Suggested reply", '<div class="ed" id="replyText" contenteditable="true">' + esc(d.suggested_reply || "") + '</div><small>Edit before you send.</small>', "ai");

  h += '<h3 style="margin:18px 0 0">Your decision</h3>';
  h += fld("Priority", '<div class="seg" id="prioritySeg">' + prioritySeg + '</div>');
  h += fld("Assign to", '<div class="st" contenteditable="true" id="agencyText">' + esc(draft.final_agency || "No agency needed") + '</div>');
  h += fld("Status", '<div class="seg" id="statusSeg">' + statusSeg + '</div>');
  h += fld("Notes", '<div class="st" contenteditable="true" id="notesText" data-placeholder="Add a note for your team…">' + esc(draft.reviewer_notes) + '</div>');

  h += '<p id="saveMsg" class="mu" style="min-height:1.2em">' + esc(draft._saveMessage || "") + '</p>';
  h += '<div class="acts"><button class="btn" id="saveBtn">Save to tracker</button>' +
    '<button class="btn o" id="routeBtn">Route to agency</button>' +
    '<button class="btn d" id="declineBtn">Decline</button></div></div></div>';

  $("rv").innerHTML = h;
  wireSrPanel(c);

  $("rv").querySelectorAll('[data-set]').forEach(function (el) {
    el.onclick = function () {
      draft[el.dataset.set] = el.dataset.val;
      if (el.dataset.set === "type") c.type = el.dataset.val;
      paintReview(c, draft);
    };
  });

  function collect() {
    draft.final_agency = $("agencyText").textContent.trim();
    draft.reviewer_notes = $("notesText").textContent.trim();
  }

  function save(nextStatus) {
    collect();
    if (nextStatus) draft.status = nextStatus;
    $("saveMsg").textContent = "Saving…";
    api.saveCase(c.id, {
      type: draft.type,
      final_priority: draft.final_priority,
      final_agency: draft.final_agency,
      status: draft.status,
      reviewer_notes: draft.reviewer_notes,
    }).then(function () {
      draft._saveMessage = "Saved.";
      paintReview(c, draft);
    }).catch(function (err) {
      $("saveMsg").innerHTML = '<span class="alert">Couldn’t save: ' + esc(err.message) + '</span>';
    });
  }

  $("saveBtn").onclick = function () { save(); };
  $("routeBtn").onclick = function () { save("reviewed"); };
  $("declineBtn").onclick = function () { save("rejected"); };
}

// ======================= 311 DRAFT (in Case review) =====================
var PORTAL_311 = "https://portal.311.nyc.gov/";
function srText(sr) {
  return "Complaint type: " + sr.complaint_type + "\nDescriptor: " + sr.descriptor + "\nAgency: " + sr.agency +
    "\nLocation: " + (sr.address || "Unknown") + "\n\n" + sr.description;
}
function srPanel(c) {
  var sr = c.service_request;
  if (!sr) {
    return '<div class="card sr" style="margin-top:14px"><h3>311 request</h3><p class="mu">' +
      esc((c.display && c.display.note) || "No 311 drafted for this case.") + '</p></div>';
  }
  var routes = (sr.routing || []).map(function (r) {
    return '<tr><td>' + esc(r.role.replace(/_/g, " ")) + '</td><td><b>' + esc(r.name) + '</b><br><small>' + esc(r.detail) + '</small></td><td><small>' + esc(r.why) + '</small></td></tr>';
  }).join("");
  return '<div class="card sr" style="margin-top:14px">' +
    '<div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap"><h3>311 draft</h3><span class="tag ' + (sr.status === "draft" ? "ai" : "staff") + '">' + esc(typeLabel(sr.status)) + (sr.sr_number ? " · " + esc(sr.sr_number) : "") + '</span></div>' +
    fld("Complaint type", '<div class="ed">' + esc(sr.complaint_type) + ' — ' + esc(sr.descriptor) + '</div>', "ai") +
    fld("Agency", '<div class="ed">' + esc(sr.agency) + '</div>', "ai") +
    fld("Location", '<div class="ed">' + esc(sr.address || "Unknown — needs a human") + '</div><small>' + esc(sr.community_board || "No community board found") + (sr.council_district ? " · Council District " + sr.council_district : "") + '</small>', "ai") +
    '<details open><summary>Description to paste into 311</summary><pre>' + esc(sr.description) + '</pre></details>' +
    '<details open><summary>Route to</summary><div class="tw"><table class="rt"><thead><tr><th>Role</th><th>Who</th><th>Why</th></tr></thead><tbody>' + routes + '</tbody></table></div></details>' +
    '<p id="srMsg" class="mu" style="min-height:1.2em"></p>' +
    '<div class="acts"><button class="btn o" id="srCopy">Copy 311 text</button><a class="btn o" style="text-decoration:none" href="' + PORTAL_311 + '" target="_blank" rel="noopener">Open 311 portal ↗</a>' +
    '<button class="btn o" data-sr="approved">Approve</button><button class="btn" data-sr="filed">Mark filed…</button><button class="btn d" data-sr="declined">Decline</button></div></div>';
}
function wireSrPanel(c) {
  var sr = c.service_request;
  if (!sr) return;
  $("srCopy").onclick = function () {
    navigator.clipboard.writeText(srText(sr)).then(function () { $("srMsg").textContent = "Copied — paste it into the 311 portal."; });
  };
  $("rv").querySelectorAll("[data-sr]").forEach(function (b) {
    b.onclick = function () {
      var patch = { status: b.dataset.sr };
      if (patch.status === "filed") {
        var n = prompt("311 SR number from the portal confirmation:");
        if (n === null) return;
        patch.sr_number = n.trim();
      }
      $("srMsg").textContent = "Saving…";
      api.updateServiceRequest(sr.id, patch).then(function () { renderReview(c.id); })
        .catch(function (err) { $("srMsg").innerHTML = '<span class="alert">Couldn’t save: ' + esc(err.message) + '</span>'; });
    };
  });
}

// ======================= HOME ============================================
var PAGE_RENDERERS = {};
var NOW = function () { return SNAPSHOT ? new Date(SNAPSHOT.exported_at).getTime() : Date.now(); }; // sentiment / ome1 / ome2 register here (see insights section)
var TOPIC_LABEL = function (t) { return t ? t.replace(/_/g, " ").replace(/^./, function (c) { return c.toUpperCase(); }) : "Other"; };

function renderHome() {
  api.getVideos(7).then(function (res) {
    var vs = res.videos;
    var outside = function (v) { return v.relevance === "outside_nyc" || /^Outside NYC/.test((v.observation && v.observation.note) || ""); };
    var fix = vs.filter(function (v) { return v.relevance === "fix_request" && !outside(v); });
    var srs = vs.filter(function (v) { return v.service_request; });
    var views = vs.reduce(function (s, v) { return s + (v.views || 0); }, 0);
    $("homeStats").innerHTML = [
      [vs.length, "videos"], [fix.length, "NYC fix requests"], [srs.length, "311 drafts"],
    ].map(function (x) { return '<div><b>' + x[0] + '</b><span>' + x[1] + '</span></div>'; }).join("");
    $("bb311").textContent = srs.length + " draft service requests and where to route them";

    var top = fix.slice().sort(function (a, b) { return (b.views || 0) - (a.views || 0); }).slice(0, 8);
    $("homeGrid").innerHTML = top.map(function (v) {
      var o = v.observation || {};
      var go311 = v.service_request ? ' onclick="go(\'review\',\'' + o.id + '\');return false"' : "";
      var href = v.service_request ? "#" : esc(v.url || "#");
      return '<a class="vcard" href="' + href + '"' + (go311 || ' target="_blank" rel="noopener"') + '>' +
        '<div class="vthumb">' + (v.thumbnail_url ? '<img alt="" src="' + esc(v.thumbnail_url) + '" onerror="this.remove()">' : '') +
        (o.topic && o.topic !== "other" ? '<span class="topic">' + esc(TOPIC_LABEL(o.topic)) + '</span>' : '') +
        '<span class="views">' + _fmtCount(v.views) + ' views</span></div>' +
        '<div class="vbody"><p>' + esc((o.quote || v.caption || "").replace(/^\[keyword draft — needs review\]\s*/, "")) + '</p>' +
        '<small>@' + esc(v.handle || "unknown") + (v.service_request ? ' · 311 draft' : '') + '</small></div></a>';
    }).join("") || '<p class="mu">No fix requests in the last week yet.</p>';

    var days = [], perDay = {};
    for (var i = 6; i >= 0; i--) { var d = new Date(NOW() - i * 864e5); days.push([d.toLocaleDateString(undefined, { weekday: "short", day: "numeric" }), d.toDateString()]); }
    vs.forEach(function (v) { if (v.posted_at) { var k = new Date(v.posted_at).toDateString(); perDay[k] = (perDay[k] || 0) + 1; } });

  }).catch(function (err) {
    $("homeGrid").innerHTML = '<p class="alert">Couldn’t load videos: ' + esc(err.message) + '</p>';
  });
}

// ======================= INSIGHT PAGES ===================================
var pct = function (x) { return Math.round((x || 0) * 100) + "%"; };
var themeLabels = {};
function themeName(id) { return themeLabels[id] || TOPIC_LABEL(id); }
function quoteCard(c, extra) {
  var q = (c.quote || "").replace(/^\[keyword draft — needs review\]\s*/, "");
  return '<div class="q"><blockquote>“' + esc(q.length > 260 ? q.slice(0, 257) + "…" : q) + '”</blockquote><small>@' + esc(c.handle || "unknown") +
    ' · ' + _fmtCount(c.views) + ' views' + (extra ? ' · ' + extra : '') + (c.url ? ' · <a href="' + esc(c.url) + '" target="_blank" rel="noopener">watch ↗</a>' : '') + '</small></div>';
}
function quotes(list, n, extraFn) { return '<div class="qs">' + (list || []).slice(0, n || 3).map(function (c) { return quoteCard(c, extraFn && extraFn(c)); }).join("") + '</div>'; }
function toneSplit(t) {
  var tot = Math.max(1, t.n), seg = function (k, cls) { return '<i class="' + cls + '" style="width:' + (t[k] / tot * 100) + '%;background:var(--c)"></i>'; };
  return '<div class="split">' + seg("positive", "t-pos") + seg("neutral", "t-neu") + seg("mixed", "t-mix") + seg("negative", "t-neg") + '</div>' +
    '<div class="legend"><span class="t-pos">Positive ' + pct(t.positive / tot) + '</span><span class="t-neu">Neutral ' + pct(t.neutral / tot) + '</span><span class="t-mix">Mixed ' + pct(t.mixed / tot) + '</span><span class="t-neg">Negative ' + pct(t.negative / tot) + '</span></div>';
}
function diverging(items) {
  var max = Math.max.apply(null, [0.2].concat(items.map(function (x) { return Math.abs(x.mean); })));
  return items.map(function (x) {
    var w = Math.abs(x.mean) / max * 50, left = x.mean >= 0 ? 50 : 50 - w;
    return '<div class="diverge"><span>' + esc(x.label) + ' <small class="mu">(' + x.n + ')</small></span><div class="track"><i style="left:' + left + '%;width:' + w + '%;background:' + (x.mean >= 0 ? "var(--brand-blue)" : "var(--brand-orange)") + '"></i></div><em>' + (x.mean > 0 ? "+" : "") + x.mean.toFixed(2) + '</em></div>';
  }).join("");
}
function insightPage(bodyId, paint) {
  return function () {
    var el = $(bodyId);
    if (!el.dataset.done) el.innerHTML = '<p class="mu"><span class="spin" role="img" aria-label="Loading"></span> Reading transcripts…</p>';
    api.getInsights().then(function (d) {
      (d.sentiment && d.sentiment.by_theme || []).forEach(function (t) { themeLabels[t.theme] = t.label; });
      el.innerHTML = paint(d) + '<p class="foot">Based on ' + d.meta.records + ' public videos (' + esc((d.meta.from || "").slice(0, 10)) + ' to ' + esc((d.meta.to || "").slice(0, 10)) +
        '), found through a handful of hashtags, so not a representative sample of New Yorkers. All labels come from keyword rules and statistics, not AI; read the quotes before acting.</p>';
      el.dataset.done = "1";
    }).catch(function (err) { el.innerHTML = '<p class="alert">Couldn’t load the analysis: ' + esc(err.message) + '</p>'; });
  };
}

PAGE_RENDERERS.sentiment = insightPage("sentimentBody", function (d) {
  var s = d.sentiment, o = s.overall;
  var regs = s.registers.slice().sort(function (a, b) { return b.count - a.count; });
  var themes = s.by_theme.filter(function (t) { return t.n >= 4; }).sort(function (a, b) { return b.mean - a.mean; });
  return '<div class="kicker"><div><b>' + pct(o.positive / o.n) + '</b><span>of videos read as positive</span></div><div><b>' + pct(o.negative / o.n) + '</b><span>read as negative</span></div><div><b>' + esc(regs[0] ? regs[0].label.split(" ")[0] : "—") + '</b><span>is the most common feeling</span></div></div>' +
    '<div class="blk"><h2>Overall tone</h2><p class="sub">All ' + o.n + ' videos, then just the ' + s.asks.n + ' that ask for something to be fixed.</p>' + toneSplit(o) +
    '<div style="height:18px"></div><b style="font-size:14px">Fix requests only</b>' + toneSplit(s.asks) + '</div>' +
    '<div class="blk"><h2>How people feel</h2><p class="sub">Each video can carry more than one feeling. Share of all videos, with what people actually said.</p><div class="rows">' +
    regs.map(function (r) { return '<div class="row"><b>' + esc(r.label) + '</b><span class="r">' + r.count + ' videos · ' + pct(r.share) + '</span><div class="full">' + quotes(r.quotes, 2) + '</div></div>'; }).join("") + '</div></div>' +
    '<div class="blk"><h2>Tone by topic</h2><p class="sub">Average score from −1 (negative) to +1 (positive). Topics with at least 4 videos.</p>' + diverging(themes) + '</div>' +
    '<div class="blk"><h2>Most negative</h2>' + quotes(s.most_negative, 3) + '</div>' +
    '<div class="blk"><h2>Most positive</h2>' + quotes(s.most_positive, 3) + '</div>' +
    '<p class="foot">' + esc(s.method) + ' ' + esc(s.caveat) + '</p>';
});

PAGE_RENDERERS.ome1 = insightPage("ome1Body", function (d) {
  var b = d.blind_spots, m = b.summary;
  return '<div class="kicker"><div><b>' + pct(m.share_not_routable) + '</b><span>of ' + m.nyc_asks + ' NYC requests have no 311 draft path</span></div><div><b>' + m.tried_official_channels + '</b><span>say they already tried 311 or their board</span></div><div><b>' + m.quiet_but_serious + '</b><span>serious requests almost nobody saw</span></div></div>' +
    '<div class="blk"><h2>Why requests fall through</h2><div class="rows">' + b.gaps.map(function (g) {
      return '<div class="row"><b>' + esc(g.label) + '</b><span class="r">' + g.count + ' requests</span><p class="full">' + esc(g.why_it_matters) + '</p><div class="full">' + quotes(g.items, 2) + '</div></div>';
    }).join("") + '</div></div>' +
    '<div class="blk"><h2>They already tried official channels</h2><p class="sub">Residents who say 311 or their community board didn’t work.</p>' + quotes(b.tried_official_channels, 3) + '</div>' +
    '<div class="blk"><h2>Quiet but serious</h2><p class="sub">Safety or health language, low view counts. Easy to miss if you only follow what goes viral.</p>' + quotes(b.quiet_but_serious, 6, function (c) { return esc(c.severity_why || ""); }) + '</div>' +
    '<div class="blk"><h2>Topics without a clear 311 route</h2><div class="rows">' + b.unmet_themes.filter(function (t) { return t.asks > 0; }).map(function (t) {
      return '<div class="row"><b>' + esc(t.label) + '</b><span class="r">' + t.asks + ' requests · ' + _fmtCount(t.views) + ' views</span><p class="full">' + esc(t.route_hint || "") + '</p></div>';
    }).join("") + '</div></div>';
});

PAGE_RENDERERS.ome2 = insightPage("ome2Body", function (d) {
  var e = d.engagement_plan;
  var known = Object.entries(e.boroughs).filter(function (x) { return x[0] !== "Unknown"; }).sort(function (a, b) { return b[1] - a[1]; });
  var kinds = { unanswered_ask: "Reply & route", amplify_fix: "Amplify a fix", claim_check: "Check a claim", narrative: "Join the story" };
  return '<div class="blk"><h2>Places to visit</h2><p class="sub">Where residents name a place. ' + (e.boroughs.Unknown || 0) + ' requests name no place at all.</p><div class="rows">' + e.show_up.map(function (p) {
      return '<div class="row"><b>' + esc(p.place) + (p.place !== p.borough && p.borough ? ' <small class="mu">' + esc(p.borough) + '</small>' : '') + '</b><span class="r">' + p.asks + ' requests · ' + _fmtCount(p.views) + ' views</span>' +
        '<p class="full">' + (p.themes || []).map(themeName).map(esc).join(" · ") + '</p><div class="full">' + quotes(p.examples, 2) + '</div></div>';
    }).join("") + '</div></div>' +
    '<div class="blk"><h2>Worth a public reply</h2><p class="sub">Ranked by reach and whether anyone has answered.</p><div class="rows">' + e.respond_publicly.slice(0, 8).map(function (r) {
      var body = r.kind === "narrative" ? '<b class="full">' + esc(r.label) + '</b><div class="full">' + quotes(r.examples, 2) + '</div>' : '<div class="full">' + quoteCard(r) + '</div>';
      return '<div class="row"><span class="full"><span class="kind ' + esc(r.kind) + '">' + esc(kinds[r.kind] || r.kind) + '</span><span class="mu" style="font-size:14px">' + esc(r.reason) + '</span></span>' + body + '</div>';
    }).join("") + '</div></div>' +
    '<div class="blk"><h2>Who is speaking up</h2><p class="sub">Based on what videos mention (e.g. kids, school, a neighborhood), never on who a person is.</p><div class="rows">' + e.communities.slice(0, 8).map(function (c) {
      return '<div class="row"><b>' + esc(c.community) + '</b><span class="r">' + c.videos + ' videos · tone ' + (c.mean_tone > 0 ? "+" : "") + c.mean_tone.toFixed(2) + '</span><p class="full">' + (c.top_themes || []).map(esc).join(" · ") + '</p></div>';
    }).join("") + '</div></div>' +
    (e.events.length ? '<div class="blk"><h2>Events people are talking about</h2>' + quotes(e.events, 3, function (c) { return esc((c.dates_mentioned || []).join(", ")); }) + '</div>' : '') +
    '<div class="blk"><h2>Languages</h2><p class="sub">' + e.non_english_speech + ' videos with non-English speech out of ' + Object.values(e.languages).reduce(function (a, b) { return a + b; }, 0) + ' with speech. The hashtags searched were English, so this undercounts other-language posts; searching tags in Spanish, Chinese, Bengali and other languages is the next step.</p>' +
    (known.length ? '<p class="sub">Requests by borough: ' + known.map(function (k) { return esc(k[0]) + ' ' + k[1]; }).join(" · ") + '</p>' : '') + '</div>';
});

// ======================= THIS WEEK'S VIDEOS ==============================
var videoState = { days: 7, filter: "all", data: null };
var RELEVANCE = { fix_request: "Fix request", outside_nyc: "Outside NYC", mayor_related: "About the mayor", unrelated: "Unrelated", other: "Other" };

function hbars(el, entries) {
  var max = Math.max.apply(null, [1].concat(entries.map(function (e) { return e[1]; })));
  el.innerHTML = entries.length ? entries.map(function (e) {
    return '<div class="hb"><span title="' + esc(e[0]) + '">' + esc(e[0]) + '</span><i style="width:' + (e[1] / max * 100) + '%"></i><em>' + e[1] + '</em></div>';
  }).join("") : '<p class="mu">No data yet.</p>';
}
function tally(list, keyFn) {
  var m = {};
  list.forEach(function (x) { [].concat(keyFn(x) || []).forEach(function (k) { if (k) m[k] = (m[k] || 0) + 1; }); });
  return Object.entries(m).sort(function (a, b) { return b[1] - a[1]; });
}

function renderVideos() {
  $("vList").innerHTML = '<p class="mu"><span class="spin" role="img" aria-label="Loading"></span> Loading videos…</p>';
  api.getVideos(videoState.days).then(function (res) { videoState.data = res; paintVideos(); })
    .catch(function (err) { $("vList").innerHTML = '<p class="alert">Couldn’t load videos: ' + esc(err.message) + '</p>'; });
}

function paintVideos() {
  var vs = videoState.data.videos;
  var fix = vs.filter(function (v) { return v.relevance === "fix_request"; });
  var srs = vs.filter(function (v) { return v.service_request; });
  var views = vs.reduce(function (s, v) { return s + (v.views || 0); }, 0);
  $("vTiles").innerHTML = [
    ["Videos", vs.length, "last " + (videoState.days >= 365 ? "year" : videoState.days + " days")],
    ["Fix requests", fix.length, "residents asking for a fix"],
    ["311 drafts", srs.length, '<a href="#" onclick="go(\'inbox\');return false">Review in 311 cases →</a>'],
    ["Total views", _fmtCount(views), "across these videos"],
  ].map(function (t) { return '<div class="card tile"><small>' + t[0] + '</small><b>' + t[1] + '</b><small>' + t[2] + '</small></div>'; }).join("");

  var span = Math.min(videoState.days, 14), days = [];
  for (var i = span - 1; i >= 0; i--) {
    var d = new Date(NOW() - i * 864e5);
    days.push([d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }), d.toDateString()]);
  }
  var perDay = {};
  vs.forEach(function (v) { if (v.posted_at) { var k = new Date(v.posted_at).toDateString(); perDay[k] = (perDay[k] || 0) + 1; } });
  hbars($("vByDay"), days.map(function (d) { return [d[0], perDay[d[1]] || 0]; }));
  hbars($("vTags"), tally(vs, function (v) { return (v.hashtags || []).map(function (h) { return "#" + h; }); }).slice(0, 10));

  var filters = { all: ["All", function () { return true; }], fix_request: ["Fix requests", function (v) { return v.relevance === "fix_request"; }],
    sr: ["Has 311 draft", function (v) { return v.service_request; }], other: ["Everything else", function (v) { return v.relevance !== "fix_request"; }] };
  $("vFilters").innerHTML = Object.keys(filters).map(function (k) {
    return '<button class="pill" data-vf="' + k + '" aria-pressed="' + (k === videoState.filter) + '">' + filters[k][0] + ' (' + vs.filter(filters[k][1]).length + ')</button>';
  }).join("");
  $("vFilters").querySelectorAll("[data-vf]").forEach(function (b) { b.onclick = function () { videoState.filter = b.dataset.vf; paintVideos(); }; });

  var shown = vs.filter(filters[videoState.filter][1]);
  $("vList").innerHTML = shown.length ? shown.map(function (v) {
    var o = v.observation, sr = v.service_request;
    var when = v.posted_at ? new Date(v.posted_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "";
    var right = sr
      ? '<button class="btn o" onclick="go(\'review\',\'' + o.id + '\')">311: ' + esc(sr.complaint_type) + ' →</button>'
      : (o ? '<button class="btn d" onclick="go(\'review\',\'' + o.id + '\')">View case</button>' : '');
    return '<div class="vrow"><div>' +
      '<div class="vmeta"><b style="color:var(--tx)">@' + esc(v.handle || "unknown") + '</b><span>' + esc(v.platform) + '</span><span>' + esc(when) + '</span><span>' + _fmtCount(v.views) + ' views</span>' +
      '<span class="tag rel ' + esc(v.relevance) + '">' + esc(RELEVANCE[v.relevance] || v.relevance) + '</span>' + (v.url ? '<a href="' + esc(v.url) + '" target="_blank" rel="noopener">Open ↗</a>' : '') + '</div>' +
      '<p>' + esc(v.caption || "(no caption)") + '</p>' +
      (o && o.quote ? '<p class="quote">“' + esc(o.quote) + '”</p>' : '') +
      (o && o.note ? '<p class="mu" style="font-size:14px">' + esc(o.note) + '</p>' : '') +
      '</div><div>' + right + '</div></div>';
  }).join("") : '<p class="mu">No videos in this view.</p>';
}

document.querySelectorAll("#daysSeg span").forEach(function (el) {
  el.onclick = function () {
    videoState.days = Number(el.dataset.days);
    document.querySelectorAll("#daysSeg span").forEach(function (x) { x.classList.toggle("s", x === el); });
    renderVideos();
  };
});

// ======================= INBOX ==========================================
function renderInbox() {
  $("tb").innerHTML = '<tr><td colspan="9" class="mu">Loading cases&hellip;</td></tr>';
  api.getCases({}).then(function (res) {
    var obs = res.observations;
    var newCount = obs.length;
    var issues = obs.filter(function (o) { return o.type === "issue"; }).length;
    var ideas = obs.filter(function (o) { return o.type === "idea"; }).length;
    var other = obs.length - issues - ideas;
    var needsReview = obs.filter(function (o) { return o.location.needs_review; }).length;

    $("tileNew").textContent = newCount;
    $("tileSplit").textContent = issues + " · " + ideas;
    $("tileSplitSub").textContent = other + " other";
    $("tileReview").textContent = needsReview;
    var srs = obs.filter(function (o) { return o.service_request; });
    $("tileSR").textContent = srs.length;
    $("tileSRSub").textContent = srs.filter(function (o) { return o.service_request.status === "filed"; }).length + " filed";
    hbars($("routeSummary"), tally(srs, function (o) {
      return (o.service_request.routing || []).filter(function (r) { return r.kind !== "tagged" && r.kind !== "borough_president"; }).map(function (r) { return r.name; });
    }).slice(0, 10));

    $("tb").innerHTML = obs.map(function (c) {
      var agency = (c.agency_candidates[0] && c.agency_candidates[0].name) || "—";
      var urgency = c.urgency ? typeLabel(c.urgency) : "—";
      var priority = c.final_priority ? typeLabel(c.final_priority) : "—";
      var views = (c.display && c.display.views) || "—";
      return '<tr tabindex="0" data-id="' + c.id + '"><td>' + tag(c.type) + '</td><td>' + esc(c.summary) +
        (c.location.needs_review ? ' <span class="alert">Needs review</span>' : '') + '</td><td>' + esc(agency) +
        '</td><td>' + esc(c.location.borough || "Unclear") + '</td><td>' + esc(urgency) +
        (c.display && c.display.safety_flag ? ' ⚑' : '') + '</td><td>' + esc(priority) + '</td><td>' +
        esc(typeLabel(c.status)) + '</td><td>' + (c.service_request ? '<span class="tag ' + (c.service_request.status === "draft" ? "ai" : "staff") + '">' + esc(typeLabel(c.service_request.status)) + '</span>' : '<small>—</small>') +
        '</td><td>' + esc(views) + '</td></tr>';
    }).join("") || '<tr><td colspan="9" class="mu">No cases yet.</td></tr>';

    $("tb").querySelectorAll("tr[data-id]").forEach(function (row) {
      row.onclick = function () { go("review", row.dataset.id); };
      row.onkeydown = function (e) { if (e.key === "Enter") go("review", row.dataset.id); };
    });
  }).catch(function (err) {
    $("tb").innerHTML = '<tr><td colspan="9" class="alert">Couldn’t load cases: ' + esc(err.message) + '</td></tr>';
  });
}

// ======================= boot ===========================================
if (SNAPSHOT) {
  document.body.classList.add("snapshot");
  $("snapNote").textContent = "Snapshot of " + new Date(SNAPSHOT.exported_at).toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" }) + " · read-only";
}
renderIntakeState();
wireIntakeForm();
renderRecent();
go("home");
