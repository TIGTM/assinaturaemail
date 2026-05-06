/**
 * editor.js — Editor visual de campos de assinatura
 * Permite posicionar campos de texto sobre a imagem base usando drag & drop.
 */

const FIELD_TYPES = [
  { value: "name",       label: "Nome completo" },
  { value: "title",      label: "Cargo" },
  { value: "phone",      label: "Telefone" },
  { value: "email",      label: "E-mail" },
  { value: "department", label: "Departamento" },
  { value: "website",    label: "Website" },
  { value: "instagram",  label: "Instagram" },
  { value: "extra1",     label: "Campo extra 1" },
  { value: "extra2",     label: "Campo extra 2" },
];

const FIELD_COLORS = {
  name:       "#FFFFFF",
  title:      "#CCDDFF",
  phone:      "#FFFFFF",
  email:      "#AADDFF",
  department: "#FFFFFF",
  website:    "#FFFFFF",
  instagram:  "#FFFFFF",
  extra1:     "#FFFFFF",
  extra2:     "#FFFFFF",
};

// ─── Fontes padrão por tipo de campo ─────────────────────────────────────────
// Nome usa CY Grotesk Wide; demais campos usam Montserrat
// Os arquivos .ttf devem estar na pasta /fonts da VPS
const FIELD_FONTS = {
  name:       "CYGroteskWide-Bold.ttf",   // CY Grotesk Wide (negrito)
  title:      "Montserrat-Regular.ttf",
  phone:      "Montserrat-Regular.ttf",
  email:      "Montserrat-Regular.ttf",
  department: "Montserrat-Regular.ttf",
  website:    "Montserrat-Regular.ttf",
  instagram:  "Montserrat-Regular.ttf",
  extra1:     "Montserrat-Regular.ttf",
  extra2:     "Montserrat-Regular.ttf",
};

const FIELD_BOLD = {
  name:       true,
  title:      false,
  phone:      false,
  email:      false,
  department: false,
  website:    false,
  instagram:  false,
  extra1:     false,
  extra2:     false,
};

const PREVIEW_VALUES = {
  name:       "Pablo Baldoni de Assis",
  title:      "Analista de compras",
  phone:      "(31) 9.9982-9763",
  email:      "pablo@gtmalimentos.com.br",
  department: "Compras",
  website:    "www.gtmalimentos.com.br",
  instagram:  "@gtmalimentos",
  extra1:     "Campo extra 1",
  extra2:     "Campo extra 2",
};

// ─── Carregamento dinâmico de fontes ─────────────────────────────────────────

const _loadedFonts = new Set();

function getFontFamily(fontFile) {
  if (!fontFile) return "sans-serif";
  return fontFile.replace(/\.ttf$/i, "").replace(/[^a-zA-Z0-9]/g, "-");
}

function ensureFontLoaded(fontFile) {
  if (!fontFile || _loadedFonts.has(fontFile)) return;
  _loadedFonts.add(fontFile);
  const family = getFontFamily(fontFile);
  const style  = document.createElement("style");
  style.textContent = `@font-face { font-family: "${family}"; src: url("/fonts/${fontFile}") format("truetype"); }`;
  document.head.appendChild(style);
}

// ─── Estado global ────────────────────────────────────────────────────────────

let fields        = [];
let selectedIndex = -1;
let dragging      = false;
let dragOffX      = 0;
let dragOffY      = 0;
let imgEl         = null;
let imgRect       = null;
let canvasScale   = 1;

// ─── Inicialização ────────────────────────────────────────────────────────────

window.addEventListener("DOMContentLoaded", () => {
  imgEl = document.getElementById("base-img");
  loadFieldsFromServer();
  setupCanvasListeners();
  renderFieldList();
});

function loadFieldsFromServer() {
  const layoutId = document.getElementById("layout-id").value;
  fetch(`/api/layout/${layoutId}`)
    .then(r => r.json())
    .then(data => {
      fields = data.fields || [];
      renderAll();
    });
}

// ─── Renderização ─────────────────────────────────────────────────────────────

function renderAll() {
  renderOverlays();
  renderFieldList();
}

function getImgRect() {
  return imgEl.getBoundingClientRect();
}

function getNaturalScale() {
  return imgEl.naturalWidth > 0 ? imgEl.offsetWidth / imgEl.naturalWidth : 1;
}

function renderOverlays() {
  const container = document.getElementById("img-container");
  // Remove overlays antigos
  container.querySelectorAll(".field-overlay").forEach(el => el.remove());

  const scale = getNaturalScale();

  fields.forEach((f, i) => {
    const div = document.createElement("div");
    div.className   = "field-overlay" + (i === selectedIndex ? " selected" : "");
    div.dataset.idx = i;

    const displayX = Math.round(f.x * scale);
    const displayY = Math.round(f.y * scale);

    const fontFile = f.font_file || "";
    ensureFontLoaded(fontFile);

    div.style.left       = displayX + "px";
    div.style.top        = displayY + "px";
    div.style.color      = f.color || "#fff";
    div.style.fontSize   = Math.round((f.font_size || 14) * scale) + "px";
    div.style.fontWeight = f.bold ? "bold" : "normal";
    div.style.fontFamily = fontFile ? `"${getFontFamily(fontFile)}", sans-serif` : "sans-serif";

    const label = FIELD_TYPES.find(t => t.value === f.field_type)?.label || f.field_type;
    const preview = PREVIEW_VALUES[f.field_type] || label;
    div.textContent = (f.prefix || "") + preview + (f.suffix || "");

    div.addEventListener("mousedown", onOverlayMouseDown);
    div.addEventListener("click",     () => selectField(i));

    container.appendChild(div);
  });
}

function renderFieldList() {
  const ul = document.getElementById("field-list");
  ul.innerHTML = "";

  fields.forEach((f, i) => {
    const li = document.createElement("li");
    li.className = "field-item" + (i === selectedIndex ? " active" : "");

    const label = FIELD_TYPES.find(t => t.value === f.field_type)?.label || f.field_type;

    li.innerHTML = `
      <span class="field-label">
        <span class="field-badge">${label}</span>
        <small>${f.x}px, ${f.y}px — ${f.font_size}pt</small>
      </span>
      <div class="field-actions">
        <button onclick="selectField(${i})" title="Editar">✏️</button>
        <button onclick="removeField(${i})" title="Remover">🗑️</button>
      </div>
    `;
    li.addEventListener("click", () => selectField(i));
    ul.appendChild(li);
  });

  if (fields.length === 0) {
    ul.innerHTML = '<li class="empty-msg">Nenhum campo adicionado.</li>';
  }
}

// ─── Seleção / edição ─────────────────────────────────────────────────────────

function selectField(i) {
  selectedIndex = i;
  renderAll();
  fillPanel(fields[i]);
  document.getElementById("edit-panel").style.display = "block";
}

function fillPanel(f) {
  document.getElementById("p-field-type").value  = f.field_type || "name";
  document.getElementById("p-font-size").value   = f.font_size  || 14;
  document.getElementById("p-color").value        = f.color      || "#ffffff";
  document.getElementById("p-bold").checked       = f.bold       || false;
  document.getElementById("p-shadow").checked     = f.shadow     || false;
  document.getElementById("p-align").value        = f.align      || "left";
  document.getElementById("p-prefix").value       = f.prefix     || "";
  document.getElementById("p-suffix").value       = f.suffix     || "";
  document.getElementById("p-x").value            = f.x          || 0;
  document.getElementById("p-y").value            = f.y          || 0;

  const fontFile = f.font_file || "";
  document.getElementById("p-font-file").value = fontFile;

  // Sincroniza o select com o valor atual
  const sel = document.getElementById("p-font-select");
  const found = Array.from(sel.options).some(o => {
    if (o.value === fontFile) { sel.value = fontFile; return true; }
    return false;
  });
  if (!found) sel.value = "custom";
}

function onFontSelect() {
  const sel = document.getElementById("p-font-select");
  if (sel.value !== "custom") {
    document.getElementById("p-font-file").value = sel.value;
    applyPanel();
  }
}

function applyPanel() {
  if (selectedIndex < 0 || selectedIndex >= fields.length) return;
  const f = fields[selectedIndex];
  f.field_type = document.getElementById("p-field-type").value;
  f.font_size  = parseInt(document.getElementById("p-font-size").value) || 14;
  f.color      = document.getElementById("p-color").value;
  f.bold       = document.getElementById("p-bold").checked;
  f.shadow     = document.getElementById("p-shadow").checked;
  f.align      = document.getElementById("p-align").value;
  f.prefix     = document.getElementById("p-prefix").value;
  f.suffix     = document.getElementById("p-suffix").value;
  f.x          = parseInt(document.getElementById("p-x").value) || 0;
  f.y          = parseInt(document.getElementById("p-y").value) || 0;
  f.font_file  = document.getElementById("p-font-file").value.trim();
  renderAll();
}

// ─── Adicionar / remover campos ───────────────────────────────────────────────

function addField() {
  const type = document.getElementById("add-field-type").value;
  const newField = {
    field_type: type,
    x:          50,
    y:          50,
    font_size:  type === "name" ? 18 : 14,
    color:      FIELD_COLORS[type] || "#ffffff",
    bold:       FIELD_BOLD[type] || false,
    shadow:     false,
    align:      "left",
    prefix:     "",
    suffix:     "",
    font_file:  FIELD_FONTS[type] || "Montserrat-Regular.ttf",
    visible:    true,
  };
  fields.push(newField);
  selectedIndex = fields.length - 1;
  renderAll();
  fillPanel(newField);
  document.getElementById("edit-panel").style.display = "block";
}

function removeField(i) {
  fields.splice(i, 1);
  if (selectedIndex >= fields.length) selectedIndex = fields.length - 1;
  renderAll();
  if (fields.length === 0) {
    document.getElementById("edit-panel").style.display = "none";
  }
}

// ─── Drag & Drop ──────────────────────────────────────────────────────────────

function setupCanvasListeners() {
  document.addEventListener("mousemove", onMouseMove);
  document.addEventListener("mouseup",   onMouseUp);

  // Click na imagem → posicionar campo selecionado
  document.getElementById("img-container").addEventListener("click", onContainerClick);
}

function onOverlayMouseDown(e) {
  e.stopPropagation();
  const i     = parseInt(e.currentTarget.dataset.idx);
  selectField(i);
  dragging  = true;
  imgRect   = document.getElementById("img-container").getBoundingClientRect();
  const scale = getNaturalScale();
  dragOffX  = e.clientX - imgRect.left - fields[i].x * scale;
  dragOffY  = e.clientY - imgRect.top  - fields[i].y * scale;
}

function onMouseMove(e) {
  if (!dragging || selectedIndex < 0) return;
  imgRect = document.getElementById("img-container").getBoundingClientRect();
  const scale = getNaturalScale();
  let nx = (e.clientX - imgRect.left - dragOffX) / scale;
  let ny = (e.clientY - imgRect.top  - dragOffY) / scale;
  // Limita dentro da imagem
  nx = Math.max(0, Math.min(nx, imgEl.naturalWidth));
  ny = Math.max(0, Math.min(ny, imgEl.naturalHeight));
  fields[selectedIndex].x = Math.round(nx);
  fields[selectedIndex].y = Math.round(ny);
  document.getElementById("p-x").value = fields[selectedIndex].x;
  document.getElementById("p-y").value = fields[selectedIndex].y;
  renderOverlays();
}

function onMouseUp() {
  dragging = false;
}

function onContainerClick(e) {
  if (dragging) return;
  if (e.target.classList.contains("field-overlay")) return;
  if (selectedIndex < 0) return;
  imgRect = document.getElementById("img-container").getBoundingClientRect();
  const scale = getNaturalScale();
  const nx = Math.round((e.clientX - imgRect.left) / scale);
  const ny = Math.round((e.clientY - imgRect.top)  / scale);
  fields[selectedIndex].x = nx;
  fields[selectedIndex].y = ny;
  document.getElementById("p-x").value = nx;
  document.getElementById("p-y").value = ny;
  renderOverlays();
}

// ─── Salvar ───────────────────────────────────────────────────────────────────

function saveLayout() {
  const layoutId = document.getElementById("layout-id").value;
  const btn = document.getElementById("btn-save");
  btn.disabled  = true;
  btn.textContent = "Salvando…";

  fetch(`/api/layout/${layoutId}/save`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ fields }),
  })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        showToast("Layout salvo com sucesso!", "success");
      } else {
        showToast("Erro ao salvar layout.", "error");
      }
    })
    .catch(() => showToast("Erro de conexão.", "error"))
    .finally(() => {
      btn.disabled    = false;
      btn.textContent = "💾 Salvar layout";
    });
}

// ─── Utilidades ───────────────────────────────────────────────────────────────

function showToast(msg, type = "success") {
  const t = document.getElementById("toast");
  t.textContent  = msg;
  t.className    = "toast show " + type;
  setTimeout(() => t.classList.remove("show"), 3000);
}
