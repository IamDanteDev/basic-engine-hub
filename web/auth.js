"use strict";

/* Basic Engine Hub — Scratch sign-in core (Scratch Auth, custom frontend).
 *
 * Pure helpers with no DOM and no implicit globals, so `node --test tests/`
 * can exercise every rule. web/app.js owns the DOM wiring.
 *
 * Flow (documented at https://auth.itinerary.eu.org/documentation/introduction,
 * real spec in Looky1173/Scratch-Auth-Client src/docs/custom-frontend.mdx):
 *   1. GET {AUTH_API_BASE}/auth/getTokens?method=&redirect=<base64>&authProject=
 *      -> {publicCode, privateCode, redirectLocation, method, authProject}
 *   2. The user enters `publicCode` in AUTH_PROJECT_URL (or comments it).
 *   3. GET {AUTH_API_BASE}/auth/verifyToken/<privateCode>
 *      -> {valid:false} while pending, {valid:true, username, redirect} once done.
 *
 * The base64 `redirect` is percent-encoded on the wire. Raw base64 is not safe:
 * a "+" decodes as a space and silently corrupts the URL (evidence L6 in
 * odd/tasks/scratch-auth.md).
 */

const AUTH_API_BASE = "https://auth-api.itinerary.eu.org";
const AUTH_PROJECT_ID = 1391621033;
const AUTH_PROJECT_URL = `https://scratch.mit.edu/projects/${AUTH_PROJECT_ID}/`;
const AUTH_METHODS = ["cloud", "comment", "profile-comment"];
const AUTH_SESSION_KEY = "basic-engine-hub:sesion:v1";
/* The service's own frontend refreshes tokens every 5 minutes (TOKEN_VALIDITY). */
const AUTH_CODE_TTL_MS = 5 * 60 * 1000;

function isKnownMethod(method) {
  return AUTH_METHODS.includes(String(method));
}

function base64Encode(text) {
  const bytes = new TextEncoder().encode(String(text));
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function base64Decode(text) {
  try {
    const binary = atob(String(text));
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
    return new TextDecoder().decode(bytes);
  } catch {
    return null;
  }
}

/* The page the service has to send the user back to: origin + path, no trailing
 * slash and no query, so the value we send and the value we check are identical. */
function buildCallbackUrl(location) {
  const origin = String(location?.origin || "").replace(/\/+$/, "");
  const path = String(location?.pathname || "/").replace(/\/+$/, "");
  return `${origin}${path}`;
}

function encodeRedirect(url) {
  return base64Encode(url);
}

function buildTokensUrl({ apiBase = AUTH_API_BASE, redirect, method = "cloud", authProject = AUTH_PROJECT_ID, username = "" } = {}) {
  const params = new URLSearchParams();
  params.set("method", isKnownMethod(method) ? method : "cloud");
  params.set("redirect", encodeRedirect(redirect));
  params.set("authProject", String(authProject));
  if (String(method) === "profile-comment" && String(username).trim()) {
    params.set("username", String(username).trim());
  }
  return `${apiBase}/auth/getTokens?${params.toString()}`;
}

function verifyUrl({ apiBase = AUTH_API_BASE, privateCode } = {}) {
  return `${apiBase}/auth/verifyToken/${encodeURIComponent(String(privateCode))}`;
}

function normalizeUrl(value) {
  try {
    const url = new URL(String(value));
    const path = url.pathname.replace(/\/+$/, "");
    return `${url.protocol}//${url.host}${path}${url.search}`;
  } catch {
    return "";
  }
}

/* Anti-phishing check the documentation insists on: the verified identity must
 * belong to the redirect location we asked for.
 *
 * A missing value is accepted (and the caller warns): our privateCode was
 * requested by this very page, so the token is already bound to us, and
 * rejecting an absent field would break every legitimate sign-in. A value that
 * is present and points somewhere else rejects the sign-in. */
function isTrustedRedirect(returned, expected) {
  if (returned === null || returned === undefined || returned === "") return true;
  const target = normalizeUrl(expected);
  if (!target) return false;
  const decoded = base64Decode(returned);
  return [returned, decoded].some((candidate) => candidate && normalizeUrl(candidate) === target);
}

function extractPrivateCode(search) {
  try {
    const value = new URLSearchParams(String(search || "")).get("privateCode");
    return value ? value : null;
  } catch {
    return null;
  }
}

function readSession(storage) {
  try {
    const raw = storage && storage.getItem(AUTH_SESSION_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw);
    if (!value || typeof value !== "object" || Array.isArray(value)) return null;
    const username = typeof value.username === "string" ? value.username.trim() : "";
    if (!username) return null;
    return {
      username,
      method: typeof value.method === "string" ? value.method : "",
      at: Number(value.at) || 0,
    };
  } catch {
    return null;
  }
}

function writeSession(storage, session) {
  const username = String(session?.username || "").trim();
  if (!username) return null;
  const value = { username, method: String(session?.method || ""), at: Number(session?.at) || Date.now() };
  storage.setItem(AUTH_SESSION_KEY, JSON.stringify(value));
  return value;
}

function clearSession(storage) {
  if (storage) storage.removeItem(AUTH_SESSION_KEY);
}

function isOwnProject(projectUsername, sessionUsername) {
  const author = String(projectUsername || "").trim().toLowerCase();
  const viewer = String(sessionUsername || "").trim().toLowerCase();
  return author !== "" && viewer !== "" && author === viewer;
}

/* Scratch usernames are case-insensitive, so compare them that way. */
function authorLabel(username, sessionUsername) {
  const name = String(username || "").trim();
  if (!name) return "";
  return isOwnProject(name, sessionUsername) ? `@${name} (You)` : `@${name}`;
}

async function requestTokens(fetchImpl, { apiBase, redirect, method = "cloud", authProject, username = "" } = {}) {
  if (String(method) === "profile-comment" && !String(username).trim()) {
    throw new Error("profile-comment requires the Scratch username");
  }
  const response = await fetchImpl(buildTokensUrl({ apiBase, redirect, method, authProject, username }));
  if (!response || !response.ok) {
    throw new Error(`getTokens failed with HTTP ${response ? response.status : "?"}`);
  }
  const tokens = await response.json();
  if (!tokens || !tokens.privateCode) throw new Error("getTokens returned no privateCode");
  return tokens;
}

async function verifyCode(fetchImpl, { apiBase, privateCode } = {}) {
  const response = await fetchImpl(verifyUrl({ apiBase, privateCode }));
  /* A pending sign-in answers 403 with {"valid":false}; that is not an error. */
  if (!response || !response.ok) return { valid: false, username: null, redirect: null };
  const data = await response.json();
  const username = data && typeof data.username === "string" ? data.username : "";
  const valid = Boolean(data && data.valid === true && username);
  return {
    valid,
    username: valid ? username : null,
    redirect: data && data.redirect ? data.redirect : null,
  };
}

const AuthCore = {
  AUTH_API_BASE,
  AUTH_PROJECT_ID,
  AUTH_PROJECT_URL,
  AUTH_METHODS,
  AUTH_SESSION_KEY,
  AUTH_CODE_TTL_MS,
  isKnownMethod,
  base64Encode,
  base64Decode,
  buildCallbackUrl,
  encodeRedirect,
  buildTokensUrl,
  verifyUrl,
  isTrustedRedirect,
  extractPrivateCode,
  readSession,
  writeSession,
  clearSession,
  isOwnProject,
  authorLabel,
  requestTokens,
  verifyCode,
};

if (typeof module !== "undefined" && module.exports) module.exports = AuthCore;
