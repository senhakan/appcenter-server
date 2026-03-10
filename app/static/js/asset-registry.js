(function () {
  function escHtml(value) {
    return (value || "").toString()
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function setOptions(id, items, valueKey, labelKey, empty) {
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = (empty ? `<option value="">${empty}</option>` : "") + (items || []).map((item) => {
      const value = item?.[valueKey] ?? "";
      const label = escHtml(item?.[labelKey] ?? "");
      return `<option value="${value}">${label}</option>`;
    }).join("");
  }

  function drawKeyValueRows(id, items, emptyLabel, colspan) {
    const el = document.getElementById(id);
    if (!el) return;
    const span = Number(colspan || 2);
    el.innerHTML = (items || []).map((item) => `<tr><td>${escHtml(item.label)}</td><td>${item.value ?? "-"}</td></tr>`).join("")
      || `<tr><td colspan="${span}" class="text-secondary">${escHtml(emptyLabel || "Kayit yok")}</td></tr>`;
  }

  function toNumberOrNull(value) {
    if (value === null || value === undefined || value === "") return null;
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }

  function fillValues(pairs) {
    Object.entries(pairs || {}).forEach(([id, value]) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.value = value ?? "";
    });
  }

  function sparkBars(points, tone) {
    const items = points || [];
    const max = Math.max(1, ...items.map((item) => Number(item.value || 0)));
    return items.map((item) => {
      const value = Number(item.value || 0);
      const pct = Math.max(8, Math.round((value / max) * 100));
      return `<div class="ar-spark-item"><div class="ar-spark-bar ${tone || ""}" style="height:${pct}%"></div><div class="ar-spark-label">${escHtml(item.label.slice(5))}</div><div class="ar-spark-value">${value}</div></div>`;
    }).join("");
  }

  window.AssetRegistryUI = {
    escHtml,
    setOptions,
    drawKeyValueRows,
    toNumberOrNull,
    fillValues,
    sparkBars,
  };
})();
