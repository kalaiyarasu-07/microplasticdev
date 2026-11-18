from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import pandas as pd
import numpy as np
import os, json, uuid
from datetime import datetime
import plotly
import plotly.graph_objects as go
from scipy import signal
from sklearn.ensemble import IsolationForest

BASE = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE, "data")
UPLOAD_DIR = os.path.join(BASE, "uploads")
SAVED_DIR = os.path.join(BASE, "saved_visualizations")
REPORT_DIR = os.path.join(BASE, "generated_reports")
for d in (UPLOAD_DIR, SAVED_DIR, REPORT_DIR):
    os.makedirs(d, exist_ok=True)

FRONTEND_DIR = os.path.join(BASE, "..", "frontend")
app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
CORS(app)
datasets = {
    "aquapulse_sample_dataset": os.path.join(DATA_DIR, "aquapulse_sample_dataset.csv")
}

@app.get("/")
def frontend():
    return send_from_directory(FRONTEND_DIR, "index.html")

def load_dataset(dataset_id):
    path = datasets.get(dataset_id)
    if not path or not os.path.isfile(path):
        raise ValueError("Dataset not found")
    return pd.read_csv(path)

def column_type(series):
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    try:
        parsed = pd.to_datetime(series.dropna().head(20), errors="raise")
        return "datetime" if len(parsed) else "categorical"
    except Exception:
        return "categorical"

@app.get("/api/health")
def health():
    return jsonify(status="healthy", datasets=len(datasets), timestamp=datetime.utcnow().isoformat())

@app.post("/api/datasets/upload")
def upload_dataset():
    file = request.files.get("file")
    if not file or not file.filename.lower().endswith(".csv"):
        return jsonify(error="Please upload a valid CSV file"), 400
    dataset_id = "upload_" + uuid.uuid4().hex[:10]
    safe_name = f"{dataset_id}.csv"
    path = os.path.join(UPLOAD_DIR, safe_name)
    file.save(path)
    try:
        df = pd.read_csv(path)
        if len(df) > 100000:
            os.remove(path)
            return jsonify(error="Dataset exceeds the 100,000 row upload limit"), 400
    except Exception as exc:
        os.remove(path)
        return jsonify(error=f"Invalid CSV: {exc}"), 400
    datasets[dataset_id] = path
    return jsonify(id=dataset_id, name=file.filename, rows=len(df), columns=len(df.columns))

@app.get("/api/datasets")
def get_datasets():
    result = []
    for dataset_id, path in datasets.items():
        df = pd.read_csv(path)
        name = "aquapulse_sample_dataset.csv" if dataset_id == "aquapulse_sample_dataset" else os.path.basename(path)
        result.append({"id": dataset_id, "name": name, "rows": len(df), "columns": len(df.columns)})
    return jsonify(result)

@app.get("/api/datasets/<dataset_id>/preview")
def preview(dataset_id):
    df = load_dataset(dataset_id)
    page = max(int(request.args.get("page", 1)), 1)
    limit = min(max(int(request.args.get("limit", 20)), 1), 100)
    start = (page - 1) * limit
    return jsonify(columns=df.columns.tolist(), rows=df.iloc[start:start+limit].where(pd.notna(df.iloc[start:start+limit]), None).to_dict("records"), total=len(df), page=page)

@app.get("/api/datasets/<dataset_id>/columns")
def columns(dataset_id):
    df = load_dataset(dataset_id)
    result = [{"name": c, "type": column_type(df[c]), "missing": int(df[c].isna().sum())} for c in df.columns]
    return jsonify(result)

@app.get("/api/datasets/<dataset_id>/statistics")
def statistics(dataset_id):
    df = load_dataset(dataset_id)
    return jsonify(df.describe(include="all").where(pd.notna(df.describe(include="all")), None).to_dict())

@app.delete("/api/datasets/<dataset_id>")
def delete_dataset(dataset_id):
    if dataset_id == "aquapulse_sample_dataset":
        return jsonify(error="The supplied sample dataset cannot be removed"), 400
    path = datasets.pop(dataset_id, None)
    if path:
        os.remove(path)
    return jsonify(success=True)

@app.get("/api/dashboard/summary")
def dashboard_summary():
    df = load_dataset(request.args.get("dataset", "aquapulse_sample_dataset"))
    device = request.args.get("device")
    if device:
        df = df[df["Device_ID"].astype(str) == device]
    numeric = df.select_dtypes(include="number")
    classification = df["Classification"].value_counts().to_dict() if "Classification" in df else {}
    readings = []
    for _, row in df.tail(100).iterrows():
        readings.append({"timestamp": str(row.get("Timestamp", "")), "piezo": float(row.get("Piezoelectric_Reading", 0)), "ultrasonic": float(row.get("Ultrasonic_Response", 0))})
    daily = {}
    if "Timestamp" in df:
        daily = df.assign(Date=pd.to_datetime(df["Timestamp"]).dt.strftime("%Y-%m-%d")).groupby("Date").size().tail(30).to_dict()
    return jsonify({
        "observations": len(df),
        "devices": int(df["Device_ID"].nunique()) if "Device_ID" in df else 0,
        "average_piezo": round(float(df["Piezoelectric_Reading"].mean()), 3) if "Piezoelectric_Reading" in df else None,
        "average_ultrasonic": round(float(df["Ultrasonic_Response"].mean()), 3) if "Ultrasonic_Response" in df else None,
        "particle_responses": int(classification.get("Particle-Like Response", 0)),
        "normal_observations": int(classification.get("Normal Water Observation", 0)),
        "further_analysis": int(classification.get("Requires Further Analysis", 0)),
        "latest_timestamp": str(df["Timestamp"].max()) if "Timestamp" in df else None,
        "classification": classification,
        "readings": readings,
        "daily": daily,
        "devices_counts": df["Device_ID"].value_counts().to_dict() if "Device_ID" in df else {}
    })

@app.get("/api/visualization/types")
def visualization_types():
    types = ["Line Chart","Bar Chart","Horizontal Bar Chart","Scatter Plot","Area Chart","Pie Chart","Donut Chart","Histogram","Box Plot","Violin Plot","Heatmap","Correlation Matrix","Bubble Chart","3D Scatter Plot","Time Series Line Chart","Moving Average Chart","GPS Scatter Map","Distribution Plot","Regression Plot","Outlier Visualization","Raw Signal Visualization","Frequency Spectrum"]
    return jsonify(types)

@app.post("/api/visualization/generate")
def generate_visualization():
    body = request.get_json(silent=True) or {}
    dataset_id = body.get("dataset", "aquapulse_sample_dataset")
    df = load_dataset(dataset_id)
    chart_type = body.get("chartType", "Line Chart")
    x = body.get("x")
    y = body.get("y")
    color = body.get("color")
    title = body.get("title", chart_type)
    if x and x not in df.columns:
        return jsonify(error="Invalid X-axis column"), 400
    if y and y not in df.columns:
        return jsonify(error="Invalid Y-axis column"), 400
    if color and color not in df.columns:
        return jsonify(error="Invalid grouping column"), 400

    fig = go.Figure()
    violet, lavender = "#8B5CF6", "#C4B5FD"
    chart_lower = chart_type.lower()
    if "pie" in chart_lower or "donut" in chart_lower:
        counts = df[x or df.columns[0]].value_counts().head(20)
        fig.add_trace(go.Pie(labels=counts.index.astype(str), values=counts.values, hole=.58 if "donut" in chart_lower else 0))
    elif "histogram" in chart_lower or "distribution" in chart_lower:
        fig.add_trace(go.Histogram(x=df[y or x or df.select_dtypes("number").columns[0]], marker_color=violet))
    elif "correlation" in chart_lower or "heatmap" in chart_lower:
        corr = df.select_dtypes("number").corr()
        fig.add_trace(go.Heatmap(z=corr.values, x=corr.columns, y=corr.columns, colorscale=[[0,"#17131F"],[.5,"#7C3AED"],[1,"#C4B5FD"]]))
    elif "3d" in chart_lower:
        nums = df.select_dtypes("number").columns
        if len(nums) < 3:
            return jsonify(error="3D Scatter requires at least three numeric columns"), 400
        fig.add_trace(go.Scatter3d(x=df[nums[0]], y=df[nums[1]], z=df[nums[2]], mode="markers", marker=dict(size=4,color=df[nums[2]],colorscale=[[0,"#7C3AED"],[1,"#C4B5FD"]])))
    elif "moving average" in chart_lower:
        if not y or not pd.api.types.is_numeric_dtype(df[y]):
            return jsonify(error="Moving average requires a numeric Y-axis"), 400
        series = df[y].rolling(window=min(10,len(df)), min_periods=1).mean()
        fig.add_trace(go.Scatter(x=df[x] if x else df.index, y=df[y], mode="lines", line=dict(color="#30263D"), name="Raw"))
        fig.add_trace(go.Scatter(x=df[x] if x else df.index, y=series, mode="lines", line=dict(color=violet,width=3), name="Moving average"))
    elif "box" in chart_lower or "violin" in chart_lower:
        cls = go.Violin if "violin" in chart_lower else go.Box
        fig.add_trace(cls(y=df[y], x=df[color] if color else None, marker=dict(color=violet), line=dict(color=lavender)))
    else:
        if not y:
            return jsonify(error="Select a Y-axis field for this chart"), 400
        if color and color in df.columns:
            for key, part in df.groupby(color):
                fig.add_trace(go.Scatter(x=part[x] if x else part.index, y=part[y], mode="lines+markers" if "line" in chart_lower or "area" in chart_lower or "time" in chart_lower else "markers", name=str(key), line=dict(color=violet), marker=dict(color=violet)))
        else:
            mode = "lines+markers" if "line" in chart_lower or "area" in chart_lower or "time" in chart_lower else "markers"
            fig.add_trace(go.Bar(x=df[x] if x else df.index, y=df[y], marker=dict(color=violet)) if "bar" in chart_lower and "horizontal" not in chart_lower else go.Scatter(x=df[y] if "horizontal" in chart_lower else (df[x] if x else df.index), y=df[x] if "horizontal" in chart_lower else df[y], mode=mode, line=dict(color=violet,width=2), marker=dict(color=violet)))
    fig.update_layout(title=title, template="plotly_dark", paper_bgcolor="#17131F", plot_bgcolor="#17131F", font=dict(color="#FFFFFF",family="Inter"), margin=dict(l=40,r=30,t=70,b=50), legend=dict(orientation="h",yanchor="bottom",y=1.02), xaxis=dict(gridcolor="#30263D"), yaxis=dict(gridcolor="#30263D"))
    return jsonify(plotly=json.loads(fig.to_json()))

@app.post("/api/visualization/save")
def save_visualization():
    body = request.get_json(silent=True) or {}
    viz_id = uuid.uuid4().hex
    path = os.path.join(SAVED_DIR, viz_id + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(body, f)
    return jsonify(id=viz_id)

@app.get("/api/visualization/saved")
def saved_visualizations():
    items=[]
    for name in os.listdir(SAVED_DIR):
        if name.endswith(".json"):
            with open(os.path.join(SAVED_DIR,name),encoding="utf-8") as f:
                items.append({"id":name[:-5], **json.load(f)})
    return jsonify(items)

@app.delete("/api/visualization/saved/<viz_id>")
def delete_saved(viz_id):
    path=os.path.join(SAVED_DIR,viz_id+".json")
    if os.path.isfile(path): os.remove(path)
    return jsonify(success=True)

@app.post("/api/analytics/statistics")
def analytics_statistics():
    body=request.get_json(silent=True) or {}
    df=load_dataset(body.get("dataset","aquapulse_sample_dataset"))
    field=body.get("field")
    if not field or field not in df or not pd.api.types.is_numeric_dtype(df[field]):
        return jsonify(error="Select a numeric field"),400
    s=df[field].dropna()
    return jsonify(mean=float(s.mean()),median=float(s.median()),mode=float(s.mode().iloc[0]) if not s.mode().empty else None,min=float(s.min()),max=float(s.max()),std=float(s.std()),variance=float(s.var()),q1=float(s.quantile(.25)),q3=float(s.quantile(.75)),skewness=float(s.skew()),kurtosis=float(s.kurt()))

@app.post("/api/analytics/correlation")
def correlation():
    body=request.get_json(silent=True) or {}
    df=load_dataset(body.get("dataset","aquapulse_sample_dataset"))
    method=body.get("method","pearson")
    corr=df.select_dtypes("number").corr(method=method)
    return jsonify(columns=corr.columns.tolist(),values=corr.where(pd.notna(corr),None).values.tolist())

@app.post("/api/analytics/signal-processing")
def signal_processing():
    body=request.get_json(silent=True) or {}
    df=load_dataset(body.get("dataset","aquapulse_sample_dataset"))
    field=body.get("field")
    if not field or field not in df or not pd.api.types.is_numeric_dtype(df[field]):
        return jsonify(error="Select a numeric signal field"),400
    values=df[field].dropna().to_numpy()
    window=body.get("window",10)
    window=max(3,min(int(window),51))
    moving=pd.Series(values).rolling(window=window,min_periods=1).mean().tolist()
    smooth=signal.savgol_filter(values,min(window if window%2 else window+1,len(values)) if len(values)>=3 else 3,2) if len(values)>=3 else values
    peaks,_=signal.find_peaks(values)
    energy=float(np.sum(np.square(values)))
    return jsonify(raw=values[:500].tolist(),moving=moving[:500],filtered=smooth[:500].tolist(),peaks=peaks[:100].tolist(),peak_count=int(len(peaks)),energy=energy)

@app.post("/api/analytics/outlier-detection")
def outliers():
    body=request.get_json(silent=True) or {}
    df=load_dataset(body.get("dataset","aquapulse_sample_dataset"))
    field=body.get("field")
    method=body.get("method","IQR")
    if not field or field not in df or not pd.api.types.is_numeric_dtype(df[field]):
        return jsonify(error="Select a numeric field"),400
    s=df[field].dropna()
    if method=="Z-score":
        z=np.abs((s-s.mean())/s.std()) if s.std() else np.zeros(len(s))
        mask=z>float(body.get("threshold",3))
    elif method=="Isolation Forest":
        mask=IsolationForest(contamination=float(body.get("threshold",.05)),random_state=42).fit_predict(s.to_numpy().reshape(-1,1))==-1
    else:
        q1,q3=s.quantile(.25),s.quantile(.75); iqr=q3-q1
        mask=(s<(q1-1.5*iqr))|(s>(q3+1.5*iqr))
    indices=s.index[mask].tolist()
    return jsonify(indices=indices[:1000],count=int(mask.sum()),values=s.loc[indices].head(1000).tolist())

@app.post("/api/analytics/classification")
def classification():
    df=load_dataset((request.get_json(silent=True) or {}).get("dataset","aquapulse_sample_dataset"))
    if "Classification" not in df:
        return jsonify(error="Dataset does not contain a Classification field"),400
    return jsonify(distribution=df["Classification"].value_counts().to_dict())

@app.get("/api/gps/observations")
def gps():
    df=load_dataset(request.args.get("dataset","aquapulse_sample_dataset"))
    if not {"Latitude","Longitude"}.issubset(df.columns):
        return jsonify(error="Dataset requires Latitude and Longitude fields"),400
    if request.args.get("device"): df=df[df["Device_ID"].astype(str)==request.args["device"]]
    if request.args.get("classification"): df=df[df["Classification"].astype(str)==request.args["classification"]]
    return jsonify(df.head(2000).fillna("").to_dict("records"))

@app.post("/api/reports/generate")
def report_generate():
    body=request.get_json(silent=True) or {}
    df=load_dataset(body.get("dataset","aquapulse_sample_dataset"))
    report_id=uuid.uuid4().hex
    path=os.path.join(REPORT_DIR,report_id+".csv")
    df.describe(include="all").to_csv(path)
    return jsonify(id=report_id,url=f"/api/reports/download/{report_id}")

@app.get("/api/reports/download/<report_id>")
def report_download(report_id):
    path=os.path.join(REPORT_DIR,report_id+".csv")
    if not os.path.isfile(path): return jsonify(error="Report not found"),404
    return send_file(path,as_attachment=True,download_name="aquapulse_report.csv")

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
