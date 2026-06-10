// ---------- CONFIG ----------
const BASE_URL = "http://127.0.0.1:5500";
const API_URL = `${BASE_URL}/data`;
const ML_URL = `${BASE_URL}/ml/insights`;
const POLL_INTERVAL = 3000;
const MAX_POINTS = 30;

// ---------- DOM ELEMENTS ----------
const connEl = document.getElementById("connection");
const machineEl = document.getElementById("machineStatus");
const tempEl = document.getElementById("temperature");
const powerEl = document.getElementById("powerUsage");
const effEl = document.getElementById("efficiency");
const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const resetBtn = document.getElementById("resetBtn");
const alertContainer = document.getElementById("alertContainer");

// ML Elements
const mlSummary = document.getElementById("mlSummary");
const mlPredEff = document.getElementById("mlPredEff");
const mlPredPower = document.getElementById("mlPredPower");
const mlOverheat = document.getElementById("mlOverheat");
const mlMaintenance = document.getElementById("mlMaintenance");
const mlAnomaly = document.getElementById("mlAnomaly");
const mlOptimize = document.getElementById("mlOptimize");

// ---------- CHART.JS SETUP ----------
const tempCtx = document.getElementById("tempChart").getContext("2d");
const powerCtx = document.getElementById("powerChart").getContext("2d");

let tempData = [];
let tempLabels = [];
let powerData = [];
let powerLabels = [];

const tempChart = new Chart(tempCtx, {
  type: "line",
  data: {
    labels: tempLabels,
    datasets: [
      {
        label: "Temperature (°C)",
        data: tempData,
        borderColor: "#1f6feb",
        fill: false,
        borderWidth: 2,
        tension: 0.3,
      },
    ],
  },
  options: { responsive: true, scales: { y: { beginAtZero: false } } },
});

const powerChart = new Chart(powerCtx, {
  type: "line",
  data: {
    labels: powerLabels,
    datasets: [
      {
        label: "Power Usage (W)",
        data: powerData,
        borderColor: "#34d399",
        fill: false,
        borderWidth: 2,
        tension: 0.3,
      },
    ],
  },
  options: { responsive: true, scales: { y: { beginAtZero: true } } },
});

// ---------- STATE CONTROL ----------
let polling = false;
let pollTimer = null;
let machineRunning = false;
let lastStatus = "";

// ---------- ALERT FUNCTION ----------
function showAlert(message, type = "info") {
  const alert = document.createElement("div");
  alert.className = `alert ${type}`;
  alert.textContent = message;

  alertContainer.appendChild(alert);

  setTimeout(() => {
    alert.remove();
  }, 4000);
}

// ---------- ML INSIGHTS FETCH ----------
async function fetchMLInsights() {
  try {
    const res = await fetch(ML_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      body: JSON.stringify({}),
    });

    if (!res.ok) throw new Error("ML API Error");

    const ml = await res.json();
    updateMLUI(ml);

  } catch (err) {
    mlSummary.textContent = "❌ ML Insights unavailable";
    mlSummary.style.color = "var(--danger)";
  }
}

// ---------- ML UI UPDATE ----------
function updateMLUI(ml) {
  // Summary
  mlSummary.textContent = ml.summary || "No critical issues";

  // Predicted Efficiency
  if (ml.insights.pred_efficiency !== undefined) {
    mlPredEff.textContent = ml.insights.pred_efficiency + " %";
    mlPredEff.className = classifyValue(ml.insights.pred_efficiency, 60, 40);
  }

  // Predicted Power
  if (ml.insights.pred_power_kw !== undefined) {
    mlPredPower.textContent = ml.insights.pred_power_kw.toFixed(2) + " kW";
    mlPredPower.className = "ml-ok";
  }

  // Overheat Risk
  if (ml.insights.overheat_class !== undefined) {
    if (ml.insights.overheat_class === 1) {
      mlOverheat.textContent = "HIGH";
      mlOverheat.className = "ml-bad";
    } else {
      mlOverheat.textContent = "Normal";
      mlOverheat.className = "ml-ok";
    }
  }

  // Maintenance Prediction
  if (ml.insights.maintenance_required !== undefined) {
    if (ml.insights.maintenance_required === 1) {
      mlMaintenance.textContent = "Required Soon";
      mlMaintenance.className = "ml-warn";
    } else {
      mlMaintenance.textContent = "Not Needed";
      mlMaintenance.className = "ml-ok";
    }
  }

  // Anomaly Detection
  if (ml.insights.anomaly_pred !== undefined) {
    if (ml.insights.anomaly_pred === -1) {
      mlAnomaly.textContent = "Anomaly Detected";
      mlAnomaly.className = "ml-bad";
    } else {
      mlAnomaly.textContent = "Normal";
      mlAnomaly.className = "ml-ok";
    }
  }

  // Optimization
  if (ml.insights.optimization) {
    const opt = ml.insights.optimization;
    mlOptimize.textContent = `
      Power → ${opt.opt_power_kw || "--"} kW
      Temp → ${opt.opt_temp_c || "--"} °C
    `;
    mlOptimize.className = "small-text ml-ok";
  }
}

// ---------- VALUE CLASSIFIER ----------
function classifyValue(val, good, bad) {
  if (val >= good) return "ml-ok";
  if (val <= bad) return "ml-bad";
  return "ml-warn";
}

// ---------- FETCH LOOP ----------
async function fetchAndUpdate() {
  try {
    const res = await fetch(API_URL, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const data = await res.json();
    setConnected(true);

    // Update top cards
    const status = data.machine_status || "-";
    machineEl.textContent = status;
    tempEl.textContent = data.temperature !== undefined ? `${data.temperature.toFixed(2)} °C` : "-";
    powerEl.textContent = data.power_usage !== undefined ? `${data.power_usage.toFixed(2)} W` : "-";
    effEl.textContent = data.efficiency !== undefined ? `${data.efficiency.toFixed(1)} %` : "-";

    // Update charts
    if (["Running", "Overheated", "Cooldown"].includes(status)) {
      const time = new Date().toLocaleTimeString();
      pushRolling(tempLabels, tempData, time, data.temperature, MAX_POINTS);
      pushRolling(powerLabels, powerData, time, data.power_usage, MAX_POINTS);
      tempChart.update();
      powerChart.update();
    }

    // Fetch ML Insights
    fetchMLInsights();

    // Status change logic
    if (status !== lastStatus) {
      if (status === "Overheated") {
        logEvent(`🔥 Machine overheated! Entering cooldown...`);
        showAlert("⚠️ Machine overheated!", "danger");
      } else if (status === "Cooldown") {
        logEvent(`🧊 Machine cooling down...`);
        showAlert("🧊 Cooling down process started", "warning");
      } else if (status === "Running" && lastStatus === "Cooldown") {
        logEvent(`✅ Machine cooled down and resumed running.`);
        showAlert("✅ Machine back to normal operation", "success");
      } else if (status === "Idle" && lastStatus !== "Idle") {
        logEvent(`⏸ Machine is now idle.`);
        showAlert("⏸ Machine switched to idle mode", "info");
      }

      lastStatus = status;
    }

    // Button state
    if (status === "Running") {
      startBtn.disabled = true;
      stopBtn.disabled = false;
      machineRunning = true;
    } else if (status === "Cooldown" || status === "Overheated") {
      startBtn.disabled = true;
      stopBtn.disabled = true;
      machineRunning = false;
    } else {
      startBtn.disabled = false;
      stopBtn.disabled = true;
      machineRunning = false;
    }

    // Warn for high temp
    if (data.temperature > 80 && status === "Running") {
      logEvent(`⚠️ High temperature: ${data.temperature.toFixed(1)}°C`);
      showAlert(`⚠️ High temperature: ${data.temperature.toFixed(1)}°C`, "warning");
    }

  } catch (err) {
    setConnected(false);
    logEvent(`❌ Fetch error: ${err.message}`);
    showAlert(`❌ Connection lost: ${err.message}`, "danger");
  }
}

// ---------- UTIL FUNCTIONS ----------
function pushRolling(labels, data, label, value, max) {
  labels.push(label);
  data.push(value !== undefined ? parseFloat(value.toFixed(2)) : null);
  while (labels.length > max) labels.shift();
  while (data.length > max) data.shift();
}

function setConnected(isConnected) {
  if (isConnected) {
    connEl.textContent = "Connected";
    connEl.className = "status online";
  } else {
    connEl.textContent = "Disconnected";
    connEl.className = "status offline";
  }
}

// Log storage
function logEvent(text) {
  const timestamp = new Date().toLocaleTimeString();
  const entry = `${timestamp} — ${text}`;
  const existing = JSON.parse(localStorage.getItem("logs") || "[]");
  existing.unshift(entry);
  if (existing.length > 200) existing.pop();
  localStorage.setItem("logs", JSON.stringify(existing));
}

// ---------- POLLING CONTROL ----------
function startPolling() {
  if (polling) return;
  polling = true;
  pollTimer = setInterval(fetchAndUpdate, POLL_INTERVAL);
  fetchAndUpdate();
}

function stopPolling() {
  polling = false;
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
}

// ---------- BUTTON EVENTS ----------
startBtn.addEventListener("click", async () => {
  if (machineRunning) return;
  try {
    const res = await fetch(`${BASE_URL}/start`);
    const data = await res.json();
    logEvent(`▶️ ${data.message}`);
    showAlert(`▶️ ${data.message}`, "success");

    if (data.status === "Running") {
      machineRunning = true;
      startBtn.disabled = true;
      stopBtn.disabled = false;
      startPolling();
    } else {
      logEvent(`⚠️ Cannot start: ${data.status}`);
      showAlert(`⚠️ Cannot start: ${data.status}`, "warning");
    }
  } catch (err) {
    logEvent(`⚠️ Failed to start: ${err.message}`);
    showAlert(`⚠️ Failed to start: ${err.message}`, "danger");
  }
});

stopBtn.addEventListener("click", async () => {
  if (!machineRunning) return;
  try {
    const res = await fetch(`${BASE_URL}/stop`);
    const data = await res.json();
    logEvent(`⏸ ${data.message}`);
    showAlert(`⏸ ${data.message}`, "info");

    stopPolling();
    machineRunning = false;
    startBtn.disabled = false;
    stopBtn.disabled = true;
    machineEl.textContent = "Idle";
    tempEl.textContent = "--";
    powerEl.textContent = "--";
    effEl.textContent = "--";
  } catch (err) {
    logEvent(`⚠️ Failed to stop: ${err.message}`);
    showAlert(`⚠️ Failed to stop: ${err.message}`, "danger");
  }
});

resetBtn.addEventListener("click", () => {
  tempData = [];
  tempLabels = [];
  powerData = [];
  powerLabels = [];
  tempChart.data.labels = tempLabels;
  tempChart.data.datasets[0].data = tempData;
  powerChart.data.labels = powerLabels;
  powerChart.data.datasets[0].data = powerData;
  tempChart.update();
  powerChart.update();
  logEvent("🔁 Graphs reset");
  showAlert("🔁 Graphs reset successfully", "success");
});

// ---------- START ----------
startPolling();
