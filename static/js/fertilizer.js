const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));
const toast = $("#toast");
const APP_LANG = window.APP_LANG || "de";
const APP_SETTINGS = window.APP_SETTINGS || {};
const MEASUREMENT_SYSTEM = APP_SETTINGS.measurement_system || "metric";
const FERTILIZER_WEEKS = Array.isArray(window.FERTILIZER_WEEKS) ? window.FERTILIZER_WEEKS : [];
const HIGHLIGHT_FERT_WEEK = Number(window.HIGHLIGHT_FERT_WEEK || window.CURRENT_FERT_WEEK || 1);
let fertilizerCatalog = Array.isArray(window.FERTILIZER_CATALOG) ? window.FERTILIZER_CATALOG : [];
const DEFAULT_WEEK_COUNT = Math.max(FERTILIZER_WEEKS.length || 0, 1);

const TXT = {
  de: {
    week: "Woche",
    total: "Gesamt",
    saveCopy: "Nutze „Als Standard speichern“, um diese Werte zu sichern.",
    calculated: "Düngerplan berechnet",
    defaultSaved: "Standard gespeichert",
    fertilizerSaved: "Dünger gespeichert",
    fertilizerDeleted: "Dünger gelöscht",
    noFertilizers: "Keine Dünger hinterlegt.",
    edit: "Bearbeiten",
    del: "Löschen",
    deleteConfirm: "Diesen Dünger wirklich löschen?",
    selectDeleteFirst: "Bitte zuerst einen Dünger wählen.",
    missingName: "Bitte einen Namen eingeben.",
  },
  en: {
    week: "Week",
    total: "Total",
    saveCopy: "Use “Save as default” to keep these values.",
    calculated: "Fertilizer plan calculated",
    defaultSaved: "Default saved",
    fertilizerSaved: "Fertilizer saved",
    fertilizerDeleted: "Fertilizer deleted",
    noFertilizers: "No fertilizers configured.",
    edit: "Edit",
    del: "Delete",
    deleteConfirm: "Delete this fertilizer?",
    selectDeleteFirst: "Please select a fertilizer first.",
    missingName: "Please enter a name.",
  },
};
const t = (key) => (TXT[APP_LANG] && TXT[APP_LANG][key]) || TXT.de[key] || key;

function displayVolumeUnit() {
  return MEASUREMENT_SYSTEM === "imperial" ? "gal" : "L";
}

function toLiters(value) {
  return MEASUREMENT_SYSTEM === "imperial" ? value / 0.264172 : value;
}

function displayRateUnit(unit) {
  const normalized = String(unit || "").toLowerCase().startsWith("g") ? "g/L" : "ml/L";
  if (MEASUREMENT_SYSTEM === "imperial") {
    return normalized === "g/L" ? "oz/gal" : "fl oz/gal";
  }
  return normalized;
}

function displayTotalUnit(unit) {
  const normalized = String(unit || "").toLowerCase().startsWith("g") ? "g/L" : "ml/L";
  if (MEASUREMENT_SYSTEM === "imperial") {
    return normalized === "g/L" ? "oz" : "fl oz";
  }
  return normalized === "g/L" ? "g" : "ml";
}

function convertRateValue(value, unit) {
  const numeric = Number(value || 0);
  const normalized = String(unit || "").toLowerCase().startsWith("g") ? "g/L" : "ml/L";
  if (MEASUREMENT_SYSTEM !== "imperial") return numeric;
  if (normalized === "g/L") return (numeric * 3.785411784) / 28.349523125;
  return (numeric * 3.785411784) / 29.5735295625;
}

function convertTotalValue(value, unit) {
  const numeric = Number(value || 0);
  const normalized = String(unit || "").toLowerCase().startsWith("g") ? "g/L" : "ml/L";
  if (MEASUREMENT_SYSTEM !== "imperial") return numeric;
  if (normalized === "g/L") return numeric / 28.349523125;
  return numeric / 29.5735295625;
}

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const msg = await response.text();
    throw new Error(msg || response.statusText);
  }
  return response.json();
}

function showToast(message, isError = false) {
  if (!toast) return;
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2500);
}

function resetManageForm() {
  $("#fertOriginalName").value = "";
  $("#fertName").value = "";
  $("#fertUnit").value = "ml/L";
  const weekCount = $("#fertWeekCount");
  const sameAmount = $("#fertSameAmount");
  const sameAmountValue = $("#fertSameAmountValue");
  if (weekCount) weekCount.value = String(DEFAULT_WEEK_COUNT);
  if (sameAmount) sameAmount.checked = false;
  if (sameAmountValue) sameAmountValue.value = "0";
  renderWeekInputs(DEFAULT_WEEK_COUNT);
  syncSameAmountMode();
}

function fillManageForm(fertilizer) {
  if (!fertilizer) {
    resetManageForm();
    return;
  }
  $("#fertOriginalName").value = fertilizer.name;
  $("#fertName").value = fertilizer.name;
  $("#fertUnit").value = fertilizer.unit || "ml/L";
  const schedule = fertilizer.schedule || {};
  const weekCount = Math.max(
    1,
    ...Object.keys(schedule).map((key) => Number(key) || 0),
  );
  $("#fertWeekCount").value = String(Math.min(Math.max(weekCount, 1), 24));
  $("#fertSameAmount").checked = false;
  $("#fertSameAmountValue").value = "0";
  renderWeekInputs(weekCount, schedule);
  syncSameAmountMode();
}

function getCurrentWeekCount() {
  const raw = parseInt($("#fertWeekCount")?.value || String(DEFAULT_WEEK_COUNT), 10);
  return Math.min(Math.max(Number.isFinite(raw) ? raw : DEFAULT_WEEK_COUNT, 1), 24);
}

function renderWeekInputs(weekCount, schedule = null) {
  const grid = $("#fertWeekGrid");
  if (!grid) return;
  const currentValues = {};
  if (!schedule) {
    $$("#fertWeekGrid input[data-week]").forEach((input) => {
      currentValues[input.dataset.week] = input.value;
    });
  }
  const html = Array.from({ length: weekCount }, (_, index) => {
    const week = index + 1;
    const value = schedule ? (schedule[String(week)] ?? 0) : (currentValues[String(week)] ?? 0);
    return `
      <label class="fert-week-field">
        <span>${t("week")} ${week}</span>
        <input type="number" data-week="${week}" min="0" step="0.01" value="${value}" />
      </label>
    `;
  }).join("");
  grid.innerHTML = html;
}

function syncSameAmountMode() {
  const checked = $("#fertSameAmount")?.checked;
  const wrap = $("#fertSameAmountWrap");
  if (wrap) wrap.hidden = !checked;
  $$("#fertWeekGrid input[data-week]").forEach((input) => {
    input.disabled = Boolean(checked);
  });
}

function getPercentFactor() {
  const percent = parseFloat($("#percent")?.value || "100");
  return Number.isFinite(percent) ? percent / 100 : 1;
}

function formatAmount(value) {
  return Number(value || 0).toFixed(2);
}

function renderCurrentList() {
  const list = $("#fertCurrentList");
  if (!list) return;
  if (!fertilizerCatalog.length) {
    list.innerHTML = `<li>${t("noFertilizers")}</li>`;
    return;
  }
  const factor = getPercentFactor();
  const items = fertilizerCatalog
    .map((fert) => {
      const baseValue = Number(fert.schedule?.[String(window.CURRENT_FERT_WEEK || 1)] || 0);
      const weekValue = formatAmount(convertRateValue(baseValue * factor, fert.unit));
      return `
        <li>
          <div class="icon-chip">🧪</div>
          <span>${fert.name}</span>
          <strong>${weekValue} ${displayRateUnit(fert.unit)}</strong>
          <div class="inline-actions">
            <button type="button" class="ghost small" data-fert-edit="${fert.name}">${t("edit")}</button>
            <button type="button" class="ghost small danger" data-fert-delete="${fert.name}">${t("del")}</button>
          </div>
        </li>
      `;
    })
    .join("");
  list.innerHTML = items;
  bindCatalogButtons();
}

function renderOverviewTable() {
  const body = $("#fertOverviewBody");
  if (!body) return;
  if (!fertilizerCatalog.length) {
    const cols = 2 + FERTILIZER_WEEKS.length;
    body.innerHTML = `<tr><td colspan="${cols}">${t("noFertilizers")}</td></tr>`;
    return;
  }
  const factor = getPercentFactor();
  body.innerHTML = fertilizerCatalog
    .map((fert) => {
      const weekCells = FERTILIZER_WEEKS.map((week) => {
        const amount = convertRateValue(Number(fert.schedule?.[String(week)] || 0) * factor, fert.unit);
        const klass = week === HIGHLIGHT_FERT_WEEK ? ' class="current-week"' : "";
        return `<td${klass}>${formatAmount(amount)}</td>`;
      }).join("");
      return `<tr><td>${fert.name}</td><td>${displayRateUnit(fert.unit)}</td>${weekCells}</tr>`;
    })
    .join("");
}

function bindCatalogButtons() {
  $$("[data-fert-edit]").forEach((btn) => {
    btn.onclick = () => {
      const fertilizer = fertilizerCatalog.find((item) => item.name === btn.dataset.fertEdit);
      fillManageForm(fertilizer);
      const manageCard = $("#fertManageCard");
      if (manageCard) {
        manageCard.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    };
  });
  $$("[data-fert-delete]").forEach((btn) => {
    btn.onclick = async () => {
      await deleteFertilizer(btn.dataset.fertDelete);
    };
  });
}

function renderCalculationResult(data, liters, percent) {
  const displayVolume = MEASUREMENT_SYSTEM === "imperial" ? liters * 0.264172 : liters;
  const linesHtml = data.lines
    .map(
      (line) =>
        `<li>${line.name}: ${convertRateValue(line.amount_per_l, line.unit).toFixed(2)} ${displayRateUnit(line.unit)} → ${convertTotalValue(line.total_amount, line.unit).toFixed(2)} ${displayTotalUnit(line.unit)}</li>`
    )
    .join("");
  const totalsHtml = data.totals
    .map((line) => `<strong>${t("total")}: ${convertTotalValue(line.total_amount, line.unit).toFixed(2)} ${displayTotalUnit(line.unit)}</strong>`)
    .join("<br>");
  $("#fertCalcResult").innerHTML = `
    <strong>${displayVolume.toFixed(2)} ${displayVolumeUnit()} @ ${percent}%</strong><br>
    <div>${t("week")} ${data.week} (${data.phase})</div>
    <ul>${linesHtml}</ul>
    ${totalsHtml}<br>
    <small class="hint-text">${t("saveCopy")}</small>
  `;
}

async function refreshPlan() {
  const displayLiters = parseFloat($("#liters").value);
  const percent = parseFloat($("#percent").value);
  const liters = toLiters(displayLiters);
  const data = await fetchJSON("/api/fert-plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ liters, percent }),
  });
  renderCalculationResult(data, liters, percent);
}

async function saveFertilizer() {
  const name = $("#fertName").value.trim();
  if (!name) {
    showToast(t("missingName"), true);
    return;
  }
  const schedule = {};
  const weekCount = getCurrentWeekCount();
  if ($("#fertSameAmount")?.checked) {
    const value = parseFloat($("#fertSameAmountValue")?.value || "0") || 0;
    for (let week = 1; week <= weekCount; week += 1) {
      schedule[String(week)] = value;
    }
  } else {
    $$("#fertWeekGrid input[data-week]").forEach((input) => {
      schedule[input.dataset.week] = parseFloat(input.value || "0") || 0;
    });
  }
  const res = await fetchJSON("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action: "fertilizer_save",
      original_name: $("#fertOriginalName").value,
      name,
      unit: $("#fertUnit").value,
      schedule,
    }),
  });
  fertilizerCatalog = Array.isArray(res.fertilizers) ? res.fertilizers : fertilizerCatalog;
  fillManageForm(fertilizerCatalog.find((item) => item.name === name));
  renderCurrentList();
  renderOverviewTable();
  showToast(res.message || t("fertilizerSaved"));
  setTimeout(() => window.location.reload(), 500);
}

async function deleteFertilizer(nameArg = null) {
  const name = (nameArg || $("#fertOriginalName").value || "").trim();
  if (!name) {
    showToast(t("selectDeleteFirst"), true);
    return;
  }
  if (!window.confirm(t("deleteConfirm"))) return;
  const res = await fetchJSON("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "fertilizer_delete", name }),
  });
  fertilizerCatalog = Array.isArray(res.fertilizers) ? res.fertilizers : fertilizerCatalog.filter((item) => item.name !== name);
  resetManageForm();
  renderCurrentList();
  renderOverviewTable();
  showToast(res.message || t("fertilizerDeleted"));
  setTimeout(() => window.location.reload(), 500);
}

document.addEventListener("DOMContentLoaded", () => {
  const weekCountInput = $("#fertWeekCount");
  if (weekCountInput) {
    weekCountInput.addEventListener("input", () => {
      weekCountInput.value = String(getCurrentWeekCount());
      renderWeekInputs(getCurrentWeekCount());
      syncSameAmountMode();
    });
  }

  const sameAmountToggle = $("#fertSameAmount");
  if (sameAmountToggle) {
    sameAmountToggle.addEventListener("change", syncSameAmountMode);
  }

  const form = $("#fertCalcForm");
  if (form) {
    form.addEventListener("submit", async (evt) => {
      evt.preventDefault();
      try {
        await refreshPlan();
        showToast(t("calculated"));
      } catch (err) {
        showToast(err.message, true);
      }
    });
  }

  const percentInput = $("#percent");
  if (percentInput) {
    percentInput.addEventListener("input", () => {
      renderCurrentList();
      renderOverviewTable();
    });
  }

  const saveBtn = $("#fertSaveDefault");
  if (saveBtn) {
    saveBtn.addEventListener("click", async () => {
      const liters = parseFloat($("#liters").value);
      const litersBase = toLiters(liters);
      const percent = parseFloat($("#percent").value);
      try {
        const res = await fetchJSON("/api/action", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "fert_defaults", liters: litersBase, percent }),
        });
        showToast(res.message || t("defaultSaved"));
      } catch (err) {
        showToast(err.message, true);
      }
    });
  }

  const manageForm = $("#fertManageForm");
  if (manageForm) {
    manageForm.addEventListener("submit", async (evt) => {
      evt.preventDefault();
      try {
        await saveFertilizer();
      } catch (err) {
        showToast(err.message, true);
      }
    });
  }

  const resetBtn = $("#fertResetForm");
  if (resetBtn) {
    resetBtn.addEventListener("click", () => resetManageForm());
  }

  resetManageForm();
  renderCurrentList();
  renderOverviewTable();
});
