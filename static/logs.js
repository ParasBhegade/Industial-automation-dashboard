// logs.js

const BASE_URL = "http://127.0.0.1:5500";
const API_URL = `${BASE_URL}/logs`;

const logsTableBody = document.getElementById("logsTableBody");
const refreshBtn = document.getElementById("refreshLogs");
const clearBtn = document.getElementById("clearLogs");
const exportBtn = document.getElementById("exportLogs");
const searchInput = document.getElementById("searchLog");
const filterType = document.getElementById("filterType");

// ✅ Fetch logs safely
async function fetchLogs() {
  try {
    const res = await fetch(API_URL);
    if (!res.ok) throw new Error(`Server returned ${res.status}`);
    
    // Try parsing as JSON
    const text = await res.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      console.error("❌ Backend returned HTML instead of JSON:", text);
      throw new Error("Backend did not return valid JSON (maybe server error)");
    }

    renderLogs(data);
  } catch (err) {
    console.error("❌ Error fetching logs:", err);
    logsTableBody.innerHTML = `
      <tr><td colspan="3" style="color:red;">
        ❌ Error: ${err.message}<br>
        Check if Flask (port 5500) is running correctly.
      </td></tr>`;
  }
}

// ✅ Render logs
function renderLogs(logs) {
  const search = searchInput.value.toLowerCase();
  const filter = filterType.value;

  const filtered = logs.filter((log) => {
    const matchesSearch =
      log.message.toLowerCase().includes(search) ||
      log.type.toLowerCase().includes(search);
    const matchesType = filter === "ALL" || log.type === filter;
    return matchesSearch && matchesType;
  });

  logsTableBody.innerHTML = filtered.length
    ? filtered
        .map(
          (log) => `
        <tr>
          <td>${log.timestamp}</td>
          <td class="${log.type.toLowerCase()}">${log.type}</td>
          <td>${log.message}</td>
        </tr>`
        )
        .join("")
    : `<tr><td colspan="3">No logs found.</td></tr>`;
}

// ✅ Clear logs safely
async function clearLogs() {
  if (!confirm("Are you sure you want to clear all logs?")) return;
  try {
    const res = await fetch(`${BASE_URL}/logs/clear`, { method: "DELETE" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    await fetchLogs(); // Refresh table
  } catch (err) {
    console.error("❌ Failed to clear logs:", err);
    alert("Failed to clear logs! Please check the server.");
  }
}

// ✅ Export logs to CSV
async function exportLogs() {
  try {
    const res = await fetch(API_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const logs = await res.json();

    const csv = ["Timestamp,Type,Message"]
      .concat(logs.map((l) => `${l.timestamp},${l.type},"${l.message}"`))
      .join("\n");

    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `machine_logs_${new Date().toISOString().slice(0,19).replace(/[:T]/g,"-")}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    console.error("❌ Failed to export logs:", err);
    alert("Failed to export logs. Try again.");
  }
}

// ✅ Event listeners
refreshBtn.addEventListener("click", fetchLogs);
clearBtn.addEventListener("click", clearLogs);
exportBtn.addEventListener("click", exportLogs);
searchInput.addEventListener("input", fetchLogs);
filterType.addEventListener("change", fetchLogs);

// ✅ Auto-load logs
fetchLogs();
