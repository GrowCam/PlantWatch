const $ = (selector) => document.querySelector(selector);
const toast = $("#toast");
const APP_LANG = window.APP_LANG || "de";
const TL_TXT = {
  de: { creatingVideo: "Video wird erstellt…", videoCreated: "Video erfolgreich erstellt.", videoFailed: "Video-Erstellung fehlgeschlagen.", testing: "Aufnahme läuft…" },
  en: { creatingVideo: "Creating video…", videoCreated: "Video created successfully.", videoFailed: "Video creation failed.", testing: "Capturing…" },
};
const tlt = (key) => (TL_TXT[APP_LANG] && TL_TXT[APP_LANG][key]) || TL_TXT.de[key] || key;

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

function setHidden(el, hidden) {
  if (el) el.hidden = hidden;
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
      render();
    });
    numberInput?.addEventListener("change", () => {
      input.value = numberInput.value;
      render();
    });
  });
}

function cameraSettingsPayloadFromForm() {
  return {
    camera_auto_focus: $("#cameraAutoFocus")?.checked || false,
    camera_focus: $("#cameraFocus")?.value || "-1",
    camera_auto_exposure: $("#cameraAutoExposure")?.checked || false,
    camera_exposure: $("#cameraExposure")?.value || "-1",
    camera_brightness: $("#cameraBrightness")?.value || "-1",
    camera_contrast: $("#cameraContrast")?.value || "-1",
    camera_saturation: $("#cameraSaturation")?.value || "-1",
    camera_sharpness: $("#cameraSharpness")?.value || "-1",
  };
}


function updateCameraSettingsVisibility() {
  const timelapseEnabled = $("#timelapseEnabled");
  const cameraSettingsCard = $("#cameraSettingsCard");
  if (!timelapseEnabled || !cameraSettingsCard) return;
  cameraSettingsCard.hidden = !timelapseEnabled.checked;
}

function updateAutoToggleFields(root = document) {
  root.querySelectorAll("[data-auto-toggle]").forEach((field) => {
    const toggle = document.getElementById(field.dataset.autoToggle);
    if (!toggle) return;
    const disabled = toggle.checked;
    field.classList.toggle("field-disabled", disabled);
    field.querySelectorAll("input").forEach((input) => {
      input.disabled = disabled;
    });
  });
}

function renderCameraTestSettings(info) {
  const wrap = $("#cameraTestSettingsWrap");
  const summary = $("#cameraTestSettingsSummary");
  const applyWrap = $("#cameraTestApplyWrap");
  const settings = info && info.settings;
  if (!wrap || !summary || !applyWrap) return;
  if (!settings) {
    setHidden(wrap, true);
    setHidden(applyWrap, true);
    return;
  }
  const labels = {
    camera_auto_focus: "AF",
    camera_focus: "Focus",
    camera_auto_exposure: "AE",
    camera_exposure: "Exposure",
    camera_brightness: "Brightness",
    camera_contrast: "Contrast",
    camera_saturation: "Saturation",
    camera_sharpness: "Sharpness",
  };
  summary.textContent = Object.entries(labels)
    .filter(([key]) => settings[key] !== null && settings[key] !== undefined)
    .map(([key, label]) => `${label}: ${settings[key]}`)
    .join(" · ");
  setHidden(wrap, false);
  setHidden(applyWrap, false);
}

function applyAppSettingsToForm(settings) {
  if (!settings) return;
  const fields = [
    ["cameraAutoFocus", settings.camera_auto_focus],
    ["cameraAutoExposure", settings.camera_auto_exposure],
  ];
  fields.forEach(([id, value]) => {
    const el = document.getElementById(id);
    if (el) el.checked = Boolean(value);
  });
  ["camera_focus", "camera_exposure", "camera_brightness", "camera_contrast", "camera_saturation", "camera_sharpness"].forEach((key) => {
    if (settings[key] === undefined || settings[key] === null) return;
    const rangeId = key.replace(/_([a-z])/g, (_, c) => c.toUpperCase());
    const range = document.getElementById(rangeId);
    const number = document.getElementById(`${rangeId}Number`);
    if (range) range.value = settings[key];
    if (number) number.value = settings[key];
  });
  updateAutoToggleFields();
}

function renderDashboardData(data) {
  if ($("#imgCount")) $("#imgCount").textContent = String(data.images?.count ?? "–");
  if ($("#imgOldest")) $("#imgOldest").textContent = data.images?.oldest || "–";
  if ($("#imgLatest")) $("#imgLatest").textContent = data.images?.latest || "–";
  if ($("#imgSize")) $("#imgSize").textContent = `${data.images?.size_gb ?? 0} GB`;

  const preview = $("#timelapsePreview");
  const previewTs = $("#timelapsePreviewTimestamp");
  if (preview && previewTs) {
    if (data.timelapse_latest_photo?.path) {
      preview.src = `/latest-timelapse-photo?ts=${Date.now()}`;
      previewTs.textContent = data.timelapse_latest_photo.timestamp || "–";
    } else {
      preview.removeAttribute("src");
      previewTs.textContent = "–";
    }
  }

  const info = data.timelapse || {};
  if ($("#tlTimestamp")) $("#tlTimestamp").textContent = info.timestamp || "–";
  if ($("#tlDuration")) $("#tlDuration").textContent = info.duration ? `${info.duration}s` : "–";
  if ($("#tlSize")) $("#tlSize").textContent = info.size_bytes ? `${(info.size_bytes / (1024 * 1024)).toFixed(2)} MB` : "–";

  const download = $("#tlDownload");
  if (download) {
    if (info.exists) {
      download.dataset.href = `/download-timelapse?ts=${Date.now()}`;
      download.hidden = false;
    } else {
      delete download.dataset.href;
      download.hidden = true;
    }
  }
}

function pollTimelapseJob(btn) {
  const statusEl = $("#tlJobStatus");
  const originalLabel = btn.dataset.originalLabel || btn.textContent;
  btn.dataset.originalLabel = originalLabel;
  btn.disabled = true;
  btn.textContent = `⏳ ${tlt("creatingVideo")}`;
  setHidden(statusEl, false);
  if (statusEl) statusEl.textContent = tlt("creatingVideo");

  const finish = (message, isError) => {
    clearInterval(interval);
    btn.disabled = false;
    btn.textContent = originalLabel;
    setHidden(statusEl, true);
    showToast(message, isError);
    refreshTimelapseData();
  };

  const interval = setInterval(async () => {
    try {
      const status = await fetchJSON("/api/timelapse-video-status");
      if (!status.running) {
        finish(status.ok === false ? tlt("videoFailed") : tlt("videoCreated"), status.ok === false);
      }
    } catch (err) {
      finish(err.message, true);
    }
  }, 2000);
}

async function refreshTimelapseData() {
  try {
    const data = await fetchJSON("/api/dashboard");
    renderDashboardData(data);
  } catch (err) {
    console.warn("Timelapse refresh failed", err);
  }
}

function openLightboxFor(src) {
  const lightbox = $("#timelapseImageLightbox");
  const lightboxImg = $("#timelapseImageLightboxImg");
  if (!src || !lightbox || !lightboxImg) return;
  lightboxImg.src = src;
  lightbox.hidden = false;
  document.body.classList.add("lightbox-open");
}

function closeLightbox() {
  const lightbox = $("#timelapseImageLightbox");
  const lightboxImg = $("#timelapseImageLightboxImg");
  if (!lightbox || !lightboxImg) return;
  lightbox.hidden = true;
  lightboxImg.src = "";
  document.body.classList.remove("lightbox-open");
}

document.addEventListener("DOMContentLoaded", () => {
  const timelapseForm = $("#timelapseSettingsForm");
  const cameraForm = $("#cameraSettingsForm");
  const timelapseEnabled = $("#timelapseEnabled");
  const cameraTestButton = $("#cameraTestButton");
  const cameraTestPreview = $("#cameraTestPreview");
  const cameraTestPreviewWrap = $("#cameraTestPreviewWrap");
  const cameraTestTimestamp = $("#cameraTestTimestamp");
  const cameraTestApplyButton = $("#cameraTestApplyButton");
  const cameraAutoFocus = $("#cameraAutoFocus");
  const cameraAutoExposure = $("#cameraAutoExposure");
  const lightbox = $("#timelapseImageLightbox");
  const lightboxClose = $("#timelapseImageLightboxClose");
  const downloadBtn = $("#tlDownload");
  const tlCreateButton = $("#tlCreateButton");
  const tlJobStatus = $("#tlJobStatus");

  bindSliderOutputs();
  updateCameraSettingsVisibility();
  updateAutoToggleFields();
  timelapseEnabled?.addEventListener("change", updateCameraSettingsVisibility);
  cameraAutoFocus?.addEventListener("change", () => updateAutoToggleFields());
  cameraAutoExposure?.addEventListener("change", () => updateAutoToggleFields());

  timelapseForm?.addEventListener("submit", async (evt) => {
    evt.preventDefault();
    try {
      const res = await fetchJSON("/api/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "timelapse_settings",
          enabled: $("#timelapseEnabled")?.checked || false,
          light_only: $("#timelapseLightOnly")?.checked || false,
          rotation_degrees: $("#timelapseRotation")?.value || "0",
          interval_minutes: $("#timelapseInterval")?.value || "30",
        }),
      });
      updateCameraSettingsVisibility();
      showToast(res.message || "Saved");
    } catch (err) {
      showToast(err.message, true);
    }
  });

  cameraForm?.addEventListener("submit", async (evt) => {
    evt.preventDefault();
    try {
      const res = await fetchJSON("/api/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "app_settings",
          ...window.APP_SETTINGS,
          ...cameraSettingsPayloadFromForm(),
        }),
      });
      showToast(res.message || "Saved");
    } catch (err) {
      showToast(err.message, true);
    }
  });

  cameraTestButton?.addEventListener("click", async () => {
    const originalLabel = cameraTestButton.textContent;
    cameraTestButton.disabled = true;
    cameraTestButton.textContent = `⏳ ${tlt("testing")}`;
    try {
      const res = await fetchJSON("/api/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "camera_test",
          ...cameraSettingsPayloadFromForm(),
        }),
      });
      if (res.camera_test_image && cameraTestPreview && cameraTestPreviewWrap) {
        setHidden(cameraTestPreviewWrap, false);
        cameraTestPreview.src = `/latest-camera-test?ts=${Date.now()}`;
        if (cameraTestTimestamp) {
          cameraTestTimestamp.hidden = false;
          cameraTestTimestamp.textContent = res.camera_test_image.timestamp || "–";
        }
      }
      renderCameraTestSettings(res.camera_test_image);
      showToast(res.message || "Saved");
    } catch (err) {
      showToast(err.message, true);
    } finally {
      cameraTestButton.disabled = false;
      cameraTestButton.textContent = originalLabel;
    }
  });

  cameraTestApplyButton?.addEventListener("click", async () => {
    try {
      const res = await fetchJSON("/api/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "camera_test_apply" }),
      });
      if (res.error) {
        showToast(res.error, true);
        return;
      }
      applyAppSettingsToForm(res.app_settings);
      showToast(res.message || "Saved");
    } catch (err) {
      showToast(err.message, true);
    }
  });

  const timelapsePreview = $("#timelapsePreview");
  timelapsePreview?.addEventListener("click", (evt) => {
    evt.preventDefault();
    openLightboxFor(timelapsePreview.getAttribute("src") || "");
  });
  timelapsePreview?.addEventListener("pointerup", (evt) => {
    evt.preventDefault();
    openLightboxFor(timelapsePreview.getAttribute("src") || "");
  });
  cameraTestPreview?.addEventListener("click", (evt) => {
    evt.preventDefault();
    openLightboxFor(cameraTestPreview.getAttribute("src") || "");
  });
  cameraTestPreview?.addEventListener("pointerup", (evt) => {
    evt.preventDefault();
    openLightboxFor(cameraTestPreview.getAttribute("src") || "");
  });
  lightboxClose?.addEventListener("click", closeLightbox);
  lightbox?.addEventListener("click", (evt) => {
    if (evt.target === lightbox) closeLightbox();
  });
  document.addEventListener("keydown", (evt) => {
    if (evt.key === "Escape" && lightbox && !lightbox.hidden) closeLightbox();
  });

  document.querySelectorAll("[data-action='timelapse_video']").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (btn.disabled) return;
      try {
        const res = await fetchJSON("/api/action", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "timelapse_video" }),
        });
        if (res.job_running) {
          pollTimelapseJob(btn);
        } else {
          showToast(res.message || "OK");
          refreshTimelapseData();
        }
      } catch (err) {
        showToast(err.message, true);
      }
    });
  });

  (async () => {
    try {
      const status = await fetchJSON("/api/timelapse-video-status");
      if (status.running && tlCreateButton) {
        pollTimelapseJob(tlCreateButton);
      }
    } catch (err) {
      console.warn("Timelapse job status check failed", err);
    }
  })();

  downloadBtn?.addEventListener("click", () => {
    const href = downloadBtn.dataset.href;
    if (!href) return;
    const a = document.createElement("a");
    a.href = href;
    a.download = "timelapse.mp4";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  });

  refreshTimelapseData();
});
