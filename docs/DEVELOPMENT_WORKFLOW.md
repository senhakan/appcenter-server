# Development Workflow

Bu dokuman ekip ici gelistirme akisini standartlastirir.

## 1. Hazirlik

```bash
python3.9 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Not:
- Bu projede FastAPI dahil tum Python bagimliliklari repo icindeki `venv` uzerinden kullanilir.
- Ad-hoc script, import, smoke ve debug komutlarinda sistem `python3` yerine `./venv/bin/python` tercih edilir.
- Bu hostta sistem `pip` zinciri bozuk olabilir; bagimlilik kurulumu/yenilemesi icin `venv` icindeki `pip` kullanilir.

## 2. Gelistirme Sirasi

- Faz bazli ilerle (1 -> 5).
- Faz 6 (UI yonetim iyilestirmeleri) aktif olarak faz 5 uzerine iteratif ilerletilir.
- Bu repoda server degisikligi yapildiginda, degisiklik ayni oturumda canli dizine (`/opt/appcenter/server`) deploy edilmeden is tamamlanmis sayilmaz.
- Server tarafinda bir degisiklik yapildiysa ayrica kullanici onayi beklenmeden ayni oturumda canli deploy uygulanir; varsayilan davranis budur.
- Komut kisayolu: Kullanici `+1` yazdiginda o ana kadarki degisiklikler icin sirasiyla `dokuman guncelle -> commit -> push -> canli deploy -> health/smoke` uygulanir.
- Her faz sonunda:
  - API smoke test
  - `./venv/bin/python -m pytest -q`
  - gerektiginde ad-hoc dogrulama: `./venv/bin/python - <<'PY' ... PY`
  - Dokuman guncellemesi (`README.md`, gerekirse `CLAUDE.md`).

## 2.2 Asset Registry Lab Kapsam Kurali

- `server/docs/ASSET_REGISTRY_LAB/` ve bu mod icin acilacak kod alanlari varsayilan olarak diger islerin kapsaminda degildir.
- Yalnizca kullanici acikca asset management / asset registry / CMDB kapsami acarsa bu alan isleme alinir.
- Asset Registry Lab ile ilgili plan, tasarim, migration veya kodlama isleri acik bir is emri olmadan backlog'a dahil edilmez.
- Diger server gorevlerinde bu alanlara dokunulmamalidir.

Varsayilan kapsam disi yollar:
- `server/docs/ASSET_REGISTRY_LAB/`
- `server/app/api/v1/asset_registry.py`
- `server/app/services/asset_registry_service.py`
- `server/app/services/organization_service.py`
- `server/app/services/location_service.py`
- `server/app/services/person_registry_service.py`
- `server/app/services/asset_matching_service.py`
- `server/app/services/asset_reporting_service.py`
- `server/app/templates/asset_registry/`

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

- DB degisikliklerinde PostgreSQL migration/indeks kurallari korunur.
- Tum timestamp'ler UTC tutulur.
- Agent auth: `X-Agent-UUID` + `X-Agent-Secret`
- Web auth: JWT Bearer

## 3.1 RBAC UI Route Guard Standarti (Zorunlu)

- Kisitli bir web sayfasi eklendiginde `templates.TemplateResponse(...)` context'ine mutlaka `page_roles` eklenir.
  - Ornek:
    - admin-only: `page_roles: "admin"`
    - operator/admin: `page_roles: "operator,admin"`
- `base.html` `data-page-roles` attribute'u bu bilgiyi tasir.
- Frontend'de sayfa script'i sadece `AppCenterApi.protectPage();` cagirir.
  - `protectPage()` icinde merkezi guard otomatik calisir.
  - Sayfa bazinda tekrar `guardPageRoles(...)` yazilmaz.
- API tarafinda role enforcement yine zorunludur (`require_role(...)`), UI guard tek basina guvenlik olarak kabul edilmez.

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
