# Development Workflow

Bu dokuman ekip ici gelistirme akisini standartlastirir.

## 1. Hazirlik

```bash
python3.9 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 2. Gelistirme Sirasi

- Faz bazli ilerle (1 -> 5).
- Faz 6 (UI yonetim iyilestirmeleri) aktif olarak faz 5 uzerine iteratif ilerletilir.
- Bu repoda server degisikligi yapildiginda, degisiklik ayni oturumda canli dizine (`/opt/appcenter/server`) deploy edilmeden is tamamlanmis sayilmaz.
- Komut kisayolu: Kullanici `+1` yazdiginda o ana kadarki degisiklikler icin sirasiyla `dokuman guncelle -> commit -> push -> canli deploy -> health/smoke` uygulanir.
- Her faz sonunda:
  - API smoke test
  - `./venv/bin/python -m pytest -q`
  - Dokuman guncellemesi (`README.md`, gerekirse `CLAUDE.md`).

## 2.1 Sonraki Asama Plani

1. Faz 6.1:
- Edit formlarinda validation + daha net hata mesaji
- uygulama/dağıtım/grup duzenleme icin frontend form kontrolleri
2. Faz 6.2:
- Gruplar icin silme/pasife alma stratejisi
- deployment listesinde app/group/agent isimlerinin zengin gosterimi
3. Faz 6.3:
- Audit log (kim, neyi, ne zaman degistirdi)
- kritik degisikliklerde onay/ikinci adim
4. Faz 6.4 (en son):
- Tabler tabanli UI modernizasyonu
- Not: Bu faza, 6.1-6.3 tamamlanmadan girilmez.
5. Faz 7 (aktif):
- Kullanici yonetimi + RBAC yetkilendirme modulu
- Roller: `admin`, `operator`, `viewer`
- Kural: UI gizleme + backend `403` enforcement birlikte uygulanir
- Durum:
  - `require_role(...)` backend dependency aktif
  - `/api/v1/users` CRUD (admin-only) aktif
  - `/api/v1/auth/me` aktif
  - Web menude role-gore gorunurluk aktif

Detayli yol haritasi ve tema notlari:
- `docs/ROADMAP_AND_THEME.md`

## 3. Kod Standarti

- DB degisikliklerinde SQLite PRAGMA kurallari korunur.
- Tum timestamp'ler UTC tutulur.
- Agent auth: `X-Agent-UUID` + `X-Agent-Secret`
- Web auth: JWT Bearer

## 4. Commit Kurali

- Tek sorumluluklu commit tercih edilir.
- Mesaj formati:
  - `feat: ...`
  - `fix: ...`
  - `docs: ...`
  - `test: ...`

Ornek:

```bash
git add -A
git commit -m "feat: add deployment task assignment flow"
```

## 5. Merge Oncesi Kontrol

```bash
./venv/bin/python -m pytest -q
```

- CI yesil olmadan merge edilmez.
