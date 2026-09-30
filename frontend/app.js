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
  if (screen === "review") renderReview(id);
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

function fld(label, value, kind) {
  var badge = kind === "ai" ? ' <span class="tag ai">AI suggested</span>' : "";
  return '<div class="f"><label>' + label + badge + '</label><div>' + value + '</div></div>';
}

function renderReview(id) {
  $("rv").innerHTML = '<p class="mu"><span class="spin" role="img" aria-label="Loading"></span> Loading case&hellip;</p>';
  $("vars").innerHTML = "";

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

  var typeSeg = ["issue", "idea", "other"].map(function (t) {
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
  h += '<div class="vid"><i>▶</i><span>Video placeholder' + (d.date ? " · " + esc(d.date) : "") + '</span></div>';
  h += '<p style="margin:10px 0 0"><b>' + esc(d.handle || "unknown creator") + '</b> · ' + esc(d.platform || "—") +
    '<br><small>' + esc(d.views || "?") + ' views · ' + esc(d.shares || "?") + ' shares</small></p>';
  if (c.language && c.language !== "en") {
    h += '<p><span class="alert">Translation needed</span> <small>' + esc(c.language) + '</small></p>';
  }
  h += '<details open><summary>Transcript</summary><p><mark>' + esc(c.evidence.quote || "(no transcript captured)") + '</mark></p>';
  if (c.evidence.quote_en) h += '<p class="mu">English: ' + esc(c.evidence.quote_en) + '</p>';
  h += '</details></div>';

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

// ======================= INBOX ==========================================
function renderInbox() {
  $("tb").innerHTML = '<tr><td colspan="8" class="mu">Loading cases&hellip;</td></tr>';
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

    $("tb").innerHTML = obs.map(function (c) {
      var agency = (c.agency_candidates[0] && c.agency_candidates[0].name) || "—";
      var urgency = c.urgency ? typeLabel(c.urgency) : "—";
      var priority = c.final_priority ? typeLabel(c.final_priority) : "—";
      var views = (c.display && c.display.views) || "—";
      return '<tr tabindex="0" data-id="' + c.id + '"><td>' + tag(c.type) + '</td><td>' + esc(c.summary) +
        (c.location.needs_review ? ' <span class="alert">Needs review</span>' : '') + '</td><td>' + esc(agency) +
        '</td><td>' + esc(c.location.borough || "Unclear") + '</td><td>' + esc(urgency) +
        (c.display && c.display.safety_flag ? ' ⚑' : '') + '</td><td>' + esc(priority) + '</td><td>' +
        esc(typeLabel(c.status)) + '</td><td>' + esc(views) + '</td></tr>';
    }).join("") || '<tr><td colspan="8" class="mu">No cases yet.</td></tr>';

    $("tb").querySelectorAll("tr[data-id]").forEach(function (row) {
      row.onclick = function () { go("review", row.dataset.id); };
      row.onkeydown = function (e) { if (e.key === "Enter") go("review", row.dataset.id); };
    });
  }).catch(function (err) {
    $("tb").innerHTML = '<tr><td colspan="8" class="alert">Couldn’t load cases: ' + esc(err.message) + '</td></tr>';
  });
}

// ======================= boot ===========================================
renderIntakeState();
wireIntakeForm();
renderRecent();
go("intake");
