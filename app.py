from flask import Flask, jsonify, request, send_file, Response, send_from_directory
from flask_cors import CORS
import random
from datetime import datetime
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import math
import sqlite3
import csv
import os
from joblib import load
import json
import statistics
import traceback

app = Flask(__name__)
CORS(app)

# ---------- PATHS ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
MODELS_DIR = os.path.join(BASE_DIR, "models")
DB_PATH = os.path.join(BASE_DIR, "machine_data.db")

# ---------- FRONTEND ROUTES ----------
@app.route('/')
def serve_dashboard():
    return send_from_directory(STATIC_DIR, 'index.html')

@app.route('/home')
def serve_home():
    return send_from_directory(STATIC_DIR, 'home.html')

@app.route('/login')
def serve_login():
    return send_from_directory(STATIC_DIR, 'login.html')

@app.route('/register')
def serve_register():
    return send_from_directory(STATIC_DIR, 'register.html')

@app.route('/analysis')
def serve_analysis():
    return send_from_directory(STATIC_DIR, 'analysis.html')

@app.route('/logs_page')
def serve_logs_page():
    return send_from_directory(STATIC_DIR, 'logs.html')

@app.route('/<path:filename>')
def serve_static_files(filename):
    return send_from_directory(STATIC_DIR, filename)

# ---------- GLOBAL STATE ----------
machine_status = "Idle"
overheat_counter = 0
cooldown_counter = 0
current_temp = 40.0
current_power = 0.0

# ---------- LOG STORAGE ----------
logs = []

# ---------- HISTORICAL DATA (runtime memory, also persisted to DB) ----------
historical_data = []

# ---------- LOGGING ----------
def add_log(message, level="INFO"):
    logs.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": level,
        "message": message
    })
    if len(logs) > 200:
        logs.pop(0)

# ---------- HELPER ----------
def smooth_change(value, target_min, target_max, step=1.5, noise=0.3):
    target = random.uniform(target_min, target_max)
    if target > value:
        value += min(step, target - value)
    else:
        value -= min(step, value - target)
    value += random.uniform(-noise, noise)
    return round(value, 2)

# ---------- DB SETUP ----------
def init_machine_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # existing machine_data table
    c.execute("""
        CREATE TABLE IF NOT EXISTS machine_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            time_label TEXT,
            temperature REAL,
            power_kw REAL,
            efficiency REAL,
            status TEXT
        )
    """)
    # new ml_history table for persistent ML insights
    c.execute("""
        CREATE TABLE IF NOT EXISTS ml_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            time_label TEXT,
            features_json TEXT,
            pred_efficiency REAL,
            pred_power REAL,
            overheat_class INTEGER,
            maintenance_required INTEGER,
            anomaly_pred INTEGER,
            anomaly_score REAL,
            opt_power_kw REAL,
            opt_temp_c REAL,
            overheat_proba REAL,
            maintenance_proba REAL,
            runtime_forecast REAL
        )
    """)
    conn.commit()
    conn.close()

def save_data_point_to_db(time_label, temperature, power_kw, efficiency, status):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            INSERT INTO machine_data (created_at, time_label, temperature, power_kw, efficiency, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), time_label, temperature, power_kw, efficiency, status))
        conn.commit()
        conn.close()
    except Exception as e:
        add_log(f"Database insert error: {e}", "ERROR")

def save_ml_insight_to_db(time_label, feat, insights):
    """
    Persist ML insights into ml_history table.
    feat: dict of features (may be included as JSON)
    insights: dict of insights collected in /ml/insights response body
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # normalize some fields
        pred_eff = insights.get("pred_efficiency")
        pred_power = insights.get("pred_power_kw")
        overheat_class = insights.get("overheat_class")
        maintenance_required = insights.get("maintenance_required")
        anomaly_pred = insights.get("anomaly_pred")
        anomaly_score = insights.get("anomaly_score")
        opt_power = None
        opt_temp = None
        if "optimization" in insights and isinstance(insights["optimization"], dict):
            opt_power = insights["optimization"].get("opt_power_kw")
            opt_temp = insights["optimization"].get("opt_temp_c")
        # probabilities: if list, take average for storage as a single float; else None
        overheat_proba = None
        if insights.get("overheat_proba") is not None:
            try:
                val = insights.get("overheat_proba")
                if isinstance(val, list) and val:
                    overheat_proba = float(sum([float(x) for x in val if x is not None]) / len(val))
                else:
                    overheat_proba = float(val)
            except Exception:
                overheat_proba = None
        maintenance_proba = None
        if insights.get("maintenance_proba") is not None:
            try:
                val = insights.get("maintenance_proba")
                if isinstance(val, list) and val:
                    maintenance_proba = float(sum([float(x) for x in val if x is not None]) / len(val))
                else:
                    maintenance_proba = float(val)
            except Exception:
                maintenance_proba = None

        feat_json = json.dumps(feat or {})
        c.execute("""
            INSERT INTO ml_history
            (timestamp, time_label, features_json, pred_efficiency, pred_power, overheat_class, maintenance_required,
             anomaly_pred, anomaly_score, opt_power_kw, opt_temp_c, overheat_proba, maintenance_proba, runtime_forecast)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            time_label,
            feat_json,
            pred_eff,
            pred_power,
            overheat_class,
            maintenance_required,
            anomaly_pred,
            anomaly_score,
            opt_power,
            opt_temp,
            overheat_proba,
            maintenance_proba,
            insights.get("runtime_forecast_steps")
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        add_log(f"Failed to save ML insight: {e}", "ERROR")
        add_log(traceback.format_exc(), "ERROR")

# ---------- MODEL LOADING ----------
_model_files = {
    "model_efficiency": "model_efficiency.pkl",
    "model_power": "model_power.pkl",
    "model_overheat": "model_overheat.pkl",
    "model_efficiency_drop": "model_efficiency_drop.pkl",
    "model_anomaly": "model_anomaly.pkl",
    "model_runtime_forecast": "model_runtime_forecast.pkl",
    "model_maintenance": "model_maintenance.pkl",
    "model_optimization_power": "model_optimization_power.pkl",
    "model_optimization_temp": "model_optimization_temp.pkl",
    "model_autocontrol_meta": "model_autocontrol_meta.pkl"
}

_models = {}

def load_models():
    for key, fname in _model_files.items():
        path = os.path.join(MODELS_DIR, fname)
        if os.path.exists(path):
            try:
                _models[key] = load(path)
                add_log(f"Loaded model: {fname}", "INFO")
            except Exception as e:
                _models[key] = None
                add_log(f"Failed to load model {fname}: {e}", "ERROR")
        else:
            _models[key] = None
            add_log(f"Model not found: {fname}", "INFO")

if not os.path.isdir(MODELS_DIR):
    os.makedirs(MODELS_DIR, exist_ok=True)
load_models()

_status_map = {'Running': 2, 'Cooldown': 1, 'Overheated': -1, 'Idle': 0}

FEATURE_COLS = [
    'temperature', 'power_kw', 'efficiency', 'status_code',
    'temp_lag_1', 'power_lag_1', 'eff_lag_1',
    'temp_roll_3', 'power_roll_3', 'eff_roll_3',
    'temp_delta_1', 'power_delta_1', 'eff_delta_1'
]
# ---------- FEATURE BUILDING ----------
def build_features_from_history(use_last_n=3, provided=None):
    """
    Build feature dict matching FEATURE_COLS from either:
      - 'provided' dict with keys temperature (°C), power_kw, efficiency, status
      - Or by using historical_data last entries.
    Returns a dict of features (may contain floats) or None if insufficient data.
    """
    # current sample (provided takes precedence)
    if provided:
        try:
            cur_temp = float(provided.get("temperature", 0.0))
            cur_power = float(provided.get("power_kw", 0.0))
            cur_eff = float(provided.get("efficiency", 0.0))
        except Exception:
            return None
        cur_status = provided.get("status", "Idle")
    else:
        if not historical_data:
            return None
        last = historical_data[-1]
        cur_temp = float(last.get("temperature", 0.0))
        cur_power = float(last.get("power", 0.0))
        cur_eff = float(last.get("efficiency", 0.0))
        cur_status = last.get("status", "Idle")

    def get_hist_field(idx_from_end, field, fallback):
        i = len(historical_data) - 1 - idx_from_end
        if 0 <= i < len(historical_data):
            return historical_data[i].get(field, fallback)
        return fallback

    temp_lag_1 = float(get_hist_field(1, "temperature", cur_temp))
    power_lag_1 = float(get_hist_field(1, "power", cur_power))
    eff_lag_1 = float(get_hist_field(1, "efficiency", cur_eff))

    temps = []
    pows = []
    effs = []
    for i in range(0, 3):
        idx = len(historical_data) - 1 - i
        if idx >= 0:
            temps.append(historical_data[idx].get("temperature", cur_temp))
            pows.append(historical_data[idx].get("power", cur_power))
            effs.append(historical_data[idx].get("efficiency", cur_eff))
    if not temps:
        temps = [cur_temp]; pows = [cur_power]; effs = [cur_eff]

    temp_roll_3 = float(sum(temps) / len(temps))
    power_roll_3 = float(sum(pows) / len(pows))
    eff_roll_3 = float(sum(effs) / len(effs))

    temp_delta_1 = float(cur_temp - temp_lag_1)
    power_delta_1 = float(cur_power - power_lag_1)
    eff_delta_1 = float(cur_eff - eff_lag_1)

    status_code = int(_status_map.get(cur_status, 0))

    feat = {
        'temperature': float(cur_temp),
        'power_kw': float(cur_power),
        'efficiency': float(cur_eff),
        'status_code': status_code,
        'temp_lag_1': float(temp_lag_1),
        'power_lag_1': float(power_lag_1),
        'eff_lag_1': float(eff_lag_1),
        'temp_roll_3': temp_roll_3,
        'power_roll_3': power_roll_3,
        'eff_roll_3': eff_roll_3,
        'temp_delta_1': temp_delta_1,
        'power_delta_1': power_delta_1,
        'eff_delta_1': eff_delta_1
    }
    return feat

def feat_dict_to_array(feat):
    return [feat[c] for c in FEATURE_COLS]

# ---------- MACHINE CONTROL ROUTES ----------
@app.route("/start")
def start_machine():
    global machine_status, overheat_counter, cooldown_counter
    if machine_status not in ["Running", "Cooldown"]:
        machine_status = "Running"
        overheat_counter = 0
        cooldown_counter = 0
        add_log("Machine started/resumed", "INFO")
        return jsonify({"message": "Machine started/resumed", "status": machine_status})
    else:
        return jsonify({"message": "Machine already running or cooling down", "status": machine_status})

@app.route("/stop")
def stop_machine():
    global machine_status
    # keep values, only change status so resume picks previous levels
    machine_status = "Idle"
    add_log("Machine stopped (values retained)", "INFO")
    return jsonify({"message": "Machine stopped", "status": machine_status})

@app.route("/data")
def get_data():
    global machine_status, overheat_counter, cooldown_counter, current_temp, current_power, historical_data

    if machine_status == "Running":
        current_temp = smooth_change(current_temp, 65, 85, step=1.2)
        current_power = smooth_change(current_power, 300, 700, step=25, noise=10)
    elif machine_status == "Overheated":
        machine_status = "Cooldown"
        cooldown_counter = 0
        current_temp = smooth_change(current_temp, 90, 100, step=1.5)
        current_power = smooth_change(current_power, 300, 500, step=15, noise=3)
    elif machine_status == "Cooldown":
        current_temp = smooth_change(current_temp, 55, 70, step=1.8)
        current_power = smooth_change(current_power, 100, 250, step=20, noise=5)
        cooldown_counter += 1
        if cooldown_counter >= 5 and current_temp < 65:
            machine_status = "Running"
            add_log("Machine cooled down and resumed operation", "INFO")
            overheat_counter = 0
            cooldown_counter = 0
    elif machine_status == "Idle":
        current_temp = round(current_temp * 0.995 + 40 * 0.005, 2)
        current_power = round(current_power * 0.95, 2)
        if current_power < 1:
            current_power = 0.0

    if machine_status == "Idle":
        efficiency = 0.0
    else:
        base_efficiency = 100 - ((current_temp - 60) * 0.8) - ((current_power - 300) / 100)
        efficiency = max(0, min(100, round(base_efficiency, 2)))

    if machine_status == "Running":
        if current_temp > 74:
            overheat_counter += 1
        else:
            overheat_counter = max(0, overheat_counter - 1)
        if overheat_counter >= 3:
            machine_status = "Overheated"
            add_log("⚠️ Machine overheated! Entering cooldown mode", "WARNING")

    data = {
        "temperature": current_temp,
        "power_usage": current_power,
        "machine_status": machine_status,
        "efficiency": efficiency,
    }

    entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "temperature": current_temp,
        "power": round(current_power / 1000, 3),  # kW
        "efficiency": efficiency,
        "status": machine_status
    }
    historical_data.append(entry)
    if len(historical_data) > 1440:
        historical_data.pop(0)

    save_data_point_to_db(entry["time"], entry["temperature"], entry["power"], entry["efficiency"], entry["status"])
    return jsonify(data)

# ---------- LOGS API ----------
@app.route("/logs", methods=["GET"])
def get_logs():
    return jsonify(logs), 200

@app.route("/logs", methods=["POST"])
def add_custom_log():
    data = request.get_json()
    if not data or "message" not in data:
        return jsonify({"error": "Missing log message"}), 400
    add_log(data["message"], data.get("type", "INFO"))
    return jsonify({"status": "added"}), 201

@app.route("/logs/clear", methods=["DELETE"])
def clear_logs():
    logs.clear()
    add_log("All logs cleared", "INFO")
    return jsonify({"status": "cleared"}), 200

# ---------- EXPORT DATA (CSV) ----------
@app.route("/export_data")
def export_data_csv():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT created_at, time_label, temperature, power_kw, efficiency, status FROM machine_data ORDER BY id ASC")
        rows = c.fetchall()
        conn.close()
    except Exception as e:
        add_log(f"Database read error: {e}", "ERROR")
        return jsonify({"error": "Failed to read machine data"}), 500

    def generate():
        header = ["created_at", "time_label", "temperature", "power_kw", "efficiency", "status"]
        yield ",".join(header) + "\n"
        for r in rows:
            yield ",".join([str(v) for v in r]) + "\n"

    filename = f"machine_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(generate(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})

# ---------- ANALYSIS ----------
def sample_last_n_points(buffer, n=24):
    if not buffer:
        return []
    length = len(buffer)
    if length <= n:
        return buffer[:]
    step = length / float(n)
    sampled = []
    for i in range(n):
        idx = int(math.floor(i * step + (length - n * step)))
        idx = max(0, min(length - 1, int(round((i * step) + (length - n * step)))))
        sampled.append(buffer[idx])
    if len(sampled) != n:
        sampled = buffer[-n:]
    return sampled

@app.route('/get_analysis_data')
def get_analysis_data():
    if not historical_data:
        return jsonify({"error": "No data available"}), 400
    sampled = sample_last_n_points(historical_data, n=24)
    avg_eff = sum(d['efficiency'] for d in sampled) / len(sampled)
    peak_power_kw = max(d['power'] for d in sampled)
    total_runtime = sum(1 for d in sampled if d['status'] == "Running")
    runtime_percent = (total_runtime / len(sampled)) * 100
    summary = {
        "average_efficiency": round(avg_eff, 2),
        "peak_power": round(peak_power_kw, 3),
        "runtime_percent": round(runtime_percent, 2),
        "idle_percent": round(100 - runtime_percent, 2)
    }
    return jsonify({
        "summary": summary,
        "data": sampled
    })

# ---------- REPORT ----------
@app.route("/generate_report")
def generate_report():
    if not historical_data:
        return jsonify({"error": "No data available for report"}), 400
    analysis_data = sample_last_n_points(historical_data, n=24)
    avg_eff = sum(d['efficiency'] for d in analysis_data) / len(analysis_data)
    peak_power = max(d['power'] for d in analysis_data)
    runtime = sum(1 for d in analysis_data if d['status'] == "Running")
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.setTitle("Machine Performance Report")
    c.setFont("Helvetica-Bold", 18)
    c.drawString(150, 750, "Industrial Automation Report")
    c.setFont("Helvetica", 10)
    c.drawString(50, 730, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    c.drawString(50, 715, f"Machine Status: {machine_status}")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 690, "Summary Metrics:")
    c.setFont("Helvetica", 10)
    c.drawString(70, 675, f"Average Efficiency: {round(avg_eff,2)} %")
    c.drawString(70, 660, f"Peak Power Usage: {round(peak_power,3)} kW")
    c.drawString(70, 645, f"Total Runtime (sampled points): {runtime}")
    c.drawString(70, 630, f"Idle Points: {len(analysis_data) - runtime}")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, 605, "Time")
    c.drawString(120, 605, "Temp (°C)")
    c.drawString(190, 605, "Power (kW)")
    c.drawString(260, 605, "Efficiency (%)")
    c.drawString(350, 605, "Status")
    c.line(50, 600, 500, 600)
    y = 585
    for d in analysis_data:
        c.setFont("Helvetica", 9)
        c.drawString(50, y, d['time'])
        c.drawString(120, y, str(d['temperature']))
        c.drawString(190, y, str(d['power']))
        c.drawString(260, y, str(d['efficiency']))
        c.drawString(350, y, d['status'])
        y -= 15
        if y < 80:
            c.showPage()
            y = 750
    c.save()
    buffer.seek(0)
    add_log("📄 Report generated successfully", "INFO")
    return send_file(buffer, as_attachment=True,
                     download_name=f"Machine_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                     mimetype="application/pdf")

# ---------- ML: Status & Predict Endpoints ----------
@app.route("/ml/status")
def ml_status():
    out = {k: (v is not None) for k, v in _models.items()}
    return jsonify(out)

@app.route("/ml/predict_efficiency", methods=["POST"])
def ml_predict_efficiency():
    model = _models.get("model_efficiency")
    if model is None:
        return jsonify({"error": "model_efficiency not available"}), 404
    payload = request.get_json(silent=True) or {}
    feat = build_features_from_history(provided=payload if payload else None)
    if feat is None:
        return jsonify({"error": "No data available to build features"}), 400
    X = [feat_dict_to_array(feat)]
    try:
        pred = model.predict(X)[0]
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"pred_efficiency": float(pred)})

@app.route("/ml/predict_power", methods=["POST"])
def ml_predict_power():
    model = _models.get("model_power")
    if model is None:
        return jsonify({"error": "model_power not available"}), 404
    payload = request.get_json(silent=True) or {}
    feat = build_features_from_history(provided=payload if payload else None)
    if feat is None:
        return jsonify({"error": "No data available to build features"}), 400
    X = [feat_dict_to_array(feat)]
    try:
        pred = model.predict(X)[0]
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"pred_power_kw": float(pred)})

# ---------- REMAINING ML Endpoints ----------
@app.route("/ml/predict_overheat", methods=["POST"])
def ml_predict_overheat():
    model = _models.get("model_overheat")
    if model is None:
        return jsonify({"error": "model_overheat not available"}), 404
    payload = request.get_json(silent=True) or {}
    feat = build_features_from_history(provided=payload if payload else None)
    if feat is None:
        return jsonify({"error": "No data available to build features"}), 400
    X = [feat_dict_to_array(feat)]
    try:
        cls = int(model.predict(X)[0])
        proba = None
        if hasattr(model, "predict_proba"):
            try:
                proba = model.predict_proba(X)[0].tolist()
            except Exception:
                proba = None
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"overheat_class": cls, "probabilities": proba})


@app.route("/ml/predict_maintenance", methods=["POST"])
def ml_predict_maintenance():
    model = _models.get("model_maintenance")
    if model is None:
        return jsonify({"error": "model_maintenance not available"}), 404
    payload = request.get_json(silent=True) or {}
    feat = build_features_from_history(provided=payload if payload else None)
    if feat is None:
        return jsonify({"error": "No data available to build features"}), 400
    X = [feat_dict_to_array(feat)]
    try:
        cls = int(model.predict(X)[0])
        proba = None
        if hasattr(model, "predict_proba"):
            try:
                proba = model.predict_proba(X)[0].tolist()
            except Exception:
                proba = None
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"maintenance_required": cls, "probabilities": proba})


@app.route("/ml/anomaly", methods=["POST"])
def ml_anomaly():
    model = _models.get("model_anomaly")
    if model is None:
        return jsonify({"error": "model_anomaly not available"}), 404
    payload = request.get_json(silent=True) or {}
    feat = build_features_from_history(provided=payload if payload else None)
    if feat is None:
        return jsonify({"error": "No data available to build features"}), 400
    X = [feat_dict_to_array(feat)]
    try:
        pred = int(model.predict(X)[0])  # IsolationForest: 1 normal, -1 anomaly
        score = None
        try:
            if hasattr(model, "score_samples"):
                score = float(model.score_samples(X)[0])
        except Exception:
            score = None
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"anomaly_pred": pred, "is_anomaly": (pred == -1), "score": score})


@app.route("/ml/optimize", methods=["POST"])
def ml_optimize():
    m_power = _models.get("model_optimization_power")
    m_temp = _models.get("model_optimization_temp")
    if m_power is None and m_temp is None:
        return jsonify({"error": "Optimization models not available"}), 404
    payload = request.get_json(silent=True) or {}
    feat = build_features_from_history(provided=payload if payload else None)
    if feat is None:
        return jsonify({"error": "No data available to build features"}), 400
    X = [feat_dict_to_array(feat)]
    out = {}
    try:
        if m_power:
            out["opt_power_kw"] = float(m_power.predict(X)[0])
    except Exception as e:
        out["opt_power_kw_error"] = str(e)
    try:
        if m_temp:
            out["opt_temp_c"] = float(m_temp.predict(X)[0])
    except Exception as e:
        out["opt_temp_c_error"] = str(e)
    return jsonify(out)


@app.route("/ml/autocontrol", methods=["POST"])
def ml_autocontrol():
    """
    Suggest control setpoints with smoothing.
    Returns suggested raw and smoothed setpoints and deltas.
    """
    payload = request.get_json(silent=True) or {}
    feat = build_features_from_history(provided=payload if payload else None)
    if feat is None:
        return jsonify({"error": "No data available to build features"}), 400

    suggestions = {}
    m_power = _models.get("model_optimization_power")
    m_temp = _models.get("model_optimization_temp")

    if m_power:
        try:
            suggestions["power_kw"] = float(m_power.predict([feat_dict_to_array(feat)])[0])
        except Exception as e:
            suggestions["power_kw_error"] = str(e)
    if m_temp:
        try:
            suggestions["temp_c"] = float(m_temp.predict([feat_dict_to_array(feat)])[0])
        except Exception as e:
            suggestions["temp_c_error"] = str(e)

    # smoothing logic — do not permit large jumps
    out = {"suggested": suggestions}
    cur_power = feat.get("power_kw", 0.0)
    cur_temp = feat.get("temperature", 0.0)

    if "power_kw" in suggestions:
        delta_p = suggestions["power_kw"] - cur_power
        max_step_kW = 0.1  # change per actuation
        smoothed_power = cur_power + max(-max_step_kW, min(max_step_kW, delta_p))
        out["apply_power_kw"] = round(smoothed_power, 4)
        out["delta_power_kw"] = round(delta_p, 4)

    if "temp_c" in suggestions:
        delta_t = suggestions["temp_c"] - cur_temp
        max_step_t = 1.0
        smoothed_temp = cur_temp + max(-max_step_t, min(max_step_t, delta_t))
        out["apply_temp_c"] = round(smoothed_temp, 3)
        out["delta_temp_c"] = round(delta_t, 3)

    return jsonify(out)


# ---------- ML INSIGHTS (aggregate endpoint) ----------
@app.route("/ml/insights", methods=["POST"])
def ml_insights():
    """
    Aggregates multiple model outputs into human-friendly insights and recommendations.
    Payload: optional current sample { temperature, power_kw, efficiency, status }.
    Returns: predictions, flags, short recommendations.
    Also persists ML output into ml_history table.
    """
    payload = request.get_json(silent=True) or {}
    feat = build_features_from_history(provided=payload if payload else None)
    if feat is None:
        return jsonify({"error": "No data available to build features"}), 400

    insights = {}
    recs = []

    # 1) Efficiency & power predictions
    if _models.get("model_efficiency"):
        try:
            pred_eff = float(_models["model_efficiency"].predict([feat_dict_to_array(feat)])[0])
            insights["pred_efficiency"] = round(pred_eff, 2)
        except Exception as e:
            insights["pred_efficiency_error"] = str(e)

    if _models.get("model_power"):
        try:
            pred_power = float(_models["model_power"].predict([feat_dict_to_array(feat)])[0])
            insights["pred_power_kw"] = round(pred_power, 4)
        except Exception as e:
            insights["pred_power_error"] = str(e)

    # 2) Overheat risk
    if _models.get("model_overheat"):
        try:
            ov_cls = int(_models["model_overheat"].predict([feat_dict_to_array(feat)])[0])
            ov_proba = None
            if hasattr(_models["model_overheat"], "predict_proba"):
                try:
                    ov_proba = _models["model_overheat"].predict_proba([feat_dict_to_array(feat)])[0].tolist()
                except Exception:
                    ov_proba = None
            insights["overheat_class"] = ov_cls
            insights["overheat_proba"] = ov_proba
            if ov_cls == 1:
                recs.append("High overheat risk predicted — consider reducing power or initiating cooldown.")
        except Exception as e:
            insights["overheat_error"] = str(e)

    # 3) Maintenance prediction
    if _models.get("model_maintenance"):
        try:
            m_cls = int(_models["model_maintenance"].predict([feat_dict_to_array(feat)])[0])
            m_proba = None
            if hasattr(_models["model_maintenance"], "predict_proba"):
                try:
                    m_proba = _models["model_maintenance"].predict_proba([feat_dict_to_array(feat)])[0].tolist()
                except Exception:
                    m_proba = None
            insights["maintenance_required"] = m_cls
            insights["maintenance_proba"] = m_proba
            if m_cls == 1:
                recs.append("Maintenance likely needed in near future — schedule inspection.")
        except Exception as e:
            insights["maintenance_error"] = str(e)

    # 4) Anomaly detection
    if _models.get("model_anomaly"):
        try:
            an_pred = int(_models["model_anomaly"].predict([feat_dict_to_array(feat)])[0])  # -1 anomaly, 1 normal
            an_score = None
            try:
                if hasattr(_models["model_anomaly"], "score_samples"):
                    an_score = float(_models["model_anomaly"].score_samples([feat_dict_to_array(feat)])[0])
            except Exception:
                an_score = None
            insights["anomaly_pred"] = an_pred
            insights["anomaly_score"] = an_score
            if an_pred == -1:
                recs.append("Anomalous behavior detected — investigate sensors and process logs.")
        except Exception as e:
            insights["anomaly_error"] = str(e)

    # 5) Optimization suggestion (power/temp)
    opt = {}
    if _models.get("model_optimization_power"):
        try:
            p = float(_models["model_optimization_power"].predict([feat_dict_to_array(feat)])[0])
            opt["opt_power_kw"] = round(p, 4)
        except Exception as e:
            opt["opt_power_kw_error"] = str(e)
    if _models.get("model_optimization_temp"):
        try:
            t = float(_models["model_optimization_temp"].predict([feat_dict_to_array(feat)])[0])
            opt["opt_temp_c"] = round(t, 3)
        except Exception as e:
            opt["opt_temp_c_error"] = str(e)
    if opt:
        insights["optimization"] = opt
        # simple recommendation based on difference
        try:
            cur_p = feat.get("power_kw", 0.0)
            if "opt_power_kw" in opt:
                dp = opt["opt_power_kw"] - cur_p
                if abs(dp) > 0.2:
                    recs.append(f"Optimization suggests changing power by {round(dp,3)} kW.")
        except Exception:
            pass

    # 6) Runtime forecast (if available)
    if _models.get("model_runtime_forecast"):
        try:
            rt = float(_models["model_runtime_forecast"].predict([feat_dict_to_array(feat)])[0])
            insights["runtime_forecast_steps"] = round(rt, 2)
            if rt < 3:
                recs.append("Runtime forecast is short — consider checking process continuity.")
        except Exception as e:
            insights["runtime_forecast_error"] = str(e)

    # Compose final response
    response = {
        "features_used": feat,
        "insights": insights,
        "recommendations": recs,
        "models_loaded": {k: (v is not None) for k, v in _models.items()}
    }

    # Add a top-level short summary string
    summary_parts = []
    if insights.get("overheat_class") == 1:
        summary_parts.append("Overheat risk HIGH")
    if insights.get("anomaly_pred") == -1:
        summary_parts.append("Anomalous reading")
    if insights.get("maintenance_required") == 1:
        summary_parts.append("Maintenance likely")
    if insights.get("pred_efficiency") is not None:
        summary_parts.append(f"Pred Eff: {insights['pred_efficiency']}%")
    response["summary"] = "; ".join(summary_parts) if summary_parts else "No critical issues detected."

    # Persist ML insight (non-blocking style: try-catch but still return response)
    try:
        # store time_label as HH:MM:SS to help align with machine_data table
        time_label = datetime.now().strftime("%H:%M:%S")
        save_ml_insight_to_db(time_label, feat, insights)
    except Exception as e:
        add_log(f"Failed to persist ml insight: {e}", "ERROR")

    return jsonify(response)


# ---------- NEW: ML HISTORY & STATS ENDPOINTS ----------
@app.route("/ml/history", methods=["GET"])
def ml_history():
    """
    Returns ML history rows stored in DB.
    Query params:
      - limit (int): max number of rows, default 200
      - since (ISO datetime) optional to fetch only newer records
    """
    limit = int(request.args.get("limit", 200))
    since = request.args.get("since", None)
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        if since:
            c.execute("SELECT id, timestamp, time_label, features_json, pred_efficiency, pred_power, overheat_class, maintenance_required, anomaly_pred, anomaly_score, opt_power_kw, opt_temp_c, overheat_proba, maintenance_proba, runtime_forecast FROM ml_history WHERE timestamp > ? ORDER BY id DESC LIMIT ?", (since, limit))
        else:
            c.execute("SELECT id, timestamp, time_label, features_json, pred_efficiency, pred_power, overheat_class, maintenance_required, anomaly_pred, anomaly_score, opt_power_kw, opt_temp_c, overheat_proba, maintenance_proba, runtime_forecast FROM ml_history ORDER BY id DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        conn.close()
        # convert to list of dicts (ascending time)
        out = []
        for r in reversed(rows):
            out.append({
                "id": r[0],
                "timestamp": r[1],
                "time_label": r[2],
                "features": json.loads(r[3]) if r[3] else {},
                "pred_efficiency": r[4],
                "pred_power_kw": r[5],
                "overheat_class": r[6],
                "maintenance_required": r[7],
                "anomaly_pred": r[8],
                "anomaly_score": r[9],
                "opt_power_kw": r[10],
                "opt_temp_c": r[11],
                "overheat_proba": r[12],
                "maintenance_proba": r[13],
                "runtime_forecast_steps": r[14]
            })
        return jsonify({"count": len(out), "rows": out})
    except Exception as e:
        add_log(f"Failed to read ml_history: {e}", "ERROR")
        return jsonify({"error": "Failed to read ml_history"}), 500

@app.route("/ml/stats", methods=["GET"])
def ml_stats():
    """
    Compute basic ML stats (MAE, RMSE for pred_efficiency against recent actual efficiency),
    anomaly counts, simple drift check (mean of last half vs previous half).
    Query params:
      - limit: how many recent ml_history rows to consider (default 200)
    """
    limit = int(request.args.get("limit", 200))
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # fetch recent ml_history
        c.execute("SELECT id, timestamp, time_label, pred_efficiency, pred_power, anomaly_pred, anomaly_score FROM ml_history ORDER BY id DESC LIMIT ?", (limit,))
        ml_rows = c.fetchall()
        ml_rows = list(reversed(ml_rows))  # chronological
        # fetch matching machine_data points by time_label where possible
        preds = []
        actuals = []
        anomaly_preds = []
        anomaly_scores = []
        times = []
        for r in ml_rows:
            mid, ts, tlabel, pred_eff, pred_power, anomaly_pred, anomaly_score = r
            # try to find latest machine_data with same time_label
            actual_eff = None
            if tlabel:
                c.execute("SELECT efficiency FROM machine_data WHERE time_label = ? ORDER BY id DESC LIMIT 1", (tlabel,))
                row = c.fetchone()
                if row:
                    actual_eff = row[0]
            # fallback: if no match, try approximate by grabbing last inserted machine_data
            if actual_eff is None:
                c.execute("SELECT efficiency FROM machine_data ORDER BY id DESC LIMIT 1")
                row = c.fetchone()
                if row:
                    actual_eff = row[0]
            if pred_eff is not None and actual_eff is not None:
                try:
                    preds.append(float(pred_eff))
                    actuals.append(float(actual_eff))
                    times.append(ts)
                except Exception:
                    pass
            # anomaly arrays
            if anomaly_pred is not None:
                anomaly_preds.append(int(anomaly_pred))
            if anomaly_score is not None:
                try:
                    anomaly_scores.append(float(anomaly_score))
                except Exception:
                    pass

        stats = {}
        if preds and actuals and len(preds) == len(actuals):
            # MAE, RMSE
            diffs = [abs(a - p) for a, p in zip(actuals, preds)]
            mae = sum(diffs) / len(diffs)
            rmse = math.sqrt(sum((a - p) ** 2 for a, p in zip(actuals, preds)) / len(actuals))
            stats["mae_efficiency"] = round(mae, 4)
            stats["rmse_efficiency"] = round(rmse, 4)
            # simple accuracy: within +/- threshold (e.g., 5%)
            within5 = sum(1 for a, p in zip(actuals, preds) if abs(a - p) <= 5) / len(preds)
            stats["accuracy_within_5pct"] = round(within5, 4)
            stats["samples_compared"] = len(preds)
        else:
            stats["samples_compared"] = 0

        # anomaly summary
        if anomaly_preds:
            # count of anomalies predicted
            anomalies_count = sum(1 for v in anomaly_preds if v == -1)
            stats["anomaly_pred_count"] = anomalies_count
            stats["anomaly_pred_total"] = len(anomaly_preds)
            if anomaly_scores:
                stats["anomaly_score_avg"] = round(sum(anomaly_scores) / len(anomaly_scores), 4)
        else:
            stats["anomaly_pred_count"] = 0
            stats["anomaly_pred_total"] = 0

        # simple drift detection on pred_efficiency: compare mean of first half vs second half
        eff_values = [r[3] for r in ml_rows if r[3] is not None]
        drift_flag = False
        drift_info = {}
        if len(eff_values) >= 6:
            mid = len(eff_values) // 2
            first = eff_values[:mid]
            second = eff_values[mid:]
            mean_first = statistics.mean(first)
            mean_second = statistics.mean(second)
            # relative change
            if mean_first != 0:
                rel_change = (mean_second - mean_first) / abs(mean_first)
            else:
                rel_change = 0.0
            drift_info["mean_first"] = round(mean_first, 4)
            drift_info["mean_second"] = round(mean_second, 4)
            drift_info["relative_change"] = round(rel_change, 4)
            # flag if relative change > 5%
            if abs(rel_change) > 0.05:
                drift_flag = True
            stats["drift"] = {"drift_flag": drift_flag, "details": drift_info}
        else:
            stats["drift"] = {"drift_flag": False, "details": "insufficient samples"}

        conn.close()
        return jsonify(stats)
    except Exception as e:
        add_log(f"Failed to compute ml stats: {e}", "ERROR")
        add_log(traceback.format_exc(), "ERROR")
        return jsonify({"error": "Failed to compute stats"}), 500

@app.route("/ml/history/clear", methods=["DELETE"])
def clear_ml_history():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM ml_history")
        conn.commit()
        conn.close()
        add_log("ML history cleared", "INFO")
        return jsonify({"status": "cleared"}), 200
    except Exception as e:
        add_log(f"Failed to clear ml_history: {e}", "ERROR")
        return jsonify({"error": "Failed to clear ml_history"}), 500

# ---------- MAIN ----------
if __name__ == "__main__":
    # ensure DB and models dir exist and models are loaded
    os.makedirs(MODELS_DIR, exist_ok=True)
    init_machine_db()
    load_models()
    add_log("Server starting; loaded models status: " + ", ".join([f"{k}:{bool(v)}" for k,v in _models.items()]), "INFO")
    app.run(debug=True, port=5500)
