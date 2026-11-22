const $ = (id) => document.getElementById(id);

const MAX_SIDE = 1280;          // thu nhỏ ảnh trên máy người dùng trước khi gửi
const POLL_MS = 1500;
const POLL_TIMEOUT_MS = 180_000;

const state = {
  garment: null,   // { kind: "url", url } | { kind: "file", blob, previewUrl }
  person: null,    // Blob
  offerLink: null,
  busy: false,
};

const DEFAULT_NOTICE = $("notice").textContent.trim();

// ---------- tiện ích ----------
function notice(msg, kind = "info") {
  const el = $("notice");
  el.textContent = msg;
  el.classList.toggle("error", kind === "error");
}

function resolveStatus(msg, kind = "info") {
  const el = $("resolve-status");
  el.textContent = msg || "";
  el.classList.toggle("error", kind === "error");
}

function errorMessage(data, fallback = "Có lỗi xảy ra, vui lòng thử lại.") {
  if (data && typeof data.detail === "string") return data.detail;
  return fallback;
}

async function readJson(res) {
  try { return await res.json(); } catch { return null; }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function downscale(file) {
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
    const scale = Math.min(1, MAX_SIDE / Math.max(bmp.width, bmp.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bmp.width * scale);
    canvas.height = Math.round(bmp.height * scale);
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(bmp, 0, 0, canvas.width, canvas.height);
    bmp.close();
    return await new Promise((resolve, reject) =>
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("encode"))), "image/jpeg", 0.9));
  } catch {
    return file; // trình duyệt không giải mã được → gửi nguyên file, server tự xử lý
  }
}

function updateSubmit() {
  $("submit").disabled = state.busy || !state.garment || !state.person;
}

// ---------- ảnh sản phẩm ----------
function setGarment(g) {
  if (state.garment?.previewUrl) URL.revokeObjectURL(state.garment.previewUrl);
  state.garment = g;
  $("garment-preview").src = g.kind === "url" ? g.url : g.previewUrl;
  $("garment-current").hidden = false;
  for (const btn of $("candidates").querySelectorAll("button")) {
    btn.setAttribute("aria-pressed", String(g.kind === "url" && btn.dataset.url === g.url));
  }
  updateSubmit();
}

function renderCandidates(images) {
  const box = $("candidates");
  box.replaceChildren();
  for (const url of images) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.dataset.url = url;
    btn.setAttribute("aria-pressed", "false");
    btn.title = "Dùng ảnh này";
    const img = document.createElement("img");
    img.src = url;
    img.alt = "Ảnh sản phẩm";
    img.loading = "lazy";
    img.referrerPolicy = "no-referrer";
    img.onerror = () => btn.remove();
    btn.append(img);
    btn.addEventListener("click", () => setGarment({ kind: "url", url }));
    box.append(btn);
  }
  box.hidden = images.length < 2; // 1 ảnh thì khung "đang dùng" là đủ
}

let resolveCtl = null;
async function resolveLink(text) {
  resolveCtl?.abort();
  if (!text.trim()) { resolveStatus(""); return; }
  resolveCtl = new AbortController();
  resolveStatus("Đang đọc link…");
  try {
    const res = await fetch("/api/product/resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: text }),
      signal: resolveCtl.signal,
    });
    const data = await readJson(res);
    if (!res.ok) throw new Error(errorMessage(data, "Không đọc được link"));

    state.offerLink = data.offer_link || null;
    renderCandidates(data.images);
    if (data.images.length) {
      setGarment({ kind: "url", url: data.images[0] });
      resolveStatus(data.title ? `Đã tìm thấy: ${data.title}` : "Đã tìm thấy ảnh sản phẩm");
    } else {
      resolveStatus(data.message, "error");
      $("upload-details").open = true;
    }
  } catch (e) {
    if (e.name === "AbortError") return;
    resolveStatus(e.message, "error");
    $("upload-details").open = true;
  }
}

let debounce;
$("product-url").addEventListener("input", (e) => {
  clearTimeout(debounce);
  debounce = setTimeout(() => resolveLink(e.target.value), 400);
});

$("garment-file").addEventListener("change", async (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  const blob = await downscale(file);
  setGarment({ kind: "file", blob, previewUrl: URL.createObjectURL(blob) });
  resolveStatus("Đang dùng ảnh bạn tải lên");
});

// ---------- ảnh toàn thân ----------
async function setPerson(file) {
  if (!file || !file.type.startsWith("image/")) return;
  state.person = await downscale(file);
  const img = $("person-preview");
  if (img.src) URL.revokeObjectURL(img.src);
  img.src = URL.createObjectURL(state.person);
  img.hidden = false;
  $("dz-empty").hidden = true;
  updateSubmit();
}

$("person-file").addEventListener("change", (e) => setPerson(e.target.files?.[0]));

const dz = $("dropzone");
dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("dragover"); });
dz.addEventListener("dragleave", () => dz.classList.remove("dragover"));
dz.addEventListener("drop", (e) => {
  e.preventDefault();
  dz.classList.remove("dragover");
  setPerson(e.dataTransfer.files?.[0]);
});

// ---------- thử đồ ----------
function setBusy(on) {
  state.busy = on;
  $("progress").classList.toggle("active", on);
  $("submit").textContent = on ? "Đang xử lý…" : "Thử đồ";
  updateSubmit();
}

async function pollJob(jobId) {
  const started = Date.now();
  for (;;) {
    await sleep(POLL_MS);
    const res = await fetch(`/api/jobs/${jobId}`);
    const job = await readJson(res);
    if (!res.ok) throw new Error(errorMessage(job));
    if (job.status === "done") return job;
    if (job.status === "failed") throw new Error(job.error || "Xử lý thất bại, vui lòng thử lại.");
    notice(job.status === "queued"
      ? (job.position ? `Đang xếp hàng, vị trí ${job.position}…` : "Đang xếp hàng…")
      : "Đang mặc thử cho bạn…");
    if (Date.now() - started > POLL_TIMEOUT_MS) throw new Error("Quá thời gian chờ, vui lòng thử lại.");
  }
}

function showResult(job) {
  $("result-img").src = job.result_url;
  $("download").href = job.result_url;
  const buy = $("buy");
  buy.hidden = !state.offerLink;
  if (state.offerLink) buy.href = state.offerLink;
  $("result").hidden = false;
  $("result").scrollIntoView({ behavior: "smooth", block: "start" });
}

$("submit").addEventListener("click", async () => {
  if (!state.garment || !state.person || state.busy) return;
  setBusy(true);
  $("result").hidden = true;
  notice("Đang gửi ảnh…");

  const fd = new FormData();
  fd.append("person", state.person, "person.jpg");
  if (state.garment.kind === "file") fd.append("garment", state.garment.blob, "garment.jpg");
  else fd.append("garment_url", state.garment.url);
  fd.append("category", document.querySelector('input[name="category"]:checked').value);

  try {
    const res = await fetch("/api/tryon", { method: "POST", body: fd });
    const data = await readJson(res);
    if (!res.ok) throw new Error(errorMessage(data));
    const job = await pollJob(data.job_id);
    showResult(job);
    notice(DEFAULT_NOTICE);
  } catch (e) {
    notice(e.message, "error");
  } finally {
    setBusy(false);
  }
});
