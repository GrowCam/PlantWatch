const $ = (selector) => document.querySelector(selector);
const toast = $("#toast");
const APP_LANG = window.APP_LANG || "de";
const TXT = {
  de: { pumpOn: "Status: AN", pumpOff: "Status: AUS", unknown: "Status: unbekannt", powerUnknown: "Leistung: – W", powerLabel: "Leistung", reservoirOk: "Status: gefüllt", reservoirEmpty: "Status: leer", saved: "Gespeichert", invalidMinutes: "Bitte Minuten > 0 angeben.", remaining: "Verbleibend", choosePresetFirst: "Bitte zuerst ein Preset wählen." },
  en: { pumpOn: "Status: ON", pumpOff: "Status: OFF", unknown: "Status: unknown", powerUnknown: "Power: – W", powerLabel: "Power", reservoirOk: "Status: filled", reservoirEmpty: "Status: empty", saved: "Saved", invalidMinutes: "Please enter minutes > 0.", remaining: "Remaining", choosePresetFirst: "Please choose a preset first." },
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

const PUMP_CARDS = Array.from(document.querySelectorAll(".pump-card")).map((el) => ({
  id: el.dataset.pumpId,
}));
const pumpRuntime = {};
PUMP_CARDS.forEach((p) => (pumpRuntime[p.id] = { state: null, power: null, timerRemaining: null }));

const SENSOR_STATES = Array.from(document.querySelectorAll("[id^='waterLeakState']")).map((el) => ({
  id: el.dataset.sensorId,
  el,
}));
const sensorRuntime = {};
SENSOR_STATES.forEach((s) => (sensorRuntime[s.id] = null));

function renderPumpCountdown(id) {
  const el = document.getElementById(`pumpCountdown${id}`);
  if (!el) return;
  const rt = pumpRuntime[id];
  if (rt.state === "ON" && Number.isFinite(rt.timerRemaining) && rt.timerRemaining > 0) {
    el.hidden = false;
    el.textContent = `${t("remaining")}: ${formatRemaining(rt.timerRemaining)}`;
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

async function triggerPump(pump, command, minutes = null) {
  const payload = { action: "pump", pump_id: pump.id, command };
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
    setPumpUI(pump, "ON");
  } else if (command === "off") {
    setPumpUI(pump, "OFF");
  }
  // Refresh status after a short delay to pick up retained messages
  setTimeout(() => refreshPumpState(pump), 500);
}

async function runPreset(pump) {
  const select = document.getElementById(`pumpPresetSelect${pump.id}`);
  const presetId = select ? select.value : "";
  if (!presetId) {
    showToast(t("choosePresetFirst"), true);
    return;
  }
  const res = await fetchJSON("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "pump_run_preset", pump_id: pump.id, preset_id: presetId }),
  });
  showToast(res.message || "OK");
  setPumpUI(pump, "ON");
  setTimeout(() => refreshPumpState(pump), 500);
}

async function refreshPumpState(pump) {
  try {
    const res = await fetchJSON("/api/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "pump_state", pump_id: pump.id }),
    });
    const power = normalizePowerValue(res.power_w);
    const rt = pumpRuntime[pump.id];
    rt.timerRemaining = Number.isFinite(Number(res.timer_remaining_seconds)) ? Number(res.timer_remaining_seconds) : null;
    if (res.state) {
      setPumpUI(pump, res.state, power);
    } else if (rt.state === null || power !== null) {
      // Only show unknown state if we have never seen one; keep power updates if available.
      setPumpUI(pump, null, power);
    }
  } catch (err) {
    // Don't spam errors; toast once
    console.warn("Pump state fetch failed", err);
  }
}

function setPumpUI(pump, state, power = undefined) {
  const rt = pumpRuntime[pump.id];
  rt.state = state ? state.toUpperCase() : null;
  if (power !== undefined) {
    rt.power = normalizePowerValue(power);
  } else if (rt.state === "OFF") {
    rt.power = 0;
  }
  const switchEl = document.getElementById(`pumpSwitch${pump.id}`);
  const powerLabel = document.getElementById(`pumpPower${pump.id}`);
  if (switchEl) {
    switchEl.checked = rt.state === "ON";
  }
  if (powerLabel) {
    const displayPower = rt.state === "OFF" ? 0 : rt.power;
    powerLabel.textContent = displayPower != null ? `${t("powerLabel")}: ${displayPower.toFixed(1)} W` : t("powerUnknown");
  }
  if (rt.state === "OFF") {
    rt.timerRemaining = null;
  }
  renderPumpCountdown(pump.id);
}

async function refreshSensorState(sensor) {
  try {
    const res = await fetchJSON("/api/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "water_sensor_state", sensor_id: sensor.id }),
    });
    if (res.water_sensor_state) {
      setSensorUI(sensor, res.water_sensor_state);
    } else if (sensorRuntime[sensor.id] === null) {
      setSensorUI(sensor, null);
    }
  } catch (err) {
    console.warn("Water sensor fetch failed", err);
  }
}

function setSensorUI(sensor, state) {
  const normalized = state ? state.toUpperCase() : null;
  sensorRuntime[sensor.id] = normalized;
  const label = sensor.el;
  if (!label) return;
  let text = t("unknown");
  if (normalized === "ON") text = t("reservoirOk");
  else if (normalized === "OFF") text = t("reservoirEmpty");
  label.textContent = text;
  label.classList.toggle("wet", normalized === "ON");
  label.classList.toggle("dry", normalized === "OFF");
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

  PUMP_CARDS.forEach((pump) => {
    const switchEl = document.getElementById(`pumpSwitch${pump.id}`);
    const timerForm = document.getElementById(`pumpTimerForm${pump.id}`);
    const presetBtn = document.querySelector(`[data-pump-run-preset="${pump.id}"]`);

    if (switchEl) {
      switchEl.addEventListener("change", async () => {
        try {
          await triggerPump(pump, switchEl.checked ? "on" : "off");
        } catch (err) {
          switchEl.checked = !switchEl.checked;
          showToast(err.message, true);
        }
      });
    }

    if (timerForm) {
      timerForm.addEventListener("submit", async (evt) => {
        evt.preventDefault();
        const minutesInput = document.getElementById(`pumpMinutes${pump.id}`);
        const value = minutesInput ? parseFloat(minutesInput.value) : NaN;
        if (!Number.isFinite(value) || value <= 0) {
          showToast(t("invalidMinutes"), true);
          return;
        }
        try {
          await triggerPump(pump, "timer", value);
        } catch (err) {
          showToast(err.message, true);
        }
      });
    }

    if (presetBtn) {
      presetBtn.addEventListener("click", async () => {
        try {
          await runPreset(pump);
        } catch (err) {
          showToast(err.message, true);
        }
      });
    }

    refreshPumpState(pump);
  });

  SENSOR_STATES.forEach((sensor) => refreshSensorState(sensor));

  // Initial status fetch and periodic refresh
  setInterval(() => {
    PUMP_CARDS.forEach((pump) => {
      const rt = pumpRuntime[pump.id];
      if (Number.isFinite(rt.timerRemaining) && rt.timerRemaining > 0) {
        rt.timerRemaining -= 1;
      }
      renderPumpCountdown(pump.id);
    });
  }, 1000);
  setInterval(() => PUMP_CARDS.forEach(refreshPumpState), 10000);
  setInterval(() => SENSOR_STATES.forEach(refreshSensorState), 12000);
});
