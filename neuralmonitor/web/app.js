const state = {
  sessionId: null,
  recorderId: null,
  metrics: [],
  alerts: new Map(),
};

const $ = (id) => document.getElementById(id);

function setText(id, value) {
  $(id).textContent = value;
}

async function jsonFetch(url, options = {}) {
  const response = await fetch(url, {
    headers: { "content-type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${await response.text()}`);
  }
  return response.json();
}

async function startSession() {
  const session = await jsonFetch("/sessions", {
    method: "POST",
    body: JSON.stringify({
      recorder_id: "recorder-alpha",
      name: "Cortical Recorder Alpha",
      operator: "dashboard",
      mode: "demo-live",
      notes: "Dashboard-created monitoring session",
    }),
  });
  state.sessionId = session.id;
  state.recorderId = session.recorder_id;
  setText("session-id", session.id);
  setText("recorder-status", "connected");
  state.metrics = [];
  state.alerts.clear();
  renderAlerts();
  drawChart();
}

async function simulate() {
  if (!state.sessionId) {
    await startSession();
  }
  await jsonFetch(`/sessions/${state.sessionId}/simulate`, {
    method: "POST",
    body: JSON.stringify({
      count: 350,
      drop_rate: 0.035,
      duplicate_rate: 0.015,
      out_of_order_rate: 0.01,
      checksum_failure_rate: 0.008,
      latency_spike_every: 60,
      latency_spike_ms: 320,
    }),
  });
}

async function sendHealth() {
  if (!state.sessionId) {
    await startSession();
  }
  await jsonFetch(`/sessions/${state.sessionId}/health`, {
    method: "POST",
    body: JSON.stringify({
      battery_percent: 13,
      temperature_c: 38.4,
      buffer_depth: 6200,
      storage_remaining_mb: 4096,
      link_quality: 0.74,
      cpu_percent: 71,
      memory_percent: 68,
    }),
  });
}

async function endSession() {
  if (!state.sessionId) return;
  await jsonFetch(`/sessions/${state.sessionId}/end`, { method: "POST" });
  setText("recorder-status", "offline");
}

function handleMessage(message) {
  const { topic, payload } = message;
  if (topic === "metric.snapshot" && payload.session_id === state.sessionId) {
    state.metrics.push(payload);
    state.metrics = state.metrics.slice(-80);
    setText("event-rate", `${payload.event_rate_hz.toFixed(1)} Hz`);
    setText("drops", payload.dropped_event_count);
    setText("latency", `${payload.latency_p95_ms.toFixed(1)} ms`);
    drawChart();
  }
  if (topic === "alert.changed" && payload.session_id === state.sessionId) {
    state.alerts.set(payload.id, payload);
    renderAlerts();
  }
  if (topic === "telemetry.event" && payload.session_id === state.sessionId) {
    renderEvent(payload);
  }
  if (topic === "recorder.status" && payload.id === state.recorderId) {
    setText("recorder-status", payload.status);
  }
}

function renderAlerts() {
  const alerts = Array.from(state.alerts.values())
    .filter((alert) => alert.status === "open")
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  setText("alert-count", alerts.length);
  $("alerts").innerHTML = alerts
    .map(
      (alert) => `
        <div class="alert ${alert.severity}">
          <strong>${alert.severity.toUpperCase()} · ${alert.type.replaceAll("_", " ")}</strong>
          <span>${alert.message}</span>
        </div>
      `
    )
    .join("");
}

function renderEvent(event) {
  const row = document.createElement("tr");
  row.innerHTML = `
    <td>${event.sequence_number}</td>
    <td>${event.source}</td>
    <td>${event.payload_size} bytes</td>
    <td>${event.checksum_valid ? "valid" : "invalid"}</td>
  `;
  const body = $("events");
  body.prepend(row);
  while (body.children.length > 16) {
    body.removeChild(body.lastChild);
  }
}

function drawChart() {
  const canvas = $("chart");
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = "#d9e1dc";
  ctx.lineWidth = 1;
  for (let i = 0; i < 6; i += 1) {
    const y = 24 + i * 52;
    ctx.beginPath();
    ctx.moveTo(36, y);
    ctx.lineTo(canvas.width - 16, y);
    ctx.stroke();
  }
  drawSeries(ctx, "latency_p95_ms", "#216c5a", 520);
  drawSeries(ctx, "dropped_event_count", "#b42318", Math.max(10, maxMetric("dropped_event_count")));
}

function maxMetric(key) {
  return Math.max(1, ...state.metrics.map((metric) => Number(metric[key] || 0)));
}

function drawSeries(ctx, key, color, maxValue) {
  if (state.metrics.length < 2) return;
  const left = 36;
  const width = ctx.canvas.width - 56;
  const height = ctx.canvas.height - 48;
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.beginPath();
  state.metrics.forEach((metric, index) => {
    const x = left + (index / Math.max(1, state.metrics.length - 1)) * width;
    const y = 16 + height - Math.min(1, Number(metric[key] || 0) / maxValue) * height;
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
}

function connectSocket() {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${location.host}/ws`);
  socket.addEventListener("open", () => setText("ws-state", "connected"));
  socket.addEventListener("close", () => {
    setText("ws-state", "reconnecting");
    setTimeout(connectSocket, 1000);
  });
  socket.addEventListener("message", (event) => handleMessage(JSON.parse(event.data)));
}

$("start").addEventListener("click", () => startSession().catch(console.error));
$("health").addEventListener("click", () => sendHealth().catch(console.error));
$("simulate").addEventListener("click", () => simulate().catch(console.error));
$("end").addEventListener("click", () => endSession().catch(console.error));
connectSocket();
drawChart();
