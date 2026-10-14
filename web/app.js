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
const UI = {
  loading: "Cargando proyectos…",
  found: (n) => `${n} proyectos encontrados.`,
  filter: (visible, total) => `${visible} de ${total} proyectos encontrados.`,
  offline: "Mostrando el último listado guardado sin conexión.",
  loadError: "No se pudo cargar la lista de proyectos. Revisa tu conexión e inténtalo de nuevo.",
  playerLoading: "Cargando proyecto…",
  detailsUnavailable: "Los detalles ampliados necesitan conexión o el servidor web local.",
  commentsUnavailable: "Los comentarios no están disponibles ahora.",
  noComments: "Sin comentarios todavía.",
  favoriteAdd: "Añadir a favoritos",
  favoriteRemove: "Quitar de favoritos",
  defaultTitle: (id) => `Proyecto ${id}`,
  featuredBadge: "★ Destacado",
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
    statusEl.textContent = "No se pudo guardar este cambio en el navegador.";
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
  favoritesFilter.textContent = `Favoritos (${favorites.size})`;
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
  if (project.image) {
    const image = document.createElement("img");
    image.className = "hero-img";
    image.alt = "";
    image.loading = "lazy";
    image.src = project.image;
    image.addEventListener("error", () => {
      image.remove();
      hero.classList.add("hero-empty");
    });
    hero.appendChild(image);
  } else {
    hero.classList.add("hero-empty");
  }
  if (project.avatar) {
    const avatar = document.createElement("img");
    avatar.className = "avatar";
    avatar.alt = "";
    avatar.loading = "lazy";
    avatar.src = project.avatar;
    avatar.addEventListener("error", () => avatar.remove());
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
  user.textContent = project.username ? `@${project.username}` : "";
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
  const id = String(project.id);
  document.getElementById("detail-title").textContent = project.title || UI.defaultTitle(id);
  const author = document.getElementById("detail-author");
  author.textContent = project.username ? `@${project.username}` : "";
  author.href = project.username
    ? `https://scratch.mit.edu/users/${encodeURIComponent(project.username)}/`
    : `https://scratch.mit.edu/projects/${encodeURIComponent(id)}/`;
  const cover = document.getElementById("detail-cover");
  cover.hidden = !project.image;
  cover.src = project.image || "";
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
    showDetailText("detail-description", detail.description, "Sin descripción.");
    showDetailText("detail-instructions", detail.instructions, "Sin instrucciones.");
  }
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
      statusEl.textContent = "Proyecto cargado; el navegador no pudo guardarlo en IndexedDB.";
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
      if (typeof load !== "function") throw new Error("No se pudo iniciar el reproductor local.");
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

function openVariables() {
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
    keep.setAttribute("aria-label", `Guardar ${variable.name}`);
    keep.addEventListener("change", () => {
      if (keep.checked) saved.add(String(variable.id));
      else saved.delete(String(variable.id));
      saveSelectedIds(currentPlayerId, [...saved]);
    });
    keepCell.appendChild(keep);
    const kindCell = document.createElement("td");
    kindCell.textContent = variable.kind === "list" ? "Lista" : "Variable";
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
    edit.textContent = "Editar";
    edit.addEventListener("click", () => editVariable(variable, valueCell));
    editCell.appendChild(edit);
    row.append(keepCell, kindCell, nameCell, targetCell, valueCell, editCell);
    body.appendChild(row);
  }
  variablesDialog.showModal();
}

function editVariable(variable, valueCell) {
  const current = variable.kind === "list" ? JSON.stringify(variable.value) : String(variable.value);
  editingVariable = { variable, valueCell };
  document.getElementById("edit-variable-title").textContent = `Editar ${variable.kind === "list" ? "lista" : "variable"}`;
  document.getElementById("edit-variable-label").textContent = variable.name || "Valor";
  const input = document.getElementById("edit-variable-input");
  input.value = current;
  editVariableDialog.showModal();
  input.focus();
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
  event.currentTarget.textContent = isPaused ? "Reanudar" : "Pausar";
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
loadListing();