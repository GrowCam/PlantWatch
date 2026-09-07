const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));
const toast = $("#toast");
const APP_LANG = window.APP_LANG || "de";

let tents = Array.isArray(window.TENTS) ? window.TENTS : [];
let pumps = Array.isArray(window.PUMPS) ? window.PUMPS : [];
let waterSensors = Array.isArray(window.WATER_SENSORS) ? window.WATER_SENSORS : [];
let waterPresets = Array.isArray(window.WATER_PRESETS) ? window.WATER_PRESETS : [];

const TXT = {
  de: {
    edit: "Bearbeiten",
    del: "Löschen",
    none: "— keine —",
    deleteConfirm: "Wirklich löschen?",
    selectFirst: "Bitte zuerst ein Element auswählen.",
    missingName: "Bitte einen Namen eingeben.",
    modeMinutes: "Minuten (tippen für Liter)",
    modeLiters: "Liter (tippen für Minuten)",
    inactive: "inaktiv",
    noAlerting: "keine Erinnerung",
    wet: "gefüllt",
    dry: "leer",
  },
  en: {
    edit: "Edit",
    del: "Delete",
    none: "— none —",
    deleteConfirm: "Really delete this?",
    selectFirst: "Please select an item first.",
    missingName: "Please enter a name.",
    modeMinutes: "Minutes (tap for liters)",
    modeLiters: "Liters (tap for minutes)",
    inactive: "inactive",
    noAlerting: "no reminder",
    wet: "filled",
    dry: "empty",
  },
};
const t = (key) => (TXT[APP_LANG] && TXT[APP_LANG][key]) || TXT.de[key] || key;

function presetLabel(preset) {
  const unit = preset.mode === "liters" ? "L" : "min";
  return `${preset.name} (${preset.value} ${unit})`;
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

function fillSelect(select, items, { none = true, valueKey = "id", labelKey = "name", labelFn = null } = {}) {
  if (!select) return;
  const current = select.value;
  const options = [];
  if (none) options.push(`<option value="">${t("none")}</option>`);
  items.forEach((item) => {
    const label = labelFn ? labelFn(item) : item[labelKey] || item[valueKey];
    options.push(`<option value="${item[valueKey]}">${label}</option>`);
  });
  select.innerHTML = options.join("");
  if (items.some((item) => String(item[valueKey]) === current)) {
    select.value = current;
  }
}

function refreshSelects() {
  fillSelect($("#pumpTentId"), tents);
  fillSelect($("#pumpSensorId"), waterSensors);
  fillSelect($("#pumpActivePresetId"), waterPresets, { labelFn: presetLabel });
  fillSelect($("#sensorTentId"), tents);
}

// --- Tents ---

function renderTentList() {
  const list = $("#tentCurrentList");
  if (!list) return;
  if (!tents.length) {
    list.innerHTML = `<li>${window.NO_TENTS_TEXT || ""}</li>`;
  } else {
    list.innerHTML = tents
      .map(
        (tent) => `
        <li>
          <div class="icon-chip">🏕️</div>
          <span>${tent.name}</span>
          ${tent.notes ? `<span class="manage-list-meta">${tent.notes}</span>` : ""}
          <div class="inline-actions">
            <button type="button" class="ghost small" data-tent-edit="${tent.id}">${t("edit")}</button>
            <button type="button" class="ghost small danger" data-tent-delete="${tent.id}">${t("del")}</button>
          </div>
        </li>
      `
      )
      .join("");
  }
  bindTentButtons();
}

function resetTentForm() {
  $("#tentOriginalId").value = "";
  $("#tentName").value = "";
  $("#tentNotes").value = "";
}

function fillTentForm(tent) {
  if (!tent) {
    resetTentForm();
    return;
  }
  $("#tentOriginalId").value = tent.id;
  $("#tentName").value = tent.name || "";
  $("#tentNotes").value = tent.notes || "";
}

function bindTentButtons() {
  $$("[data-tent-edit]").forEach((btn) => {
    btn.onclick = () => {
      fillTentForm(tents.find((item) => item.id === btn.dataset.tentEdit));
    };
  });
  $$("[data-tent-delete]").forEach((btn) => {
    btn.onclick = async () => {
      if (!window.confirm(t("deleteConfirm"))) return;
      await deleteTent(btn.dataset.tentDelete);
    };
  });
}

async function saveTent() {
  const name = $("#tentName").value.trim();
  if (!name) {
    showToast(t("missingName"), true);
    return;
  }
  const res = await fetchJSON("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action: "tent_save",
      original_id: $("#tentOriginalId").value,
      name,
      notes: $("#tentNotes").value.trim(),
    }),
  });
  tents = Array.isArray(res.tents) ? res.tents : tents;
  resetTentForm();
  renderTentList();
  refreshSelects();
  showToast(res.message || "OK");
}

async function deleteTent(id) {
  const target = id || $("#tentOriginalId").value;
  if (!target) {
    showToast(t("selectFirst"), true);
    return;
  }
  const res = await fetchJSON("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "tent_delete", id: target }),
  });
  tents = Array.isArray(res.tents) ? res.tents : tents.filter((item) => item.id !== target);
  if (Array.isArray(res.pumps)) pumps = res.pumps;
  if (Array.isArray(res.water_sensors)) waterSensors = res.water_sensors;
  resetTentForm();
  renderTentList();
  renderPumpList();
  renderSensorList();
  refreshSelects();
  showToast(res.message || "OK");
}

// --- Pumps ---

function pumpSummary(pump) {
  const bits = [];
  const preset = pump.active_preset_id ? waterPresets.find((p) => p.id === pump.active_preset_id) : null;
  if (preset) {
    bits.push(presetLabel(preset));
  } else if (pump.dosing_mode === "liters") {
    bits.push(`${pump.dosing_liters} L`);
  } else {
    bits.push(`${pump.dosing_minutes} min`);
  }
  if (pump.auto_water_enabled) bits.push("🤖");
  return bits.join(" · ");
}

function renderPumpList() {
  const list = $("#pumpCurrentList");
  if (!list) return;
  if (!pumps.length) {
    list.innerHTML = "<li></li>";
  } else {
    list.innerHTML = pumps
      .map(
        (pump) => `
        <li id="pump-${pump.id}">
          <div class="icon-chip">🚰</div>
          <span>${pump.name || `Pump ${pump.id}`}</span>
          <span class="manage-list-meta">${pumpSummary(pump)}</span>
          <div class="inline-actions">
            <button type="button" class="ghost small" data-pump-edit="${pump.id}">${t("edit")}</button>
            <button type="button" class="ghost small danger" data-pump-delete="${pump.id}">${t("del")}</button>
          </div>
        </li>
      `
      )
      .join("");
  }
  bindPumpButtons();
}

function setDosingModeButton(mode) {
  const btn = $("#pumpDosingModeToggle");
  const hidden = $("#pumpDosingMode");
  if (!btn || !hidden) return;
  hidden.value = mode;
  btn.dataset.mode = mode;
  btn.textContent = mode === "liters" ? t("modeLiters") : t("modeMinutes");
  const minutesWrap = $("#pumpDosingMinutesWrap");
  const litersWrap = $("#pumpDosingLitersWrap");
  if (minutesWrap) minutesWrap.hidden = mode === "liters";
  if (litersWrap) litersWrap.hidden = mode !== "liters";
}

function toggleDosingMode() {
  const current = $("#pumpDosingMode")?.value || "minutes";
  setDosingModeButton(current === "liters" ? "minutes" : "liters");
}

function syncManualDosingVisibility() {
  const section = $("#pumpManualDosingSection");
  if (!section) return;
  section.hidden = Boolean($("#pumpActivePresetId")?.value);
}

function resetPumpForm() {
  $("#pumpOriginalId").value = "";
  $("#pumpName").value = "";
  $("#pumpTopic").value = "";
  $("#pumpEnabled").checked = true;
  $("#pumpTentId").value = "";
  $("#pumpSensorId").value = "";
  setDosingModeButton("minutes");
  $("#pumpDosingMinutes").value = "2";
  $("#pumpDosingLiters").value = "1";
  $("#pumpFlowRateValue").value = "0";
  $("#pumpFlowRateUnit").value = "l_min";
  $("#pumpAutoWaterEnabled").checked = false;
  $("#pumpAutoWaterCooldown").value = "360";
  $("#pumpActivePresetId").value = "";
  syncManualDosingVisibility();
}

function fillPumpForm(pump) {
  if (!pump) {
    resetPumpForm();
    return;
  }
  $("#pumpOriginalId").value = pump.id;
  $("#pumpName").value = pump.name || "";
  $("#pumpTopic").value = pump.topic || "";
  $("#pumpEnabled").checked = pump.enabled !== false;
  $("#pumpTentId").value = pump.tent_id || "";
  $("#pumpSensorId").value = pump.sensor_id || "";
  setDosingModeButton(pump.dosing_mode === "liters" ? "liters" : "minutes");
  $("#pumpDosingMinutes").value = pump.dosing_minutes ?? 2;
  $("#pumpDosingLiters").value = pump.dosing_liters ?? 1;
  $("#pumpFlowRateValue").value = pump.flow_rate_value ?? 0;
  $("#pumpFlowRateUnit").value = pump.flow_rate_unit || "l_min";
  $("#pumpAutoWaterEnabled").checked = Boolean(pump.auto_water_enabled);
  $("#pumpAutoWaterCooldown").value = pump.auto_water_cooldown_minutes ?? 360;
  $("#pumpActivePresetId").value = pump.active_preset_id || "";
  syncManualDosingVisibility();
}

function bindPumpButtons() {
  $$("[data-pump-edit]").forEach((btn) => {
    btn.onclick = () => {
      fillPumpForm(pumps.find((item) => item.id === btn.dataset.pumpEdit));
      $("#pumpManageCard")?.scrollIntoView({ behavior: "smooth", block: "start" });
    };
  });
  $$("[data-pump-delete]").forEach((btn) => {
    btn.onclick = async () => {
      if (!window.confirm(t("deleteConfirm"))) return;
      await deletePump(btn.dataset.pumpDelete);
    };
  });
}

async function savePump() {
  const name = $("#pumpName").value.trim();
  if (!name) {
    showToast(t("missingName"), true);
    return;
  }
  const res = await fetchJSON("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action: "pump_save",
      original_id: $("#pumpOriginalId").value,
      name,
      topic: $("#pumpTopic").value.trim(),
      enabled: $("#pumpEnabled").checked,
      tent_id: $("#pumpTentId").value,
      sensor_id: $("#pumpSensorId").value,
      auto_water_enabled: $("#pumpAutoWaterEnabled").checked,
      auto_water_cooldown_minutes: parseInt($("#pumpAutoWaterCooldown").value || "360", 10),
      dosing_mode: $("#pumpDosingMode").value === "liters" ? "liters" : "minutes",
      dosing_minutes: parseFloat($("#pumpDosingMinutes").value || "0"),
      dosing_liters: parseFloat($("#pumpDosingLiters").value || "0"),
      flow_rate_value: parseFloat($("#pumpFlowRateValue").value || "0"),
      flow_rate_unit: $("#pumpFlowRateUnit").value,
      active_preset_id: $("#pumpActivePresetId").value,
    }),
  });
  if (res.message && res.message.startsWith("❌")) {
    showToast(res.message, true);
    return;
  }
  pumps = Array.isArray(res.pumps) ? res.pumps : pumps;
  resetPumpForm();
  renderPumpList();
  showToast(res.message || "OK");
}

async function deletePump(id) {
  const target = id || $("#pumpOriginalId").value;
  if (!target) {
    showToast(t("selectFirst"), true);
    return;
  }
  const res = await fetchJSON("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "pump_delete", id: target }),
  });
  pumps = Array.isArray(res.pumps) ? res.pumps : pumps.filter((item) => item.id !== target);
  resetPumpForm();
  renderPumpList();
  showToast(res.message || "OK");
}

// --- Water sensors ---

function sensorStateLabel(sensor) {
  if (sensor.state === "ON") return t("wet");
  if (sensor.state === "OFF") return t("dry");
  return "–";
}

function sensorSummary(sensor) {
  const bits = [sensorStateLabel(sensor)];
  const tent = sensor.tent_id ? tents.find((item) => item.id === sensor.tent_id) : null;
  bits.push(tent ? tent.name : t("none"));
  if (sensor.topic) bits.push(sensor.topic);
  if (sensor.enabled === false) bits.push(t("inactive"));
  if (sensor.alerting_enabled === false) bits.push(t("noAlerting"));
  return bits.join(" · ");
}

function renderSensorList() {
  const list = $("#sensorCurrentList");
  if (!list) return;
  if (!waterSensors.length) {
    list.innerHTML = "<li></li>";
  } else {
    list.innerHTML = waterSensors
      .map(
        (sensor) => `
        <li>
          <div class="icon-chip">🛟</div>
          <span>${sensor.name || `Sensor ${sensor.id}`}</span>
          <span class="manage-list-meta">${sensorSummary(sensor)}</span>
          <div class="inline-actions">
            <button type="button" class="ghost small" data-sensor-edit="${sensor.id}">${t("edit")}</button>
            <button type="button" class="ghost small danger" data-sensor-delete="${sensor.id}">${t("del")}</button>
          </div>
        </li>
      `
      )
      .join("");
  }
  bindSensorButtons();
}

function resetSensorForm() {
  $("#sensorOriginalId").value = "";
  $("#sensorName").value = "";
  $("#sensorTopic").value = "";
  $("#sensorEnabled").checked = true;
  $("#sensorTentId").value = "";
  $("#sensorAlertingEnabled").checked = true;
}

function fillSensorForm(sensor) {
  if (!sensor) {
    resetSensorForm();
    return;
  }
  $("#sensorOriginalId").value = sensor.id;
  $("#sensorName").value = sensor.name || "";
  $("#sensorTopic").value = sensor.topic || "";
  $("#sensorEnabled").checked = sensor.enabled !== false;
  $("#sensorTentId").value = sensor.tent_id || "";
  $("#sensorAlertingEnabled").checked = sensor.alerting_enabled !== false;
}

function bindSensorButtons() {
  $$("[data-sensor-edit]").forEach((btn) => {
    btn.onclick = () => {
      fillSensorForm(waterSensors.find((item) => item.id === btn.dataset.sensorEdit));
    };
  });
  $$("[data-sensor-delete]").forEach((btn) => {
    btn.onclick = async () => {
      if (!window.confirm(t("deleteConfirm"))) return;
      await deleteSensor(btn.dataset.sensorDelete);
    };
  });
}

async function saveSensor() {
  const name = $("#sensorName").value.trim();
  if (!name) {
    showToast(t("missingName"), true);
    return;
  }
  const res = await fetchJSON("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action: "water_sensor_save",
      original_id: $("#sensorOriginalId").value,
      name,
      topic: $("#sensorTopic").value.trim(),
      enabled: $("#sensorEnabled").checked,
      tent_id: $("#sensorTentId").value,
      alerting_enabled: $("#sensorAlertingEnabled").checked,
    }),
  });
  if (res.message && res.message.startsWith("❌")) {
    showToast(res.message, true);
    return;
  }
  waterSensors = Array.isArray(res.water_sensors) ? res.water_sensors : waterSensors;
  resetSensorForm();
  renderSensorList();
  refreshSelects();
  showToast(res.message || "OK");
}

async function deleteSensor(id) {
  const target = id || $("#sensorOriginalId").value;
  if (!target) {
    showToast(t("selectFirst"), true);
    return;
  }
  const res = await fetchJSON("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "water_sensor_delete", id: target }),
  });
  waterSensors = Array.isArray(res.water_sensors) ? res.water_sensors : waterSensors.filter((item) => item.id !== target);
  if (Array.isArray(res.pumps)) pumps = res.pumps;
  resetSensorForm();
  renderSensorList();
  renderPumpList();
  refreshSelects();
  showToast(res.message || "OK");
}

// --- Presets ---

function renderPresetList() {
  const list = $("#presetCurrentList");
  if (!list) return;
  if (!waterPresets.length) {
    list.innerHTML = "<li></li>";
  } else {
    list.innerHTML = waterPresets
      .map(
        (preset) => `
        <li>
          <div class="icon-chip">🧴</div>
          <span>${preset.name}</span>
          <span class="manage-list-meta">${preset.value} ${preset.mode === "liters" ? "L" : "min"}</span>
          <div class="inline-actions">
            <button type="button" class="ghost small" data-preset-edit="${preset.id}">${t("edit")}</button>
            <button type="button" class="ghost small danger" data-preset-delete="${preset.id}">${t("del")}</button>
          </div>
        </li>
      `
      )
      .join("");
  }
  bindPresetButtons();
}

function resetPresetForm() {
  $("#presetOriginalId").value = "";
  $("#presetName").value = "";
  $("#presetMode").value = "minutes";
  $("#presetValue").value = "10";
}

function fillPresetForm(preset) {
  if (!preset) {
    resetPresetForm();
    return;
  }
  $("#presetOriginalId").value = preset.id;
  $("#presetName").value = preset.name || "";
  $("#presetMode").value = preset.mode || "minutes";
  $("#presetValue").value = preset.value ?? 10;
}

function bindPresetButtons() {
  $$("[data-preset-edit]").forEach((btn) => {
    btn.onclick = () => {
      fillPresetForm(waterPresets.find((item) => item.id === btn.dataset.presetEdit));
    };
  });
  $$("[data-preset-delete]").forEach((btn) => {
    btn.onclick = async () => {
      if (!window.confirm(t("deleteConfirm"))) return;
      await deletePreset(btn.dataset.presetDelete);
    };
  });
}

async function savePreset() {
  const name = $("#presetName").value.trim();
  if (!name) {
    showToast(t("missingName"), true);
    return;
  }
  const res = await fetchJSON("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action: "water_preset_save",
      original_id: $("#presetOriginalId").value,
      name,
      mode: $("#presetMode").value,
      value: parseFloat($("#presetValue").value || "0"),
    }),
  });
  if (res.message && res.message.startsWith("❌")) {
    showToast(res.message, true);
    return;
  }
  waterPresets = Array.isArray(res.water_presets) ? res.water_presets : waterPresets;
  resetPresetForm();
  renderPresetList();
  refreshSelects();
  showToast(res.message || "OK");
}

async function deletePreset(id) {
  const target = id || $("#presetOriginalId").value;
  if (!target) {
    showToast(t("selectFirst"), true);
    return;
  }
  const res = await fetchJSON("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "water_preset_delete", id: target }),
  });
  waterPresets = Array.isArray(res.water_presets) ? res.water_presets : waterPresets.filter((item) => item.id !== target);
  if (Array.isArray(res.pumps)) pumps = res.pumps;
  resetPresetForm();
  renderPresetList();
  renderPumpList();
  refreshSelects();
  showToast(res.message || "OK");
}

document.addEventListener("DOMContentLoaded", () => {
  refreshSelects();
  renderTentList();
  renderPumpList();
  renderSensorList();
  renderPresetList();
  resetTentForm();
  resetPumpForm();
  resetSensorForm();
  resetPresetForm();

  $("#tentManageForm")?.addEventListener("submit", async (evt) => {
    evt.preventDefault();
    try {
      await saveTent();
    } catch (err) {
      showToast(err.message, true);
    }
  });
  $("#tentResetForm")?.addEventListener("click", () => resetTentForm());
  $("#tentDeleteBtn")?.addEventListener("click", async () => {
    if (!window.confirm(t("deleteConfirm"))) return;
    try {
      await deleteTent();
    } catch (err) {
      showToast(err.message, true);
    }
  });

  $("#pumpManageForm")?.addEventListener("submit", async (evt) => {
    evt.preventDefault();
    try {
      await savePump();
    } catch (err) {
      showToast(err.message, true);
    }
  });
  $("#pumpResetForm")?.addEventListener("click", () => resetPumpForm());
  $("#pumpDeleteBtn")?.addEventListener("click", async () => {
    if (!window.confirm(t("deleteConfirm"))) return;
    try {
      await deletePump();
    } catch (err) {
      showToast(err.message, true);
    }
  });
  $("#pumpDosingModeToggle")?.addEventListener("click", toggleDosingMode);
  $("#pumpActivePresetId")?.addEventListener("change", syncManualDosingVisibility);

  $("#sensorManageForm")?.addEventListener("submit", async (evt) => {
    evt.preventDefault();
    try {
      await saveSensor();
    } catch (err) {
      showToast(err.message, true);
    }
  });
  $("#sensorResetForm")?.addEventListener("click", () => resetSensorForm());
  $("#sensorDeleteBtn")?.addEventListener("click", async () => {
    if (!window.confirm(t("deleteConfirm"))) return;
    try {
      await deleteSensor();
    } catch (err) {
      showToast(err.message, true);
    }
  });

  $("#presetManageForm")?.addEventListener("submit", async (evt) => {
    evt.preventDefault();
    try {
      await savePreset();
    } catch (err) {
      showToast(err.message, true);
    }
  });
  $("#presetResetForm")?.addEventListener("click", () => resetPresetForm());
  $("#presetDeleteBtn")?.addEventListener("click", async () => {
    if (!window.confirm(t("deleteConfirm"))) return;
    try {
      await deletePreset();
    } catch (err) {
      showToast(err.message, true);
    }
  });

  if (window.location.hash.startsWith("#pump-")) {
    const pumpId = window.location.hash.replace("#pump-", "");
    const pump = pumps.find((item) => item.id === pumpId);
    if (pump) {
      fillPumpForm(pump);
      $("#pumpManageCard")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }
});
