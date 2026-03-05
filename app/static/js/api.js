(function () {
  const API_PREFIX = "/api/v1";
  const UI_SETTINGS_CACHE_TTL_MS = 5 * 60 * 1000; // refresh occasionally so settings changes apply without reload
  const SESSION_WARNING_SECONDS = 30;

  let _sessionWarnTimer = null;
  let _sessionExpireTimer = null;
  let _sessionCountdownTimer = null;
  let _sessionCountdownValue = SESSION_WARNING_SECONDS;
  let _sessionModalBound = false;
  let _globalModalHotkeysBound = false;
  let _sessionExtending = false;
  let _currentUser = null;
  let _currentUserLoading = null;
  const ROLE_WEIGHTS = { viewer: 10, operator: 20, admin: 30 };

  function getToken() {
    return localStorage.getItem("appcenter_token") || "";
  }

  function setToken(token) {
    localStorage.setItem("appcenter_token", token);
    scheduleSessionTimers();
  }

  function clearToken() {
    localStorage.removeItem("appcenter_token");
    _currentUser = null;
    _currentUserLoading = null;
    clearSessionTimers();
    hideSessionModal();
  }

  function authHeaders(extra) {
    const headers = extra ? { ...extra } : {};
    const token = getToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
    return headers;
  }

  async function req(path, options) {
    const opts = options ? { ...options } : {};
    opts.headers = authHeaders(opts.headers || {});
    const res = await fetch(`${API_PREFIX}${path}`, opts);
    if (res.status === 401) {
      forceLogout();
      throw new Error("Unauthorized");
    }
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Request failed");
      }
      return data;
    }
    if (!res.ok) {
      throw new Error("Request failed");
    }
    return res;
  }

  let _uiSettings = { timezone: null, loadedAt: 0, loading: null };

  async function initUi(force) {
    const now = Date.now();
    if (_uiSettings.loading) return _uiSettings.loading;
    if (!force && _uiSettings.timezone && (now - _uiSettings.loadedAt) < UI_SETTINGS_CACHE_TTL_MS) return;

    _uiSettings.loading = (async () => {
      try {
        const data = await req("/settings");
        const map = {};
        (data.items || []).forEach((x) => { map[x.key] = x.value; });
        const tz = (map.ui_timezone || "").toString().trim();
        _uiSettings.timezone = tz || null;
        _uiSettings.loadedAt = Date.now();
      } catch (_) {
        // ignore - we can fall back to browser timezone
      } finally {
        _uiSettings.loading = null;
      }
    })();
    return _uiSettings.loading;
  }

  function getUiTimezone() {
    return _uiSettings.timezone || (Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
  }

  function parseDate(value) {
    if (!value) return null;
    if (value instanceof Date) return isNaN(value.getTime()) ? null : value;
    if (typeof value === "number") return new Date(value);
    const s0 = value.toString().trim();
    if (!s0) return null;
    // Handle sqlite-style "YYYY-MM-DD HH:MM:SS" (treat as UTC)
    let s = s0;
    if (s.includes(" ") && !s.includes("T")) s = s.replace(" ", "T");
    const hasTz =
      s.endsWith("Z") ||
      /[+-]\d{2}:\d{2}$/.test(s) ||
      /[+-]\d{2}\d{2}$/.test(s);
    if (!hasTz) s = `${s}Z`; // If no explicit offset, treat as UTC
    const d = new Date(s);
    if (!isNaN(d.getTime())) return d;
    // Final fallback: try raw string
    const d2 = new Date(s0);
    return isNaN(d2.getTime()) ? null : d2;
  }

  function formatDate(value) {
    const dt = parseDate(value);
    if (!dt) return "-";
    const tz = getUiTimezone();
    try {
      const fmt = new Intl.DateTimeFormat("tr-TR", {
        timeZone: tz,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
      return fmt.format(dt);
    } catch (_) {
      return dt.toLocaleString();
    }
  }

  function relTime(value) {
    const dt = parseDate(value);
    if (!dt) return "-";
    const ms = Date.now() - dt.getTime();
    const sec = Math.floor(ms / 1000);
    if (sec < 60) return `${sec} sn önce`;
    const min = Math.floor(sec / 60);
    if (min < 60) return `${min} dk önce`;
    const hr = Math.floor(min / 60);
    if (hr < 24) return `${hr} saat önce`;
    const day = Math.floor(hr / 24);
    return `${day} gün önce`;
  }

  function _escapeHtml(value) {
    return (value ?? "")
      .toString()
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function _guessToastType(message) {
    const text = (message || "").toString().toLowerCase();
    if (text.includes("hata") || text.includes("failed") || text.includes("error") || text.includes("not found") || text.includes("unauthorized")) {
      return "error";
    }
    if (text.includes("silindi") || text.includes("eklendi") || text.includes("guncellendi") || text.includes("tamamlandi") || text.includes("ok")) {
      return "success";
    }
    return "info";
  }

  function toast(message, type) {
    const container = document.getElementById("toast");
    if (!container) return;
    const tone = (type || _guessToastType(message) || "info").toString().trim().toLowerCase();
    const map = {
      info: { cls: "text-bg-info", icon: "ti ti-info-circle", title: "Bilgi" },
      success: { cls: "text-bg-success", icon: "ti ti-circle-check", title: "Basarili" },
      warning: { cls: "text-bg-warning", icon: "ti ti-alert-triangle", title: "Uyari" },
      error: { cls: "text-bg-danger", icon: "ti ti-alert-circle", title: "Hata" },
    };
    const selected = map[tone] || map.info;
    const item = document.createElement("div");
    item.className = `toast ${selected.cls} border-0`;
    item.setAttribute("role", "alert");
    item.setAttribute("aria-live", "assertive");
    item.setAttribute("aria-atomic", "true");
    item.setAttribute("data-bs-autohide", "true");
    item.setAttribute("data-bs-delay", "2600");
    item.innerHTML = `
      <div class="toast-header">
        <span class="me-2"><i class="${selected.icon}"></i></span>
        <strong class="me-auto">${selected.title}</strong>
        <small>${new Date().toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" })}</small>
        <button type="button" class="ms-2 btn-close" data-bs-dismiss="toast" aria-label="Close"></button>
      </div>
      <div class="toast-body">
        ${_escapeHtml(message || "")}
      </div>
    `;
    container.appendChild(item);

    const maxToasts = 4;
    while (container.children.length > maxToasts) {
      container.removeChild(container.firstElementChild);
    }

    if (window.bootstrap && window.bootstrap.Toast) {
      const instance = new window.bootstrap.Toast(item, { autohide: true, delay: 2600 });
      item.addEventListener(
        "hidden.bs.toast",
        () => {
          if (item.parentElement) item.parentElement.removeChild(item);
        },
        { once: true }
      );
      instance.show();
    } else {
      item.classList.add("show");
      setTimeout(() => {
        if (item.parentElement) item.parentElement.removeChild(item);
      }, 2600);
    }
  }

  function clearSessionTimers() {
    if (_sessionWarnTimer) {
      clearTimeout(_sessionWarnTimer);
      _sessionWarnTimer = null;
    }
    if (_sessionExpireTimer) {
      clearTimeout(_sessionExpireTimer);
      _sessionExpireTimer = null;
    }
    if (_sessionCountdownTimer) {
      clearInterval(_sessionCountdownTimer);
      _sessionCountdownTimer = null;
    }
  }

  function decodeJwtPayload(token) {
    const parts = (token || "").split(".");
    if (parts.length < 2) return null;
    try {
      const b64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
      const padded = b64.padEnd(Math.ceil(b64.length / 4) * 4, "=");
      return JSON.parse(atob(padded));
    } catch (_) {
      return null;
    }
  }

  function getTokenExpiryMs(token) {
    const payload = decodeJwtPayload(token);
    if (!payload || !payload.exp) return null;
    const exp = Number(payload.exp);
    if (!Number.isFinite(exp) || exp <= 0) return null;
    return exp * 1000;
  }

  function getSessionModalElements() {
    return {
      modal: document.getElementById("session-timeout-modal"),
      card: document.querySelector("#session-timeout-modal .session-modal-card"),
      countdown: document.getElementById("session-timeout-countdown"),
      continueBtn: document.getElementById("session-continue-btn"),
      logoutBtn: document.getElementById("session-logout-btn"),
    };
  }

  function renderSessionCountdown() {
    const { card, countdown } = getSessionModalElements();
    const isCritical = _sessionCountdownValue <= 10;
    if (card) card.classList.toggle("critical", isCritical);
    if (countdown) countdown.textContent = String(Math.max(0, _sessionCountdownValue));
    if (countdown) countdown.classList.toggle("critical", isCritical);
  }

  function hideSessionModal() {
    const { modal, card, countdown } = getSessionModalElements();
    if (!modal) return;
    modal.classList.add("hidden");
    if (card) card.classList.remove("critical");
    if (countdown) countdown.classList.remove("critical");
  }

  function showSessionModal() {
    const { modal, continueBtn } = getSessionModalElements();
    if (!modal) return;
    _sessionCountdownValue = SESSION_WARNING_SECONDS;
    renderSessionCountdown();
    modal.classList.remove("hidden");
    if (continueBtn) continueBtn.focus();
    if (_sessionCountdownTimer) clearInterval(_sessionCountdownTimer);
    _sessionCountdownTimer = setInterval(() => {
      _sessionCountdownValue -= 1;
      renderSessionCountdown();
      if (_sessionCountdownValue <= 0) {
        clearInterval(_sessionCountdownTimer);
        _sessionCountdownTimer = null;
      }
    }, 1000);
  }

  function forceLogout() {
    clearSessionTimers();
    hideSessionModal();
    localStorage.removeItem("appcenter_token");
    _currentUser = null;
    _currentUserLoading = null;
    if (window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
  }

  function normalizeRole(raw) {
    const role = (raw || "").toString().trim().toLowerCase();
    if (role === "admin" || role === "operator" || role === "viewer") return role;
    return "viewer";
  }

  function isCustomRoleProfile() {
    const key = (_currentUser && _currentUser.role_profile_key ? _currentUser.role_profile_key : "").toString().trim().toLowerCase();
    const role = getCurrentRole();
    if (!key) return false;
    return key !== role;
  }

  function getCurrentRole() {
    return normalizeRole(_currentUser && _currentUser.role ? _currentUser.role : "viewer");
  }

  function roleAllowed(role, allowedCsv) {
    if (isCustomRoleProfile()) return true;
    const allowed = (allowedCsv || "")
      .toString()
      .split(",")
      .map((x) => x.trim().toLowerCase())
      .filter(Boolean);
    if (!allowed.length) return true;
    return allowed.includes(role);
  }

  function currentPermissions() {
    const arr = (_currentUser && Array.isArray(_currentUser.permissions)) ? _currentUser.permissions : [];
    return arr
      .map((x) => (x || "").toString().trim())
      .filter(Boolean);
  }

  function permissionAllowed(requiredCsvOrKey) {
    const required = (requiredCsvOrKey || "")
      .toString()
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean);
    if (!required.length) return true;
    const perms = currentPermissions();
    if (perms.includes("*")) return true;
    return required.some((p) => perms.includes(p));
  }

  function canAny(roles) {
    if (isCustomRoleProfile()) return true;
    const normalized = getCurrentRole();
    const allowed = Array.isArray(roles) ? roles : [roles];
    return allowed
      .map((r) => normalizeRole(r))
      .some((r) => r === normalized);
  }

  function canAtLeast(minRole) {
    const currentWeight = ROLE_WEIGHTS[getCurrentRole()] || 0;
    const minWeight = ROLE_WEIGHTS[normalizeRole(minRole)] || 0;
    return currentWeight >= minWeight;
  }

  function initialsFromUser(me) {
    const fullName = (me && me.full_name ? me.full_name : "").toString().trim();
    const username = (me && me.username ? me.username : "").toString().trim();
    const source = fullName || username || "AC";
    const parts = source.split(/\s+/).filter(Boolean);
    if (parts.length >= 2) {
      return `${parts[0][0] || ""}${parts[1][0] || ""}`.toUpperCase();
    }
    return (parts[0] || "AC").slice(0, 2).toUpperCase();
  }

  function applyCurrentUserToTopbar(me) {
    const nameEl = document.getElementById("topbar-user-name");
    const roleEl = document.getElementById("topbar-user-role");
    const avatarEl = document.getElementById("topbar-user-avatar");
    if (!nameEl && !roleEl && !avatarEl) return;
    const displayName = (me && (me.full_name || me.username)) ? (me.full_name || me.username) : "AppCenter";
    const roleProfile = (me && me.role_profile_name ? me.role_profile_name : (me && me.role ? me.role : "-"));
    const avatarUrl = (me && me.avatar_url ? me.avatar_url : "").toString().trim();
    if (nameEl) nameEl.textContent = displayName;
    if (roleEl) roleEl.textContent = roleProfile || "-";
    if (avatarEl) {
      if (avatarUrl) {
        avatarEl.textContent = "";
        avatarEl.style.backgroundImage = `url('${avatarUrl}')`;
        avatarEl.style.backgroundSize = "cover";
        avatarEl.style.backgroundPosition = "center";
      } else {
        avatarEl.style.backgroundImage = "";
        avatarEl.style.backgroundSize = "";
        avatarEl.style.backgroundPosition = "";
        avatarEl.textContent = initialsFromUser(me);
      }
    }
  }

  function applyNavPermissions(role) {
    const resolvedRole = normalizeRole(role);
    document.body.setAttribute("data-user-role", resolvedRole);

    document.querySelectorAll("[data-nav-item]").forEach((el) => {
      const allowedCsv = el.getAttribute("data-roles") || "";
      const permissionKey = el.getAttribute("data-permissions") || "";
      el.hidden = !roleAllowed(resolvedRole, allowedCsv) || !permissionAllowed(permissionKey);
    });

    document.querySelectorAll(".nav-dropdown").forEach((dropdown) => {
      if (dropdown.hidden) return;
      const visibleChildren = dropdown.querySelectorAll(".dropdown-menu [data-nav-item]:not([hidden]), .nav-submenu [data-nav-item]:not([hidden])");
      if (visibleChildren.length === 0) dropdown.hidden = true;
    });
  }

  function applyRoleControls(role) {
    const resolvedRole = normalizeRole(role);
    document.querySelectorAll("[data-required-roles]").forEach((el) => {
      const allowedCsv = el.getAttribute("data-required-roles") || "";
      const visible = roleAllowed(resolvedRole, allowedCsv);
      el.hidden = !visible;
      if (!visible && (el instanceof HTMLInputElement || el instanceof HTMLButtonElement || el instanceof HTMLSelectElement || el instanceof HTMLTextAreaElement)) {
        el.disabled = true;
      }
    });
    document.querySelectorAll("[data-required-permissions]").forEach((el) => {
      const permissionKey = el.getAttribute("data-required-permissions") || "";
      const visible = permissionAllowed(permissionKey);
      el.hidden = !visible;
      if (!visible && (el instanceof HTMLInputElement || el instanceof HTMLButtonElement || el instanceof HTMLSelectElement || el instanceof HTMLTextAreaElement)) {
        el.disabled = true;
      }
    });
  }

  function guardPageRoles(requiredRoles, redirectPath) {
    const target = (redirectPath || "/dashboard").toString();
    const roles = Array.isArray(requiredRoles) ? requiredRoles : [requiredRoles];
    const normalized = roles.map((r) => normalizeRole(r)).filter(Boolean);
    if (!normalized.length) return true;
    const allowed = canAny(normalized);
    if (!allowed) {
      window.location.href = target;
      return false;
    }
    return true;
  }

  function guardPageRolesFromDom() {
    const body = document.body;
    if (!body) return true;
    const raw = (body.getAttribute("data-page-roles") || "").trim();
    if (!raw) return true;
    const required = raw.split(",").map((x) => x.trim()).filter(Boolean);
    return guardPageRoles(required);
  }

  function guardPagePermissions(requiredPermissions, redirectPath) {
    const target = (redirectPath || "/remote-support").toString();
    const raw = Array.isArray(requiredPermissions) ? requiredPermissions : [requiredPermissions];
    const needed = raw.map((x) => (x || "").toString().trim()).filter(Boolean);
    if (!needed.length) return true;
    if (permissionAllowed(needed.join(","))) return true;
    window.location.href = target;
    return false;
  }

  function guardPagePermissionsFromDom() {
    const body = document.body;
    if (!body) return true;
    const raw = (body.getAttribute("data-page-permissions") || "").trim();
    if (!raw) return true;
    const required = raw.split(",").map((x) => x.trim()).filter(Boolean);
    return guardPagePermissions(required);
  }

  async function getCurrentUser(force) {
    if (!getToken()) return null;
    if (!force && _currentUser) return _currentUser;
    if (_currentUserLoading) return _currentUserLoading;
    _currentUserLoading = (async () => {
      try {
        const me = await req("/auth/me");
        _currentUser = me || null;
        applyCurrentUserToTopbar(_currentUser);
      } catch (_) {
        _currentUser = null;
        applyCurrentUserToTopbar(null);
      } finally {
        _currentUserLoading = null;
      }
      return _currentUser;
    })();
    return _currentUserLoading;
  }

  async function extendSession() {
    if (_sessionExtending) return;
    _sessionExtending = true;
    const { continueBtn } = getSessionModalElements();
    if (continueBtn) continueBtn.disabled = true;
    try {
      const res = await fetch(`${API_PREFIX}/auth/extend`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
      });
      if (!res.ok) throw new Error("Session extend failed");
      const data = await res.json();
      if (!data.access_token) throw new Error("Session extend failed");
      setToken(data.access_token);
      hideSessionModal();
      toast("Oturum suresi uzatildi");
    } catch (_) {
      forceLogout();
    } finally {
      _sessionExtending = false;
      if (continueBtn) continueBtn.disabled = false;
    }
  }

  function bindSessionModalOnce() {
    if (_sessionModalBound) return;
    const { continueBtn, logoutBtn } = getSessionModalElements();
    if (!continueBtn || !logoutBtn) return;
    continueBtn.addEventListener("click", () => {
      extendSession();
    });
    logoutBtn.addEventListener("click", () => {
      forceLogout();
    });
    document.addEventListener("keydown", (evt) => {
      if (evt.key !== "Enter") return;
      const { modal } = getSessionModalElements();
      if (!modal || modal.classList.contains("hidden")) return;
      evt.preventDefault();
      extendSession();
    });
    _sessionModalBound = true;
  }

  function getVisibleCustomModal() {
    const open = Array.from(document.querySelectorAll(
      ".session-modal:not(.hidden), [class*='modal-backdrop']:not(.hidden), .rs-modal-backdrop.show"
    )).filter((el) => {
      if (el.closest(".hidden")) return false;
      const cs = window.getComputedStyle(el);
      if (!cs) return false;
      if (cs.display === "none" || cs.visibility === "hidden" || cs.opacity === "0") return false;
      return true;
    });
    if (!open.length) return null;
    return open[open.length - 1];
  }

  function findModalCloseAction(modal) {
    if (!modal) return null;
    return modal.querySelector(
      "[data-modal-close], .btn-close, button[id*='close'], button[id*='cancel'], .rs-info-close, #rs-rejected-ok"
    );
  }

  function closeCustomModal(modal) {
    const target = modal || getVisibleCustomModal();
    if (!target) return;
    const closeAction = findModalCloseAction(target);
    if (closeAction && typeof closeAction.click === "function") {
      closeAction.click();
      return;
    }
    if (target.classList.contains("show")) {
      target.classList.remove("show");
      return;
    }
    target.classList.add("hidden");
  }

  function findModalPrimaryAction(modal) {
    if (!modal) return null;
    return modal.querySelector(
      "[data-modal-primary], button[type='submit']:not([disabled]), .btn.btn-primary:not([disabled]), .btn.btn-danger:not([disabled])"
    );
  }

  function triggerCustomModalPrimary(modal) {
    const target = modal || getVisibleCustomModal();
    if (!target) return;
    const primary = findModalPrimaryAction(target);
    if (primary && typeof primary.click === "function") primary.click();
  }

  function bindGlobalModalHotkeysOnce() {
    if (_globalModalHotkeysBound) return;
    document.addEventListener("keydown", (evt) => {
      const modal = getVisibleCustomModal();
      if (!modal) return;

      if (evt.key === "Escape") {
        evt.preventDefault();
        closeCustomModal(modal);
        return;
      }

      if (evt.key !== "Enter") return;
      const tag = (evt.target && evt.target.tagName ? evt.target.tagName : "").toUpperCase();
      if (tag === "TEXTAREA" || tag === "SELECT") return;
      if (tag === "INPUT") return; // native form submit should stay untouched
      if (evt.target && evt.target.isContentEditable) return;
      evt.preventDefault();
      triggerCustomModalPrimary(modal);
    });
    _globalModalHotkeysBound = true;
  }

  function scheduleSessionTimers() {
    clearSessionTimers();
    bindSessionModalOnce();
    const token = getToken();
    if (!token) return;

    const expiryMs = getTokenExpiryMs(token);
    if (!expiryMs) return;

    const now = Date.now();
    const remainingMs = expiryMs - now;
    if (remainingMs <= 0) {
      forceLogout();
      return;
    }

    const warningMs = SESSION_WARNING_SECONDS * 1000;
    const warnInMs = remainingMs - warningMs;
    if (warnInMs <= 0) {
      showSessionModal();
    } else {
      _sessionWarnTimer = setTimeout(() => {
        showSessionModal();
      }, warnInMs);
    }

    _sessionExpireTimer = setTimeout(() => {
      forceLogout();
    }, remainingMs);
  }

  async function protectPage() {
    if (!getToken()) {
      window.location.href = "/login";
      return;
    }
    scheduleSessionTimers();
    bindGlobalModalHotkeysOnce();
    const me = await getCurrentUser();
    if (me && me.role) {
      applyCurrentUserToTopbar(me);
      applyNavPermissions(me.role);
      applyRoleControls(me.role);
      guardPageRolesFromDom();
      guardPagePermissionsFromDom();
      return me;
    } else {
      applyCurrentUserToTopbar(null);
      applyNavPermissions("viewer");
      applyRoleControls("viewer");
      guardPageRolesFromDom();
      guardPagePermissionsFromDom();
      return null;
    }
  }

  window.AppCenterApi = {
    getToken,
    setToken,
    clearToken,
    req,
    initUi,
    getUiTimezone,
    parseDate,
    formatDate,
    relTime,
    toast,
    closeCustomModal,
    triggerCustomModalPrimary,
    getCurrentUser,
    applyNavPermissions,
    getCurrentRole,
    canAny,
    canAtLeast,
    canPermission: permissionAllowed,
    guardPageRoles,
    guardPageRolesFromDom,
    guardPagePermissions,
    guardPagePermissionsFromDom,
    protectPage,
  };
})();
