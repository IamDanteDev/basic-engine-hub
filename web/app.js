"use strict";

/* Basic Engine Hub — standalone browser menu.
 *
 * Listing sources, tried in order:
 *   1. ./api/listing   — the local server (web/serve.py) merges live.
 *   2. ./listing.json or ../listing.json — GitHub Pages build output at the
 *      site root, whether this app is opened from / or /web/.
 * Cards are rendered client-side; clicking one opens the project in a
"use strict";

/* Browser frontend. Durable user state is stored in localStorage/IndexedDB;
 * web/serve.py only streams Scratch data and never writes project files. */
/* The menu's copy. web/i18n.js owns the table and the choice; every value here
 * is resolved on read, so switching the language re-renders without a reload.
 * The core is a classic-script global (same shape as AuthCore below); if it ever
 * fails to load, tr() degrades to showing the key instead of throwing. */
const i18n = typeof I18n !== "undefined" ? I18n : null;
const tr = (key, params) => (i18n ? i18n.tr(key, params) : key);

const UI = {
  get loading() { return tr("loading"); },
  get offline() { return tr("offline"); },
  get loadError() { return tr("loadError"); },
  get playerLoading() { return tr("playerLoading"); },
  get detailsUnavailable() { return tr("detailsUnavailable"); },
  get commentsUnavailable() { return tr("commentsUnavailable"); },
  get noComments() { return tr("noComments"); },
  get favoriteAdd() { return tr("favoriteAdd"); },
  get favoriteRemove() { return tr("favoriteRemove"); },
  get featuredBadge() { return tr("featuredBadge"); },
  get signIn() { return tr("signIn"); },
  get signOut() { return tr("signOut"); },
  get authChecking() { return tr("authChecking"); },
  get authRequesting() { return tr("authRequesting"); },
  get authWaitingProject() { return tr("authWaitingProject"); },
  get authWaitingComment() { return tr("authWaitingComment"); },
  get authWaitingProfile() { return tr("authWaitingProfile"); },
  get authUsernameRequired() { return tr("authUsernameRequired"); },
  get authCopied() { return tr("authCopied"); },
  get authCopyError() { return tr("authCopyError"); },
  get authRequestFailed() { return tr("authRequestFailed"); },
  get authRejected() { return tr("authRejected"); },
  get authExpired() { return tr("authExpired"); },
  get authCallbackFailed() { return tr("authCallbackFailed"); },
  found: (n) => tr("found", { n }),
  filter: (visible, total) => tr("filter", { visible, total }),
  defaultTitle: (id) => tr("defaultTitle", { id }),
  sessionUser: (name) => tr("sessionUser", { name }),
};

const KEYS = {
  listing: "basic-engine-hub:listado:v1",
  favorites: "basic-engine-hub:favoritos:v1",
  search: "basic-engine-hub:busqueda:v1",
  savedIds: "basic-engine-hub:variables-guardadas:v1",
  savedValues: "basic-engine-hub:valores-guardados:v1",
};
const DB_NAME = "basic-engine-hub";
const DB_VERSION = 1;
const scriptElement = [...document.scripts].find((script) => /\/app\.js(?:\?|$)/.test(script.src));
const ASSET_BASE = new URL(".", scriptElement ? scriptElement.src : location.href);
const apiUrl = (route) => new URL(`../api/${route}`, ASSET_BASE).href;
/* Shared art (placeholder images, language titles) lives in the repository's
 * Assets/ next to web/, so it is one level above this script under both hosting
 * layouts: /web/app.js -> /Assets/... and /app.js -> /Assets/.... */
const assetUrl = (path) => new URL(`../Assets/${path}`, ASSET_BASE).href;
const playerUrl = () => new URL(`player.html?session=${Date.now()}`, ASSET_BASE).href;

const grid = document.getElementById("grid");
const statusEl = document.getElementById("status");
const searchEl = document.getElementById("search");
const refreshBtn = document.getElementById("refresh");
const favoritesFilter = document.getElementById("favorites-filter");
const retryBtn = document.getElementById("retry");
const errorBox = document.getElementById("error");
const errorText = document.getElementById("error-text");
const overlay = document.getElementById("player-overlay");
const playerFrame = document.getElementById("player");
const playerLoading = document.getElementById("player-loading");
const backBtn = document.getElementById("back");
const detailDialog = document.getElementById("detail-dialog");
const variablesDialog = document.getElementById("variables-dialog");
const editVariableDialog = document.getElementById("edit-variable-dialog");
const localControls = document.getElementById("local-player-controls");

function report(level, message, details) {
  console[level](`[Basic Engine Hub] ${message}`, ...(details === undefined ? [] : [details]));
}

let projects = readJSON(KEYS.listing, []);
if (!Array.isArray(projects)) projects = [];
const storedFavorites = readJSON(KEYS.favorites, []);
let favorites = new Set(Array.isArray(storedFavorites) ? storedFavorites.map(String) : []);
const storedIds = readJSON(KEYS.savedIds, {});
const storedValues = readJSON(KEYS.savedValues, {});
let savedIdsByProject = storedIds && typeof storedIds === "object" && !Array.isArray(storedIds) ? storedIds : {};
let savedValuesByProject = storedValues && typeof storedValues === "object" && !Array.isArray(storedValues) ? storedValues : {};
let loaded = projects.length > 0;
let favoritesOnly = false;
let activeProject = null;
let activeDetail = null;
let detailLoaded = false;
let lastComments = null;
let currentPlayerId = null;
let localPlayer = false;
let isPaused = false;
let editingVariable = null;

function readJSON(key, fallback) {
  try {
    const value = JSON.parse(localStorage.getItem(key));
    return value ?? fallback;
  } catch {
    return fallback;
  }
}

function writeJSON(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    statusEl.textContent = tr("storageFailed");
  }
}

function setFavorites() {
  writeJSON(KEYS.favorites, [...favorites]);
  render();
}

/* ---- Listing and browser persistence ------------------------------------- */
async function loadListing() {
  refreshBtn.disabled = true;
  errorBox.classList.add("hidden");
  statusEl.textContent = UI.loading;
  try {
    projects = await fetchListingOrFallback();
    loaded = true;
    writeJSON(KEYS.listing, projects);
    report("info", "Listado cargado.", { count: projects.length });
    render();
  } catch (error) {
    report("error", "No se pudo cargar el listado.", error);
    loaded = projects.length > 0;
    if (loaded) {
      render();
      statusEl.textContent = UI.offline;
      report("warn", "Usando el listado guardado sin conexión.", { count: projects.length });
    } else {
      errorText.textContent = UI.loadError;
      errorBox.classList.remove("hidden");
      statusEl.textContent = "";
    }
  } finally {
    refreshBtn.disabled = false;
  }
}

async function fetchListingOrFallback() {
  const failures = [];
  for (const source of ["./api/listing", "./listing.json", "../listing.json"]) {
    try {
      const response = await fetch(source, { cache: "no-store" });
      if (!response.ok) {
        failures.push(`${source}: HTTP ${response.status}`);
        continue;
      }
      const data = await response.json();
      if (Array.isArray(data)) {
        report("info", "Fuente del listado cargada.", { source, count: data.length });
        return data;
      }
      failures.push(`${source}: la respuesta JSON no es una lista`);
    } catch (error) {
      failures.push(`${source}: ${error.message}`);
    }
  }
  throw new Error(`No se pudo cargar ninguna fuente del listado. ${failures.join("; ")}`);
}

/* ---- Menu ----------------------------------------------------------------- */
function matches(project, needle) {
  return !needle ||
    (project.title || "").toLowerCase().includes(needle) ||
    (project.username || "").toLowerCase().includes(needle) ||
    String(project.id).includes(needle);
}

/* Display order: featured first, then programmatic pinned, then newest first.
 * Scratch project ids grow over time, so id descending == most recent. */
function projectRank(project) {
  if (project.featured === true) return 2;
  if (project.pinned === true) return 1;
  return 0;
}

function byNewestFirst(a, b) {
  return projectRank(b) - projectRank(a) || Number(b.id) - Number(a.id);
}

function render() {
  grid.textContent = "";
  const needle = searchEl.value.trim().toLowerCase();
  const visibleProjects = projects
    .filter((project) =>
      matches(project, needle) && (!favoritesOnly || favorites.has(String(project.id)))
    )
    .sort(byNewestFirst);
  for (const project of visibleProjects) grid.appendChild(cardFor(project));
  favoritesFilter.setAttribute("aria-pressed", String(favoritesOnly));
  favoritesFilter.textContent = tr("favoritesCount", { n: favorites.size });
  statusEl.textContent = needle || favoritesOnly
    ? UI.filter(visibleProjects.length, projects.length)
    : UI.found(projects.length);
}

function cardFor(project) {
  const card = document.createElement("button");
  card.type = "button";
  card.className = "card";
  card.title = project.title || UI.defaultTitle(project.id);
  if (project.featured === true) card.classList.add("featured");

  const hero = document.createElement("span");
  hero.className = "hero";
  /* Both images sit on the placeholder art declared by .hero / .avatar in
   * style.css: a slow request shows the placeholder and a failed one keeps it,
   * so dropping the `src` reveals the background instead of a broken icon. */
  if (project.image) {
    const image = document.createElement("img");
    image.className = "hero-img";
    image.alt = "";
    image.loading = "lazy";
    image.src = project.image;
    image.addEventListener("error", () => image.removeAttribute("src"));
    hero.appendChild(image);
  }
  if (project.avatar) {
    const avatar = document.createElement("img");
    avatar.className = "avatar";
    avatar.alt = "";
    avatar.loading = "lazy";
    avatar.src = project.avatar;
    avatar.addEventListener("error", () => avatar.removeAttribute("src"));
    hero.appendChild(avatar);
  }
  if (favorites.has(String(project.id))) {
    const favoriteMark = document.createElement("span");
    favoriteMark.className = "favorite-mark";
    favoriteMark.textContent = "★";
    favoriteMark.setAttribute("aria-label", UI.favoriteRemove);
    hero.appendChild(favoriteMark);
  }

  const info = document.createElement("span");
  info.className = "info";
  if (project.featured === true) {
    const badge = document.createElement("span");
    badge.className = "featured-badge";
    badge.textContent = UI.featuredBadge;
    info.appendChild(badge);
  }
  const title = document.createElement("span");
  title.className = "title";
  title.textContent = project.title || UI.defaultTitle(project.id);
  const user = document.createElement("span");
  user.className = "user";
  user.textContent = authorLabel(project.username);
  info.append(title, user);
  card.append(hero, info);
  card.addEventListener("click", () => openDetails(project));
  return card;
}

/* ---- Project details and favorites --------------------------------------- */
function showDetailText(selector, text, fallback) {
  const element = document.getElementById(selector);
  element.textContent = text || fallback;
}

function setFavoriteButton() {
  const button = document.getElementById("detail-favorite");
  const isFavorite = favorites.has(String(activeProject.id));
  button.textContent = isFavorite ? UI.favoriteRemove : UI.favoriteAdd;
  button.setAttribute("aria-pressed", String(isFavorite));
}

async function openDetails(project) {
  activeProject = project;
  activeDetail = project;
  detailLoaded = false;
  lastComments = null;
  const id = String(project.id);
  document.getElementById("detail-title").textContent = project.title || UI.defaultTitle(id);
  const author = document.getElementById("detail-author");
  author.textContent = authorLabel(project.username);
  author.href = project.username
    ? `https://scratch.mit.edu/users/${encodeURIComponent(project.username)}/`
    : `https://scratch.mit.edu/projects/${encodeURIComponent(id)}/`;
  const cover = document.getElementById("detail-cover");
  /* The cover keeps .detail-cover's placeholder art while loading and when the
   * request fails, so it is never hidden and never shows a broken icon. */
  cover.hidden = false;
  if (project.image) {
    cover.src = project.image;
  } else {
    cover.removeAttribute("src");
  }
  cover.onerror = () => cover.removeAttribute("src");
  document.getElementById("detail-open-scratch").href = `https://scratch.mit.edu/projects/${encodeURIComponent(id)}/`;
  const initialStats = project.stats || {};
  document.getElementById("detail-stats").textContent = Object.keys(initialStats).length
    ? formatStats(initialStats)
    : UI.detailsUnavailable;
  showDetailText("detail-description", project.description, UI.detailsUnavailable);
  showDetailText("detail-instructions", project.instructions, UI.detailsUnavailable);
  document.getElementById("detail-comments").textContent = UI.commentsUnavailable;
  setFavoriteButton();
  detailDialog.showModal();

  const [detail, comments] = await Promise.all([
    fetchApiJSON(apiUrl(`project/${encodeURIComponent(id)}`)),
    fetchApiJSON(apiUrl(`comments/${encodeURIComponent(id)}`)),
  ]);
  if (activeProject !== project || !detailDialog.open) return;
  if (detail) {
    activeDetail = { ...project, ...detail };
    Object.assign(project, detail);
    const index = projects.findIndex((item) => String(item.id) === id);
    if (index >= 0) projects[index] = project;
    writeJSON(KEYS.listing, projects);
    document.getElementById("detail-stats").textContent = formatStats(detail.stats || {});
    showDetailText("detail-description", detail.description, tr("noDescription"));
    showDetailText("detail-instructions", detail.instructions, tr("noInstructions"));
  }
  detailLoaded = true;
  renderComments(comments);
}

function formatStats(stats) {
  return `❤ ${stats.loves || 0}   ⭐ ${stats.favorites || 0}   👁 ${stats.views || 0}   🔀 ${stats.remixes || 0}`;
}

async function fetchApiJSON(url) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 7000);
  try {
    const response = await fetch(url, { signal: controller.signal, cache: "no-store" });
    if (!response.ok) {
      report("warn", "La consulta de detalles falló.", { url, status: response.status });
      return null;
    }
    return await response.json();
  } catch (error) {
    report("warn", "No se pudieron consultar los detalles.", { url, error });
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

function renderComments(comments) {
  lastComments = comments;
  const container = document.getElementById("detail-comments");
  container.textContent = "";
  if (!Array.isArray(comments)) {
    container.textContent = UI.commentsUnavailable;
    return;
  }
  if (!comments.length) {
    container.textContent = UI.noComments;
    return;
  }
  for (const comment of comments) {
    const article = document.createElement("article");
    article.className = "comment-item";
    const username = document.createElement("p");
    username.className = "comment-user";
    username.textContent = comment.user || "";
    const content = document.createElement("p");
    content.className = "comment-text";
    content.textContent = comment.content || "";
    const time = document.createElement("time");
    time.className = "comment-time";
    time.textContent = comment.timestamp || "";
    article.append(username, content, time);
    for (const reply of comment.replies || []) {
      const replyItem = document.createElement("p");
      replyItem.className = "comment-text";
      replyItem.textContent = `↳ ${reply.user || ""}: ${reply.content || ""}`;
      article.appendChild(replyItem);
    }
    container.appendChild(article);
  }
}

/* ---- Browser project cache (IndexedDB) ----------------------------------- */
function openProjectDB() {
  return new Promise((resolve, reject) => {
    if (!("indexedDB" in window)) return reject(new Error("IndexedDB unavailable"));
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains("projects")) {
        request.result.createObjectStore("projects", { keyPath: "id" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function readProject(id) {
  const db = await openProjectDB();
  return new Promise((resolve, reject) => {
    const request = db.transaction("projects", "readonly").objectStore("projects").get(String(id));
    request.onsuccess = () => resolve(request.result ? request.result.bytes : null);
    request.onerror = () => reject(request.error);
  });
}

async function saveProject(id, bytes, project) {
  const db = await openProjectDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction("projects", "readwrite");
    transaction.objectStore("projects").put({
      id: String(id), bytes, title: project.title || "", username: project.username || "",
      savedAt: new Date().toISOString(),
    });
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
  });
}

async function getProjectBytes(id) {
  try {
    const cached = await readProject(id);
    if (cached) {
      report("info", "Proyecto abierto desde la caché del navegador.", { id });
      return cached;
    }
  } catch (error) {
    // IndexedDB can be disabled or full; continue without persistent caching.
    report("warn", "No se pudo leer la caché del navegador.", { id, error });
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(apiUrl(`download/${encodeURIComponent(id)}`), {
      signal: controller.signal,
      cache: "no-store",
    });
    if (!response.ok) {
      report("error", "Falló la descarga del proyecto.", { id, status: response.status });
      return null;
    }
    const bytes = await response.arrayBuffer();
    if (!bytes.byteLength) {
      report("error", "La descarga del proyecto estaba vacía.", { id });
      return null;
    }
    try {
      await saveProject(id, bytes, activeProject);
    } catch (error) {
      report("warn", "No se pudo guardar el proyecto en la caché.", { id, error });
      statusEl.textContent = tr("cacheSaveFailed");
    }
    return bytes;
  } catch (error) {
    report("error", "No se pudo descargar el proyecto.", { id, error });
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

/* ---- Player --------------------------------------------------------------- */
async function openPlayer(project) {
  report("info", "Abriendo proyecto.", { id: String(project.id) });
  activeProject = project;
  detailDialog.close();
  captureCheckedVariables();
  overlay.classList.remove("hidden");
  document.body.classList.add("player-open");
  playerLoading.hidden = false;
  localControls.hidden = true;
  isPaused = false;
  currentPlayerId = String(project.id);
  const fullscreenRequest = document.documentElement.requestFullscreen?.();
  fullscreenRequest?.catch(() => {});

  const bytes = await getProjectBytes(project.id);
  if (currentPlayerId !== String(project.id) || overlay.classList.contains("hidden")) return;
  if (bytes) {
    playLocalProject(project, bytes);
  } else {
    playRemoteProject(project);
  }
}

function playLocalProject(project, bytes) {
  localPlayer = true;
  localControls.hidden = false;
  playerFrame.onload = async () => {
    try {
      const load = playerFrame.contentWindow.loadScratchProjectBytes;
      if (typeof load !== "function") throw new Error(tr("playerStartFailed"));
      const result = await load(bytes);
      if (typeof result === "string" && result.startsWith("error:")) throw new Error(result.slice(6));
      playerLoading.hidden = true;
      restoreCheckedVariables(project.id);
    } catch (error) {
      playerLoading.hidden = true;
      statusEl.textContent = error.message;
      report("error", "Falló la carga del proyecto en el reproductor local.", { id: String(project.id), error });
    }
  };
  playerFrame.src = playerUrl();
}

function playRemoteProject(project) {
  localPlayer = false;
  localControls.hidden = true;
  playerFrame.onload = () => { playerLoading.hidden = true; };
  playerFrame.src = `https://turbowarp.org/${encodeURIComponent(String(project.id))}/embed?autoplay`;
}

function callLocalPlayer(method, ...args) {
  if (!localPlayer) return null;
  try {
    const fn = playerFrame.contentWindow[method];
    return typeof fn === "function" ? fn(...args) : null;
  } catch {
    return null;
  }
}

function closePlayer() {
  captureCheckedVariables();
  callLocalPlayer("stopAll");
  playerFrame.onload = null;
  playerFrame.src = "about:blank";
  overlay.classList.add("hidden");
  playerLoading.hidden = true;
  localControls.hidden = true;
  document.body.classList.remove("player-open");
  localPlayer = false;
  currentPlayerId = null;
  if (document.fullscreenElement) {
    const fullscreenExit = document.exitFullscreen?.();
    fullscreenExit?.catch(() => {});
  }
}

/* ---- Browser-persisted variables/lists ----------------------------------- */
function selectedVariableIds(projectId) {
  const selected = savedIdsByProject[String(projectId)];
  return Array.isArray(selected) ? selected.map(String) : [];
}

function saveSelectedIds(projectId, ids) {
  savedIdsByProject[String(projectId)] = ids;
  writeJSON(KEYS.savedIds, savedIdsByProject);
}

function captureCheckedVariables() {
  if (!localPlayer || !currentPlayerId) return;
  const rows = callLocalPlayer("listVariables") || [];
  const ids = selectedVariableIds(currentPlayerId);
  const values = {};
  for (const row of rows) if (ids.includes(String(row.id))) values[row.id] = row.value;
  savedValuesByProject[currentPlayerId] = values;
  writeJSON(KEYS.savedValues, savedValuesByProject);
}

function restoreCheckedVariables(projectId) {
  const values = savedValuesByProject[String(projectId)] || {};
  for (const [id, value] of Object.entries(values)) callLocalPlayer("setVariableValue", id, value);
}

/* Filled from the running player; re-run on a language switch. */
function fillVariablesTable() {
  const rows = callLocalPlayer("listVariables") || [];
  const body = document.getElementById("variables-rows");
  body.textContent = "";
  document.getElementById("variables-empty").hidden = rows.length > 0;
  const saved = new Set(selectedVariableIds(currentPlayerId));
  for (const variable of rows) {
    const row = document.createElement("tr");
    const keepCell = document.createElement("td");
    const keep = document.createElement("input");
    keep.type = "checkbox";
    keep.checked = saved.has(String(variable.id));
    keep.setAttribute("aria-label", tr("saveVariableLabel", { name: variable.name }));
    keep.addEventListener("change", () => {
      if (keep.checked) saved.add(String(variable.id));
      else saved.delete(String(variable.id));
      saveSelectedIds(currentPlayerId, [...saved]);
    });
    keepCell.appendChild(keep);
    const kindCell = document.createElement("td");
    kindCell.textContent = variable.kind === "list" ? tr("kindList") : tr("kindVariable");
    const nameCell = document.createElement("td");
    nameCell.textContent = `${variable.name || ""}${variable.isCloud ? " ☁" : ""}`;
    const targetCell = document.createElement("td");
    targetCell.textContent = variable.target || "";
    const valueCell = document.createElement("td");
    valueCell.className = "value";
    valueCell.textContent = variable.kind === "list" ? JSON.stringify(variable.value) : String(variable.value);
    const editCell = document.createElement("td");
    const edit = document.createElement("button");
    edit.type = "button";
    edit.className = "btn";
    edit.textContent = tr("edit");
    edit.addEventListener("click", () => editVariable(variable, valueCell));
    editCell.appendChild(edit);
    row.append(keepCell, kindCell, nameCell, targetCell, valueCell, editCell);
    body.appendChild(row);
  }
  return rows;
}

function openVariables() {
  fillVariablesTable();
  variablesDialog.showModal();
}

function editVariable(variable, valueCell) {
  const current = variable.kind === "list" ? JSON.stringify(variable.value) : String(variable.value);
  editingVariable = { variable, valueCell };
  refreshEditVariableCopy();
  const input = document.getElementById("edit-variable-input");
  input.value = current;
  editVariableDialog.showModal();
  input.focus();
}

/* Re-applied when the language changes while the dialog is open. */
function refreshEditVariableCopy() {
  if (!editingVariable) return;
  const { variable } = editingVariable;
  document.getElementById("edit-variable-title").textContent =
    variable.kind === "list" ? tr("editListTitle") : tr("editVariableTitle");
  document.getElementById("edit-variable-label").textContent = variable.name || tr("valueLabel");
}

function parseVariableValue(variable, text) {
  let next = text;
  if (variable.kind === "list") {
    try {
      const parsed = JSON.parse(text);
      next = Array.isArray(parsed) ? parsed : text.split(",").map((part) => part.trim());
    } catch {
      next = text ? text.split(",").map((part) => part.trim()) : [];
    }
  } else {
    try {
      const parsed = JSON.parse(text);
      if (["string", "number", "boolean"].includes(typeof parsed)) next = parsed;
    } catch {
      // Keep ordinary text as a string.
    }
  }
  return next;
}

function saveVariableEdit() {
  if (!editingVariable) return;
  const { variable, valueCell } = editingVariable;
  const input = document.getElementById("edit-variable-input");
  const next = parseVariableValue(variable, input.value);
  const result = callLocalPlayer("setVariableValue", variable.id, next);
  if (result === false || (typeof result === "string" && result.startsWith("error:"))) return;
  variable.value = next;
  valueCell.textContent = variable.kind === "list" ? JSON.stringify(next) : String(next);
  captureCheckedVariables();
  editVariableDialog.close();
  editingVariable = null;
}

/* ---- Scratch sign-in (Scratch Auth; pure core in web/auth.js) ------------- */
/* The session is identity only: it shows who you are and marks your own
 * projects with "(You)". Nothing else is gated. Only the username is stored;
 * the privateCode lives while the dialog is open and is then dropped. */
const Auth = typeof AuthCore !== "undefined" ? AuthCore : null;
const AUTH_POLL_MS = 3000; /* how often we ask the service if the code was used */
const AUTH_WINDOW_MS = 15 * 60 * 1000; /* how long the dialog keeps trying */
const sessionEl = document.getElementById("session");
const authDialog = document.getElementById("auth-dialog");
const authMethodEl = document.getElementById("auth-method");
const authUsernameRow = document.getElementById("auth-username-row");
const authUsernameEl = document.getElementById("auth-username");
const authReadyEl = document.getElementById("auth-ready");
const authCodeEl = document.getElementById("auth-code");
const authStatusEl = document.getElementById("auth-status");
const authOpenEl = document.getElementById("auth-open");
const authContinueEl = document.getElementById("auth-continue");
const authVerifyEl = document.getElementById("auth-verify");
const authStorage = (() => {
  try {
    return window.localStorage;
  } catch {
    return null; /* storage can be blocked; the app then runs signed out */
  }
})();
const authState = { tokens: null, poll: null, refresh: null, deadline: 0, statusKey: "", attempts: 0 };
/* Last HTTP status the service answered for a session request. The core reads a
 * non-ok answer as "not yet", so the status only survives for the log. */
let authHttpStatus = 0;
/* One pending line every N polls: the 15-minute window polls 300 times, and a
 * line per try would bury every other message in the console. */
const AUTH_POLL_LOG_EVERY = 5;
let session = Auth && authStorage ? Auth.readSession(authStorage) : null;

/* Username shown on a card or in the detail dialog, plus the literal "(You)"
 * when the project belongs to the signed-in user. */
function authorLabel(username) {
  if (!username) return "";
  return Auth ? Auth.authorLabel(username, session ? session.username : "") : `@${username}`;
}

/* The status line is kept as a translation key, not as text, so a language
 * switch can re-render the message that is currently on screen. */
function setAuthStatus(key) {
  authState.statusKey = key || "";
  if (authStatusEl) authStatusEl.textContent = key ? tr(key) : "";
}

/* Every sign-in request goes through here, so one wrapper can report the status
 * of each poll without touching the core. The private code is the handle to the
 * session, so it never reaches the console: the URL is redacted first. */
function redactAuthUrl(url) {
  return String(url).replace(/(\/auth\/verifyToken\/)[^?&]+/, "$1<privateCode>");
}

function fetchImpl(url) {
  const shown = redactAuthUrl(url);
  const isPoll = shown.includes("/auth/verifyToken/");
  return fetch(url).then(
    (response) => {
      if (isPoll) {
        /* The pending answer is a 403 on every tick; pollSignIn summarizes it. */
        authHttpStatus = response.status;
      } else {
        report(response.ok ? "info" : "warn", "El servicio de sesión respondió a la petición de código.", {
          url: shown,
          status: response.status,
          ok: response.ok,
        });
      }
      return response;
    },
    (error) => {
      authHttpStatus = 0;
      report("error", "La petición de sesión no llegó al servicio.", {
        url: shown,
        isPoll,
        error: String((error && error.message) || error),
      });
      throw error;
    }
  );
}

function renderSession() {
  if (!sessionEl) return;
  sessionEl.textContent = "";
  if (!Auth) {
    sessionEl.hidden = true;
    return;
  }
  sessionEl.hidden = false;
  if (session) {
    const link = document.createElement("a");
    link.className = "session-user";
    link.href = `https://scratch.mit.edu/users/${encodeURIComponent(session.username)}/`;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = `@${session.username}`;
    link.title = UI.sessionUser(session.username);
    const out = document.createElement("button");
    out.type = "button";
    out.className = "btn session-out";
    out.textContent = UI.signOut;
    out.addEventListener("click", signOut);
    sessionEl.append(link, out);
  } else {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn session-signin";
    button.textContent = UI.signIn;
    button.addEventListener("click", () => openAuthDialog());
    sessionEl.appendChild(button);
  }
}

function refreshGrid() {
  if (loaded) render();
}

function signOut() {
  const outgoing = session ? session.username : null;
  if (Auth && authStorage) Auth.clearSession(authStorage);
  session = null;
  renderSession();
  refreshGrid();
  report("info", "Sesión de Scratch cerrada.", { username: outgoing });
}

function openAuthDialog(options = {}) {
  if (!Auth || !authDialog) return;
  if (options.method && Auth.isKnownMethod(options.method)) authMethodEl.value = options.method;
  report("info", "Diálogo de sesión abierto.", {
    method: authMethodEl.value,
    authProject: Auth.AUTH_PROJECT_ID,
    callback: Auth.buildCallbackUrl(location),
    signedIn: session ? session.username : null,
  });
  authDialog.showModal();
  updateAuthDialog();
  startSignIn();
}

function updateAuthDialog() {
  const method = authMethodEl.value;
  const needsUsername = method === "profile-comment";
  const ready = Boolean(authState.tokens);
  if (authUsernameRow) authUsernameRow.hidden = !needsUsername;
  if (authReadyEl) authReadyEl.hidden = !ready;
  if (ready && authCodeEl) authCodeEl.textContent = authState.tokens.publicCode || "—";
}

function authWaitingKey(method) {
  if (method === "profile-comment") return "authWaitingProfile";
  if (method === "comment") return "authWaitingComment";
  return "authWaitingProject";
}

function stopPolling() {
  if (authState.poll) clearInterval(authState.poll);
  authState.poll = null;
}

function stopAuthTimers() {
  stopPolling();
  if (authState.refresh) clearTimeout(authState.refresh);
  authState.refresh = null;
}

/* Ask the service for a fresh token pair (a new code) for the chosen method. */
async function startSignIn() {
  if (!Auth) return;
  const method = authMethodEl.value;
  const username = authUsernameEl.value.trim();
  if (method === "profile-comment" && !username) {
    report("warn", "El método de perfil necesita el usuario de Scratch.", { method });
    setAuthStatus("authUsernameRequired");
    return;
  }
  stopAuthTimers();
  authState.tokens = null;
  updateAuthDialog();
  setAuthStatus("authRequesting");
  report("info", "Pidiendo un código de acceso al servicio de sesión.", {
    method,
    authProject: Auth.AUTH_PROJECT_ID,
    callback: Auth.buildCallbackUrl(location),
  });
  try {
    const tokens = await Auth.requestTokens(fetchImpl, {
      redirect: Auth.buildCallbackUrl(location),
      method,
      username,
    });
    if (!authDialog.open) return;
    authState.tokens = tokens;
    authState.deadline = Date.now() + AUTH_WINDOW_MS;
    authState.attempts = 0;
    authHttpStatus = 0; /* a new attempt must not report the previous one's status */
    updateAuthDialog();
    setAuthStatus(authWaitingKey(method));
    authState.poll = setInterval(pollSignIn, AUTH_POLL_MS);
    report("info", "Código de acceso recibido: la sesión se sondea hasta que el servicio la confirme.", {
      publicCode: tokens.publicCode,
      method: tokens.method,
      authProject: tokens.authProject,
      redirectLocation: tokens.redirectLocation,
      pollMs: AUTH_POLL_MS,
      windowMs: AUTH_WINDOW_MS,
      codeTtlMs: Auth.AUTH_CODE_TTL_MS,
    });
    /* The service expires a token pair after 5 minutes; refresh before that. */
    authState.refresh = setTimeout(() => {
      if (authDialog.open && authState.tokens) startSignIn();
    }, Auth.AUTH_CODE_TTL_MS);
  } catch (error) {
    report("error", "No se pudo generar el código de acceso.", {
      method,
      callback: Auth.buildCallbackUrl(location),
      error, /* the Error itself, so the console keeps its stack */
    });
    setAuthStatus("authRequestFailed");
  }
}

/* The manual check parks the status line on "checking"; when the service still
 * has nothing to confirm, the wait has to be visible again instead of frozen
 * there for the rest of the dialog's life. */
function resumeAuthWaiting() {
  if (authState.statusKey === "authChecking") setAuthStatus(authWaitingKey(authMethodEl.value));
}

async function pollSignIn() {
  if (!authState.tokens || !authState.tokens.privateCode) return;
  authState.attempts += 1;
  if (Date.now() > authState.deadline) {
    stopAuthTimers();
    setAuthStatus("authExpired");
    report("warn", "La ventana de la sesión expiró sin que el servicio confirmara nada.", {
      attempts: authState.attempts,
      lastHttpStatus: authHttpStatus,
    });
    return;
  }
  let result;
  try {
    result = await Auth.verifyCode(fetchImpl, { privateCode: authState.tokens.privateCode });
  } catch (error) {
    report("warn", "El sondeo de la sesión falló; se reintenta en el próximo ciclo.", error);
    resumeAuthWaiting();
    return;
  }
  if (!result.valid) {
    /* The first try and then every fifth: `httpStatus` tells whether the service
     * is answering "not yet" (403) or the request never reached it (0). */
    if (authState.attempts % AUTH_POLL_LOG_EVERY === 1) {
      report("info", "Sondeo de la sesión: el servicio todavía no confirma el código.", {
        attempt: authState.attempts,
        lastHttpStatus: authHttpStatus,
        remainingMs: Math.max(0, authState.deadline - Date.now()),
      });
    }
    resumeAuthWaiting();
    return;
  }
  if (!Auth.isTrustedRedirect(result.redirect, Auth.buildCallbackUrl(location))) {
    stopAuthTimers();
    authState.tokens = null;
    report("warn", "La confirmación apunta a otro sitio; se descarta.", {
      redirect: result.redirect,
      expected: Auth.buildCallbackUrl(location),
    });
    setAuthStatus("authRejected");
    return;
  }
  report("info", "El servicio confirmó la identidad; guardando la sesión.", {
    username: result.username,
    method: authMethodEl.value,
    attempts: authState.attempts,
    redirect: result.redirect,
  });
  completeSignIn(result.username, authMethodEl.value);
}

/* The manual check: don't wait for the next poll tick. With nothing live to
 * check (no code yet, or the dialog already gave up on the window) it asks the
 * service for a fresh pair instead of doing nothing. */
async function verifyNow() {
  if (!authState.tokens || !authState.tokens.privateCode || Date.now() > authState.deadline) {
    report("info", "Verificación manual sin código vivo: se pide uno nuevo.", {
      hadTokens: Boolean(authState.tokens),
      expired: Boolean(authState.tokens) && Date.now() > authState.deadline,
    });
    await startSignIn();
    return;
  }
  report("info", "Verificación manual pedida por el usuario.", {
    method: authMethodEl.value,
    attempts: authState.attempts,
  });
  setAuthStatus("authChecking");
  await pollSignIn();
}

function completeSignIn(username, method) {
  stopAuthTimers();
  if (!Auth || !authStorage || !username) {
    report("warn", "La sesión no se pudo guardar.", {
      core: Boolean(Auth),
      storage: Boolean(authStorage),
      username: Boolean(username),
    });
    setAuthStatus("authCallbackFailed");
    return;
  }
  session = Auth.writeSession(authStorage, { username, method: method || "cloud", at: Date.now() });
  authState.tokens = null;
  if (authDialog && authDialog.open) authDialog.close();
  renderSession();
  refreshGrid();
  report("info", "Sesión de Scratch iniciada.", { username, method: method || "cloud" });
}

/* Fallback path: the service sent the browser back with ?privateCode=... */
async function handleAuthCallback() {
  if (!Auth) return;
  const privateCode = Auth.extractPrivateCode(location.search);
  if (!privateCode) return;
  stripAuthQuery(); /* never leave the code in the address bar */
  setAuthStatus("authChecking");
  report("info", "El servicio devolvió el navegador con un código en la URL.", {
    callback: Auth.buildCallbackUrl(location),
  });
  let result = null;
  try {
    result = await Auth.verifyCode(fetchImpl, { privateCode });
  } catch (error) {
    report("warn", "No se pudo verificar el código que llegó en la URL.", error);
  }
  if (result && result.valid && Auth.isTrustedRedirect(result.redirect, Auth.buildCallbackUrl(location))) {
    report("info", "El código de la URL confirmó la sesión.", { username: result.username });
    completeSignIn(result.username, "cloud");
    return;
  }
  report("warn", "El código de la URL no produjo una sesión válida.", {
    valid: Boolean(result && result.valid),
    redirect: result ? result.redirect : null,
    expected: Auth.buildCallbackUrl(location),
  });
  setAuthStatus("authCallbackFailed");
}

function stripAuthQuery() {
  try {
    history.replaceState(null, "", `${location.pathname}${location.hash}`);
  } catch {
    /* history can be unavailable (file://); the code in the URL is then left as is */
  }
}

function initAuth() {
  if (!Auth || !sessionEl || !authDialog) {
    /* The sign-in control is built at runtime, so a missing core or a missing
     * dialog leaves the page with no visible symptom but no way in either. */
    report("warn", "El inicio de sesión no se pudo montar.", {
      core: Boolean(Auth),
      session: Boolean(sessionEl),
      dialog: Boolean(authDialog),
    });
    if (sessionEl) sessionEl.hidden = true;
    return;
  }
  authOpenEl.href = Auth.AUTH_PROJECT_URL;
  renderSession();
  authMethodEl.addEventListener("change", () => {
    stopAuthTimers();
    authState.tokens = null;
    updateAuthDialog();
    startSignIn();
  });
  // username row removed
  if (authUsernameEl) {
    authUsernameEl.addEventListener("keydown", (event) => {
      if (event.key === "Enter") startSignIn();
    });
  }
  if (authContinueEl) {
    authContinueEl.addEventListener("click", startSignIn);
    authContinueEl.hidden = true;
  }
  authVerifyEl.addEventListener("click", verifyNow);
  document.getElementById("auth-copy").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(authCodeEl.textContent);
      setAuthStatus("authCopied");
    } catch {
      setAuthStatus("authCopyError");
    }
  });
  document.getElementById("auth-close").addEventListener("click", () => authDialog.close());
  authDialog.addEventListener("close", () => {
    stopAuthTimers();
    authState.tokens = null;
  });
  handleAuthCallback();
}

/* ---- Language ------------------------------------------------------------- */

/* The header selector and the first-visit chooser are both built from the core's
 * own list, so the four languages, their order and their flags have a single
 * source and cannot drift from the table. A language always shows its own name. */
function fillLanguageOptions() {
  if (!i18n) return;
  const select = document.getElementById("language");
  const options = document.getElementById("language-chooser-options");
  select.textContent = "";
  options.textContent = "";
  for (const language of i18n.LANGUAGES) {
    const option = document.createElement("option");
    option.value = language.code;
    option.textContent = language.name;
    select.appendChild(option);

    const button = document.createElement("button");
    button.type = "button";
    button.className = "language-option";
    const flag = document.createElement("span");
    flag.className = "language-option-flag";
    flag.innerHTML = language.flag;
    /* The visible name is the language's own title art, so the option reads in
     * the language it offers; `alt` keeps that name available to screen readers
     * and to browsers that never get the image. */
    const title = document.createElement("img");
    title.className = "language-option-title";
    title.src = assetUrl(`Lengs/Titles/${language.title}`);
    title.alt = language.name;
    button.append(flag, title);
    button.addEventListener("click", () => chooseLanguage(language.code));
    options.appendChild(button);
  }
  select.value = i18n.current();
}

function chooseLanguage(code) {
  if (!i18n || !i18n.isKnownCode(code)) return;
  i18n.setLanguage(code);
  const chooser = document.getElementById("language-chooser");
  if (chooser.open) chooser.close();
}

/* Re-apply every translated surface in place: the static hooks, the grid, the
 * session chip, and whichever dialog happens to be open. */
function applyLanguage() {
  if (i18n) i18n.apply(document);
  const select = document.getElementById("language");
  if (select && i18n) select.value = i18n.current();
  document.getElementById("player-pause").textContent = tr(isPaused ? "resume" : "pause");
  if (loaded) render();
  renderSession();
  if (detailDialog.open && detailLoaded) refreshDetailCopy();
  if (variablesDialog.open) fillVariablesTable();
  if (editVariableDialog.open && editingVariable) refreshEditVariableCopy();
  if (authDialog.open) {
    updateAuthDialog();
    if (authState.statusKey) setAuthStatus(authState.statusKey);
  }
}

/* Re-run the detail dialog's copy for the currently open project; the values
 * that came from the API (stats, comments) are formatted again as well. */
function refreshDetailCopy() {
  if (!activeDetail) return;
  const stats = activeDetail.stats || {};
  document.getElementById("detail-stats").textContent = Object.keys(stats).length
    ? formatStats(stats)
    : tr("detailsUnavailable");
  showDetailText("detail-description", activeDetail.description, tr("noDescription"));
  showDetailText("detail-instructions", activeDetail.instructions, tr("noInstructions"));
  renderComments(lastComments);
  setFavoriteButton();
}

/* The chooser asks only while neither a stored choice nor a ?lang= exists. */
fillLanguageOptions();
document.getElementById("language").addEventListener("change", (event) => {
  chooseLanguage(event.currentTarget.value);
});
if (i18n && i18n.needsChoice(window.location.search)) {
  document.getElementById("language-chooser").showModal();
}

if (i18n) i18n.onChange(applyLanguage);

/* ---- Events --------------------------------------------------------------- */
searchEl.value = readJSON(KEYS.search, "");
searchEl.addEventListener("input", () => {
  writeJSON(KEYS.search, searchEl.value);
  if (loaded) render();
});
refreshBtn.addEventListener("click", loadListing);
retryBtn.addEventListener("click", loadListing);
favoritesFilter.addEventListener("click", () => {
  favoritesOnly = !favoritesOnly;
  render();
});
document.getElementById("detail-close").addEventListener("click", () => detailDialog.close());
document.getElementById("detail-favorite").addEventListener("click", () => {
  const id = String(activeProject.id);
  if (favorites.has(id)) favorites.delete(id);
  else favorites.add(id);
  setFavoriteButton();
  setFavorites();
});
document.getElementById("detail-play").addEventListener("click", () => openPlayer(activeProject));
document.getElementById("variables-close").addEventListener("click", () => variablesDialog.close());
document.getElementById("edit-variable-cancel").addEventListener("click", () => {
  editVariableDialog.close();
  editingVariable = null;
});
document.getElementById("edit-variable-save").addEventListener("click", saveVariableEdit);
backBtn.addEventListener("click", closePlayer);
document.getElementById("player-flag").addEventListener("click", () => callLocalPlayer("greenFlag"));
document.getElementById("player-pause").addEventListener("click", (event) => {
  isPaused = !isPaused;
  callLocalPlayer(isPaused ? "pausePlayer" : "resumePlayer");
  event.currentTarget.textContent = tr(isPaused ? "resume" : "pause");
});
document.getElementById("player-stop").addEventListener("click", () => callLocalPlayer("stopAll"));
document.getElementById("player-variables").addEventListener("click", openVariables);
document.getElementById("player-clones").addEventListener("click", () => callLocalPlayer("toggleClonesPanel"));
document.getElementById("player-fullscreen").addEventListener("click", () => callLocalPlayer("enterFullscreen"));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !overlay.classList.contains("hidden")) closePlayer();
});

if ("serviceWorker" in navigator && location.protocol !== "file:") {
  const workerUrl = new URL("../sw.js", ASSET_BASE);
  const workerScope = new URL("../", ASSET_BASE).pathname;
  navigator.serviceWorker.register(workerUrl.href, { scope: workerScope }).catch(() => {});
}

if (projects.length) {
  render();
  statusEl.textContent = UI.offline;
}
initAuth();
loadListing();