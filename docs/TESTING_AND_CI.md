# Testing and CI

## 1. Local Test

Ortak PostgreSQL ortami kullaniminda testler stateful olabilir. Deterministik sonuc icin once tablo temizligi yap:

```bash
cat <<'SQL' | PGPASSWORD='Appcenter2026' psql -h 127.0.0.1 -U appcenter -d appcenter -v ON_ERROR_STOP=1
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname='public') LOOP
    EXECUTE 'TRUNCATE TABLE public.' || quote_ident(r.tablename) || ' RESTART IDENTITY CASCADE';
  END LOOP;
END $$;
SQL
```

Sonra testleri calistir:

```bash
./venv/bin/python -m pytest -q
```

Mevcut test dosyalari:
- `tests/conftest.py`
- `tests/test_agent_signal.py`
- `tests/test_application_ps1.py`
- `tests/test_inventory.py`
- `tests/test_phase5_api.py`
- `tests/test_sam_smoke.py`

Guncel kapsam:
- upload + icon + install args
- deployment assignment + task status
- group management + group target deployment
- app/group/deployment edit endpointleri
- signal listener + wake-up davranisi
- inventory hash + `inventory_sync_required` akis dogrulamasi
- SAM UI route smoke kontrolleri

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
