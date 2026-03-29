const $ = (selector) => document.querySelector(selector);
const toast = $("#toast");
let pumpState = null;
let pumpPower = null;
let leakState = null;
let pumpTimerRemaining = null;
const APP_LANG = window.APP_LANG || "de";
const TXT = {
  de: { pumpOn: "Status: AN", pumpOff: "Status: AUS", unknown: "Status: unbekannt", powerUnknown: "Leistung: – W", powerLabel: "Leistung", reservoirOk: "Status: gefüllt", reservoirEmpty: "Status: leer", saved: "Gespeichert", invalidMinutes: "Bitte Minuten > 0 angeben.", remaining: "Verbleibend" },
  en: { pumpOn: "Status: ON", pumpOff: "Status: OFF", unknown: "Status: unknown", powerUnknown: "Power: – W", powerLabel: "Power", reservoirOk: "Status: filled", reservoirEmpty: "Status: empty", saved: "Saved", invalidMinutes: "Please enter minutes > 0.", remaining: "Remaining" },
};
const t = (key) => (TXT[APP_LANG] && TXT[APP_LANG][key]) || TXT.de[key] || key;

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

function normalizePowerValue(power) {
  if (power === null || power === undefined) return null;
  const num = Number(power);
  if (!Number.isFinite(num)) return null;
  return Number(num.toFixed(1));
}

function formatRemaining(seconds) {
  if (!Number.isFinite(seconds) || seconds <= 0) return null;
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${String(secs).padStart(2, "0")}`;
}

function renderPumpCountdown() {
  const el = $("#pumpCountdown");
  if (!el) return;
  if (pumpState === "ON" && Number.isFinite(pumpTimerRemaining) && pumpTimerRemaining > 0) {
    el.hidden = false;
    el.textContent = `${t("remaining")}: ${formatRemaining(pumpTimerRemaining)}`;
  } else {
    el.hidden = true;
    el.textContent = "";
  }
}

async function saveWatering(dateValue, clear = false) {
  const payload = { action: "water" };
  if (dateValue) {
    payload.date = dateValue;
  }
  if (clear) {
    payload.clear = true;
  }
  const res = await fetchJSON("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  showToast(res.message || t("saved"));
  setTimeout(() => window.location.reload(), 800);
}

async function triggerPump(command, minutes = null) {
  const payload = { action: "pump", command };
  if (minutes !== null && minutes !== undefined) {
    payload.minutes = minutes;
  }
  const res = await fetchJSON("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  showToast(res.message || "OK");
  if (command === "on" || command === "timer") {
    setPumpUI("ON");
  } else if (command === "off") {
    setPumpUI("OFF");
  }
  // Refresh status after a short delay to pick up retained messages
  setTimeout(() => refreshPumpState(), 500);
}

async function refreshPumpState() {
  try {
    const res = await fetchJSON("/api/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "pump_state" }),
    });
    const power = normalizePowerValue(res.power_w);
    pumpTimerRemaining = Number.isFinite(Number(res.timer_remaining_seconds)) ? Number(res.timer_remaining_seconds) : null;
    if (res.pump_state) {
      setPumpUI(res.pump_state, power);
    } else if (pumpState === null || power !== null) {
      // Only show unknown state if we have never seen one; keep power updates if available.
      setPumpUI(null, power);
    }
  } catch (err) {
    // Don't spam errors; toast once
    console.warn("Pump state fetch failed", err);
  }
}

function setPumpUI(state, power = undefined) {
  pumpState = state ? state.toUpperCase() : null;
  if (power !== undefined) {
    pumpPower = normalizePowerValue(power);
  } else if (pumpState === "OFF") {
    pumpPower = 0;
  }
  const switchEl = $("#pumpSwitch");
  const powerLabel = $("#pumpPower");
  if (switchEl) {
    switchEl.checked = pumpState === "ON";
  }
  if (powerLabel) {
    const displayPower = pumpState === "OFF" ? 0 : pumpPower;
    powerLabel.textContent = displayPower != null ? `${t("powerLabel")}: ${displayPower.toFixed(1)} W` : t("powerUnknown");
  }
  if (pumpState === "OFF") {
    pumpTimerRemaining = null;
  }
  renderPumpCountdown();
}

async function refreshLeakState() {
  try {
    const res = await fetchJSON("/api/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "water_sensor_state" }),
    });
    if (res.water_sensor_state) {
      setLeakUI(res.water_sensor_state);
    } else if (leakState === null) {
      setLeakUI(null);
    }
  } catch (err) {
    console.warn("Water sensor fetch failed", err);
  }
}

function setLeakUI(state) {
  leakState = state ? state.toUpperCase() : null;
  const label = $("#waterLeakState");
  if (!label) return;
  let text = "Status: unbekannt";
  if (leakState === "ON") text = t("reservoirOk");
  else if (leakState === "OFF") text = t("reservoirEmpty");
  label.textContent = text;
  label.classList.toggle("wet", leakState === "ON");
  label.classList.toggle("dry", leakState === "OFF");
}

document.addEventListener("DOMContentLoaded", () => {
  const form = $("#waterForm");
  if (form) {
    form.addEventListener("submit", async (evt) => {
      evt.preventDefault();
      const value = $("#waterDate").value || null;
      try {
        await saveWatering(value);
      } catch (err) {
        showToast(err.message, true);
      }
    });
  }

  document.querySelectorAll("[data-water-action]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const action = btn.dataset.waterAction;
      try {
        if (action === "today") {
          const today = new Date().toISOString().slice(0, 10);
          await saveWatering(today);
        } else if (action === "clear") {
          await saveWatering(null, true);
        }
      } catch (err) {
        showToast(err.message, true);
      }
    });
  });

  const pumpSwitch = $("#pumpSwitch");
  const pumpTimerForm = $("#pumpTimerForm");

  if (pumpSwitch) {
    pumpSwitch.addEventListener("change", async () => {
      try {
        await triggerPump(pumpSwitch.checked ? "on" : "off");
      } catch (err) {
        pumpSwitch.checked = !pumpSwitch.checked;
        showToast(err.message, true);
      }
    });
  }

  if (pumpTimerForm) {
    pumpTimerForm.addEventListener("submit", async (evt) => {
      evt.preventDefault();
      const minutesInput = $("#pumpMinutes");
      const value = minutesInput ? parseFloat(minutesInput.value) : NaN;
      if (!Number.isFinite(value) || value <= 0) {
        showToast(t("invalidMinutes"), true);
        return;
      }
      try {
        await triggerPump("timer", value);
      } catch (err) {
        showToast(err.message, true);
      }
    });
  }

  // Initial status fetch and periodic refresh
  refreshPumpState();
  refreshLeakState();
  setInterval(() => {
    if (Number.isFinite(pumpTimerRemaining) && pumpTimerRemaining > 0) {
      pumpTimerRemaining -= 1;
    }
    renderPumpCountdown();
  }, 1000);
  setInterval(refreshPumpState, 10000);
  setInterval(refreshLeakState, 12000);
});
