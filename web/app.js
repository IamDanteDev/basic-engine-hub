"use strict";

/* Basic Engine Hub — standalone browser menu.
 *
 * Listing sources, tried in order:
 *   1. ./api/listing   — the local server (web/serve.py) merges live.
 *   2. ./listing.json  — GitHub Pages build output (web/listing.py),
 *      same-origin static JSON so no CORS is involved.
 * Cards are rendered client-side; clicking one opens the project in a
 * TurboWarp embed overlay. UI copy is Spanish (the desktop app default).
 */

// UI strings.
const UI = {
  loading: "Cargando proyectos…",
  found: (n) => `${n} proyectos encontrados.`,
  filter: (visible, total) => `${visible} de ${total} proyectos encontrados.`,
  loadError:
    "No se pudo cargar la lista de proyectos. Revisa tu conexión e inténtalo de nuevo.",
  playerLoading: "Cargando proyecto…",
  defaultTitle: (id) => `Proyecto ${id}`,
};

const grid = document.getElementById("grid");
const statusEl = document.getElementById("status");
const searchEl = document.getElementById("search");
const refreshBtn = document.getElementById("refresh");
const retryBtn = document.getElementById("retry");
const errorBox = document.getElementById("error");
const errorText = document.getElementById("error-text");
const overlay = document.getElementById("player-overlay");
const playerFrame = document.getElementById("player");
const playerLoading = document.getElementById("player-loading");
const backBtn = document.getElementById("back");

let projects = []; // normalized listing: {id,title,username,creator_id,image,avatar}
let loaded = false; // true once /api/listing succeeded (enables live filtering)

/* ---- Listing -------------------------------------------------------------- */

async function loadListing() {
  refreshBtn.disabled = true;
  errorBox.classList.add("hidden");
  statusEl.textContent = UI.loading;
  try {
    projects = await fetchListingOrFallback();
    loaded = true;
    render();
  } catch {
    loaded = false;
    errorText.textContent = UI.loadError;
    errorBox.classList.remove("hidden");
    statusEl.textContent = "";
  } finally {
    refreshBtn.disabled = false;
  }
}

async function fetchListingOrFallback() {
  for (const source of ["./api/listing", "./listing.json"]) {
    try {
      const response = await fetch(source);
      if (response.ok) {
        const data = await response.json();
        if (Array.isArray(data)) {
          return data;
        }
      }
    } catch {
      // this source failed; try the next one
    }
  }
  throw new Error("no listing source available");
}

/* ---- Rendering ------------------------------------------------------------ */

function matches(project, needle) {
  return (
    !needle ||
    (project.title || "").toLowerCase().includes(needle) ||
    (project.username || "").toLowerCase().includes(needle) ||
    String(project.id).includes(needle)
  );
}

function render() {
  grid.textContent = "";
  const needle = searchEl.value.trim().toLowerCase();
  let visible = 0;
  for (const project of projects) {
    if (!matches(project, needle)) {
      continue;
    }
    grid.appendChild(cardFor(project));
    visible += 1;
  }
  statusEl.textContent = needle
    ? UI.filter(visible, projects.length)
    : UI.found(projects.length);
}

function cardFor(project) {
  const card = document.createElement("button");
  card.type = "button";
  card.className = "card";
  card.title = project.title || UI.defaultTitle(project.id);

  // Hero image: the project thumbnail, or a placeholder surface when missing.
  const hero = document.createElement("span");
  hero.className = "hero";
  if (project.image) {
    const image = document.createElement("img");
    image.className = "hero-img";
    image.alt = "";
    image.loading = "lazy";
    image.src = project.image;
    image.addEventListener("error", () => {
      // Broken thumbnail: fall back to the placeholder and stop retrying.
      image.remove();
      hero.classList.add("hero-empty");
    });
    hero.appendChild(image);
  } else {
    hero.classList.add("hero-empty");
  }

  // Avatar badge overlaid on top of the hero image.
  if (project.avatar) {
    const avatar = document.createElement("img");
    avatar.className = "avatar";
    avatar.alt = "";
    avatar.loading = "lazy";
    avatar.src = project.avatar;
    avatar.addEventListener("error", () => avatar.remove());
    hero.appendChild(avatar);
  }

  const info = document.createElement("span");
  info.className = "info";
  const title = document.createElement("span");
  title.className = "title";
  title.textContent = project.title || UI.defaultTitle(project.id);
  const user = document.createElement("span");
  user.className = "user";
  user.textContent = project.username ? `@${project.username}` : "";
  info.append(title, user);

  card.append(hero, info);
  card.addEventListener("click", () => openPlayer(project));
  return card;
}

/* ---- Player overlay ------------------------------------------------------- */

function openPlayer(project) {
  playerLoading.hidden = false;
  playerFrame.onload = () => {
    playerLoading.hidden = true;
  };
  playerFrame.src = ""; // stop any previously loaded project
  overlay.classList.remove("hidden");
  document.body.classList.add("player-open");
  playerFrame.src = `https://turbowarp.org/embed?project=${encodeURIComponent(
    String(project.id)
  )}&autoplay`;
}

function closePlayer() {
  playerFrame.onload = null;
  playerFrame.src = ""; // unload the iframe so the project stops
  overlay.classList.add("hidden");
  playerLoading.hidden = true;
  document.body.classList.remove("player-open");
}

/* ---- Events ---------------------------------------------------------------- */

searchEl.addEventListener("input", () => {
  if (loaded) {
    render();
  }
});
refreshBtn.addEventListener("click", loadListing);
retryBtn.addEventListener("click", loadListing);
backBtn.addEventListener("click", closePlayer);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !overlay.classList.contains("hidden")) {
    closePlayer();
  }
});

loadListing();