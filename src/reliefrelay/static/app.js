const scenarios = {
  flood: { label: "RIVERSIDE FLOOD", slug: "riverside-flood" },
  fire: { label: "NORTH CLINIC FIRE", slug: "north-clinic-fire" },
  medical: { label: "HARBOR SCHOOL MEDICAL", slug: "harbor-school-medical" },
};

let activeScenario = "flood";
let activeVariant = "radio";
let selectedAudioFile = null;
let pendingIncidentId = null;
let recorderState = null;
let previewObjectUrl = null;

const markerPositions = [[182, 302], [510, 145], [360, 228], [584, 330], [137, 124]];
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
})[character]);

function updateClock() {
  const value = new Intl.DateTimeFormat("en-US", {
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
    timeZone: "America/Chicago", timeZoneName: "short",
  }).format(new Date());
  document.querySelector("#clock").textContent = value;
}

function showToast(message) {
  const toast = document.querySelector("#toast");
  toast.textContent = message;
  toast.classList.add("visible");
  window.setTimeout(() => toast.classList.remove("visible"), 3200);
}

async function apiRequest(url, options = {}) {
  const token = window.sessionStorage.getItem("reliefrelay-token");
  const headers = new Headers(options.headers || {});
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(url, { ...options, headers });
  if (response.status === 401) {
    const supplied = window.prompt("Enter the ReliefRelay operator access token");
    if (supplied) {
      window.sessionStorage.setItem("reliefrelay-token", supplied);
      return apiRequest(url, options);
    }
  }
  if (!response.ok) {
    let detail = "Request failed";
    try { detail = (await response.json()).detail || detail; } catch (_) { /* no body */ }
    throw new Error(detail);
  }
  return response.status === 204 ? null : response.json();
}

async function loadHealth() {
  const health = await apiRequest("/api/health");
  const status = document.querySelector("#system-status");
  status.textContent = health.status.toUpperCase();
  status.classList.toggle("degraded", health.inference !== "ready");
  document.querySelector("#architecture").textContent = health.architecture.toUpperCase();
  if (health.inference !== "ready") {
    document.querySelector("#benchmark-status").textContent = "Whisper setup required";
  }
}

function renderIncidents(records) {
  const incidentList = document.querySelector("#incident-list");
  const mapMarkers = document.querySelector("#map-markers");
  const active = records.filter(({ status }) => !["resolved", "rejected"].includes(status));
  document.querySelector("#incident-total").textContent = String(active.length).padStart(2, "0");
  document.querySelector("#critical-total").textContent = String(
    active.filter(({ incident }) => incident.severity === "critical").length,
  ).padStart(2, "0");
  document.querySelector("#map-empty").hidden = active.length > 0;

  incidentList.innerHTML = records.length ? records.map(({ incident, report_count: count, status, assigned_to: assignee }) => `
    <article class="incident-card ${escapeHtml(incident.severity)} ${["resolved", "rejected"].includes(status) ? "closed" : ""}">
      <span class="severity-bar"></span>
      <div>
        <div class="card-flags"><span>${escapeHtml(status.replaceAll("_", " "))}</span>${incident.review_required ? "<b>REVIEW</b>" : ""}</div>
        <h3>${escapeHtml(incident.location)} · ${escapeHtml(incident.incident_type.toUpperCase())}</h3>
        <p>${escapeHtml(incident.transcript)}</p>
        <small>${assignee ? `Assigned to ${escapeHtml(assignee)}` : "Unassigned"}</small>
      </div>
      <div class="incident-meta">
        <strong>${escapeHtml(incident.severity)}</strong>
        <small>${count} report${count === 1 ? "" : "s"}</small>
        <button class="detail-action" type="button" data-incident-id="${escapeHtml(incident.id)}">OPEN</button>
      </div>
    </article>
  `).join("") : '<div class="queue-empty">No incidents in this view.</div>';

  mapMarkers.innerHTML = active.map(({ incident }, index) => {
    const [x, y] = markerPositions[index % markerPositions.length];
    return `<g class="map-marker ${escapeHtml(incident.severity)}" transform="translate(${x} ${y})">
      <circle class="pulse" r="16"></circle><circle r="6"></circle>
      <text x="14" y="4">${escapeHtml(incident.location.toUpperCase())}</text>
    </g>`;
  }).join("");
}

async function loadIncidents() {
  const includeClosed = document.querySelector("#include-closed").checked;
  const records = await apiRequest(`/api/incidents?include_closed=${includeClosed}`);
  renderIncidents(records);
}

function populateReview(result) {
  pendingIncidentId = result.incident.id;
  document.querySelector("#review-location").value = result.incident.location;
  document.querySelector("#review-type").value = result.incident.incident_type;
  document.querySelector("#review-severity").value = result.incident.severity;
  document.querySelector("#review-people").value = result.incident.people_affected ?? "";
  document.querySelector("#review-resource").value = result.incident.requested_resource ?? "";
  const warnings = result.assessment?.warnings || [];
  document.querySelector("#review-warnings").innerHTML = warnings.length
    ? warnings.map((warning) => `<span>⚠ ${escapeHtml(warning)}</span>`).join("")
    : "<span>Review all extracted fields before acknowledgement.</span>";
  document.querySelector("#review-form").hidden = false;
}

async function processReport() {
  const button = document.querySelector("#process-report");
  const audio = document.querySelector("#scenario-audio");
  const signalBadge = document.querySelector(".signal-badge");
  button.disabled = true;
  button.querySelector("span").textContent = "TRANSCRIBING LOCALLY";
  signalBadge.textContent = "PROCESSING";
  document.querySelector("#transcription-state").textContent = "Running whisper.cpp";
  document.querySelector("#review-form").hidden = true;
  try {
    let audioBlob;
    let filename;
    if (selectedAudioFile) {
      audioBlob = selectedAudioFile;
      filename = selectedAudioFile.name;
    } else {
      const audioResponse = await fetch(audio.getAttribute("src"));
      if (!audioResponse.ok) throw new Error("Audio fixture could not be loaded");
      audioBlob = await audioResponse.blob();
      filename = audio.getAttribute("src").split("/").pop();
    }
    const formData = new FormData();
    formData.append("audio", audioBlob, filename);
    const result = await apiRequest("/api/reports/audio", { method: "POST", body: formData });
    document.querySelector("#transcript").value = result.processing.text;
    document.querySelector("#inference-time").textContent = `${result.processing.inference_seconds.toFixed(2)} s`;
    document.querySelector("#audio-duration").textContent = `${result.processing.duration_seconds.toFixed(2)} s`;
    document.querySelector("#real-time-factor").textContent = `${result.processing.real_time_factor.toFixed(2)}×`;
    document.querySelector("#runtime-result").textContent = `${result.processing.runtime} · ${result.processing.architecture}`;
    document.querySelector("#processing-result").hidden = false;
    document.querySelector("#benchmark-status").textContent = `${result.processing.inference_seconds.toFixed(2)} s · ${result.processing.real_time_factor.toFixed(2)}× RTF`;
    document.querySelector("#architecture").textContent = result.processing.architecture.toUpperCase();
    document.querySelector("#transcription-state").textContent = `Complete · ${result.processing.inference_seconds.toFixed(2)} s`;
    document.querySelector("#extraction-state").textContent = `Draft · ${Math.round(result.assessment.confidence * 100)}% confidence`;
    document.querySelector("#routing-state").textContent = "Awaiting operator review";
    document.querySelectorAll(".pipeline-card li").forEach((step, index) => step.classList.toggle("complete", index < 3));
    populateReview(result);
    await loadIncidents();
    signalBadge.textContent = "REVIEW";
    showToast(`REPORT SAVED · OPERATOR REVIEW REQUIRED`);
  } catch (error) {
    signalBadge.textContent = "ERROR";
    document.querySelector("#transcription-state").textContent = "Runtime error";
    showToast(error.message);
  } finally {
    button.disabled = false;
    button.querySelector("span").textContent = "TRANSCRIBE + REVIEW REPORT";
  }
}

function resetPipeline() {
  pendingIncidentId = null;
  document.querySelector("#transcript").value = "";
  document.querySelector("#processing-result").hidden = true;
  document.querySelector("#review-form").hidden = true;
  document.querySelector(".signal-badge").textContent = "READY";
  document.querySelector("#voice-state").textContent = "Audio selected";
  document.querySelector("#transcription-state").textContent = "Waiting for audio";
  document.querySelector("#extraction-state").textContent = "Waiting for transcript";
  document.querySelector("#routing-state").textContent = "Waiting for review";
  document.querySelectorAll(".pipeline-card li").forEach((step, index) => step.classList.toggle("complete", index === 0));
}

function selectFixture() {
  selectedAudioFile = null;
  document.querySelector("#audio-upload").value = "";
  const scenario = scenarios[activeScenario];
  const audio = document.querySelector("#scenario-audio");
  document.querySelector("#audio-label").textContent = `${scenario.label} · ${activeVariant.toUpperCase()}`;
  audio.src = `/audio/${scenario.slug}-${activeVariant}.wav`;
  audio.load();
  document.querySelector("#input-source").textContent = "Using synthetic radio fixture";
  resetPipeline();
}

function setSelectedFile(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".wav")) {
    showToast("Please choose a WAV recording");
    return;
  }
  selectedAudioFile = file;
  if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl);
  previewObjectUrl = URL.createObjectURL(file);
  const audio = document.querySelector("#scenario-audio");
  audio.src = previewObjectUrl;
  audio.load();
  document.querySelector("#audio-label").textContent = file.name.toUpperCase();
  document.querySelector("#input-source").textContent = `Using local recording · ${file.name}`;
  resetPipeline();
}

function encodeWav(chunks, sampleRate) {
  const length = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const buffer = new ArrayBuffer(44 + length * 2);
  const view = new DataView(buffer);
  const write = (offset, text) => [...text].forEach((character, index) => view.setUint8(offset + index, character.charCodeAt(0)));
  write(0, "RIFF"); view.setUint32(4, 36 + length * 2, true); write(8, "WAVE");
  write(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
  view.setUint16(22, 1, true); view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); view.setUint16(32, 2, true);
  view.setUint16(34, 16, true); write(36, "data"); view.setUint32(40, length * 2, true);
  let offset = 44;
  chunks.forEach((chunk) => chunk.forEach((sample) => {
    const clipped = Math.max(-1, Math.min(1, sample));
    view.setInt16(offset, clipped < 0 ? clipped * 0x8000 : clipped * 0x7fff, true);
    offset += 2;
  }));
  return new Blob([buffer], { type: "audio/wav" });
}

async function toggleRecording() {
  const button = document.querySelector("#record-audio");
  if (recorderState) {
    recorderState.processor.disconnect();
    recorderState.source.disconnect();
    recorderState.stream.getTracks().forEach((track) => track.stop());
    await recorderState.context.close();
    const blob = encodeWav(recorderState.chunks, recorderState.sampleRate);
    const file = new File([blob], `field-report-${Date.now()}.wav`, { type: "audio/wav" });
    recorderState = null;
    button.textContent = "● START MICROPHONE RECORDING";
    button.classList.remove("recording");
    setSelectedFile(file);
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const context = new AudioContext();
    const source = context.createMediaStreamSource(stream);
    const processor = context.createScriptProcessor(4096, 1, 1);
    const chunks = [];
    processor.onaudioprocess = (event) => chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
    source.connect(processor);
    processor.connect(context.destination);
    recorderState = { stream, context, source, processor, chunks, sampleRate: context.sampleRate };
    button.textContent = "■ STOP + USE RECORDING";
    button.classList.add("recording");
    document.querySelector("#input-source").textContent = "Recording microphone…";
  } catch (error) {
    showToast(`Microphone unavailable: ${error.message}`);
  }
}

async function confirmReview(event) {
  event.preventDefault();
  if (!pendingIncidentId) return;
  const assignee = document.querySelector("#review-assignee").value.trim();
  const people = document.querySelector("#review-people").value;
  const body = {
    status: assignee ? "assigned" : "acknowledged",
    actor: "dashboard-operator",
    assigned_to: assignee,
    transcript: document.querySelector("#transcript").value.trim(),
    location: document.querySelector("#review-location").value.trim(),
    incident_type: document.querySelector("#review-type").value.trim(),
    severity: document.querySelector("#review-severity").value,
    people_affected: people === "" ? null : Number(people),
    requested_resource: document.querySelector("#review-resource").value.trim() || null,
  };
  try {
    await apiRequest(`/api/incidents/${pendingIncidentId}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    document.querySelector("#review-form").hidden = true;
    document.querySelector("#routing-state").textContent = assignee ? "Assigned for dispatch" : "Operator acknowledged";
    document.querySelectorAll(".pipeline-card li").forEach((step) => step.classList.add("complete"));
    document.querySelector(".signal-badge").textContent = "CONFIRMED";
    showToast(assignee ? `INCIDENT ASSIGNED TO ${assignee.toUpperCase()}` : "INCIDENT ACKNOWLEDGED");
    await loadIncidents();
  } catch (error) { showToast(error.message); }
}

async function openIncident(incidentId) {
  try {
    const record = await apiRequest(`/api/incidents/${incidentId}`);
    const incident = record.incident;
    const detail = document.querySelector("#incident-detail");
    detail.innerHTML = `
      <span class="eyebrow">INCIDENT DETAIL</span>
      <h2>${escapeHtml(incident.location)} · ${escapeHtml(incident.incident_type)}</h2>
      <p>${escapeHtml(incident.transcript)}</p>
      <div class="detail-metrics"><span><small>Severity</small>${escapeHtml(incident.severity)}</span><span><small>Reports</small>${record.report_count}</span><span><small>Confidence</small>${Math.round(incident.extraction_confidence * 100)}%</span></div>
      <form id="detail-workflow" data-id="${escapeHtml(incident.id)}">
        <label>Status<select id="detail-status">${["needs_review", "acknowledged", "assigned", "dispatched", "resolved", "rejected"].map((value) => `<option value="${value}" ${record.status === value ? "selected" : ""}>${value.replaceAll("_", " ")}</option>`).join("")}</select></label>
        <label>Assigned to<input id="detail-assignee" value="${escapeHtml(record.assigned_to || "")}" maxlength="120"></label>
        <button class="confirm-action" type="submit">SAVE WORKFLOW</button>
      </form>
      <h3>Report history</h3>
      <div class="history-list">${record.reports.map((report) => `<article><b>${escapeHtml(report.source)} · ${report.pending_review ? "REVIEW PENDING" : `REVIEWED BY ${escapeHtml(report.reviewed_by || "OPERATOR")}`}</b><time>${new Date(report.created_at).toLocaleString()}</time><p>${escapeHtml(report.transcript)}</p></article>`).join("")}</div>
      <h3>Audit trail</h3>
      <div class="audit-list">${record.audit_events.map((event) => `<span>${new Date(event.created_at).toLocaleString()} · ${escapeHtml(event.actor)} · ${escapeHtml(event.action)}</span>`).join("")}</div>`;
    document.querySelector("#incident-dialog").showModal();
  } catch (error) { showToast(error.message); }
}

async function saveWorkflow(event) {
  if (event.target.id !== "detail-workflow") return;
  event.preventDefault();
  const incidentId = event.target.dataset.id;
  try {
    await apiRequest(`/api/incidents/${incidentId}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        status: document.querySelector("#detail-status").value,
        assigned_to: document.querySelector("#detail-assignee").value.trim(),
        actor: "dashboard-operator",
      }),
    });
    document.querySelector("#incident-dialog").close();
    showToast("INCIDENT WORKFLOW UPDATED");
    await loadIncidents();
  } catch (error) { showToast(error.message); }
}

document.querySelector("#process-report").addEventListener("click", processReport);
document.querySelector("#audio-upload").addEventListener("change", (event) => setSelectedFile(event.target.files[0]));
document.querySelector("#record-audio").addEventListener("click", toggleRecording);
document.querySelector("#review-form").addEventListener("submit", confirmReview);
document.querySelector("#include-closed").addEventListener("change", loadIncidents);
document.querySelector("#incident-list").addEventListener("click", (event) => {
  const button = event.target.closest("[data-incident-id]");
  if (button) openIncident(button.dataset.incidentId);
});
document.querySelector("#incident-detail").addEventListener("submit", saveWorkflow);
document.querySelector("#close-dialog").addEventListener("click", () => document.querySelector("#incident-dialog").close());
document.querySelectorAll("[data-scenario]").forEach((button) => button.addEventListener("click", () => {
  activeScenario = button.dataset.scenario;
  document.querySelectorAll("[data-scenario]").forEach((candidate) => {
    const selected = candidate === button;
    candidate.classList.toggle("selected", selected);
    candidate.setAttribute("aria-pressed", String(selected));
  });
  selectFixture();
}));
document.querySelectorAll("[data-variant]").forEach((button) => button.addEventListener("click", () => {
  activeVariant = button.dataset.variant;
  document.querySelectorAll("[data-variant]").forEach((candidate) => candidate.setAttribute("aria-pressed", String(candidate === button)));
  selectFixture();
}));

updateClock();
window.setInterval(updateClock, 1000);
window.setInterval(() => loadIncidents().catch(() => {}), 5000);
Promise.all([loadHealth(), loadIncidents()]).catch(() => {
  document.querySelector("#system-status").textContent = "OFFLINE";
});
