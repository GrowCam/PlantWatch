const $ = (selector) => document.querySelector(selector);
const toast = $("#toast");
let climateChart;
let climateQuery = "range=24h";
let currentMode = "raw";
let heaterState = null;
let heaterPower = null;
let exhaustState = null;
let exhaustPower = null;
let dehumidifierState = null;
let dehumidifierPower = null;
let humidifierState = null;
let humidifierPower = null;
const APP_LANG = window.APP_LANG || "de";
const APP_SETTINGS = window.APP_SETTINGS || {};
const TEMP_UNIT = APP_SETTINGS.temperature_unit || "c";
const DATETIME_FORMAT = APP_SETTINGS.datetime_format || "eu";
const TXT = {
  de: { statusOn: "Status: AN", statusOff: "Status: AUS", statusUnknown: "Status: unbekannt", powerUnknown: "Leistung: – W", powerLabel: "Leistung", confirmed: "bestätigt", notConfirmed: "nicht bestätigt", idle: "idle", ageSuffix: "s alt", invalidTimeframe: "Ungültiges Zeitfenster", on: "An", off: "Aus" },
  en: { statusOn: "Status: ON", statusOff: "Status: OFF", statusUnknown: "Status: unknown", powerUnknown: "Power: – W", powerLabel: "Power", confirmed: "confirmed", notConfirmed: "not confirmed", idle: "idle", ageSuffix: "s old", invalidTimeframe: "Invalid timeframe", on: "On", off: "Off" },
};
const t = (key) => (TXT[APP_LANG] && TXT[APP_LANG][key]) || TXT.de[key] || key;

function formatDateTime(value) {
  if (!value) return "–";
  const date = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return String(value);
  if (DATETIME_FORMAT === "iso") {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")} ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
  }
  if (DATETIME_FORMAT === "us") {
    return date.toLocaleString("en-US", { month: "2-digit", day: "2-digit", year: "numeric", hour: "numeric", minute: "2-digit" });
  }
  return date.toLocaleString(APP_LANG === "en" ? "en-GB" : "de-DE", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function formatDateTimeLocal(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function setClimateDateInputs(start, end) {
  const startInput = $("#climateStart");
  const endInput = $("#climateEnd");
  if (startInput) startInput.value = formatDateTimeLocal(start);
  if (endInput) endInput.value = formatDateTimeLocal(end);
}

function syncClimateRangeControls(query) {
  const tabs = document.querySelectorAll("#climateRangeTabs .tab");
  const params = new URLSearchParams(query);
  const range = params.get("range");
  tabs.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.range === range);
  });
  if (params.has("start") || params.has("end")) {
    const end = params.get("end") ? new Date(params.get("end")) : new Date();
    const start = params.get("start") ? new Date(params.get("start")) : new Date(end.getTime() - 24 * 3600 * 1000);
    if (!Number.isNaN(start.getTime()) && !Number.isNaN(end.getTime())) {
      setClimateDateInputs(start, end);
    }
  } else if (range && range !== "all") {
    const match = String(range).match(/^(\d+)h$/);
    const hours = match ? parseInt(match[1], 10) : 24;
    const end = new Date();
    const start = new Date(end.getTime() - hours * 3600 * 1000);
    setClimateDateInputs(start, end);
  }
}

function convertTemp(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return null;
  return TEMP_UNIT === "f" ? (num * 9) / 5 + 32 : num;
}

function tempSuffix() {
  return TEMP_UNIT === "f" ? "°F" : "°C";
}

async function fetchJSON(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const msg = await res.text();
    throw new Error(msg || res.statusText);
  }
  return res.json();
}

function showToast(message, isError = false) {
  if (!toast) return;
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2500);
}

function bindSliderOutputs(root = document) {
  root.querySelectorAll(".slider-field input[type='range']").forEach((input) => {
    const numberInput = input.parentElement?.querySelector(`[data-slider-number-for='${input.id}']`);
    const render = () => {
      if (numberInput) numberInput.value = input.value;
    };
    render();
    input.addEventListener("input", render);
    input.addEventListener("change", render);
    numberInput?.addEventListener("input", () => {
      input.value = numberInput.value;
    });
    numberInput?.addEventListener("change", () => {
      input.value = numberInput.value;
      render();
    });
  });
}

function boolLabel(enabled) {
  return enabled ? t("on") : t("off");
}

function normalizePowerValue(power) {
  if (power === null || power === undefined) return null;
  const num = Number(power);
  if (!Number.isFinite(num)) return null;
  return Number(num.toFixed(1));
}

function movingAverage(series, window = 5) {
  if (window <= 1) return series.slice();
  const result = [];
  for (let i = 0; i < series.length; i++) {
    const start = Math.max(0, i - window + 1);
    const slice = series.slice(start, i + 1).filter((v) => v !== null && v !== undefined);
    if (!slice.length) {
      result.push(null);
    } else {
      const avg = slice.reduce((sum, v) => sum + v, 0) / slice.length;
      result.push(Number(avg.toFixed(2)));
    }
  }
  return result;
}

function deltas(series) {
  const result = [null];
  for (let i = 1; i < series.length; i++) {
    const prev = series[i - 1];
    const curr = series[i];
    if (prev === null || curr === null || prev === undefined || curr === undefined) {
      result.push(null);
    } else {
      result.push(Number((curr - prev).toFixed(2)));
    }
  }
  return result;
}

function transformSeries(series, mode) {
  if (mode === "smooth") {
    return movingAverage(series, 5);
  }
  if (mode === "delta") {
    return deltas(series);
  }
  return series;
}

function renderChart(points) {
  const labels = points.map((p) => (p.raw_timestamp ? formatDateTime(p.raw_timestamp) : p.timestamp));
  const temps = points.map((p) => (p.temperature != null ? convertTemp(p.temperature) : null));
  const hums = points.map((p) => (p.humidity != null ? Number(p.humidity) : null));
  const vpds = points.map((p) => (p.vpd != null ? Number(p.vpd) : null));
  const tempsTransformed = transformSeries(temps, currentMode);
  const humsTransformed = transformSeries(hums, currentMode);
  const vpdsTransformed = transformSeries(vpds, currentMode);
  const isDelta = currentMode === "delta";
  const tempRange = isDelta ? { min: TEMP_UNIT === "f" ? -5.4 : -3, max: TEMP_UNIT === "f" ? 5.4 : 3 } : { min: TEMP_UNIT === "f" ? 59 : 15, max: TEMP_UNIT === "f" ? 86 : 30 };
  const humRange = isDelta ? { min: -5, max: 5 } : { min: 40, max: 80 };
  const vpdRange = isDelta ? { min: -0.5, max: 0.5 } : { min: 0.2, max: 1.8 };

  const ctx = document.getElementById("climateChart");
  if (!ctx) return;
  const gradientTemp = ctx.getContext("2d").createLinearGradient(0, 0, 0, ctx.height);
  gradientTemp.addColorStop(0, "rgba(249,115,22,0.35)");
  gradientTemp.addColorStop(1, "rgba(249,115,22,0)");
  const gradientHum = ctx.getContext("2d").createLinearGradient(0, 0, 0, ctx.height);
  gradientHum.addColorStop(0, "rgba(96,165,250,0.35)");
  gradientHum.addColorStop(1, "rgba(96,165,250,0)");
  const gradientVpd = ctx.getContext("2d").createLinearGradient(0, 0, 0, ctx.height);
  gradientVpd.addColorStop(0, "rgba(34,197,94,0.35)");
  gradientVpd.addColorStop(1, "rgba(34,197,94,0)");

  const datasets = [
    {
      label: currentMode === "delta" ? `Δ Temperatur ${tempSuffix()}` : `Temperatur ${tempSuffix()}`,
      data: tempsTransformed,
      borderColor: "#f97316",
      backgroundColor: gradientTemp,
      tension: 0.25,
      borderWidth: 2,
      spanGaps: true,
      pointRadius: 0,
      yAxisID: "y",
    },
    {
      label: currentMode === "delta" ? "Δ Luftfeuchtigkeit %" : "Luftfeuchtigkeit %",
      data: humsTransformed,
      borderColor: "#60a5fa",
      backgroundColor: gradientHum,
      tension: 0.25,
      borderWidth: 2,
      spanGaps: true,
      pointRadius: 0,
      yAxisID: "y1",
    },
    {
      label: currentMode === "delta" ? "Δ VPD kPa" : "VPD kPa",
      data: vpdsTransformed,
      borderColor: "#22c55e",
      backgroundColor: gradientVpd,
      tension: 0.25,
      borderWidth: 2,
      spanGaps: true,
      pointRadius: 0,
      yAxisID: "y2",
    },
  ];

  if (!climateChart) {
    climateChart = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets,
      },
      options: {
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { labels: { color: "#94a3b8" } },
        },
        scales: {
          x: {
            ticks: { color: "#94a3b8", maxRotation: 45, minRotation: 45 },
          },
          y: {
            ticks: { color: "#f97316" },
            min: tempRange.min,
            max: tempRange.max,
          },
          y1: {
            position: "right",
            ticks: { color: "#60a5fa" },
            min: humRange.min,
            max: humRange.max,
            grid: { drawOnChartArea: false },
          },
          y2: {
            position: "right",
            ticks: { color: "#22c55e" },
            min: vpdRange.min,
            max: vpdRange.max,
            grid: { drawOnChartArea: false },
          },
        },
      },
    });
  } else {
    climateChart.data.labels = labels;
    climateChart.data.datasets = datasets;
    climateChart.options.scales.y.min = tempRange.min;
    climateChart.options.scales.y.max = tempRange.max;
    climateChart.options.scales.y1.min = humRange.min;
    climateChart.options.scales.y1.max = humRange.max;
    climateChart.options.scales.y2.min = vpdRange.min;
    climateChart.options.scales.y2.max = vpdRange.max;
    climateChart.update();
  }
}

async function loadClimate(query = "range=24h") {
  climateQuery = query;
  syncClimateRangeControls(query);
  try {
    const res = await fetchJSON(`/api/sensor-history?${query}`);
    renderChart(res.points || []);
  } catch (err) {
    showToast(err.message, true);
  }
}

function renderHeaterDebug(data) {
  const fmtTemp = (value) => (value != null && Number.isFinite(Number(value)) ? `${Number(value).toFixed(2)}°C` : "–");
  const fmtTempDisplay = (value) => {
    const converted = convertTemp(value);
    return converted != null && Number.isFinite(Number(converted)) ? `${Number(converted).toFixed(2)}${tempSuffix()}` : "–";
  };
  const fmtPower = (value) => (value != null && Number.isFinite(Number(value)) ? `${Number(value).toFixed(1)} W` : "–");
  const setText = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  };
  setText("heaterDebugCurrent", fmtTempDisplay(data.current_reading_c));
  setText("heaterDebugMedian", fmtTempDisplay(data.median_c));
  setText("heaterDebugState", data.plug_state || "–");
  setText("heaterDebugPower", fmtPower(data.plug_power_w));
  setText("heaterDebugTime", data.reading_time ? `${data.reading_time} (${data.reading_age_seconds}${t("ageSuffix")})` : "–");
  if (data.target_c != null) {
    setText(
      "heaterDebugThresholds",
      `${fmtTempDisplay(data.target_c)} | ON<=${fmtTempDisplay(data.on_threshold_c)} | OFF>=${fmtTempDisplay(data.off_threshold_c)}`
    );
  } else {
    setText("heaterDebugThresholds", "–");
  }
  setText("heaterDebugDecision", data.last_decision || t("idle"));
  if (data.last_command_requested_state || data.last_command_time) {
    setText(
      "heaterDebugCommand",
      `${data.last_command_requested_state || "–"} @ ${data.last_command_time || "–"} via ${data.command_topic || "–"}`
    );
  } else {
    setText("heaterDebugCommand", "–");
  }
  const ackText =
    data.last_command_confirmed === true
      ? `${t("confirmed")} | ${data.last_command_result || ""}`
      : data.last_command_confirmed === false
        ? `${t("notConfirmed")} | ${data.last_command_result || ""}`
        : data.last_command_result || "–";
  setText("heaterDebugAck", ackText);
}

async function loadHeaterDebug() {
  try {
    const data = await fetchJSON("/api/heater-debug");
    renderHeaterDebug(data);
  } catch (err) {
    console.warn("Heater debug fetch failed", err);
  }
}

function renderExhaustDebug(data) {
  const fmtTempDisplay = (value) => {
    const converted = convertTemp(value);
    return converted != null && Number.isFinite(Number(converted)) ? `${Number(converted).toFixed(2)}${tempSuffix()}` : "–";
  };
  const fmtPower = (value) => (value != null && Number.isFinite(Number(value)) ? `${Number(value).toFixed(1)} W` : "–");
  const setText = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  };
  setText("exhaustDebugTemp", fmtTempDisplay(data.current_temp_c));
  setText("exhaustDebugRh", data.current_rh != null ? `${Number(data.current_rh).toFixed(1)}%` : "–");
  setText(
    "exhaustDebugMedian",
    `${fmtTempDisplay(data.median_temp_c)} | ${data.median_rh != null ? `${Number(data.median_rh).toFixed(1)}%` : "–"}`
  );
  setText("exhaustDebugState", data.plug_state || "–");
  setText("exhaustDebugPower", fmtPower(data.plug_power_w));
  setText("exhaustDebugTime", data.reading_time ? `${data.reading_time} (${data.reading_age_seconds}${t("ageSuffix")})` : "–");
  setText("exhaustDebugRefresh", data.forced_refresh_active ? "ON" : "OFF");
  setText("exhaustDebugReason", data.last_reason || t("idle"));
  setText("exhaustDebugChangeReason", data.last_change_reason || "–");
  if (data.last_command_requested_state || data.last_command_time) {
    setText(
      "exhaustDebugCommand",
      `${data.last_command_requested_state || "–"} @ ${data.last_command_time || "–"} via ${data.command_topic || "–"}`
    );
  } else {
    setText("exhaustDebugCommand", "–");
  }
  const ackText =
    data.last_command_confirmed === true
      ? `${t("confirmed")} | ${data.last_command_result || ""}`
      : data.last_command_confirmed === false
        ? `${t("notConfirmed")} | ${data.last_command_result || ""}`
        : data.last_command_result || "–";
  setText("exhaustDebugAck", ackText);
}

async function loadExhaustDebug() {
  try {
    const data = await fetchJSON("/api/exhaust-debug");
    renderExhaustDebug(data);
  } catch (err) {
    console.warn("Exhaust debug fetch failed", err);
  }
}

async function triggerHeater(command) {
  const payload = { action: "heater", command };
  const res = await fetchJSON("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  showToast(res.message || "OK");
  if (command === "on") {
    setHeaterUI("ON");
  } else if (command === "off") {
    setHeaterUI("OFF");
  }
  setTimeout(refreshHeaterState, 500);
}

async function saveHeaterDefaults() {
  const payload = {
    action: "heater_defaults",
    enabled: $("#heaterEnabled")?.checked || false,
    debug_notify: $("#heaterDebugNotify")?.checked || false,
    day_target_c: parseFloat($("#heaterDayTarget")?.value || "0"),
    night_target_c: parseFloat($("#heaterNightTarget")?.value || "0"),
    on_below_offset_c: parseFloat($("#heaterOnOffset")?.value || "0"),
    off_above_offset_c: parseFloat($("#heaterOffOffset")?.value || "0"),
    min_on_seconds: parseInt($("#heaterMinOn")?.value || "0", 10),
    min_off_seconds: parseInt($("#heaterMinOff")?.value || "0", 10),
    sensor_max_age_seconds: parseInt($("#heaterSensorAge")?.value || "0", 10),
    control_interval_seconds: parseInt($("#heaterControlInterval")?.value || "0", 10),
    sensor_median_samples: parseInt($("#heaterMedianSamples")?.value || "0", 10),
  };
  if ($("#heaterDebugCardEnabled")) {
    payload.heater_debug_card_enabled = $("#heaterDebugCardEnabled").checked;
  }
  const res = await fetchJSON("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const settings = res.heater_settings || payload;
  if ($("#heaterCardAuto")) $("#heaterCardAuto").textContent = boolLabel(Boolean(settings.enabled));
  if ($("#heaterCardDebug")) $("#heaterCardDebug").textContent = boolLabel(Boolean(settings.debug_notify));
  if ($("#heaterCardTargets")) $("#heaterCardTargets").textContent = `${settings.day_target_c}°C / ${settings.night_target_c}°C`;
  showToast(res.message || "Heizungs-Defaults gespeichert");
}

async function refreshHeaterState() {
  try {
    const res = await fetchJSON("/api/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "heater_state" }),
    });
    const power = normalizePowerValue(res.power_w);
    if (res.heater_state) {
      setHeaterUI(res.heater_state, power);
    } else if (heaterState === null || power !== null) {
      setHeaterUI(null, power);
    }
  } catch (err) {
    console.warn("Heizungsstatus fehlgeschlagen", err);
  }
}

function setHeaterUI(state, power = undefined) {
  heaterState = state ? state.toUpperCase() : null;
  if (power !== undefined) {
    heaterPower = normalizePowerValue(power);
  } else if (heaterState === "OFF") {
    heaterPower = 0;
  }
  const switchEl = $("#dehumSwitch");
  const powerLabel = $("#dehumPower");
  if (switchEl) {
    switchEl.checked = heaterState === "ON";
  }
  if (powerLabel) {
    const displayPower = heaterState === "OFF" ? 0 : heaterPower;
    powerLabel.textContent = displayPower != null ? `${t("powerLabel")}: ${displayPower.toFixed(1)} W` : t("powerUnknown");
  }
}

async function triggerExhaust(command) {
  const payload = { action: "exhaust", command };
  const res = await fetchJSON("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  showToast(res.message || "OK");
  if (command === "on") {
    setExhaustUI("ON");
  } else if (command === "off") {
    setExhaustUI("OFF");
  }
  setTimeout(refreshExhaustState, 500);
}

async function saveExhaustDefaults() {
  const payload = {
    action: "exhaust_defaults",
    enabled: $("#exhaustEnabled")?.checked || false,
    debug_notify: $("#exhaustDebugNotify")?.checked || false,
    rh_turn_on_above: parseFloat($("#exhaustRhOn")?.value || "0"),
    rh_turn_off_below: parseFloat($("#exhaustRhOff")?.value || "0"),
    temp_force_on_above: parseFloat($("#exhaustTempOn")?.value || "0"),
    temp_allow_off_below: parseFloat($("#exhaustTempOff")?.value || "0"),
    min_on_seconds: parseInt($("#exhaustMinOn")?.value || "0", 10),
    min_off_seconds: parseInt($("#exhaustMinOff")?.value || "0", 10),
    max_off_time_before_refresh: parseInt($("#exhaustMaxOffRefresh")?.value || "0", 10),
    forced_refresh_run_time: parseInt($("#exhaustForcedRefresh")?.value || "0", 10),
    sensor_max_age_seconds: parseInt($("#exhaustSensorAge")?.value || "0", 10),
    control_interval_seconds: parseInt($("#exhaustControlInterval")?.value || "0", 10),
    sensor_median_samples: parseInt($("#exhaustMedianSamples")?.value || "0", 10),
  };
  const res = await fetchJSON("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const settings = res.exhaust_settings || payload;
  if ($("#exhaustCardAuto")) $("#exhaustCardAuto").textContent = boolLabel(Boolean(settings.enabled));
  if ($("#exhaustCardDebug")) $("#exhaustCardDebug").textContent = boolLabel(Boolean(settings.debug_notify));
  if ($("#exhaustCardRh")) $("#exhaustCardRh").textContent = `${settings.rh_turn_on_above}% / ${settings.rh_turn_off_below}%`;
  if ($("#exhaustCardTemp")) $("#exhaustCardTemp").textContent = `${settings.temp_force_on_above}°C / ${settings.temp_allow_off_below}°C`;
  showToast(res.message || "Abluft-Einstellungen gespeichert");
}

async function refreshExhaustState() {
  try {
    const res = await fetchJSON("/api/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "exhaust_state" }),
    });
    const power = normalizePowerValue(res.power_w);
    if (res.exhaust_state) {
      setExhaustUI(res.exhaust_state, power);
    } else if (exhaustState === null || power !== null) {
      setExhaustUI(null, power);
    }
  } catch (err) {
    console.warn("Abluftstatus fehlgeschlagen", err);
  }
}

function setExhaustUI(state, power = undefined) {
  exhaustState = state ? state.toUpperCase() : null;
  if (power !== undefined) {
    exhaustPower = normalizePowerValue(power);
  } else if (exhaustState === "OFF") {
    exhaustPower = 0;
  }
  const switchEl = $("#exhaustSwitch");
  const powerLabel = $("#exhaustPower");
  if (switchEl) {
    switchEl.checked = exhaustState === "ON";
  }
  if (powerLabel) {
    const displayPower = exhaustState === "OFF" ? 0 : exhaustPower;
    powerLabel.textContent = displayPower != null ? `${t("powerLabel")}: ${displayPower.toFixed(1)} W` : t("powerUnknown");
  }
}

async function triggerDevice(action, command) {
  const res = await fetchJSON("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, command }),
  });
  showToast(res.message || "OK");
}

function setSimpleDeviceUI(switchId, powerId, state, power = undefined) {
  const normalizedState = state ? state.toUpperCase() : null;
  let normalizedPower = power !== undefined ? normalizePowerValue(power) : null;
  if (normalizedState === "OFF") normalizedPower = 0;
  const switchEl = $(switchId);
  const powerLabel = $(powerId);
  if (switchEl) switchEl.checked = normalizedState === "ON";
  if (powerLabel) {
    const displayPower = normalizedState === "OFF" ? 0 : normalizedPower;
    powerLabel.textContent = displayPower != null ? `${t("powerLabel")}: ${displayPower.toFixed(1)} W` : t("powerUnknown");
  }
}

async function refreshDeviceState(action, stateKey, switchId, powerId, setter) {
  try {
    const res = await fetchJSON("/api/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    });
    const power = normalizePowerValue(res.power_w);
    const state = res[stateKey];
    setter(state ? state.toUpperCase() : null, power);
    setSimpleDeviceUI(switchId, powerId, state, power);
  } catch (err) {
    console.warn(`${action} failed`, err);
  }
}

async function saveHumidityDefaults() {
  const methodSelect = $("#humidityControlMethod");
  const controlMethod = methodSelect?.value || ($("#dehumidifierSwitch") || $("#humidifierSwitch") ? "devices" : "exhaust");
  const humidityPayload = {
    action: "humidity_defaults",
    enabled: $("#humidityEnabled")?.checked || false,
    debug_notify: $("#humidityDebugNotify")?.checked || false,
    control_method: controlMethod,
    exhaust_control_mode: $("#exhaustControlMode")?.value || "sensor",
    rh_upper_threshold: parseFloat($("#humidityUpper")?.value || "0"),
    rh_lower_threshold: parseFloat($("#humidityLower")?.value || "0"),
    cycle_on_seconds: parseInt($("#humidityCycleOn")?.value || "0", 10),
    cycle_off_seconds: parseInt($("#humidityCycleOff")?.value || "0", 10),
    min_on_seconds: parseInt($("#humidityMinOn")?.value || "0", 10),
    min_off_seconds: parseInt($("#humidityMinOff")?.value || "0", 10),
    sensor_max_age_seconds: parseInt($("#humiditySensorAge")?.value || "0", 10),
    control_interval_seconds: parseInt($("#humidityControlInterval")?.value || "0", 10),
    sensor_median_samples: parseInt($("#humidityMedianSamples")?.value || "0", 10),
  };
  if ($("#exhaustDebugCardEnabled")) {
    humidityPayload.exhaust_debug_card_enabled = $("#exhaustDebugCardEnabled").checked;
  }
  const exhaustPayload = {
    action: "exhaust_defaults",
    enabled: $("#humidityEnabled")?.checked || false,
    debug_notify: $("#humidityDebugNotify")?.checked || false,
    rh_turn_on_above: parseFloat($("#exhaustRhOn")?.value || "0"),
    rh_turn_off_below: parseFloat($("#exhaustRhOff")?.value || "0"),
    temp_force_on_above: parseFloat($("#exhaustTempOn")?.value || "0"),
    temp_allow_off_below: parseFloat($("#exhaustTempOff")?.value || "0"),
    min_on_seconds: parseInt($("#exhaustMinOn")?.value || "0", 10),
    min_off_seconds: parseInt($("#exhaustMinOff")?.value || "0", 10),
    max_off_time_before_refresh: parseInt($("#exhaustMaxOffRefresh")?.value || "0", 10),
    forced_refresh_run_time: parseInt($("#exhaustForcedRefresh")?.value || "0", 10),
    sensor_max_age_seconds: parseInt($("#exhaustSensorAge")?.value || "0", 10),
    control_interval_seconds: parseInt($("#exhaustControlInterval")?.value || "0", 10),
    sensor_median_samples: parseInt($("#exhaustMedianSamples")?.value || "0", 10),
  };
  const humidityRes = await fetchJSON("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(humidityPayload),
  });
  if ($("#exhaustSwitch")) {
    await fetchJSON("/api/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(exhaustPayload),
    });
    if ($("#exhaustCardAuto")) $("#exhaustCardAuto").textContent = boolLabel(Boolean(exhaustPayload.enabled));
    if ($("#exhaustCardDebug")) $("#exhaustCardDebug").textContent = boolLabel(Boolean(exhaustPayload.debug_notify));
    if ($("#exhaustCardRh")) $("#exhaustCardRh").textContent = `${exhaustPayload.rh_turn_on_above}% / ${exhaustPayload.rh_turn_off_below}%`;
    if ($("#exhaustCardTemp")) $("#exhaustCardTemp").textContent = `${exhaustPayload.temp_force_on_above}°C / ${exhaustPayload.temp_allow_off_below}°C`;
  }
  showToast(humidityRes.message || "Humidity settings saved");
}

function updateHumidityModeUI() {
  const hasMethodSelect = Boolean($("#humidityControlMethod"));
  const method = $("#humidityControlMethod")?.value || ($("#exhaustSwitch") ? "exhaust" : "devices");
  const exhaustMode = $("#exhaustControlMode")?.value || "sensor";
  const exhaustGroup = $("#humidityExhaustModeGroup");
  const cycleGroup = $("#humidityCycleGroup");
  const deviceThresholdGroup = $("#humidityDeviceThresholdGroup");
  const deviceTimingGroup = $("#humidityDeviceTimingGroup");
  const exhaustSensorGroup = $("#exhaustSensorThresholdGroup");
  const exhaustTimingGroup = $("#exhaustTimingGroup");
  const useExhaust = method === "exhaust";
  if (exhaustGroup) exhaustGroup.hidden = !useExhaust;
  if (cycleGroup) cycleGroup.hidden = !(useExhaust && exhaustMode === "cycle");
  if (deviceThresholdGroup) deviceThresholdGroup.hidden = useExhaust || !hasMethodSelect;
  if (deviceTimingGroup) deviceTimingGroup.hidden = useExhaust || !hasMethodSelect;
  if (exhaustSensorGroup) exhaustSensorGroup.hidden = !(useExhaust && exhaustMode === "sensor");
  if (exhaustTimingGroup) exhaustTimingGroup.hidden = !useExhaust;
}

async function loadHumidityDebug() {
  try {
    const data = await fetchJSON("/api/humidity-debug");
    const active = data.dehumidifier_state === "ON" ? "Dehumidifier" : data.humidifier_state === "ON" ? "Humidifier" : "–";
    const setText = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.textContent = value;
    };
    setText("humidityDebugCurrent", data.current_rh != null ? `${Number(data.current_rh).toFixed(1)}%` : "–");
    setText("humidityDebugMedian", data.median_rh != null ? `${Number(data.median_rh).toFixed(1)}%` : "–");
    setText("humidityDebugActive", active);
    setText("humidityDebugTime", data.reading_time || "–");
    setText("humidityDebugReason", data.last_reason || "–");
    setText("humidityDebugChange", data.last_change_reason || "–");
    setText("humidityDebugBand", `${data.rh_lower_threshold ?? "–"}% / ${data.rh_upper_threshold ?? "–"}%`);
  } catch (err) {
    console.warn("Humidity debug fetch failed", err);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  bindSliderOutputs();
  document.querySelectorAll("#climateRangeTabs .tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#climateRangeTabs .tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      loadClimate(`range=${encodeURIComponent(btn.dataset.range || "24h")}`);
    });
  });

  const customApply = $("#climateCustomApply");
  if (customApply) {
    customApply.addEventListener("click", () => {
      const startValue = $("#climateStart")?.value || "";
      const endValue = $("#climateEnd")?.value || "";
      if (!startValue || !endValue) {
        showToast(t("invalidTimeframe"), true);
        return;
      }
      const start = new Date(startValue);
      const end = new Date(endValue);
      if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || start > end) {
        showToast(t("invalidTimeframe"), true);
        return;
      }
      loadClimate(`start=${encodeURIComponent(startValue)}&end=${encodeURIComponent(endValue)}`);
    });
  }

  const select = $("#resolutionSelect");
  if (select) {
    select.addEventListener("change", () => {
      currentMode = select.value;
      loadClimate(climateQuery);
    });
  }

  syncClimateRangeControls(climateQuery);
  loadClimate(climateQuery);
  refreshHeaterState();
  refreshExhaustState();
  refreshDeviceState("dehumidifier_device_state", "dehumidifier_state", "#dehumidifierSwitch", "#dehumidifierPower", (state, power) => {
    dehumidifierState = state;
    dehumidifierPower = power;
  });
  refreshDeviceState("humidifier_state", "humidifier_state", "#humidifierSwitch", "#humidifierPower", (state, power) => {
    humidifierState = state;
    humidifierPower = power;
  });
  if ($("#heaterDebugList")) {
    loadHeaterDebug();
    setInterval(loadHeaterDebug, 12000);
  }
  if ($("#exhaustDebugReason")) {
    loadExhaustDebug();
    setInterval(loadExhaustDebug, 12000);
  }
  if ($("#humidityDebugReason")) {
    loadHumidityDebug();
    setInterval(loadHumidityDebug, 12000);
  }
  setInterval(refreshHeaterState, 12000);
  setInterval(refreshExhaustState, 12000);
  setInterval(() => refreshDeviceState("dehumidifier_device_state", "dehumidifier_state", "#dehumidifierSwitch", "#dehumidifierPower", (state, power) => {
    dehumidifierState = state;
    dehumidifierPower = power;
  }), 12000);
  setInterval(() => refreshDeviceState("humidifier_state", "humidifier_state", "#humidifierSwitch", "#humidifierPower", (state, power) => {
    humidifierState = state;
    humidifierPower = power;
  }), 12000);

  const dehumSwitch = $("#dehumSwitch");
  const heaterDefaultsForm = $("#heaterDefaultsForm");
  const exhaustSwitch = $("#exhaustSwitch");
  const dehumidifierSwitch = $("#dehumidifierSwitch");
  const humidifierSwitch = $("#humidifierSwitch");
  const humidityDefaultsForm = $("#humidityDefaultsForm");
  const humidityControlMethod = $("#humidityControlMethod");
  const exhaustControlMode = $("#exhaustControlMode");
  if (dehumSwitch) {
    dehumSwitch.addEventListener("change", async () => {
      try {
        await triggerHeater(dehumSwitch.checked ? "on" : "off");
      } catch (err) {
        dehumSwitch.checked = !dehumSwitch.checked;
        showToast(err.message, true);
      }
    });
  }
  if (heaterDefaultsForm) {
    heaterDefaultsForm.addEventListener("submit", async (evt) => {
      evt.preventDefault();
      try {
        await saveHeaterDefaults();
        loadHeaterDebug();
      } catch (err) {
        showToast(err.message, true);
      }
    });
  }
  if (exhaustSwitch) {
    exhaustSwitch.addEventListener("change", async () => {
      try {
        await triggerExhaust(exhaustSwitch.checked ? "on" : "off");
      } catch (err) {
        exhaustSwitch.checked = !exhaustSwitch.checked;
        showToast(err.message, true);
      }
    });
  }
  if (dehumidifierSwitch) {
    dehumidifierSwitch.addEventListener("change", async () => {
      try {
        await triggerDevice("dehumidifier_device", dehumidifierSwitch.checked ? "on" : "off");
      } catch (err) {
        dehumidifierSwitch.checked = !dehumidifierSwitch.checked;
        showToast(err.message, true);
      }
    });
  }
  if (humidifierSwitch) {
    humidifierSwitch.addEventListener("change", async () => {
      try {
        await triggerDevice("humidifier", humidifierSwitch.checked ? "on" : "off");
      } catch (err) {
        humidifierSwitch.checked = !humidifierSwitch.checked;
        showToast(err.message, true);
      }
    });
  }
  if (humidityDefaultsForm) {
    humidityDefaultsForm.addEventListener("submit", async (evt) => {
      evt.preventDefault();
      try {
        await saveHumidityDefaults();
        loadExhaustDebug();
        loadHumidityDebug();
      } catch (err) {
        showToast(err.message, true);
      }
    });
  }
  humidityControlMethod?.addEventListener("change", updateHumidityModeUI);
  exhaustControlMode?.addEventListener("change", updateHumidityModeUI);
  updateHumidityModeUI();
});
