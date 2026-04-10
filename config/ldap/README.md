# OpenLDAP Lab

Bu klasor LDAP entegrasyonunu gercek bir dizin ortami uzerinde test etmek icin hazirlandi.

## Baslat

```bash
docker build -t appcenter-openldap-lab ./config/ldap
docker rm -f appcenter-openldap >/dev/null 2>&1 || true
docker run -d \
  --name appcenter-openldap \
  --hostname ldap.appcenter.local \
  -p 1389:389 \
  -e LDAP_ORGANISATION=AppCenter \
  -e LDAP_DOMAIN=appcenter.local \
  -e LDAP_BASE_DN=dc=appcenter,dc=local \
  -e LDAP_ADMIN_PASSWORD=admin123 \
  -e LDAP_CONFIG_PASSWORD=config123 \
  -e LDAP_TLS=false \
  appcenter-openldap-lab
```

## Baglanti Bilgileri

- Host: `127.0.0.1`
- Port: `1389`
- Base DN: `dc=appcenter,dc=local`
- Bind DN: `cn=admin,dc=appcenter,dc=local`
- Bind Password: `admin123`
- User Base DN: `ou=people,dc=appcenter,dc=local`
- Group Base DN: `ou=groups,dc=appcenter,dc=local`

## Hazir Kullanici ve Gruplar

- `admin.user` / `AdminPass123!`
- `operator.user` / `OperatorPass123!`
- `viewer.user` / `ViewerPass123!`

Gruplar:

- `appcenter-admins`
- `appcenter-operators`
- `appcenter-viewers`

## Not

- Bu hostta `docker-compose` eski/uyumsuz davrandigi icin test akisi `docker build` + `docker run` uzerinden tasarlandi.
