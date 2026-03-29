const $ = (selector) => document.querySelector(selector);
const toast = $("#toast");

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
  const lightbox = $("#timelapseImageLightbox");
  const lightboxClose = $("#timelapseImageLightboxClose");
  const downloadBtn = $("#tlDownload");

  bindSliderOutputs();
  updateCameraSettingsVisibility();
  timelapseEnabled?.addEventListener("change", updateCameraSettingsVisibility);

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
      try {
        const res = await fetchJSON("/api/action", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "timelapse_video" }),
        });
        showToast(res.message || "OK");
        refreshTimelapseData();
      } catch (err) {
        showToast(err.message, true);
      }
    });
  });

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
