export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#39;")
}

export function setText(element, text, { muted = false } = {}) {
  if (!element) {
    return
  }
  element.textContent = text
  element.classList.toggle("muted", muted)
}

export function setHtml(element, html, { muted = false } = {}) {
  if (!element) {
    return
  }
  element.innerHTML = html
  element.classList.toggle("muted", muted)
}

export function renderCards(container, items, emptyMessage, buildCard) {
  if (!Array.isArray(items) || !items.length) {
    setHtml(container, `<p class="muted">${escapeHtml(emptyMessage)}</p>`)
    return
  }

  setHtml(container, items.map(buildCard).join(""))
}

export function parseJsonArray(rawValue, fieldName) {
  const raw = String(rawValue || "").trim()
  if (!raw) {
    return []
  }

  const value = JSON.parse(raw)
  if (!Array.isArray(value)) {
    throw new Error(`${fieldName} 必须是数组。`)
  }
  return value
}
