# Testing and CI

## 1. Local Test

```bash
./venv/bin/python -m pytest -q
```

Mevcut test dosyalari:
- `tests/conftest.py`
- `tests/test_phase5_api.py`

Guncel kapsam:
- upload + icon + install args
- deployment assignment + task status
- group management + group target deployment
- app/group/deployment edit endpointleri

## 2. CI

Workflow dosyasi:
- `.github/workflows/ci.yml`

CI ozeti:
- Trigger: push + pull_request
- Python: 3.10, 3.11
- Komut: `pytest -q`

## 3. Warning Notu

`httpx` tarafinda TestClient ile ilgili bir deprecation warning gorulebilir.
Bu warning test sonucunu bozmaz; build basarisizligina sebep olmaz.
