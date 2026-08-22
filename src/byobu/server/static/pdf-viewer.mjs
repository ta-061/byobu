const VENDOR_BASE = "/static/vendor/pdfjs";
const MISSING_VIEWER_MESSAGE =
  'PDF.js viewer assets are not installed. Run "byobu fetch-viewer" in the terminal (pip installs), or use the Docker image which bundles them.';

const params = new URLSearchParams(window.location.search);
const requestedFile = params.get("file") || "";
const loading = document.querySelector("#viewer-loading");
const loadingMessage = document.querySelector("#loading-message");
const status = document.querySelector("#viewer-status");
const pageInput = document.querySelector("#page-number");
const pageCount = document.querySelector("#page-count");
const controls = document.querySelectorAll("button, #page-number");

function showError(message) {
  loading.classList.add("error");
  loadingMessage.textContent = message;
  status.textContent = "Load error";
}

let vendorAvailable = false;
try {
  const response = await fetch(`${VENDOR_BASE}/build/pdf.mjs`, { method: "HEAD" });
  vendorAvailable = response.ok;
} catch (_) {
  vendorAvailable = false;
}
if (!vendorAvailable) {
  showError(MISSING_VIEWER_MESSAGE);
  throw new Error("PDF.js viewer assets are not installed");
}

const pdfjsLib = await import(`${VENDOR_BASE}/build/pdf.mjs`);
globalThis.pdfjsLib = pdfjsLib;
const { EventBus, PDFLinkService, PDFViewer } = await import(`${VENDOR_BASE}/web/pdf_viewer.mjs`);

pdfjsLib.GlobalWorkerOptions.workerSrc = `${VENDOR_BASE}/build/pdf.worker.mjs`;

let fileUrl;
try {
  fileUrl = new URL(requestedFile, window.location.origin);
  const validPath = /^\/api\/jobs\/[0-9a-f]{32}\/artifacts\/.+\.pdf$/i.test(fileUrl.pathname);
  if (fileUrl.origin !== window.location.origin || !validPath) throw new Error("invalid path");
} catch (_) {
  showError("No PDF was specified to display.");
  throw new Error("Invalid PDF preview URL");
}

controls.forEach((control) => {
  control.disabled = true;
});

const container = document.querySelector("#viewerContainer");
const eventBus = new EventBus();
const linkService = new PDFLinkService({ eventBus });
const viewer = new PDFViewer({
  container,
  viewer: document.querySelector("#viewer"),
  eventBus,
  linkService,
  textLayerMode: 1,
  annotationMode: pdfjsLib.AnnotationMode.ENABLE,
});
linkService.setViewer(viewer);

eventBus.on("pagesinit", () => {
  viewer.currentScaleValue = "page-width";
  controls.forEach((control) => {
    control.disabled = false;
  });
  loading.classList.add("hidden");
  status.textContent = "Drag to select text";
});

eventBus.on("pagechanging", ({ pageNumber }) => {
  pageInput.value = String(pageNumber);
});

document.querySelector("#zoom-in").addEventListener("click", () => {
  viewer.increaseScale({ steps: 1 });
});

document.querySelector("#zoom-out").addEventListener("click", () => {
  viewer.decreaseScale({ steps: 1 });
});

document.querySelector("#fit-width").addEventListener("click", () => {
  viewer.currentScaleValue = "page-width";
});

pageInput.addEventListener("change", () => {
  const requested = Number.parseInt(pageInput.value, 10);
  viewer.currentPageNumber = Math.max(1, Math.min(viewer.pagesCount, requested || 1));
});

container.addEventListener("keydown", (event) => {
  if (!(event.ctrlKey || event.metaKey)) return;
  if (["+", "="].includes(event.key)) {
    event.preventDefault();
    viewer.increaseScale({ steps: 1 });
  } else if (event.key === "-") {
    event.preventDefault();
    viewer.decreaseScale({ steps: 1 });
  } else if (event.key === "0") {
    event.preventDefault();
    viewer.currentScaleValue = "page-width";
  }
});

try {
  const loadingTask = pdfjsLib.getDocument({
    url: fileUrl.href,
    cMapUrl: `${VENDOR_BASE}/cmaps/`,
    cMapPacked: true,
    standardFontDataUrl: `${VENDOR_BASE}/standard_fonts/`,
    wasmUrl: `${VENDOR_BASE}/wasm/`,
    enableXfa: false,
  });
  loadingTask.onProgress = ({ loaded, total }) => {
    if (total > 0) {
      loadingMessage.textContent = `Loading with PDF.js… ${Math.round((loaded / total) * 100)}%`;
    }
  };
  const document_ = await loadingTask.promise;
  pageCount.textContent = String(document_.numPages);
  pageInput.max = String(document_.numPages);
  viewer.setDocument(document_);
  linkService.setDocument(document_, null);
} catch (error) {
  console.error(error);
  showError("Could not display the PDF. Use the page previews below instead.");
}
