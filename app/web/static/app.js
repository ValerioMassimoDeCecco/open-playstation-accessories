/**
 * PlayStation Accessories - Pure Hardware Client
 * Zero simulation, zero demo mode.
 * Reflects real physical DualSense & DualSense Edge hardware.
 */

let allProfiles = [];
let currentProfile = null;
let currentActiveSlot = "slot_1";
let isHardwareConnected = false;

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initCurveCanvas();
  loadProfiles();
  startStatusPolling();
  startInputPolling();
});

/* ==========================================================================
   Tab Navigation
   ========================================================================== */
function initTabs() {
  const tabs = document.querySelectorAll(".nav-btn");
  tabs.forEach(btn => {
    btn.addEventListener("click", () => {
      tabs.forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));

      btn.classList.add("active");
      const target = document.getElementById(btn.dataset.tab);
      if (target) {
        target.classList.add("active");
        if (btn.dataset.tab === "tab-profiles") {
          renderCurveGraph();
        }
      }
    });
  });
}

/* ==========================================================================
   Real-Time Hardware Status Polling
   ========================================================================== */
function startStatusPolling() {
  const update = async () => {
    try {
      const res = await fetch("/api/status");
      if (res.ok) {
        const data = await res.json();
        updateStatusUI(data);
      }
    } catch (e) {
      console.warn("Status poll error", e);
    }
  };
  update();
  setInterval(update, 1000);
}

function updateStatusUI(data) {
  const modelNameEl = document.getElementById("modelName");
  const statusDot = document.getElementById("statusDot");
  const batteryLevel = document.getElementById("batteryLevel");
  const batteryIcon = document.getElementById("batteryIcon");
  const connTypeBadge = document.getElementById("connTypeBadge");
  const diagModel = document.getElementById("diagModel");
  const diagPid = document.getElementById("diagPid");
  const diagConnStatus = document.getElementById("diagConnStatus");
  const disconnectedBanner = document.getElementById("disconnectedBanner");

  isHardwareConnected = data.connected || false;

  if (isHardwareConnected) {
    disconnectedBanner.style.display = "none";
    modelNameEl.textContent = data.model;
    statusDot.className = "status-dot online";

    // Battery
    const b = data.battery || {};
    batteryLevel.textContent = `${b.level || 0}%`;
    batteryIcon.textContent = b.charging ? "⚡" : "🔋";

    // Connection badge
    const connType = data.is_bluetooth ? "Bluetooth" : "USB";
    connTypeBadge.textContent = connType;
    connTypeBadge.className = "badge badge-online";

    // Diagnostics
    diagConnStatus.textContent = `Connesso (${connType})`;
    diagModel.textContent = data.model;
    diagPid.textContent = data.is_edge ? "0x0DF2 (DualSense Edge)" : "0x0CE6 (DualSense)";

    // Update real lightbar color on SVG
    if (data.lightbar) {
      const lb = data.lightbar;
      const rgbStr = `rgb(${lb.r}, ${lb.g}, ${lb.b})`;
      const svgLb = document.getElementById("svgLightbar");
      if (svgLb) {
        svgLb.style.fill = rgbStr;
        svgLb.style.filter = `drop-shadow(0 0 14px ${rgbStr})`;
        const glowPaths = svgLb.querySelectorAll("path");
        glowPaths.forEach((p) => { p.style.fill = rgbStr; });
      }
    }
  } else {
    // Controller disconnected
    disconnectedBanner.style.display = "flex";
    modelNameEl.textContent = "In attesa di controller DualSense...";
    statusDot.className = "status-dot offline";
    batteryLevel.textContent = "--%";
    batteryIcon.textContent = "🔋";
    connTypeBadge.textContent = "Disconnesso";
    connTypeBadge.className = "badge";

    diagConnStatus.textContent = "Non rilevato";
    diagModel.textContent = "Nessuna periferica";
    diagPid.textContent = "--";

    const svgLb = document.getElementById("svgLightbar");
    if (svgLb) {
      svgLb.style.fill = "#1a2430";
      svgLb.style.filter = "none";
    }
  }
}

/* ==========================================================================
   Real-Time Hardware Input Polling
   ========================================================================== */
function startInputPolling() {
  const poll = async () => {
    try {
      const res = await fetch("/api/inputs");
      if (res.ok) {
        const data = await res.json();
        renderInputs(data);
      }
    } catch (e) {
      // ignore transient drops
    }
    requestAnimationFrame(poll);
  };
  requestAnimationFrame(poll);
}

function renderInputs(data) {
  if (!data || !data.sticks) return;

  const sticks = data.sticks;
  const triggers = data.triggers || {};
  const buttons = data.buttons || {};

  const lx = sticks.left?.norm_x || 0;
  const ly = sticks.left?.norm_y || 0;
  const rx = sticks.right?.norm_x || 0;
  const ry = sticks.right?.norm_y || 0;

  // 1. Thumbsticks SVG transform
  const stickL = document.getElementById("svgStickLeft");
  const stickR = document.getElementById("svgStickRight");
  if (stickL) stickL.style.transform = `translate(${lx * 26}px, ${-ly * 26}px)`;
  if (stickR) stickR.style.transform = `translate(${rx * 26}px, ${-ry * 26}px)`;

  // 2. Sticks Canvas Radars
  drawStickRadar("canvasLeftStick", lx, ly, currentProfile?.left_stick?.deadzone || 2);
  drawStickRadar("canvasRightStick", rx, ry, currentProfile?.right_stick?.deadzone || 2);

  document.getElementById("lStickCoords").textContent = `X: ${lx.toFixed(2)} | Y: ${ly.toFixed(2)}`;
  document.getElementById("rStickCoords").textContent = `X: ${rx.toFixed(2)} | Y: ${ry.toFixed(2)}`;

  // 3. Triggers
  const l2 = triggers.l2_norm || 0;
  const r2 = triggers.r2_norm || 0;
  document.getElementById("l2Val").textContent = `${Math.round(l2 * 100)}%`;
  document.getElementById("r2Val").textContent = `${Math.round(r2 * 100)}%`;
  document.getElementById("l2Fill").style.width = `${l2 * 100}%`;
  document.getElementById("r2Fill").style.width = `${r2 * 100}%`;

  // 4. Digital Buttons Highlight in SVG
  const btnMap = {
    "btn_dpad_up": buttons.dpad_up,
    "btn_dpad_down": buttons.dpad_down,
    "btn_dpad_left": buttons.dpad_left,
    "btn_dpad_right": buttons.dpad_right,
    "btn_cross": buttons.cross,
    "btn_circle": buttons.circle,
    "btn_square": buttons.square,
    "btn_triangle": buttons.triangle,
    "btn_l1": buttons.l1,
    "btn_r1": buttons.r1,
    "btn_create": buttons.create,
    "btn_options": buttons.options,
    "btn_ps": buttons.ps,
    "btn_mute": buttons.mute,
    "btn_back_left": buttons.back_left,
    "btn_back_right": buttons.back_right
  };

  for (const [id, isPressed] of Object.entries(btnMap)) {
    const el = document.getElementById(id);
    if (el) el.classList.toggle("pressed", Boolean(isPressed));
  }
}

function drawStickRadar(canvasId, normX, normY, deadzonePct) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  const cx = w / 2;
  const cy = h / 2;
  const radius = w * 0.42;

  ctx.clearRect(0, 0, w, h);

  // Outer circle boundary
  ctx.beginPath();
  ctx.arc(cx, cy, radius, 0, Math.PI * 2);
  ctx.fillStyle = "#101520";
  ctx.fill();
  ctx.strokeStyle = "#253046";
  ctx.lineWidth = 2;
  ctx.stroke();

  // Deadzone inner circle
  const dzRadius = radius * (deadzonePct / 100.0);
  ctx.beginPath();
  ctx.arc(cx, cy, Math.max(3, dzRadius), 0, Math.PI * 2);
  ctx.fillStyle = "rgba(255, 51, 68, 0.12)";
  ctx.fill();
  ctx.strokeStyle = "rgba(255, 51, 68, 0.4)";
  ctx.lineWidth = 1;
  ctx.stroke();

  // Crosshairs
  ctx.beginPath();
  ctx.moveTo(cx, cy - radius);
  ctx.lineTo(cx, cy + radius);
  ctx.moveTo(cx - radius, cy);
  ctx.lineTo(cx + radius, cy);
  ctx.strokeStyle = "#1b2434";
  ctx.stroke();

  // Stick position dot (only if connected or off-center)
  if (isHardwareConnected || Math.abs(normX) > 0.01 || Math.abs(normY) > 0.01) {
    const dotX = cx + normX * radius;
    const dotY = cy - normY * radius;

    ctx.beginPath();
    ctx.arc(dotX, dotY, 6, 0, Math.PI * 2);
    ctx.fillStyle = "#00f0ff";
    ctx.shadowColor = "#00f0ff";
    ctx.shadowBlur = 10;
    ctx.fill();
    ctx.shadowBlur = 0;
  }
}

/* ==========================================================================
   Profile Management & Mathematical Curves
   ========================================================================== */
async function loadProfiles() {
  try {
    const res = await fetch("/api/profiles");
    if (!res.ok) return;
    const data = await res.json();
    allProfiles = data.profiles || [];
    currentActiveSlot = data.active_slot || "slot_1";

    renderProfilesList();
    renderSlots(data.slots || {});

    if (!currentProfile && allProfiles.length > 0) {
      const activePid = data.slots?.[currentActiveSlot] || allProfiles[0].id;
      selectProfile(activePid);
    }
  } catch (e) {
    console.error("Failed to load profiles", e);
  }
}

function renderProfilesList() {
  const container = document.getElementById("profilesList");
  container.innerHTML = "";

  allProfiles.forEach(p => {
    const item = document.createElement("div");
    item.className = `profile-item ${currentProfile?.id === p.id ? 'active' : ''}`;
    item.onclick = () => selectProfile(p.id);

    item.innerHTML = `
      <div class="profile-item-title">${p.name}</div>
      <div class="profile-item-curve">Curva: ${p.curve_type || 'Linear'}</div>
    `;
    container.appendChild(item);
  });
}

function selectProfile(profileId) {
  const prof = allProfiles.find(p => p.id === profileId);
  if (!prof) return;

  currentProfile = JSON.parse(JSON.stringify(prof));

  document.getElementById("profNameInput").value = currentProfile.name;
  document.getElementById("profDesc").textContent = currentProfile.description || "Nessuna descrizione";

  const cType = currentProfile.curve_type || "Linear";
  document.querySelectorAll(".curve-btn").forEach(b => {
    b.classList.toggle("active", b.dataset.curve === cType);
  });

  document.getElementById("stickDeadzoneSlider").value = currentProfile.left_stick?.deadzone || 2;
  document.getElementById("stickAntiDeadzoneSlider").value = currentProfile.left_stick?.anti_deadzone || 0;
  document.getElementById("l2ThresholdSlider").value = currentProfile.triggers?.l2_threshold || 100;
  document.getElementById("r2ThresholdSlider").value = currentProfile.triggers?.r2_threshold || 100;
  document.getElementById("vibIntensitySlider").value = currentProfile.vibration_intensity ?? 100;
  document.getElementById("trigIntensitySlider").value = currentProfile.trigger_effect_intensity ?? 100;

  document.getElementById("mapBackLeft").value = currentProfile.button_mappings?.back_left || "cross";
  document.getElementById("mapBackRight").value = currentProfile.button_mappings?.back_right || "square";

  updateSliderLabels();
  renderProfilesList();
  renderCurveGraph();
}

function updateSliderLabels() {
  document.getElementById("stickDeadzoneVal").textContent = `${document.getElementById("stickDeadzoneSlider").value}%`;
  document.getElementById("stickAntiDeadzoneVal").textContent = `${document.getElementById("stickAntiDeadzoneSlider").value}%`;
  document.getElementById("l2ThresholdVal").textContent = `${document.getElementById("l2ThresholdSlider").value}%`;
  document.getElementById("r2ThresholdVal").textContent = `${document.getElementById("r2ThresholdSlider").value}%`;
  document.getElementById("vibIntensityVal").textContent = `${document.getElementById("vibIntensitySlider").value}%`;
  document.getElementById("trigIntensityVal").textContent = `${document.getElementById("trigIntensitySlider").value}%`;
}

function updateProfileSliders() {
  if (!currentProfile) return;
  updateSliderLabels();

  currentProfile.left_stick.deadzone = parseInt(document.getElementById("stickDeadzoneSlider").value);
  currentProfile.right_stick.deadzone = currentProfile.left_stick.deadzone;
  currentProfile.left_stick.anti_deadzone = parseInt(document.getElementById("stickAntiDeadzoneSlider").value);

  currentProfile.triggers.l2_threshold = parseInt(document.getElementById("l2ThresholdSlider").value);
  currentProfile.triggers.r2_threshold = parseInt(document.getElementById("r2ThresholdSlider").value);

  currentProfile.vibration_intensity = parseInt(document.getElementById("vibIntensitySlider").value);
  currentProfile.trigger_effect_intensity = parseInt(document.getElementById("trigIntensitySlider").value);

  currentProfile.button_mappings = {
    back_left: document.getElementById("mapBackLeft").value,
    back_right: document.getElementById("mapBackRight").value
  };

  renderCurveGraph();
}

function selectCurve(curveName) {
  if (!currentProfile) return;
  currentProfile.curve_type = curveName;
  currentProfile.left_stick.curve = curveName;
  currentProfile.right_stick.curve = curveName;

  document.querySelectorAll(".curve-btn").forEach(b => {
    b.classList.toggle("active", b.dataset.curve === curveName);
  });

  renderCurveGraph();
}

const CURVE_DESCRIPTIONS = {
  "Linear": {
    title: "Predefinito (Lineare)",
    desc: "Rapporto 1:1 identico tra l'inclinazione fisica della levetta e il movimento generato in-game."
  },
  "Quick": {
    title: "Rapido (Quick Ramp)",
    desc: "Accelerazione iniziale accentuata per mirare e voltarsi rapidamente. Ideale per giochi sparatutto frenetici."
  },
  "Precise": {
    title: "Preciso (Slow Curve)",
    desc: "Sensibilità minima sui piccoli movimenti. Permette micro-aggiustamenti chirurgici per mirare da lontano."
  },
  "Steady": {
    title: "Costante (Steady)",
    desc: "Riduce leggermente la velocità a metà corsa della levetta per mantenere traiettorie stabili."
  },
  "Digital": {
    title: "Digitale (Instant Trigger)",
    desc: "Raggiunge subito il 100% dell'output appena si supera la zona morta. Ideale per picchiaduro e controlli D-pad."
  },
  "Dynamic": {
    title: "Dinamico (S-Curve)",
    desc: "Fine e delicato al centro, progressivo a media distanza ed estremamente reattivo alle estremità."
  }
};

function initCurveCanvas() {
  const canvas = document.getElementById("curveCanvas");
  if (!canvas) return;
  renderCurveGraph();
}

function computeCurveY(x, curveType, deadzonePct) {
  const dz = deadzonePct / 100.0;
  if (x <= dz) return 0.0;
  const effX = (x - dz) / (1.0 - dz);

  switch (curveType) {
    case "Quick":
      return Math.pow(effX, 0.45);
    case "Precise":
      return Math.pow(effX, 2.2);
    case "Steady":
      return 0.5 * effX + 0.5 * Math.pow(effX, 1.8);
    case "Digital":
      return 1.0;
    case "Dynamic":
      return (1.0 / (1.0 + Math.exp(-8.0 * (effX - 0.5)))) * 1.02 - 0.01;
    case "Linear":
    default:
      return effX;
  }
}

function renderCurveGraph() {
  const canvas = document.getElementById("curveCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  const pad = 30;

  const curveType = currentProfile?.curve_type || "Linear";
  const deadzone = currentProfile?.left_stick?.deadzone || 2;

  const meta = CURVE_DESCRIPTIONS[curveType] || CURVE_DESCRIPTIONS["Linear"];
  document.getElementById("curveMetaTitle").textContent = meta.title;
  document.getElementById("curveMetaDesc").textContent = meta.desc;

  ctx.clearRect(0, 0, w, h);

  ctx.fillStyle = "#0c1018";
  ctx.fillRect(pad, pad, w - pad * 2, h - pad * 2);

  ctx.strokeStyle = "#1b2536";
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let i = 1; i <= 3; i++) {
    const x = pad + (i / 4) * (w - pad * 2);
    const y = pad + (i / 4) * (h - pad * 2);
    ctx.moveTo(x, pad);
    ctx.lineTo(x, h - pad);
    ctx.moveTo(pad, y);
    ctx.lineTo(w - pad, y);
  }
  ctx.stroke();

  const dzWidth = (deadzone / 100.0) * (w - pad * 2);
  ctx.fillStyle = "rgba(255, 51, 68, 0.15)";
  ctx.fillRect(pad, pad, dzWidth, h - pad * 2);

  ctx.fillStyle = "#6b7c96";
  ctx.font = "11px Inter, sans-serif";
  ctx.fillText("0%", pad - 4, h - pad + 16);
  ctx.fillText("100% (Inclinazione fisica)", w - pad - 60, h - pad + 16);
  ctx.fillText("100% (Output)", pad - 26, pad - 8);

  ctx.beginPath();
  ctx.strokeStyle = "#00f0ff";
  ctx.lineWidth = 3;
  ctx.shadowColor = "#00f0ff";
  ctx.shadowBlur = 10;

  const plotW = w - pad * 2;
  const plotH = h - pad * 2;

  for (let px = 0; px <= plotW; px++) {
    const normX = px / plotW;
    const normY = computeCurveY(normX, curveType, deadzone);
    const clampedY = Math.max(0.0, Math.min(1.0, normY));

    const canvasX = pad + px;
    const canvasY = h - pad - clampedY * plotH;

    if (px === 0) {
      ctx.moveTo(canvasX, canvasY);
    } else {
      ctx.lineTo(canvasX, canvasY);
    }
  }
  ctx.stroke();
  ctx.shadowBlur = 0;
}

async function saveCurrentProfile() {
  if (!currentProfile) return;
  currentProfile.name = document.getElementById("profNameInput").value;

  try {
    const res = await fetch("/api/profiles/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentProfile)
    });

    if (res.ok) {
      const resp = await res.json();
      currentProfile = resp.profile;
      await loadProfiles();
      alert("Profilo salvato con successo!");
    }
  } catch (e) {
    alert("Errore durante il salvataggio");
  }
}

function createNewProfile() {
  const newId = `custom_${Date.now()}`;
  const newP = {
    id: newId,
    name: "Nuovo Profilo Personalizzato",
    description: "Configurato dall'utente",
    curve_type: "Linear",
    left_stick: { curve: "Linear", deadzone: 2, anti_deadzone: 0, max_threshold: 100 },
    right_stick: { curve: "Linear", deadzone: 2, anti_deadzone: 0, max_threshold: 100 },
    triggers: { l2_deadzone: 0, l2_threshold: 100, r2_deadzone: 0, r2_threshold: 100 },
    vibration_intensity: 100,
    trigger_effect_intensity: 100,
    lightbar: { r: 0, g: 112, b: 240 },
    button_mappings: { back_left: "cross", back_right: "square" }
  };
  allProfiles.push(newP);
  selectProfile(newId);
}

/* ==========================================================================
   Slot Assignments (Fn Shortcuts)
   ========================================================================== */
function renderSlots(slots) {
  const slotKeys = ["slot_1", "slot_2", "slot_3", "slot_4"];
  slotKeys.forEach((key, idx) => {
    const num = idx + 1;
    const pid = slots[key];
    const prof = allProfiles.find(p => p.id === pid) || { name: "Non assegnato", description: "-" };

    const titleEl = document.getElementById(`slotProfile_${num}`);
    const descEl = document.getElementById(`slotDesc_${num}`);
    const cardEl = document.getElementById(`slotCard_${num}`);
    const selectEl = document.getElementById(`slotSelector_${num}`);

    if (titleEl) titleEl.textContent = prof.name;
    if (descEl) descEl.textContent = prof.description;
    if (cardEl) cardEl.classList.toggle("active", currentActiveSlot === key);

    if (selectEl) {
      selectEl.innerHTML = "";
      allProfiles.forEach(p => {
        const opt = document.createElement("option");
        opt.value = p.id;
        opt.textContent = p.name;
        opt.selected = (p.id === pid);
        selectEl.appendChild(opt);
      });
    }
  });
}

async function assignSlot(slotKey, profileId) {
  try {
    await fetch("/api/slots/assign", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slot: slotKey, profile_id: profileId })
    });
    loadProfiles();
  } catch (e) {
    console.error("Assign slot error", e);
  }
}

async function selectSlot(slotKey) {
  try {
    const res = await fetch("/api/slots/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slot: slotKey })
    });
    if (res.ok) {
      const data = await res.json();
      currentActiveSlot = slotKey;
      renderSlots(data.slots || {});
    }
  } catch (e) {
    console.error("Select slot error", e);
  }
}

/* ==========================================================================
   Lightbar & Hardware Controls
   ========================================================================== */
async function setPresetColor(r, g, b) {
  try {
    await fetch("/api/lightbar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ r, g, b })
    });
    const hex = rgbToHex(r, g, b);
    document.getElementById("lightbarColorInput").value = hex;
    document.getElementById("colorPreviewBlock").style.backgroundColor = hex;
  } catch (e) {
    console.error("Lightbar error", e);
  }
}

function applyCustomColor(hex) {
  const rgb = hexToRgb(hex);
  if (rgb) {
    setPresetColor(rgb.r, rgb.g, rgb.b);
  }
}

async function setPlayerLed(playerNum) {
  try {
    await fetch("/api/player_led", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_num: playerNum })
    });
  } catch (e) {
    console.error("Player led error", e);
  }
}

async function testRumble(left, right, duration) {
  try {
    await fetch("/api/rumble", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ left, right, duration })
    });
  } catch (e) {
    console.error("Rumble error", e);
  }
}

function hexToRgb(hex) {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result ? {
    r: parseInt(result[1], 16),
    g: parseInt(result[2], 16),
    b: parseInt(result[3], 16)
  } : null;
}

function rgbToHex(r, g, b) {
  return "#" + (1 << 24 | r << 16 | g << 8 | b).toString(16).slice(1);
}
