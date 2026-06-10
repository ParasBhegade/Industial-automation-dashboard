// analysis.js (UPDATED — server-backed ML history & stats)
// Loads ML history from /ml/history and stats from /ml/stats
// Also triggers /ml/insights periodically (so server persists new ML samples)

console.log("✅ Real-time Analysis Dashboard Loaded (server-backed ML history)");

// ---- DOM Elements ----
const avgEffEl = document.getElementById("avgEfficiency");
const peakPowerEl = document.getElementById("peakPower");
const runtimeEl = document.getElementById("runtimePercent");
const idleEl = document.getElementById("idlePercent");
const statusMsg = document.getElementById("reportStatus");
const reportBtn = document.getElementById("generateReportBtn");

// ML DOM Elements (new)
const exportMlPdfBtn = document.getElementById("exportMlPdfBtn");
const mlHistoryCountEl = document.getElementById("mlHistoryCount");
const mlTextSummaryEl = document.getElementById("mlTextSummary");

// ---- Backend Base URL ----
const BASE_URL = "http://127.0.0.1:5500";

// ---- Chart Variables ----
let tempChart, powerChart, effChart;

// ---- ML Charts & History (server-backed) ----
let mlHistory = []; // filled from /ml/history
const ML_HISTORY_LIMIT = 200;

let mlPredVsRealChart, mlAnomalyChart, mlOptChart, mlConfidenceChart;

// store last analysis data snapshot for alignment (kept for fallback)
let lastAnalysisData = [];

// ---------- Helper fetch wrappers ----------
async function safeJsonFetch(url, options = {}) {
  try {
    const res = await fetch(url, options);
    if (!res.ok) {
      const txt = await res.text().catch(()=>"");
      throw new Error(`HTTP ${res.status} ${res.statusText} ${txt}`);
    }
    return await res.json();
  } catch (err) {
    console.error("Fetch error:", url, err);
    throw err;
  }
}

// ---- Fetch and Update Analysis Data ----
async function fetchAnalysisData(retry = true) {
  try {
    const response = await fetch(`${BASE_URL}/get_analysis_data`);
    if (!response.ok) throw new Error("Failed to fetch analysis data");

    const { summary, data } = await response.json();
    if (!summary || !data) throw new Error("Invalid data format");

    updateSummary(summary);
    updateCharts(data);

    // store latest sampled analysis data to align with ML samples (fallback)
    lastAnalysisData = data.slice(); // clone

    // 1) first fetch ML history from server (persistent)
    await fetchMlHistory();

    // 2) request a fresh ML insights sample (server will persist it)
    //    then re-fetch history so UI reflects newest sample
    await triggerServerMlInsight();
    await fetchMlHistory();

    // 3) fetch aggregated ML stats and append to summary
    await fetchMlStats();

    statusMsg.textContent = `📡 Updated at ${new Date().toLocaleTimeString()}`;
  } catch (err) {
    console.error("❌ Error loading analysis data:", err);
    statusMsg.textContent = "⚠️ Error fetching data. Retrying...";
    if (retry) setTimeout(() => fetchAnalysisData(false), 3000);
  }
}

// ---- Update Summary Cards ----
function updateSummary(summary) {
  avgEffEl.textContent = `${summary.average_efficiency.toFixed(2)} %`;
  peakPowerEl.textContent = `${summary.peak_power.toFixed(2)} kW`;
  runtimeEl.textContent = `${summary.runtime_percent.toFixed(1)} %`;
  idleEl.textContent = `${summary.idle_percent.toFixed(1)} %`;

  // Dynamic color feedback
  avgEffEl.style.color =
    summary.average_efficiency > 85
      ? "#2ecc71"
      : summary.average_efficiency > 70
      ? "#f1c40f"
      : "#e74c3c";
  runtimeEl.style.color =
    summary.runtime_percent > 60 ? "#2ecc71" : "#f1c40f";
}

// ---- Chart Update Logic (existing charts) ----
function updateCharts(data) {
  const labels = data.map((d) => d.time);
  const temps = data.map((d) => d.temperature);
  const powers = data.map((d) => d.power);
  const effs = data.map((d) => d.efficiency);

  const tempCtx = document.getElementById("tempChart").getContext("2d");
  const powerCtx = document.getElementById("powerChart").getContext("2d");
  const effCtx = document.getElementById("effChart").getContext("2d");

  if (tempChart) tempChart.destroy();
  if (powerChart) powerChart.destroy();
  if (effChart) effChart.destroy();

  tempChart = new Chart(tempCtx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Temperature (°C)",
          data: temps,
          borderColor: "#ff6b6b",
          backgroundColor: "rgba(255,107,107,0.1)",
          fill: true,
          tension: 0.3,
          borderWidth: 2,
          pointRadius: 0,
        },
      ],
    },
    options: chartOptions("Temperature Trend (°C)"),
  });

  powerChart = new Chart(powerCtx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Power Usage (kW)",
          data: powers,
          borderColor: "#3498db",
          backgroundColor: "rgba(52,152,219,0.1)",
          fill: true,
          tension: 0.3,
          borderWidth: 2,
          pointRadius: 0,
        },
      ],
    },
    options: chartOptions("Power Usage Trend (kW)"),
  });

  effChart = new Chart(effCtx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Efficiency (%)",
          data: effs,
          borderColor: "#2ecc71",
          backgroundColor: "rgba(46,204,113,0.1)",
          fill: true,
          tension: 0.3,
          borderWidth: 2,
          pointRadius: 0,
        },
      ],
    },
    options: chartOptions("Efficiency Trend (%)"),
  });
}

// ---- Chart Style Options ----
function chartOptions(title) {
  return {
    responsive: true,
    plugins: {
      title: {
        display: true,
        text: title,
        color: "#111",
        font: { size: 14 },
      },
      legend: { labels: { color: "#111", boxWidth: 12 } },
    },
    scales: {
      x: { ticks: { color: "#444" }, grid: { color: "rgba(0,0,0,0.03)" } },
      y: { ticks: { color: "#444" }, grid: { color: "rgba(0,0,0,0.03)" } },
    },
    animation: { duration: 600, easing: "easeOutQuart" },
  };
}

// ---- Generate PDF Report (existing) ----
reportBtn.addEventListener("click", async () => {
  reportBtn.disabled = true;
  statusMsg.textContent = "⏳ Generating report...";

  try {
    const res = await fetch(`${BASE_URL}/generate_report`);
    if (!res.ok) throw new Error("Failed to generate report");
    const blob = await res.blob();

    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `Machine_Report_${new Date()
      .toISOString()
      .slice(0, 19)
      .replace(/[:T]/g, "_")}.pdf`;
    a.click();

    statusMsg.textContent = "✅ Report downloaded successfully!";
  } catch (err) {
    console.error("⚠️ Report generation failed:", err);
    statusMsg.textContent = "⚠️ Error generating report. Backend may be down.";
  } finally {
    reportBtn.disabled = false;
  }
});

// ============================================================
// ML: Server-backed history & stats
// ============================================================

// Fetch ML history from backend and render charts
async function fetchMlHistory(limit = ML_HISTORY_LIMIT) {
  try {
    const data = await safeJsonFetch(`${BASE_URL}/ml/history?limit=${limit}`);
    if (!data || !Array.isArray(data.rows)) {
      console.warn("Invalid /ml/history response", data);
      return;
    }
    // mlHistory: chronological (oldest -> newest)
    mlHistory = data.rows || [];
    mlHistoryCountEl.textContent = mlHistory.length;
    renderMlCharts();
    buildMlTextSummary(); // textual summary based on server data
  } catch (err) {
    console.error("Failed to fetch ML history:", err);
  }
}

// Trigger server to create a new ML insight (server persists it)
async function triggerServerMlInsight() {
  try {
    // POST /ml/insights without payload (server will use latest data)
    const res = await fetch(`${BASE_URL}/ml/insights`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    if (!res.ok) {
      console.warn("ml/insights responded with non-OK:", res.status);
      return;
    }
    // we don't strictly need the response body here because /ml/history will include it,
    // but we still attempt to parse and log for debugging.
    const body = await res.json().catch(()=>null);
    if (body) console.debug("ml/insights response:", body.summary || body);
  } catch (err) {
    console.error("Failed to trigger /ml/insights:", err);
  }
}

// Fetch ML aggregated stats for dashboard/summary
async function fetchMlStats(limit = ML_HISTORY_LIMIT) {
  try {
    const stats = await safeJsonFetch(`${BASE_URL}/ml/stats?limit=${limit}`);
    // show relevant bits in the ML text summary area (append)
    let extra = "";
    if (stats && stats.samples_compared) {
      extra += ` | Samples compared: ${stats.samples_compared}`;
      if (stats.mae_efficiency !== undefined) {
        extra += ` | MAE: ${stats.mae_efficiency}`;
      }
      if (stats.rmse_efficiency !== undefined) {
        extra += ` | RMSE: ${stats.rmse_efficiency}`;
      }
      if (stats.drift && stats.drift.drift_flag) {
        extra += ` | ⚠️ Drift detected`;
      }
    }
    // append to mlTextSummaryEl (do not overwrite detailed summary)
    const prev = mlTextSummaryEl.textContent || "";
    mlTextSummaryEl.textContent = prev + extra;
  } catch (err) {
    console.error("Failed to fetch ML stats:", err);
  }
}

// ---- Build textual summary of recent ML behaviour (from server history) ----
function buildMlTextSummary() {
  if (!mlHistory.length) {
    mlTextSummaryEl.textContent = "No ML samples collected yet.";
    return;
  }

  const latest = mlHistory[mlHistory.length - 1];
  const ins = latest; // row already contains top-level fields
  const parts = [];
  if (ins.overheat_class === 1) parts.push("High overheat risk (latest).");
  if (ins.maintenance_required === 1) parts.push("Maintenance likely soon.");
  if (ins.anomaly_pred === -1) parts.push("Anomaly detected in latest sample.");
  if (ins.pred_efficiency !== undefined && ins.pred_efficiency !== null)
    parts.push(`Pred Eff: ${ins.pred_efficiency}%`);
  // real efficiency from features if present
  const realEff = ins.features && (ins.features.efficiency || ins.features.efficiency === 0) ? ins.features.efficiency : null;
  if (realEff !== null) parts.push(`Real Eff: ${realEff}%`);
  if (ins.pred_power_kw !== undefined && ins.pred_power_kw !== null)
    parts.push(`Pred Power: ${ins.pred_power_kw} kW`);

  mlTextSummaryEl.textContent = parts.length ? parts.join(" ") : "No critical issues detected in recent ML samples.";
}

// ---- Render ML Charts (creates or updates charts) ----
function renderMlCharts() {
  // labels are timestamps (short)
  const labels = mlHistory.map((r) => {
    try {
      const d = new Date(r.timestamp);
      return d.toLocaleTimeString();
    } catch (e) {
      return r.time_label || "";
    }
  });

  // Predicted Efficiency vs Real Efficiency
  const predEff = mlHistory.map((r) => (r.pred_efficiency !== null && r.pred_efficiency !== undefined) ? r.pred_efficiency : null);
  const realEff = mlHistory.map((r) => {
    if (r.features && (r.features.efficiency !== undefined && r.features.efficiency !== null)) return r.features.efficiency;
    return null;
  });

  // Anomalies
  const anomalies = mlHistory.map((r) => (r.anomaly_pred === -1 ? 1 : 0));

  // Optimization suggested power (opt_power_kw stored)
  const optPower = mlHistory.map((r) => (r.opt_power_kw !== null && r.opt_power_kw !== undefined) ? r.opt_power_kw : null);

  // Probabilities/scores
  const overheatProba = mlHistory.map((r) => (r.overheat_proba !== null && r.overheat_proba !== undefined) ? r.overheat_proba : null);
  const maintenanceProba = mlHistory.map((r) => (r.maintenance_proba !== null && r.maintenance_proba !== undefined) ? r.maintenance_proba : null);
  const anomalyScore = mlHistory.map((r) => (r.anomaly_score !== null && r.anomaly_score !== undefined) ? r.anomaly_score : null);

  // Pred vs Real chart
  const pvCtx = document.getElementById("mlPredVsRealChart").getContext("2d");
  if (mlPredVsRealChart) mlPredVsRealChart.destroy();
  mlPredVsRealChart = new Chart(pvCtx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Predicted Efficiency (%)",
          data: predEff,
          borderColor: "#f39c12",
          backgroundColor: "rgba(243,156,18,0.08)",
          fill: true,
          tension: 0.25,
          borderWidth: 2,
          pointRadius: 2,
        },
        {
          label: "Real Efficiency (%)",
          data: realEff,
          borderColor: "#27ae60",
          backgroundColor: "rgba(39,174,96,0.08)",
          fill: true,
          tension: 0.25,
          borderWidth: 2,
          pointRadius: 2,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: { title: { display: true, text: "Predicted vs Real Efficiency" } },
      scales: { x: { ticks: { color: "#333" } }, y: { beginAtZero: true } },
    },
  });

  // Anomaly timeline bar chart
  const anCtx = document.getElementById("mlAnomalyChart").getContext("2d");
  if (mlAnomalyChart) mlAnomalyChart.destroy();
  mlAnomalyChart = new Chart(anCtx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Anomaly (1=yes)",
          data: anomalies,
          backgroundColor: anomalies.map((v) => (v === 1 ? "#e74c3c" : "#2ecc71")),
        },
      ],
    },
    options: {
      responsive: true,
      plugins: { title: { display: true, text: "Anomaly Timeline" } },
      scales: { y: { ticks: { stepSize: 1 }, min: 0, max: 1 } },
    },
  });

  // Optimization history
  const opCtx = document.getElementById("mlOptChart").getContext("2d");
  if (mlOptChart) mlOptChart.destroy();
  mlOptChart = new Chart(opCtx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Suggested Power (kW)",
          data: optPower,
          borderColor: "#3498db",
          backgroundColor: "rgba(52,152,219,0.06)",
          fill: true,
          tension: 0.25,
          borderWidth: 2,
          pointRadius: 2,
        },
      ],
    },
    options: { responsive: true, plugins: { title: { display: true, text: "Optimization — Suggested Power" } } },
  });

  // Confidence chart (multiple series)
  const cfCtx = document.getElementById("mlConfidenceChart").getContext("2d");
  if (mlConfidenceChart) mlConfidenceChart.destroy();
  mlConfidenceChart = new Chart(cfCtx, {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Overheat Prob (avg)", data: overheatProba, borderColor: "#f39c12", fill: false, tension: 0.2 },
        { label: "Maintenance Prob (avg)", data: maintenanceProba, borderColor: "#9b59b6", fill: false, tension: 0.2 },
        { label: "Anomaly Score", data: anomalyScore, borderColor: "#e74c3c", fill: false, tension: 0.2 },
      ],
    },
    options: { responsive: true, plugins: { title: { display: true, text: "ML Confidence & Scores" } }, scales: { y: { beginAtZero: true } } },
  });
}

// helper: average numeric items in array (safely)
function avgArray(arr) {
  if (!Array.isArray(arr) || !arr.length) return null;
  const nums = arr.map(Number).filter((n) => !isNaN(n));
  if (!nums.length) return null;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

// ============================================================
// Export ML Insights to PDF (client-side using jsPDF)
// ============================================================
async function exportMlInsightsToPdf() {
  // Use jsPDF to create a multi-page PDF including chart images and a brief summary
  const { jsPDF } = window.jspdf;
  const doc = new jsPDF({ unit: "pt", format: "a4" });

  // Title page
  doc.setFontSize(18);
  doc.text("ML Insights Report", 40, 50);
  doc.setFontSize(11);
  doc.text(`Generated: ${new Date().toLocaleString()}`, 40, 75);
  doc.text(`Samples included: ${mlHistory.length}`, 40, 95);

  // Helper to add canvas images
  async function addCanvasToPdf(canvas, x, y, maxW) {
    try {
      const dataUrl = canvas.toDataURL("image/png", 1.0);
      // fit width while preserving aspect ratio
      const img = new Image();
      img.src = dataUrl;
      await new Promise((res) => (img.onload = res));
      const iw = img.width;
      const ih = img.height;
      const scale = Math.min(1, maxW / iw);
      const w = iw * scale;
      const h = ih * scale;
      doc.addImage(dataUrl, "PNG", x, y, w, h);
      return h + 10;
    } catch (err) {
      console.error("Canvas -> PDF error", err);
      return 0;
    }
  }

  // Prepare to place charts (we will snapshot each chart canvas)
  const marginX = 40;
  let cursorY = 120;
  const pageWidth = doc.internal.pageSize.getWidth();
  const maxChartW = pageWidth - marginX * 2;

  // capture Pred vs Real
  const predCanvas = document.getElementById("mlPredVsRealChart");
  cursorY += await addCanvasToPdf(predCanvas, marginX, cursorY, maxChartW);

  // If need new page
  if (cursorY > doc.internal.pageSize.getHeight() - 200) {
    doc.addPage();
    cursorY = 40;
  }

  // capture Anomaly
  const anCanvas = document.getElementById("mlAnomalyChart");
  cursorY += await addCanvasToPdf(anCanvas, marginX, cursorY, maxChartW);

  if (cursorY > doc.internal.pageSize.getHeight() - 200) {
    doc.addPage();
    cursorY = 40;
  }

  // Optimization
  const optCanvas = document.getElementById("mlOptChart");
  cursorY += await addCanvasToPdf(optCanvas, marginX, cursorY, maxChartW);

  if (cursorY > doc.internal.pageSize.getHeight() - 200) {
    doc.addPage();
    cursorY = 40;
  }

  // Confidence
  const cfCanvas = document.getElementById("mlConfidenceChart");
  cursorY += await addCanvasToPdf(cfCanvas, marginX, cursorY, maxChartW);

  // Add a final textual summary page
  doc.addPage();
  doc.setFontSize(14);
  doc.text("Summary (latest samples)", 40, 50);
  doc.setFontSize(11);
  if (!mlHistory.length) {
    doc.text("No ML samples to summarize.", 40, 80);
  } else {
    const latest = mlHistory[mlHistory.length - 1];
    const lines = [
      `Timestamp: ${latest.timestamp}`,
      `Predicted Efficiency: ${latest.pred_efficiency ?? "--"}`,
      `Predicted Power (kW): ${latest.pred_power_kw ?? "--"}`,
      `Overheat class: ${latest.overheat_class ?? "--"}`,
      `Maintenance required: ${latest.maintenance_required ?? "--"}`,
      `Anomaly pred: ${latest.anomaly_pred ?? "--"}`,
    ];
    let y = 80;
    lines.forEach((l) => {
      doc.text(l, 40, y);
      y += 16;
    });
  }

  // Save
  doc.save(`ML_Insights_${new Date().toISOString().slice(0,19).replace(/[:T]/g,"_")}.pdf`);
}

// attach export button
if (exportMlPdfBtn) {
  exportMlPdfBtn.addEventListener("click", async () => {
    exportMlPdfBtn.disabled = true;
    exportMlPdfBtn.textContent = "⏳ Preparing PDF...";
    try {
      await exportMlInsightsToPdf();
    } catch (err) {
      console.error("Export PDF failed:", err);
      alert("Failed to export ML Insights PDF. See console.");
    } finally {
      exportMlPdfBtn.disabled = false;
      exportMlPdfBtn.textContent = "📤 Export ML Insights to PDF";
    }
  });
}

// ============================================================
// Auto Refresh Logic
// ============================================================
window.addEventListener("DOMContentLoaded", () => {
  // initial load
  fetchAnalysisData();
  // Refresh every 10 seconds for near real-time updates
  setInterval(fetchAnalysisData, 10000);
});
