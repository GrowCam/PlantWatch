const $ = (selector) => document.querySelector(selector);
const toast = $("#toast");
let currentChart;
let energyChart;
let monthChart;
let powerData = window.POWER_SUMMARY || null;
const visibleDevices = new Set();
const builtinCurrencies = new Set(["EUR", "USD", "GBP"]);
let filtersSignature = "";
let chartRenderQueued = false;

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

function getVisibleDevices(devices) {
  return devices.filter((device) => visibleDevices.has(device.id));
}

function renderFilters(devices) {
  const container = $("#powerDeviceFilters");
  if (!container) return;
  const signature = devices.map((device) => device.id).join("|");
  if (signature === filtersSignature) return;
  filtersSignature = signature;
  container.innerHTML = "";
  devices.forEach((device) => {
    if (!visibleDevices.has(device.id)) visibleDevices.add(device.id);
    const label = document.createElement("label");
    label.className = "toggle";
    label.innerHTML = `<span>${device.icon} ${device.name}</span><input type="checkbox" ${visibleDevices.has(device.id) ? "checked" : ""} />`;
    const input = label.querySelector("input");
    input.addEventListener("change", () => {
      if (input.checked) visibleDevices.add(device.id);
      else visibleDevices.delete(device.id);
      renderCharts();
    });
    container.appendChild(label);
  });
}

function chartColors(index, colorKey = "") {
  const keyed = {
    teal: "#14b8a6",
    orange: "#f97316",
    cyan: "#06b6d4",
    gold: "#f59e0b",
    slate: "#94a3b8",
    blue: "#60a5fa",
  };
  const palette = ["#14b8a6", "#f97316", "#60a5fa", "#f59e0b", "#94a3b8", "#22c55e", "#ec4899"];
  return keyed[colorKey] || palette[index % palette.length];
}

function renderCharts() {
  if (!powerData) return;
  const devices = getVisibleDevices(powerData.devices);
  const labels = devices.map((d) => d.name);
  const powerValues = devices.map((d) => Number(d.currentPowerW || 0));
  const energyValues = devices.map((d) => Number(d.energyTodayKWh || 0));
  const monthValues = devices.map((d) => Number(d.energyMonthKWh || 0));
  const colors = devices.map((device, i) => chartColors(i, device.colorKey));
  const powerCtx = document.getElementById("powerCurrentChart");
  const energyCtx = document.getElementById("powerEnergyChart");
  const monthCtx = document.getElementById("powerMonthChart");
  if (powerCtx) {
    if (!currentChart) {
      currentChart = new Chart(powerCtx, {
        type: "bar",
        data: { labels, datasets: [{ label: "W", data: powerValues, backgroundColor: colors, borderRadius: 14 }] },
        options: { plugins: { legend: { display: false } } },
      });
    } else {
      currentChart.data.labels = labels;
      currentChart.data.datasets[0].data = powerValues;
      currentChart.data.datasets[0].backgroundColor = colors;
      currentChart.update();
    }
  }
  if (energyCtx) {
    if (!energyChart) {
      energyChart = new Chart(energyCtx, {
        type: "bar",
        data: { labels, datasets: [{ label: "kWh", data: energyValues, backgroundColor: colors, borderRadius: 14 }] },
        options: { plugins: { legend: { display: false } } },
      });
    } else {
      energyChart.data.labels = labels;
      energyChart.data.datasets[0].data = energyValues;
      energyChart.data.datasets[0].backgroundColor = colors;
      energyChart.update();
    }
  }
  if (monthCtx) {
    if (!monthChart) {
      monthChart = new Chart(monthCtx, {
        type: "bar",
        data: { labels, datasets: [{ label: "kWh", data: monthValues, backgroundColor: colors, borderRadius: 14 }] },
        options: { plugins: { legend: { display: false } } },
      });
    } else {
      monthChart.data.labels = labels;
      monthChart.data.datasets[0].data = monthValues;
      monthChart.data.datasets[0].backgroundColor = colors;
      monthChart.update();
    }
  }
}

function scheduleChartRender() {
  if (chartRenderQueued) return;
  chartRenderQueued = true;
  window.requestAnimationFrame(() => {
    chartRenderQueued = false;
    renderCharts();
  });
}

function renderSummary(data) {
  powerData = data;
  if ($("#totalPowerValue")) $("#totalPowerValue").textContent = `${Number(data.totals.currentPowerW).toFixed(1)} W`;
  if ($("#totalEnergyYesterday")) $("#totalEnergyYesterday").textContent = `${Number(data.totals.energyYesterdayKWh).toFixed(2)} kWh`;
  if ($("#totalEnergyToday")) $("#totalEnergyToday").textContent = `${Number(data.totals.energyTodayKWh).toFixed(2)} kWh`;
  if ($("#totalEnergyMonth")) $("#totalEnergyMonth").textContent = `${Number(data.totals.energyMonthKWh).toFixed(2)} kWh`;
  if ($("#totalCostYesterday")) $("#totalCostYesterday").textContent = `${data.currencySymbol}${Number(data.totals.costYesterday).toFixed(2)}`;
  if ($("#totalCostToday")) $("#totalCostToday").textContent = `${data.currencySymbol}${Number(data.totals.costToday).toFixed(2)}`;
  if ($("#totalCostMonth")) $("#totalCostMonth").textContent = `${data.currencySymbol}${Number(data.totals.costMonth).toFixed(2)}`;
  data.devices.forEach((device) => {
    const setText = (selector, value) => {
      const el = document.querySelector(selector);
      if (el) el.textContent = value;
    };
    setText(`[data-device-power="${device.id}"]`, `${Number(device.currentPowerW).toFixed(1)} W`);
    setText(`[data-device-yesterday="${device.id}"]`, `${Number(device.energyYesterdayKWh).toFixed(2)} kWh`);
    setText(`[data-device-today="${device.id}"]`, `${Number(device.energyTodayKWh).toFixed(2)} kWh`);
    setText(`[data-device-month="${device.id}"]`, `${Number(device.energyMonthKWh).toFixed(2)} kWh`);
    setText(`[data-device-cost-yesterday="${device.id}"]`, `${data.currencySymbol}${Number(device.costYesterday).toFixed(2)}`);
    setText(`[data-device-cost-today="${device.id}"]`, `${data.currencySymbol}${Number(device.costToday).toFixed(2)}`);
    setText(`[data-device-cost-month="${device.id}"]`, `${data.currencySymbol}${Number(device.costMonth).toFixed(2)}`);
    setText(`[data-device-updated="${device.id}"]`, device.updatedAt || "–");
  });
  renderFilters(data.devices);
  scheduleChartRender();
}

async function refreshPower() {
  try {
    const data = await fetchJSON("/api/power-summary");
    renderSummary(data);
  } catch (err) {
    console.warn("Power summary fetch failed", err);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const initial = window.POWER_SUMMARY || null;
  const powerSettingsForm = $("#powerSettingsForm");
  const currencySelect = $("#powerCurrency");
  const customCurrencyGroup = $("#powerCustomCurrencyGroup");
  const customCurrencyInput = $("#powerCurrencyCustom");
  const pricePerKwhInput = $("#pricePerKwh");
  const pricePerKwhLabel = $("#pricePerKwhLabel");

  const updateCurrencyMode = () => {
    const isCustom = currencySelect?.value === "custom";
    if (customCurrencyGroup) customCurrencyGroup.hidden = !isCustom;
  };

  currencySelect?.addEventListener("change", updateCurrencyMode);
  updateCurrencyMode();

  if (powerSettingsForm) {
    powerSettingsForm.addEventListener("submit", async (evt) => {
      evt.preventDefault();
      try {
        const selectedCurrency = currencySelect?.value || "EUR";
        const resolvedCurrency = selectedCurrency === "custom"
          ? (customCurrencyInput?.value || "").trim()
          : selectedCurrency;
        const data = await fetchJSON("/api/action", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action: "power_settings",
            price_per_kwh: pricePerKwhInput?.value || "0",
            currency: resolvedCurrency,
          }),
        });
        if (resolvedCurrency && currencySelect && !builtinCurrencies.has(resolvedCurrency)) {
          currencySelect.value = "custom";
        }
        if (pricePerKwhLabel && data.currency_symbol) {
          pricePerKwhLabel.textContent = `${pricePerKwhLabel.textContent.replace(/\s*\([^)]*\)\s*$/, "")} (${data.currency_symbol})`;
        }
        showToast(data.message || "Saved");
        await refreshPower();
      } catch (err) {
        showToast(err.message, true);
      }
    });
  }

  if (initial) {
    window.requestAnimationFrame(() => renderSummary(initial));
  }
  setInterval(refreshPower, 15000);
});
