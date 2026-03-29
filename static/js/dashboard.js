const $ = (selector) => document.querySelector(selector);
const toast = $("#toast");
let sensorChart;
let sensorQuery = "range=24h";
const APP_LANG = window.APP_LANG || "de";
const APP_SETTINGS = window.APP_SETTINGS || {};
const TEMP_UNIT = APP_SETTINGS.temperature_unit || "c";
const DATETIME_FORMAT = APP_SETTINGS.datetime_format || "eu";
const TXT = {
  de: {
    vegetative: "Veg",
    openPlan: "Plan offen",
    synced: "Synchronisiert",
    week: "Woche",
    noImage: "Kein Bild",
    temperature: "Temperatur °C",
    humidity: "Luftfeuchtigkeit %",
    vpd: "VPD kPa",
    dashboardError: "Dashboard Fehler",
    actionDone: "Aktion ausgeführt",
    error: "Fehler",
    sensorDataError: "Sensor-Daten Fehler",
    invalidTimeframe: "Ungültiges Zeitfenster",
  },
  en: {
    vegetative: "Veg",
    openPlan: "Open plan",
    synced: "Synced",
    week: "Week",
    noImage: "No image",
    temperature: "Temperature °C",
    humidity: "Humidity %",
    vpd: "VPD kPa",
    dashboardError: "Dashboard error",
    actionDone: "Action executed",
    error: "Error",
    sensorDataError: "Sensor data error",
    invalidTimeframe: "Invalid timeframe",
  },
};
const t = (key) => (TXT[APP_LANG] && TXT[APP_LANG][key]) || TXT.de[key] || key;

function formatDateTimeLocal(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hours}:${minutes}`;
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

function formatDate(dateStr) {
  if (!dateStr) return "–";
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return dateStr;
  if (DATETIME_FORMAT === "iso") return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  if (DATETIME_FORMAT === "us") return date.toLocaleDateString("en-US");
  return date.toLocaleDateString(APP_LANG === "en" ? "en-GB" : "de-DE");
}

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

function convertTemp(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return null;
  return TEMP_UNIT === "f" ? (num * 9) / 5 + 32 : num;
}

function tempSuffix() {
  return TEMP_UNIT === "f" ? "°F" : "°C";
}

function setText(selector, value) {
  const el = $(selector);
  if (el) el.textContent = value;
}

function setSensorDateInputs(start, end) {
  const startInput = $("#sensorStart");
  const endInput = $("#sensorEnd");
  if (startInput) startInput.value = formatDateTimeLocal(start);
  if (endInput) endInput.value = formatDateTimeLocal(end);
}

function syncSensorRangeControls(query) {
  const tabs = document.querySelectorAll("#sensorTabs .tab");
  const params = new URLSearchParams(query);
  const range = params.get("range");
  tabs.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.range === range);
  });
  if (params.has("start") || params.has("end")) {
    const end = params.get("end") ? new Date(params.get("end")) : new Date();
    const start = params.get("start") ? new Date(params.get("start")) : new Date(end.getTime() - 24 * 3600 * 1000);
    if (!Number.isNaN(start.getTime()) && !Number.isNaN(end.getTime())) {
      setSensorDateInputs(start, end);
    }
  } else if (range && range !== "all") {
    const match = String(range).match(/^(\d+)h$/);
    const hours = match ? parseInt(match[1], 10) : 24;
    const end = new Date();
    const start = new Date(end.getTime() - hours * 3600 * 1000);
    setSensorDateInputs(start, end);
  }
}

function updateCards(data) {
  setText("#growName", data.grow.name);
  const phaseText = data.stats.phase === "Veg" ? t("vegetative") : data.stats.phase;
  const phaseLabel = $("#phaseLabel");
  if (phaseLabel) {
    phaseLabel.textContent = phaseText;
    const isFlowerPhase = ["flower", "blüte"].includes(String(data.stats.phase || "").toLowerCase());
    phaseLabel.classList.toggle("flower", isFlowerPhase);
  }
  setText("#phaseWeek", data.stats.current_week || "–");
  setText("#phaseDays", data.stats.days_since_start != null ? String(data.stats.days_since_start) : "–");
  setText("#lastWatering", formatDate(data.grow.last_watering));
  setText("#nextWatering", data.stats.next_watering || t("openPlan"));
  setText("#startDate", formatDate(data.grow.start_date));
  setText("#sproutDate", formatDate(data.grow.sprout_date));
  setText("#flowerDate", formatDate(data.grow.flower_date) || "–");
  const flowerStats = $("#flowerStats");
  if (data.stats.flower_days != null) {
    if (flowerStats) flowerStats.hidden = false;
    setText("#flowerDay", String(data.stats.flower_days));
    setText("#flowerWeek", String(data.stats.flower_week));
  } else if (flowerStats) {
    flowerStats.hidden = true;
  }

  setText("#imgCount", String(data.images.count));
  setText("#imgLatest", data.images.latest || "–");
  setText("#imgOldest", data.images.oldest || "–");
  setText("#imgSize", `${data.images.size_gb} GB`);
  const latestSensor = data.latest_sensor || {};
  const liveTemp = convertTemp(latestSensor.temperature);
  setText("#liveTemp", liveTemp != null ? `${liveTemp.toFixed(1)}${tempSuffix()}` : "–");
  setText("#liveHum", latestSensor.humidity != null ? `${latestSensor.humidity.toFixed(1)}%` : "–");
  const vpd = latestSensor.vpd;
  setText("#liveVpd", vpd != null ? `${vpd.toFixed(2)} kPa` : "–");
  const vpdTarget = (data.vpd && data.vpd.optimal) || null;
  setText("#liveVpdTarget", vpdTarget ? `${vpdTarget.min}–${vpdTarget.max} kPa (${vpdTarget.label})` : "–");
  setText("#liveSensorTs", latestSensor.raw_timestamp ? formatDateTime(latestSensor.raw_timestamp) : (latestSensor.timestamp || "–"));
  const syncStatus = $("#syncStatus");
  if (syncStatus) {
    syncStatus.classList.remove("error");
    syncStatus.title = t("synced");
  }

  renderTimelapse(data.timelapse || {});

  renderFertilizers(data.fertilizers || []);
  renderLog(data.log || []);
  renderInfo(data.info_lines || []);
  renderPhoto(data.latest_photo);
  renderSensorChart(data.sensor_history || []);
}

function renderFertilizers(items) {
  const list = $("#fertList");
  if (!list) return;
  list.innerHTML = "";
  items.forEach((fert) => {
    const li = document.createElement("li");
    li.innerHTML = `
      <div>
        <strong>${fert.name}</strong>
        <span>${t("week")} ${fert.current_week}</span>
      </div>
      <strong>${fert.ml_per_l.toFixed(2)} ml/L</strong>
    `;
    list.appendChild(li);
  });
}

function renderLog(entries) {
  // Telegram log removed from dashboard layout; no-op retained for compatibility.
}

function renderInfo(lines) {
  const list = $("#infoList");
  if (!list) return;
  list.innerHTML = "";
  const iconMap = {
    "Grow-Name": "🌿",
    Start: "📅",
    Sprout: "🌱",
    "Letzte Bewässerung": "💧",
    Phase: "🌀",
    "Aktuelle Woche": "📈",
    "Blüte-Beginn": "🌸",
  };
  lines.forEach((line) => {
    const li = document.createElement("li");
    const icon = iconMap[line.label] || "•";
    li.innerHTML = `
      <div class="icon-chip">${icon}</div>
      <span>${line.label}</span>
      <strong>${line.value}</strong>
    `;
    list.appendChild(li);
  });
}

function renderPhoto(info) {
  const img = $("#photoPreview");
  const badge = $("#photoTimestamp");
  if (!img || !badge) return;
  if (info && info.path) {
    img.src = `/latest-photo?ts=${Date.now()}`;
    img.dataset.fullscreenSrc = img.src;
    badge.textContent = info.raw_timestamp ? formatDateTime(info.raw_timestamp) : info.timestamp;
  } else {
    img.src = "";
    delete img.dataset.fullscreenSrc;
    badge.textContent = t("noImage");
  }
}

function renderTimelapse(info) {
  const tsEl = $("#tlTimestamp");
  if (tsEl) tsEl.textContent = info.timestamp || "–";
  const durEl = $("#tlDuration");
  if (durEl) durEl.textContent = info.duration ? `${info.duration}s` : "–";
  const sizeEl = $("#tlSize");
  if (sizeEl) {
    if (info.size_bytes) {
      const mb = info.size_bytes / (1024 * 1024);
      sizeEl.textContent = `${mb.toFixed(2)} MB`;
    } else {
      sizeEl.textContent = "–";
    }
  }
  const download = $("#tlDownload");
  if (!download) return;
  if (info.exists) {
    const cacheBuster = Date.now();
    download.dataset.href = `/latest-timelapse?ts=${cacheBuster}`;
    download.hidden = false;
  } else {
    download.hidden = true;
    delete download.dataset.href;
  }
}

function renderSensorChart(points) {
  const ctx = document.getElementById("sensorChart");
  if (!ctx) return;
  const labels = points.map((p) => p.timestamp);
  const temps = points.map((p) => {
    const converted = convertTemp(p.temperature);
    return converted != null ? converted : null;
  });
  const hums = points.map((p) => p.humidity);
  const vpds = points.map((p) => p.vpd);

  if (!sensorChart) {
    const gradientTemp = ctx.getContext("2d").createLinearGradient(0, 0, 0, ctx.height);
    gradientTemp.addColorStop(0, "rgba(249,115,22,0.35)");
    gradientTemp.addColorStop(1, "rgba(249,115,22,0)");
    const gradientHum = ctx.getContext("2d").createLinearGradient(0, 0, 0, ctx.height);
    gradientHum.addColorStop(0, "rgba(96,165,250,0.35)");
    gradientHum.addColorStop(1, "rgba(96,165,250,0)");
    sensorChart = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: `${t("temperature").replace(" °C", "").replace(" °F", "")} ${tempSuffix()}`,
            data: temps,
            borderColor: "#f97316",
            backgroundColor: gradientTemp,
            tension: 0.25,
            borderWidth: 2,
            pointRadius: 0,
            yAxisID: "y",
          },
          {
            label: t("humidity"),
            data: hums,
            borderColor: "#60a5fa",
            backgroundColor: gradientHum,
            tension: 0.25,
            borderWidth: 2,
            pointRadius: 0,
            yAxisID: "y1",
          },
          {
            label: t("vpd"),
            data: vpds,
            borderColor: "#22c55e",
            backgroundColor: "rgba(34,197,94,0.2)",
            tension: 0.25,
            borderWidth: 2,
            pointRadius: 0,
            yAxisID: "y2",
          },
        ],
      },
      options: {
        plugins: { legend: { labels: { color: "#94a3b8" } } },
        scales: {
          x: { ticks: { color: "#94a3b8", maxRotation: 45, minRotation: 45 } },
          y: {
            ticks: { color: "#f97316" },
            suggestedMin: TEMP_UNIT === "f" ? 59 : 15,
            suggestedMax: TEMP_UNIT === "f" ? 86 : 30,
          },
          y1: {
            position: "right",
            ticks: { color: "#60a5fa" },
            suggestedMin: 40,
            suggestedMax: 80,
            grid: { drawOnChartArea: false },
          },
          y2: {
            position: "right",
            ticks: { color: "#22c55e" },
            suggestedMin: 0.2,
            suggestedMax: 1.8,
            grid: { drawOnChartArea: false },
          },
        },
      },
    });
    return;
  }

  sensorChart.data.labels = labels;
  sensorChart.data.datasets[0].data = temps;
  sensorChart.data.datasets[1].data = hums;
  sensorChart.data.datasets[2].data = vpds;
  sensorChart.data.datasets[0].pointRadius = 0;
  sensorChart.data.datasets[1].pointRadius = 0;
  sensorChart.data.datasets[2].pointRadius = 0;
  sensorChart.data.labels = points.map((p) => p.raw_timestamp ? formatDateTime(p.raw_timestamp) : p.timestamp);
  sensorChart.data.datasets[0].label = `${t("temperature").replace(" °C", "").replace(" °F", "")} ${tempSuffix()}`;
  sensorChart.options.scales.y.suggestedMin = TEMP_UNIT === "f" ? 59 : 15;
  sensorChart.options.scales.y.suggestedMax = TEMP_UNIT === "f" ? 86 : 30;
  sensorChart.options.scales.y1.suggestedMin = 40;
  sensorChart.options.scales.y1.suggestedMax = 80;
  sensorChart.options.scales.y2.suggestedMin = 0.2;
  sensorChart.options.scales.y2.suggestedMax = 1.8;
  sensorChart.update();
}

function renderTempStats(points) {
  const temps = points
    .map((p) => (typeof p.temperature === "number" ? p.temperature : null))
    .filter((v) => v !== null);
  if (!temps.length) {
    ["tempMin", "tempMedian", "tempMax"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.textContent = "–";
    });
    return;
  }
  const sorted = temps.slice().sort((a, b) => a - b);
  const min = sorted[0];
  const max = sorted[sorted.length - 1];
  const mid = Math.floor(sorted.length / 2);
  const median =
    sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
  const fmt = (value) => `${convertTemp(value).toFixed(1)}${tempSuffix()}`;
  setText("#tempMin", fmt(min));
  setText("#tempMedian", fmt(median));
  setText("#tempMax", fmt(max));
}

async function loadDashboard() {
  try {
    const data = await fetchJSON("/api/dashboard");
    updateCards(data);
  } catch (err) {
    showToast(`${t("dashboardError")}: ${err.message}`, true);
  }
}

async function performAction(action, payload = {}) {
  try {
    const res = await fetchJSON("/api/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, ...payload }),
    });
    showToast(res.message || t("actionDone"));
    loadDashboard();
    if (action === "temp") {
      loadSensorHistory(sensorQuery);
    }
  } catch (err) {
    showToast(`${t("error")}: ${err.message}`, true);
  }
}

function setupButtons() {
  document.querySelectorAll("[data-action]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const action = btn.dataset.action;
      performAction(action);
    });
  });

  document.querySelectorAll("#sensorTabs .tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      sensorQuery = `range=${encodeURIComponent(btn.dataset.range || "72h")}`;
      loadSensorHistory(sensorQuery);
    });
  });

  const customApply = $("#sensorCustomApply");
  if (customApply) {
    customApply.addEventListener("click", () => {
      const startValue = $("#sensorStart")?.value || "";
      const endValue = $("#sensorEnd")?.value || "";
      if (!startValue || !endValue) {
        showToast(`${t("error")}: ${t("invalidTimeframe")}`, true);
        return;
      }
      const start = new Date(startValue);
      const end = new Date(endValue);
      if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || start > end) {
        showToast(`${t("error")}: ${t("invalidTimeframe")}`, true);
        return;
      }
      sensorQuery = `start=${encodeURIComponent(startValue)}&end=${encodeURIComponent(endValue)}`;
      loadSensorHistory(sensorQuery);
    });
  }

  const downloadBtn = $("#tlDownload");
  if (downloadBtn) {
    downloadBtn.addEventListener("click", () => {
      const href = downloadBtn.dataset.href;
      if (!href) return;
      window.location.href = href;
    });
  }

  const preview = $("#photoPreview");
  const lightbox = $("#imageLightbox");
  const lightboxImg = $("#imageLightboxImg");
  const lightboxClose = $("#imageLightboxClose");
  const closeLightbox = () => {
    if (!lightbox || !lightboxImg) return;
    lightbox.hidden = true;
    lightboxImg.src = "";
    document.body.classList.remove("lightbox-open");
  };
  const openLightbox = () => {
    const src = preview?.dataset.fullscreenSrc || preview?.getAttribute("src") || "";
    if (!lightbox || !lightboxImg || !src) return;
    lightboxImg.src = src;
    lightbox.hidden = false;
    document.body.classList.add("lightbox-open");
  };
  const handlePreviewOpen = (event) => {
    event.preventDefault();
    if (!preview.getAttribute("src")) return;
    openLightbox();
  };
  preview?.addEventListener("click", handlePreviewOpen);
  preview?.addEventListener("pointerup", handlePreviewOpen);
  lightboxClose?.addEventListener("click", closeLightbox);
  lightbox?.addEventListener("click", (event) => {
    if (event.target === lightbox) closeLightbox();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && lightbox && !lightbox.hidden) {
      closeLightbox();
    }
  });

}

async function loadSensorHistory(query = "range=72h") {
  sensorQuery = query;
  syncSensorRangeControls(query);
  try {
    const res = await fetchJSON(`/api/sensor-history?${query}`);
    const points = res.points || [];
    renderSensorChart(points);
    renderTempStats(points);
  } catch (err) {
    showToast(`${t("sensorDataError")}: ${err.message}`, true);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  syncSensorRangeControls(sensorQuery);
  loadDashboard();
  setupButtons();
  loadSensorHistory(sensorQuery);
  setInterval(() => {
    loadDashboard();
    loadSensorHistory(sensorQuery);
  }, 60_000);
});
