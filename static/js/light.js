const $ = (selector) => document.querySelector(selector);
const toast = $("#toast");
const APP_LANG = window.APP_LANG || "de";
const TXT = {
  de: { powerUnknown: "Leistung: – W", powerLabel: "Leistung", on: "An", off: "Aus" },
  en: { powerUnknown: "Power: – W", powerLabel: "Power", on: "On", off: "Off" },
};
const t = (key) => (TXT[APP_LANG] && TXT[APP_LANG][key]) || TXT.de[key] || key;

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

function normalizePowerValue(power) {
  if (power === null || power === undefined) return null;
  const num = Number(power);
  if (!Number.isFinite(num)) return null;
  return Number(num.toFixed(1));
}

function setLightUI(state, power = undefined) {
  const normalizedState = state ? state.toUpperCase() : null;
  const switchEl = $("#lightSwitch");
  const powerLabel = $("#lightPower");
  if (switchEl) switchEl.checked = normalizedState === "ON";
  if (powerLabel) {
    const displayPower = normalizedState === "OFF" ? 0 : normalizePowerValue(power);
    powerLabel.textContent = displayPower != null ? `${t("powerLabel")}: ${displayPower.toFixed(1)} W` : t("powerUnknown");
  }
}

async function refreshLightState() {
  try {
    const res = await fetchJSON("/api/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "light_state" }),
    });
    setLightUI(res.light_state, res.power_w);
  } catch (err) {
    console.warn("Light state fetch failed", err);
  }
}

async function loadLightDebug() {
  try {
    const data = await fetchJSON("/api/light-debug");
    const setText = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.textContent = value;
    };
    setText("lightDebugState", data.plug_state || "–");
    setText("lightDebugPower", data.plug_power_w != null ? `${Number(data.plug_power_w).toFixed(1)} W` : "–");
    setText("lightDebugWindow", `${data.lights_on_start || "–"}–${data.lights_on_end || "–"}`);
    setText("lightDebugReason", data.last_reason || "–");
    setText("lightDebugCommand", data.last_command_requested_state ? `${data.last_command_requested_state} @ ${data.last_command_time || "–"}` : "–");
    setText("lightDebugAck", data.last_command_result || "–");
  } catch (err) {
    console.warn("Light debug fetch failed", err);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const lightSwitch = $("#lightSwitch");
  const form = $("#lightDefaultsForm");
  const cycleForm = $("#lightCycleForm");
  if (lightSwitch) {
    lightSwitch.addEventListener("change", async () => {
      try {
        const res = await fetchJSON("/api/action", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "light", command: lightSwitch.checked ? "on" : "off" }),
        });
        showToast(res.message || "OK");
      } catch (err) {
        lightSwitch.checked = !lightSwitch.checked;
        showToast(err.message, true);
      }
    });
  }
  if (form) {
    form.addEventListener("submit", async (evt) => {
      evt.preventDefault();
      try {
        const res = await fetchJSON("/api/action", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action: "light_defaults",
            enabled: $("#lightEnabledAutomation")?.checked || false,
            debug_notify: $("#lightDebugNotify")?.checked || false,
            light_debug_card_enabled: $("#lightDebugCardEnabled")?.checked || false,
            control_interval_seconds: parseInt($("#lightControlInterval")?.value || "0", 10),
          }),
        });
        const settings = res.light_settings || {};
        if ($("#lightCardAuto")) $("#lightCardAuto").textContent = settings.enabled ? t("on") : t("off");
        if ($("#lightCardDebug")) $("#lightCardDebug").textContent = settings.debug_notify ? t("on") : t("off");
        showToast(res.message || "Saved");
        loadLightDebug();
      } catch (err) {
        showToast(err.message, true);
      }
    });
  }
  if (cycleForm) {
    cycleForm.addEventListener("submit", async (evt) => {
      evt.preventDefault();
      try {
        const res = await fetchJSON("/api/action", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action: "light_cycle_settings",
            lights_on_start: $("#lightStart")?.value || "",
            lights_on_end: $("#lightEnd")?.value || "",
          }),
        });
        const settings = res.light_cycle_settings || {};
        if ($("#lightCardWindow")) $("#lightCardWindow").textContent = `${settings.lights_on_start || "–"}–${settings.lights_on_end || "–"}`;
        showToast(res.message || "Saved");
        loadLightDebug();
      } catch (err) {
        showToast(err.message, true);
      }
    });
  }
  refreshLightState();
  if ($("#lightDebugReason")) {
    loadLightDebug();
    setInterval(loadLightDebug, 12000);
  }
  setInterval(refreshLightState, 12000);
});
