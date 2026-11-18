# AquaPulse

A responsive environmental-intelligence platform for synthetic river-water observations, sensor analytics, visualization, and geospatial monitoring.

## Run

```powershell
python -m pip install -r backend/requirements.txt
python backend/app.py
```

Open `http://127.0.0.1:5000`.

The sample dataset is generated at `backend/data/aquapulse_sample_dataset.csv` and contains 500 observations. Uploaded CSVs are kept in `backend/uploads`.

## API

- `GET /api/health`
- `GET /api/datasets`
- `POST /api/datasets/upload`
- `GET /api/datasets/<id>/preview`
- `GET /api/datasets/<id>/columns`
- `GET /api/datasets/<id>/statistics`
- `GET /api/dashboard/summary`
- `POST /api/visualization/generate`
- `POST /api/visualization/save`
- `GET /api/visualization/saved`
- `DELETE /api/visualization/saved/<id>`
- `POST /api/analytics/statistics`
- `POST /api/analytics/correlation`
- `POST /api/analytics/signal-processing`
- `POST /api/analytics/outlier-detection`
- `POST /api/analytics/classification`
- `GET /api/gps/observations`
- `POST /api/reports/generate`
- `GET /api/reports/download/<id>`

## Scientific note

The supplied labels and observations are synthetic experimental data. They are not scientifically validated evidence of microplastic identification.
