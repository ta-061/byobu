(() => {
  "use strict";

  let MAX_FILE_SIZE = 100 * 1024 * 1024;
  const files = { old: null, new: null };
  const form = document.querySelector("#compare-form");
  const compareButton = document.querySelector("#compare-button");
  const formError = document.querySelector("#form-error");
  const processingOverlay = document.querySelector("#processing-overlay");
  const processingMessage = document.querySelector("#processing-message");
  const resultSection = document.querySelector("#result-section");
  const pageList = document.querySelector("#page-list");
  const emptyFilter = document.querySelector("#empty-filter");
  let currentJobId = null;
  let currentResult = null;
  let processingTimer = null;

  const escapeHtml = (value) =>
    String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");

  const formatBytes = (bytes) => {
    if (!Number.isFinite(bytes) || bytes <= 0) return "0 KB";
    const units = ["B", "KB", "MB", "GB"];
    const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    const value = bytes / 1024 ** index;
    return `${value.toFixed(index === 0 || value >= 10 ? 0 : 1)} ${units[index]}`;
  };

  const artifactUrl = (path, download = false) =>
    `/api/jobs/${encodeURIComponent(currentJobId)}/artifacts/${path
      .split("/")
      .map(encodeURIComponent)
      .join("/")}${download ? "?download=true" : ""}`;

  function showError(message) {
    formError.textContent = message;
    formError.hidden = false;
  }

  function clearError() {
    formError.hidden = true;
    formError.textContent = "";
  }

  function validateFile(file) {
    if (!file) return "Please choose a PDF file.";
    if (file.size > MAX_FILE_SIZE) {
      return `Files must be at most ${Math.round(MAX_FILE_SIZE / 1024 / 1024)} MB each.`;
    }
    if (!file.name.toLowerCase().endsWith(".pdf") && file.type !== "application/pdf") {
      return "Please choose a PDF file.";
    }
    return null;
  }

  function setFile(role, file) {
    const error = validateFile(file);
    if (error) {
      showError(error);
      return;
    }
    clearError();
    files[role] = file;
    const dropzone = document.querySelector(`#${role}-dropzone`);
    dropzone.classList.add("has-file");
    dropzone.querySelector(".drop-title").hidden = true;
    dropzone.querySelector(".drop-subtitle").hidden = true;
    const selected = dropzone.querySelector(".file-selected");
    selected.hidden = false;
    selected.querySelector(".file-name").textContent = file.name;
    selected.querySelector(".file-size").textContent = formatBytes(file.size);
    compareButton.disabled = !(files.old && files.new);
  }

  function setupDropzone(role) {
    const input = document.querySelector(`#${role}-pdf`);
    const dropzone = document.querySelector(`#${role}-dropzone`);
    input.addEventListener("change", () => {
      if (input.files?.[0]) setFile(role, input.files[0]);
    });
    ["dragenter", "dragover"].forEach((eventName) => {
      dropzone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropzone.classList.add("drag-over");
      });
    });
    ["dragleave", "drop"].forEach((eventName) => {
      dropzone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropzone.classList.remove("drag-over");
      });
    });
    dropzone.addEventListener("drop", (event) => {
      const file = event.dataTransfer?.files?.[0];
      if (file) setFile(role, file);
    });
    dropzone.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        input.click();
      }
    });
  }

  function startProcessing(message = "Loading files…") {
    processingMessage.textContent = message;
    processingOverlay.hidden = false;
    document.body.style.overflow = "hidden";
    const messages = [
      "Aligning page layout…",
      "Finding added and deleted text…",
      "Analyzing visual differences in figures and equations…",
      "Creating annotated PDFs…",
      "Finishing page previews…",
    ];
    let index = 0;
    processingTimer = window.setInterval(() => {
      processingMessage.textContent = messages[Math.min(index, messages.length - 1)];
      index += 1;
    }, 4200);
  }

  function stopProcessing() {
    window.clearInterval(processingTimer);
    processingTimer = null;
    processingOverlay.hidden = true;
    document.body.style.overflow = "";
  }

  async function readError(response) {
    try {
      const payload = await response.json();
      if (Array.isArray(payload.detail)) {
        return "Please check your input.";
      }
      return payload.detail || "Comparison failed.";
    } catch (_) {
      return "The server did not return a valid response.";
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError();
    if (!files.old || !files.new) {
      showError("Please choose both the old and new PDFs.");
      return;
    }
    const data = new FormData();
    data.append("old_pdf", files.old, files.old.name);
    data.append("new_pdf", files.new, files.new.name);
    data.append("sensitivity", document.querySelector("#sensitivity").value);
    data.append("dpi", document.querySelector("#dpi").value);
    compareButton.disabled = true;
    startProcessing();
    try {
      const response = await fetch("/api/compare", { method: "POST", body: data });
      if (!response.ok) throw new Error(await readError(response));
      const payload = await response.json();
      currentJobId = payload.job_id;
      currentResult = payload.result;
      window.history.replaceState({}, "", `?job=${encodeURIComponent(currentJobId)}`);
      renderResult(currentResult);
      resultSection.hidden = false;
      resultSection.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      showError(error.message || "Comparison failed.");
      document.querySelector("#upload-section").scrollIntoView({ behavior: "smooth" });
    } finally {
      stopProcessing();
      compareButton.disabled = !(files.old && files.new);
    }
  });

  function summaryCard(cssClass, label, value, unit) {
    return `
      <article class="summary-card ${cssClass}">
        <div class="summary-label"><i class="summary-dot"></i>${escapeHtml(label)}</div>
        <div class="summary-value">${Number(value).toLocaleString("en-US")}<small>${escapeHtml(unit)}</small></div>
      </article>`;
  }

  function downloadButton(artifact, label, primary = false) {
    return `
      <a class="download-button${primary ? " primary" : ""}" href="${artifactUrl(artifact.name, true)}" download>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12M7 10l5 5 5-5M4 20h16"/></svg>
        <span>${escapeHtml(label)}<small> · ${escapeHtml(formatBytes(artifact.size))}</small></span>
      </a>`;
  }

  function badges(changes, side, kind) {
    const values = [];
    if (kind === "added_page" && side === "new") values.push(["page-change", "Added page"]);
    if (kind === "deleted_page" && side === "old") values.push(["page-change", "Deleted page"]);
    if (side === "new" && changes.added_words) values.push(["added", `+${changes.added_words} tokens`]);
    if (side === "old" && changes.deleted_words) values.push(["deleted", `-${changes.deleted_words} tokens`]);
    if (changes.visual_regions) values.push(["visual", `${changes.visual_regions} visual`]);
    if (side === "new" && changes.added_annotations) values.push(["added", `Annotations +${changes.added_annotations}`]);
    if (side === "old" && changes.deleted_annotations) values.push(["deleted", `Annotations -${changes.deleted_annotations}`]);
    if (changes.style_changes) values.push(["style", `${changes.style_changes} style`]);
    if (!values.length && kind === "unchanged") values.push(["unchanged", "No changes"]);
    return values.map(([type, text]) => `<span class="change-badge ${type}">${escapeHtml(text)}</span>`).join("");
  }

  function snippetPanel(changes, side) {
    const snippets = side === "old" ? changes.deleted_snippets : changes.added_snippets;
    if (!snippets?.length) return "";
    const label = side === "old" ? "Deleted" : "Added";
    const text = snippets.slice(0, 3).join(" / ");
    return `<div class="snippet-panel"><b>${label}:</b>${escapeHtml(text)}</div>`;
  }

  function pageCard(page, side, row) {
    if (!page) return `<article class="page-card empty"><span>No matching page</span></article>`;
    const sideLabel = side === "old" ? "Old" : "New";
    const imageUrl = artifactUrl(page.preview);
    return `
      <article class="page-card">
        <div class="page-meta">
          <span class="page-number">${sideLabel} · page ${page.page}</span>
          <span class="change-badges">${badges(row.changes, side, row.kind)}</span>
        </div>
        <button class="page-image-button" type="button" data-image="${imageUrl}" data-title="${sideLabel} · page ${page.page}" aria-label="Enlarge ${sideLabel} page ${page.page}">
          <img src="${imageUrl}" loading="lazy" decoding="async" alt="Diff preview of ${sideLabel} page ${page.page}" />
        </button>
        ${snippetPanel(row.changes, side)}
      </article>`;
  }

  function renderRows(rows) {
    pageList.innerHTML = rows
      .map(
        (row) => `
          <article class="page-row" data-changed="${row.has_changes ? "true" : "false"}">
            <div class="row-index">${String(row.row).padStart(2, "0")}</div>
            ${pageCard(row.old, "old", row)}
            ${pageCard(row.new, "new", row)}
          </article>`,
      )
      .join("");
    pageList.querySelectorAll(".page-image-button").forEach((button) => {
      button.addEventListener("click", () => openModal(button.dataset.image, button.dataset.title));
    });
  }

  function renderResult(result) {
    const summary = result.summary;
    const annotationChanges = summary.annotation_changes || 0;
    document.querySelector("#result-filenames").textContent = `${result.files.old.name}  →  ${result.files.new.name}`;
    document.querySelector("#summary-grid").innerHTML = [
      summaryCard("changed", "Changed pages", summary.changed_pages, "pages"),
      summaryCard("added", "Added text", summary.added_words, "tokens"),
      summaryCard("deleted", "Deleted text", summary.deleted_words, "tokens"),
      summaryCard("visual", "Figure & annotation changes", summary.visual_regions + annotationChanges, "spots"),
      summaryCard("style", "Style changes", summary.style_changes || 0, "words"),
    ].join("");
    const artifacts = result.artifacts;
    document.querySelector("#download-actions").innerHTML = [
      downloadButton(artifacts.old, "Old version"),
      downloadButton(artifacts.new, "New version"),
      downloadButton(artifacts.side_by_side, "Side-by-side", true),
    ].join("");
    setupPdfPreview(artifacts, "side_by_side");
    document.querySelector("#viewer-caption").textContent = `Comparing ${summary.compared_rows} page pairs · green = added / red = deleted / purple = figures & layout / amber = style; dashed boxes mark annotation changes`;
    renderRows(result.rows);
    setFilter(summary.changed_pages > 0 ? "changed" : "all");
  }

  function setupPdfPreview(artifacts, selectedKey) {
    const frame = document.querySelector("#pdfjs-preview-frame");
    const openLink = document.querySelector("#pdf-open-new");
    const select = (key) => {
      const artifact = artifacts[key];
      if (!artifact) return;
      const url = artifactUrl(artifact.name);
      openLink.href = url;
      frame.src = `/viewer?file=${encodeURIComponent(url)}`;
      document.querySelectorAll("#pdf-preview-tabs button").forEach((button) => {
        const active = button.dataset.pdf === key;
        button.classList.toggle("active", active);
        button.setAttribute("aria-selected", String(active));
      });
    };
    document.querySelectorAll("#pdf-preview-tabs button").forEach((button) => {
      button.onclick = () => select(button.dataset.pdf);
    });
    select(selectedKey);
  }

  function setFilter(filter) {
    document.querySelectorAll(".filter-button").forEach((button) => {
      button.classList.toggle("active", button.dataset.filter === filter);
    });
    let visible = 0;
    pageList.querySelectorAll(".page-row").forEach((row) => {
      const show = filter === "all" || row.dataset.changed === "true";
      row.hidden = !show;
      if (show) visible += 1;
    });
    emptyFilter.hidden = visible !== 0;
  }

  document.querySelectorAll(".filter-button").forEach((button) => {
    button.addEventListener("click", () => setFilter(button.dataset.filter));
  });

  document.querySelector("#new-comparison").addEventListener("click", () => {
    document.querySelector("#upload-section").scrollIntoView({ behavior: "smooth", block: "start" });
  });

  const modal = document.querySelector("#image-modal");
  const modalImage = document.querySelector("#modal-image");
  const modalTitle = document.querySelector("#modal-title");

  function openModal(url, title) {
    modalImage.src = url;
    modalTitle.textContent = title;
    modal.hidden = false;
    document.body.style.overflow = "hidden";
    document.querySelector("#modal-close").focus();
  }

  function closeModal() {
    modal.hidden = true;
    modalImage.removeAttribute("src");
    document.body.style.overflow = "";
  }

  document.querySelector("#modal-close").addEventListener("click", closeModal);
  modal.addEventListener("click", (event) => {
    if (event.target === modal || event.target.classList.contains("modal-canvas")) closeModal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.hidden) closeModal();
  });

  async function restoreJob(jobId) {
    if (!/^[0-9a-f]{32}$/.test(jobId)) return;
    currentJobId = jobId;
    startProcessing("Loading the saved comparison result…");
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
      if (!response.ok) throw new Error(await readError(response));
      const payload = await response.json();
      currentResult = payload.result;
      renderResult(currentResult);
      resultSection.hidden = false;
      resultSection.scrollIntoView({ behavior: "auto", block: "start" });
    } catch (error) {
      window.history.replaceState({}, "", window.location.pathname);
      showError(error.message || "Could not load the saved comparison result.");
    } finally {
      stopProcessing();
    }
  }

  async function loadConfig() {
    try {
      const response = await fetch("/api/config");
      if (!response.ok) return;
      const config = await response.json();
      if (Number.isFinite(config.max_upload_mb) && config.max_upload_mb > 0) {
        MAX_FILE_SIZE = config.max_upload_mb * 1024 * 1024;
      }
    } catch (_) {
      // keep the fallback default
    }
  }

  loadConfig();
  setupDropzone("old");
  setupDropzone("new");
  const savedJob = new URLSearchParams(window.location.search).get("job");
  if (savedJob) restoreJob(savedJob);
})();
