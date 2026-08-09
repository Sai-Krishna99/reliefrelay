const scenarios = {
  flood: {
    label: "RIVERSIDE FLOOD",
    slug: "riverside-flood",
  },
  fire: {
    label: "NORTH CLINIC FIRE",
    slug: "north-clinic-fire",
  },
  medical: {
    label: "HARBOR SCHOOL MEDICAL",
    slug: "harbor-school-medical",
  },
};

let activeScenario = "flood";
let activeVariant = "radio";

const markerPositions = [
  [182, 302],
  [510, 145],
  [360, 228],
  [584, 330],
  [137, 124],
];

const escapeHtml = (value) => value.replace(/[&<>'"]/g, (character) => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  "'": "&#39;",
  '"': "&quot;",
})[character]);

function updateClock() {
  const time = new Intl.DateTimeFormat("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "America/Chicago",
  }).format(new Date());
  document.querySelector("#clock").textContent = `${time} CDT`;
}

function showToast(message) {
  const toast = document.querySelector("#toast");
  toast.textContent = message;
  toast.classList.add("visible");
  window.setTimeout(() => toast.classList.remove("visible"), 2400);
}

async function loadHealth() {
  const response = await fetch("/api/health");
  const health = await response.json();
  document.querySelector("#system-status").textContent = health.status.toUpperCase();
  document.querySelector("#architecture").textContent = health.architecture.toUpperCase();
}

function renderIncidents(records) {
  const incidentList = document.querySelector("#incident-list");
  const mapMarkers = document.querySelector("#map-markers");
  document.querySelector("#incident-total").textContent = String(records.length).padStart(2, "0");
  document.querySelector("#critical-total").textContent = String(
    records.filter(({ incident }) => incident.severity === "critical").length,
  ).padStart(2, "0");

  document.querySelector("#map-empty").hidden = records.length > 0;
  incidentList.innerHTML = records.map(({ incident, report_count: reportCount }) => `
    <article class="incident-card ${incident.severity}">
      <span class="severity-bar"></span>
      <div>
        <h3>${escapeHtml(incident.location)} · ${escapeHtml(incident.incident_type.toUpperCase())}</h3>
        <p>${escapeHtml(incident.transcript)}</p>
      </div>
      <div class="incident-meta">
        <strong>${escapeHtml(incident.severity)}</strong>
        <small>${reportCount} report${reportCount === 1 ? "" : "s"}</small>
      </div>
    </article>
  `).join("");

  mapMarkers.innerHTML = records.map(({ incident }, index) => {
    const [x, y] = markerPositions[index % markerPositions.length];
    return `
      <g class="map-marker ${incident.severity}" transform="translate(${x} ${y})">
        <circle class="pulse" r="16"></circle>
        <circle r="6"></circle>
        <text x="14" y="4">${escapeHtml(incident.location.toUpperCase())}</text>
      </g>
    `;
  }).join("");
}

async function loadIncidents() {
  const response = await fetch("/api/incidents");
  renderIncidents(await response.json());
}

async function processReport() {
  const button = document.querySelector("#process-report");
  const audio = document.querySelector("#scenario-audio");
  const signalBadge = document.querySelector(".signal-badge");

  button.disabled = true;
  button.querySelector("span").textContent = "TRANSCRIBING LOCALLY";
  signalBadge.textContent = "PROCESSING";
  document.querySelector("#transcription-state").textContent = "Running whisper.cpp";
  try {
    const audioResponse = await fetch(audio.getAttribute("src"));
    if (!audioResponse.ok) throw new Error("Audio fixture could not be loaded");
    const audioBlob = await audioResponse.blob();
    const filename = audio.getAttribute("src").split("/").pop();
    const formData = new FormData();
    formData.append("audio", audioBlob, filename);

    const response = await fetch("/api/reports/audio", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Report processing failed");
    }
    const result = await response.json();
    document.querySelector("#transcript").value = result.processing.text;
    document.querySelector("#inference-time").textContent = `${result.processing.inference_seconds.toFixed(2)} s`;
    document.querySelector("#audio-duration").textContent = `${result.processing.duration_seconds.toFixed(2)} s`;
    document.querySelector("#real-time-factor").textContent = `${result.processing.real_time_factor.toFixed(2)}×`;
    document.querySelector("#runtime-result").textContent = `${result.processing.runtime} · ${result.processing.architecture}`;
    document.querySelector("#processing-result").hidden = false;
    document.querySelector("#benchmark-status").textContent = `${result.processing.inference_seconds.toFixed(2)} s · ${result.processing.real_time_factor.toFixed(2)}× RTF`;
    document.querySelector("#architecture").textContent = result.processing.architecture.toUpperCase();
    document.querySelector("#transcription-state").textContent = `Complete · ${result.processing.inference_seconds.toFixed(2)} s`;
    document.querySelector("#extraction-state").textContent = "Incident fields extracted";
    document.querySelector("#routing-state").textContent = "Priority queue updated";
    document.querySelectorAll(".pipeline-card li").forEach((step) => step.classList.add("complete"));
    await loadIncidents();
    signalBadge.textContent = "ROUTED";
    showToast(`${result.incident.severity.toUpperCase()} INCIDENT ROUTED · ${result.incident.location.toUpperCase()}`);
  } catch (error) {
    signalBadge.textContent = "ERROR";
    document.querySelector("#transcription-state").textContent = "Runtime error";
    showToast(error.message);
  } finally {
    button.disabled = false;
    button.querySelector("span").textContent = "TRANSCRIBE + ROUTE REPORT";
  }
}

function selectAudio() {
  const scenario = scenarios[activeScenario];
  const audio = document.querySelector("#scenario-audio");
  document.querySelector("#audio-label").textContent = `${scenario.label} · ${activeVariant.toUpperCase()}`;
  audio.src = `/audio/${scenario.slug}-${activeVariant}.wav`;
  audio.load();
  document.querySelector("#voice-state").textContent = "Fixture selected";
  document.querySelector("#transcription-state").textContent = "Waiting for audio";
  document.querySelector("#extraction-state").textContent = "Waiting for transcript";
  document.querySelector("#routing-state").textContent = "Waiting for incident";
  document.querySelectorAll(".pipeline-card li").forEach((step, index) => {
    step.classList.toggle("complete", index === 0);
  });
}

document.querySelector("#process-report").addEventListener("click", processReport);
document.querySelectorAll("[data-scenario]").forEach((button) => {
  button.addEventListener("click", () => {
    const scenario = scenarios[button.dataset.scenario];
    activeScenario = button.dataset.scenario;
    document.querySelector("#transcript").value = "";
    document.querySelector("#processing-result").hidden = true;
    document.querySelector(".signal-badge").textContent = "READY";
    document.querySelectorAll("[data-scenario]").forEach((scenarioButton) => {
      const isSelected = scenarioButton === button;
      scenarioButton.classList.toggle("selected", isSelected);
      scenarioButton.setAttribute("aria-pressed", String(isSelected));
    });
    selectAudio();
  });
});

document.querySelectorAll("[data-variant]").forEach((button) => {
  button.addEventListener("click", () => {
    activeVariant = button.dataset.variant;
    document.querySelector("#transcript").value = "";
    document.querySelector("#processing-result").hidden = true;
    document.querySelector(".signal-badge").textContent = "READY";
    document.querySelectorAll("[data-variant]").forEach((variantButton) => {
      variantButton.setAttribute("aria-pressed", String(variantButton === button));
    });
    selectAudio();
  });
});

updateClock();
window.setInterval(updateClock, 1000);
Promise.all([loadHealth(), loadIncidents()]).catch(() => {
  document.querySelector("#system-status").textContent = "OFFLINE";
});
