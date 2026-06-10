"""
train_model.py

Train a suite of ML models from your machine_data.db and save them to /models.

This updated version fixes NaN alignment issues and deprecation warnings,
and guards each training step against NaN / single-class targets.
"""
import os
import sqlite3
import math
from datetime import datetime
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier, IsolationForest
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, roc_auc_score, accuracy_score
from joblib import dump

# ----------------------
# Configuration
# ----------------------
DB_FILE = "machine_data.db"
TABLE_NAME = "machine_data"
MODELS_DIR = "models"
MIN_ROWS_FOR_TRAIN = 100  # minimal recommended rows, warn if less
RANDOM_STATE = 42

# create models dir
os.makedirs(MODELS_DIR, exist_ok=True)

# ----------------------
# Utilities
# ----------------------
def load_db_to_df(db_file=DB_FILE, table=TABLE_NAME):
    conn = sqlite3.connect(db_file)
    df = pd.read_sql_query(f"SELECT * FROM {table} ORDER BY id ASC", conn)
    conn.close()
    return df

def safe_print(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

# ----------------------
# Data preparation
# ----------------------
safe_print("Loading data from DB...")
if not os.path.exists(DB_FILE):
    raise SystemExit(f"Database file '{DB_FILE}' not found. Run the app to generate data, or place your DB in project root.")

df = load_db_to_df()
if df.empty:
    raise SystemExit("No rows found in machine_data table. Collect some data by running the dashboard first.")

# Ensure expected columns exist. the schema we used earlier contains:
# (id, created_at, time_label, temperature, power_kw, efficiency, status)
expected_cols = set(['id', 'created_at', 'time_label', 'temperature', 'power_kw', 'efficiency', 'status'])
if not expected_cols.issubset(set(df.columns)):
    safe_print("Warning: table columns don't match expected. Available columns: " + ", ".join(df.columns))

# Convert numeric columns
df['temperature'] = pd.to_numeric(df['temperature'], errors='coerce')
df['power_kw'] = pd.to_numeric(df['power_kw'], errors='coerce')
df['efficiency'] = pd.to_numeric(df['efficiency'], errors='coerce')

# basic cleaning: drop rows with NaNs in core features
df = df.dropna(subset=['temperature', 'power_kw', 'efficiency']).reset_index(drop=True)

safe_print(f"Loaded {len(df)} valid rows after cleanup.")

if len(df) < MIN_ROWS_FOR_TRAIN:
    safe_print(f"Warning: only {len(df)} rows available — models may underperform. Recommended >= {MIN_ROWS_FOR_TRAIN} rows.")

# ----------------------
# Feature engineering
# ----------------------
safe_print("Feature engineering...")

# encode status
df['status_str'] = df['status'].astype(str)
status_mapping = {'Running': 2, 'Cooldown': 1, 'Overheated': -1, 'Idle': 0}
df['status_code'] = df['status_str'].map(status_mapping).fillna(0).astype(int)

# create timestamps index (optional)
try:
    df['created_at_dt'] = pd.to_datetime(df['created_at'])
except Exception:
    df['created_at_dt'] = pd.NaT

# sort by created_at if available else keep id order
if df['created_at_dt'].notna().any():
    df = df.sort_values('created_at_dt').reset_index(drop=True)

# create lag features and rolling stats
LAGS = [1, 2, 3]
for lag in LAGS:
    df[f'temp_lag_{lag}'] = df['temperature'].shift(lag)
    df[f'power_lag_{lag}'] = df['power_kw'].shift(lag)
    df[f'eff_lag_{lag}'] = df['efficiency'].shift(lag)
    df[f'status_lag_{lag}'] = df['status_code'].shift(lag)

# rolling means
df['temp_roll_3'] = df['temperature'].rolling(window=3, min_periods=1).mean()
df['power_roll_3'] = df['power_kw'].rolling(window=3, min_periods=1).mean()
df['eff_roll_3'] = df['efficiency'].rolling(window=3, min_periods=1).mean()

# deltas
df['temp_delta_1'] = df['temperature'] - df['temp_lag_1']
df['power_delta_1'] = df['power_kw'] - df['power_lag_1']
df['eff_delta_1'] = df['efficiency'] - df['eff_lag_1']

# ----------------------
# Targets creation (heuristic) — compute on full df to avoid alignment issues
# ----------------------
safe_print("Creating targets for each model (heuristics used where necessary)...")

# 1) Efficiency prediction (next-step regression)
df['eff_next'] = df['efficiency'].shift(-1)

# 2) Power prediction (next-step regression)
df['power_next'] = df['power_kw'].shift(-1)

# 3) Overheat risk: if within next 3 steps status becomes 'Overheated' or temp > 85
def compute_overheat_risk(series_temp, series_status, horizon=3):
    out = []
    n = len(series_temp)
    for i in range(n):
        risk = 0
        for j in range(1, horizon+1):
            idx = i + j
            if idx < n:
                if series_temp.iloc[idx] > 85 or series_status.iloc[idx] == 'Overheated':
                    risk = 1
                    break
        out.append(risk)
    return np.array(out, dtype=int)

df['overheat_risk'] = compute_overheat_risk(df['temperature'], df['status_str'], horizon=3)

# 4) Efficiency drop detection: if avg next-3 efficiency decreases by >5% relative to current
def future_eff_drop(eff_series, drop_pct=5, horizon=3):
    out = []
    n = len(eff_series)
    for i in range(n):
        future_vals = []
        for j in range(1, horizon+1):
            idx = i + j
            if idx < n:
                future_vals.append(eff_series.iloc[idx])
        if not future_vals:
            out.append(0)
            continue
        current = eff_series.iloc[i]
        future_avg = np.mean(future_vals)
        out.append(1 if (current - future_avg) >= (drop_pct / 100.0 * current) else 0)
    return np.array(out, dtype=int)

df['eff_drop'] = future_eff_drop(df['efficiency'], drop_pct=5, horizon=3)

# 5) Maintenance label heuristic: if in the next 24 samples we observe > 2 'Overheated' or many efficiency drops
def compute_maintenance_label(status_series, eff_drop_series, future_window=24, overheat_thresh=2, drop_thresh=3):
    out = []
    n = len(status_series)
    for i in range(n):
        ov_count = 0
        drop_count = 0
        for j in range(1, future_window+1):
            idx = i + j
            if idx < n:
                if status_series.iloc[idx] == 'Overheated':
                    ov_count += 1
                if eff_drop_series[idx] == 1:
                    drop_count += 1
        out.append(1 if (ov_count >= overheat_thresh or drop_count >= drop_thresh) else 0)
    return np.array(out, dtype=int)

df['maintenance'] = compute_maintenance_label(df['status_str'], df['eff_drop'], future_window=24)

# 6) Runtime forecast: count consecutive "Running" steps until non-running from current index
def compute_runtime_until_nonrunning(status_series):
    out = []
    n = len(status_series)
    for i in range(n):
        count = 0
        for j in range(i, n):
            if status_series.iloc[j] == 'Running':
                count += 1
            else:
                break
        out.append(count)
    return np.array(out, dtype=int)

df['runtime_steps'] = compute_runtime_until_nonrunning(df['status_str'])

# 7) Optimization target: within next 5 steps, choose pair that gave highest efficiency
def compute_optimal_targets(temp_series, power_series, eff_series, horizon=5):
    opt_power = []
    opt_temp = []
    n = len(eff_series)
    for i in range(n):
        best_idx = i
        best_eff = eff_series.iloc[i]
        for j in range(1, horizon+1):
            idx = i + j
            if idx < n:
                if eff_series.iloc[idx] > best_eff:
                    best_eff = eff_series.iloc[idx]
                    best_idx = idx
        opt_power.append(power_series.iloc[best_idx])
        opt_temp.append(temp_series.iloc[best_idx])
    return np.array(opt_temp, dtype=float), np.array(opt_power, dtype=float)

opt_temp_all, opt_power_all = compute_optimal_targets(df['temperature'], df['power_kw'], df['efficiency'], horizon=5)
df['opt_power'] = opt_power_all
df['opt_temp'] = opt_temp_all

# ----------------------
# Final features for supervised models
# ----------------------
FEATURE_COLS = [
    'temperature', 'power_kw', 'efficiency', 'status_code',
    'temp_lag_1', 'power_lag_1', 'eff_lag_1',
    'temp_roll_3', 'power_roll_3', 'eff_roll_3',
    'temp_delta_1', 'power_delta_1', 'eff_delta_1'
]

# Build df_model by dropping rows where features are NaN (due to lags)
df_model = df.dropna(subset=FEATURE_COLS).reset_index(drop=True)
safe_print(f"{len(df_model)} rows available after dropping rows with missing features.")

# ----------------------
# Helper: robust train and save wrappers (handle NaNs in y)
# ----------------------
def safe_mask_xy(X, y):
    """
    Ensure X and y are numpy arrays and remove rows where y is NaN.
    Returns (X_clean, y_clean).
    """
    X_arr = np.asarray(X)
    y_arr = np.asarray(y)
    if y_arr.ndim > 1 and y_arr.shape[1] == 1:
        y_arr = y_arr.ravel()
    mask = ~np.isnan(y_arr)
    if mask.sum() == 0:
        return None, None
    return X_arr[mask], y_arr[mask]

def train_and_save_regression(name, X, y):
    safe_print(f"Training regression model: {name} ...")
    Xc, yc = safe_mask_xy(X, y)
    if Xc is None:
        safe_print(f"  Skipping {name}: target contains only NaNs.")
        return None
    # If yc has zero variance (all same value), skip training
    if np.nanstd(yc) == 0:
        safe_print(f"  Skipping {name}: target has zero variance (constant value).")
        return None
    X_train, X_test, y_train, y_test = train_test_split(Xc, yc, test_size=0.2, random_state=RANDOM_STATE)
    model = RandomForestRegressor(n_estimators=200, random_state=RANDOM_STATE, n_jobs=-1)
    model.fit(X_train, y_train)
    preds = model.predict(X_test)
    rmse = math.sqrt(mean_squared_error(y_test, preds))
    safe_print(f"  {name} RMSE: {rmse:.4f} (trained on {len(yc)} rows)")
    dump(model, os.path.join(MODELS_DIR, f"{name}.pkl"))
    safe_print(f"  Saved: {os.path.join(MODELS_DIR, f'{name}.pkl')}")
    return model

def train_and_save_classifier(name, X, y):
    safe_print(f"Training classifier model: {name} ...")
    Xc, yc = safe_mask_xy(X, y)
    if Xc is None:
        safe_print(f"  Skipping {name}: target contains only NaNs.")
        return None
    # must have at least 2 classes
    unique_vals = np.unique(yc)
    if len(unique_vals) < 2:
        safe_print(f"  Skipping {name}: only one class present in target ({unique_vals}).")
        return None
    # if extremely imbalanced, RF still can train but we note it
    X_train, X_test, y_train, y_test = train_test_split(Xc, yc, test_size=0.2, random_state=RANDOM_STATE, stratify=yc if len(unique_vals)>1 else None)
    model = RandomForestClassifier(n_estimators=200, random_state=RANDOM_STATE, n_jobs=-1)
    model.fit(X_train, y_train)
    preds = model.predict(X_test)
    acc = accuracy_score(y_test, preds)
    auc = None
    try:
        if len(np.unique(y_test)) > 1:
            proba = model.predict_proba(X_test)[:, 1]
            auc = roc_auc_score(y_test, proba)
    except Exception:
        auc = None
    safe_print(f"  {name} Accuracy: {acc:.4f}, AUC: {auc}")
    dump(model, os.path.join(MODELS_DIR, f"{name}.pkl"))
    safe_print(f"  Saved: {os.path.join(MODELS_DIR, f'{name}.pkl')}")
    return model

# ----------------------
# 1. model_efficiency (regression -> predict eff_next)
# ----------------------
if 'eff_next' in df_model.columns:
    X = df_model[FEATURE_COLS]
    y = df_model['eff_next'].ffill().values  # forward-fill only to reduce NaNs in tail
    model_eff = train_and_save_regression("model_efficiency", X, y)
else:
    safe_print("Skipping model_efficiency: no target column eff_next.")

# ----------------------
# 2. model_power (regression -> predict power_next)
# ----------------------
if 'power_next' in df_model.columns:
    X = df_model[FEATURE_COLS]
    y = df_model['power_next'].ffill().values
    model_power = train_and_save_regression("model_power", X, y)
else:
    safe_print("Skipping model_power: no target column power_next.")

# ----------------------
# 3. model_overheat (classification)
# ----------------------
if 'overheat_risk' in df_model.columns:
    X = df_model[FEATURE_COLS]
    y = df_model['overheat_risk'].astype(int).values
    model_overheat = train_and_save_classifier("model_overheat", X, y)
else:
    safe_print("Skipping model_overheat: no target column overheat_risk.")

# ----------------------
# 4. model_efficiency_drop (classification)
# ----------------------
if 'eff_drop' in df_model.columns:
    X = df_model[FEATURE_COLS]
    y = df_model['eff_drop'].astype(int).values
    model_eff_drop = train_and_save_classifier("model_efficiency_drop", X, y)
else:
    safe_print("Skipping model_efficiency_drop: no target column eff_drop.")

# ----------------------
# 5. model_anomaly (IsolationForest unsupervised)
# ----------------------
safe_print("Training IsolationForest for anomaly detection (model_anomaly)...")
X_anom = df_model[FEATURE_COLS].values
iso = IsolationForest(n_estimators=200, contamination=0.02, random_state=RANDOM_STATE)
iso.fit(X_anom)
dump(iso, os.path.join(MODELS_DIR, "model_anomaly.pkl"))
safe_print(f"  Saved: {os.path.join(MODELS_DIR, 'model_anomaly.pkl')}")

# ----------------------
# 6. model_runtime_forecast (regression -> runtime_steps)
# ----------------------
if 'runtime_steps' in df_model.columns:
    X = df_model[FEATURE_COLS]
    y = df_model['runtime_steps'].astype(float).values
    model_runtime = train_and_save_regression("model_runtime_forecast", X, y)
else:
    safe_print("Skipping model_runtime_forecast: no runtime_steps target.")

# ----------------------
# 7. model_maintenance (classification)
# ----------------------
if 'maintenance' in df_model.columns:
    X = df_model[FEATURE_COLS]
    y = df_model['maintenance'].astype(int).values
    model_maint = train_and_save_classifier("model_maintenance", X, y)
else:
    safe_print("Skipping model_maintenance: no maintenance target.")

# ----------------------
# 8. model_optimization (regression -> opt_power, opt_temp)
#    We'll train models that predict opt_power and opt_temp (two separate regressors)
# ----------------------
if 'opt_power' in df_model.columns and 'opt_temp' in df_model.columns:
    X = df_model[FEATURE_COLS]
    y_power = df_model['opt_power'].astype(float).values
    y_temp = df_model['opt_temp'].astype(float).values
    model_opt_power = train_and_save_regression("model_optimization_power", X, y_power)
    model_opt_temp = train_and_save_regression("model_optimization_temp", X, y_temp)
    # save a simple meta-model file as indication for auto-control (we'll combine these later)
    dump({'power_model': 'model_optimization_power.pkl', 'temp_model': 'model_optimization_temp.pkl'},
         os.path.join(MODELS_DIR, "model_optimization_meta.pkl"))
    safe_print("  Saved optimization meta mapping.")
else:
    safe_print("Skipping model_optimization: opt_power/opt_temp not available.")

# ----------------------
# 9. model_autocontrol (decision/regression)
#    Create a tiny controller metadata file pointing to optimization models.
# ----------------------
controller_meta = {
    "controller_type": "optimum_regression",
    "power_model": "model_optimization_power.pkl" if os.path.exists(os.path.join(MODELS_DIR, "model_optimization_power.pkl")) else None,
    "temp_model": "model_optimization_temp.pkl" if os.path.exists(os.path.join(MODELS_DIR, "model_optimization_temp.pkl")) else None,
    "notes": "Use these two models to suggest next power_kW and temp. Wrap with smoothing when applying to machine actuators."
}
dump(controller_meta, os.path.join(MODELS_DIR, "model_autocontrol_meta.pkl"))
safe_print(f"  Saved controller meta: {os.path.join(MODELS_DIR, 'model_autocontrol_meta.pkl')}")

safe_print("All done! Models are saved in the 'models' folder.")
safe_print("Important notes:")
safe_print(" - Targets like maintenance and efficiency drop are heuristically generated from historical data.")
safe_print(" - Anomaly detector is unsupervised; tune contamination param if you expect more/less anomalies.")
safe_print(" - For production use, retrain periodically and validate with new labeled events.")
