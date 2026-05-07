#!/usr/bin/env python3
"""
MindfulNest Close-Up Cropper Builder
=====================================
Generates a self-contained HTML cropping tool with a preloaded image.
Kim opens the HTML, draws crop boxes, names them, and saves PNGs directly.

USAGE (CLI):
    python3 build_cropper.py --image /path/to/image.png --output cropper.html
    python3 build_cropper.py --image /path/to/image.png --title "Shot 6 Master" --output cropper.html

USAGE (Python):
    from build_cropper import build_cropper
    build_cropper("/path/to/image.png", "cropper.html", title="Shot 6 Master")
"""

import argparse
import base64
import json
import os
import sys
import re
from pathlib import Path
from datetime import datetime, timezone
try:
    import requests
except ImportError:
    requests = None


# ─── HTML TEMPLATE ──────────────────────────────────────────────────────────

CROPPER_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>MindfulNest — Close-Up Cropper{{TITLE_SUFFIX}}</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #1a1a2e; color: #e0e0e0; }

  .header { padding: 16px 24px; background: #16213e; border-bottom: 1px solid #0f3460; display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
  .header h1 { font-size: 18px; color: #e94560; }
  .header .subtitle { font-size: 13px; color: #888; }

  .toolbar { padding: 12px 24px; background: #1a1a2e; border-bottom: 1px solid #333; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .toolbar label { font-size: 13px; color: #aaa; }
  .toolbar input[type="file"] { font-size: 13px; }
  .toolbar button { padding: 6px 14px; border: 1px solid #0f3460; background: #16213e; color: #e0e0e0; border-radius: 4px; cursor: pointer; font-size: 13px; }
  .toolbar button:hover { background: #0f3460; }
  .toolbar button.primary { background: #e94560; border-color: #e94560; color: #fff; font-weight: 600; }
  .toolbar button.primary:hover { background: #c73550; }
  .toolbar button:disabled { opacity: 0.4; cursor: default; }
  .toolbar .sep { width: 1px; height: 24px; background: #333; }

  .size-enforcement-banner { padding: 8px 12px; border-radius: 4px; font-size: 13px; font-weight: 600; display: flex; align-items: center; gap: 8px; margin: 0 12px; }
  .size-enforcement-banner.warning { background: #ffeb3b; color: #000; }
  .size-enforcement-banner.ready { background: #4caf50; color: #fff; }
  .size-enforcement-banner.info { background: #2196f3; color: #fff; }
  .dimensions-display { padding: 6px 10px; background: #16213e; border: 1px solid #0f3460; border-radius: 4px; font-size: 13px; color: #e0e0e0; font-family: monospace; }
  .dimensions-display.warning { border-color: #ffeb3b; color: #ffeb3b; }
  .dimensions-display.ready { border-color: #4caf50; color: #4caf50; }

  .main { display: flex; height: calc(100vh - 110px); }

  .canvas-area { flex: 1; position: relative; overflow: auto; background: #111; display: flex; align-items: center; justify-content: center; }
  .canvas-area canvas { cursor: crosshair; }

  .sidebar { width: 300px; background: #16213e; border-left: 1px solid #0f3460; padding: 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 16px; }
  .sidebar h3 { font-size: 14px; color: #e94560; border-bottom: 1px solid #333; padding-bottom: 6px; }
  .sidebar .field { display: flex; align-items: center; gap: 8px; margin: 4px 0; }
  .sidebar .field label { font-size: 12px; color: #aaa; width: 60px; flex-shrink: 0; }
  .sidebar .field input { width: 70px; padding: 4px 6px; background: #1a1a2e; border: 1px solid #333; color: #e0e0e0; border-radius: 3px; font-size: 12px; text-align: right; }
  .sidebar .field span { font-size: 12px; color: #666; }

  .preview-box { background: #111; border: 1px solid #333; border-radius: 4px; min-height: 180px; display: flex; align-items: center; justify-content: center; overflow: hidden; }
  .preview-box img { max-width: 100%; max-height: 260px; object-fit: contain; }
  .preview-box .placeholder { color: #555; font-size: 12px; }

  .crop-list { flex: 1; overflow-y: auto; }
  .crop-item { background: #1a1a2e; border: 1px solid #333; border-radius: 4px; padding: 8px; margin-bottom: 8px; cursor: pointer; }
  .crop-item:hover { border-color: #e94560; }
  .crop-item.active { border-color: #e94560; background: #1f1f3a; }
  .crop-item .ci-header { display: flex; justify-content: space-between; align-items: center; }
  .crop-item .ci-name { font-size: 13px; font-weight: 600; }
  .crop-item .ci-dims { font-size: 11px; color: #888; }
  .crop-item .ci-thumb { margin-top: 6px; max-height: 80px; border-radius: 2px; }
  .crop-item .ci-actions { margin-top: 6px; display: flex; gap: 6px; }
  .crop-item .ci-actions button { font-size: 11px; padding: 2px 8px; }

  .info-bar { padding: 6px 24px; background: #16213e; border-top: 1px solid #0f3460; font-size: 12px; color: #888; display: flex; gap: 24px; }

  .ratio-lock { display: flex; align-items: center; gap: 6px; }
  .ratio-lock input[type="checkbox"] { margin: 0; }
  .ratio-lock label { font-size: 12px; color: #aaa; cursor: pointer; }

  .aspect-presets { display: flex; gap: 4px; flex-wrap: wrap; }
  .aspect-presets button { font-size: 11px; padding: 2px 8px; }
</style>
</head>
<body>

<div class="header">
  <h1>Close-Up Cropper</h1>
  <span class="subtitle">{{SUBTITLE}}</span>
</div>

<div class="toolbar">
  <label>Load different image:</label>
  <input type="file" id="fileInput" accept="image/*">
  <div class="sep"></div>
  <button id="btnUndo" disabled>Undo</button>
  <button id="btnClear" disabled>Clear All</button>
  <div class="sep"></div>
  <label>Zoom:</label>
  <button id="btnZoomOut">&minus;</button>
  <span id="zoomLevel">100%</span>
  <button id="btnZoomIn">+</button>
  <button id="btnZoomFit">Fit</button>
  <div class="sep"></div>
  <div class="dimensions-display" id="dimensionsDisplay">No selection</div>
  <div class="size-enforcement-banner info" id="enforcementBanner" style="display:none;"></div>
  <div class="sep"></div>
  <button id="btnSaveAll" class="primary" disabled>Save All Crops</button>
  <button id="btnSaveAllWithManifest" class="primary" disabled>Save All + Manifest</button>
  <span id="folderStatus" style="font-size:12px; color:#0a7; max-width:250px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">💡 Crops download as PNGs — Chrome will ask where to save</span>
</div>

<div class="main">
  <div class="canvas-area" id="canvasArea">
    <canvas id="canvas"></canvas>
  </div>
  <div class="sidebar">
    <div>
      <h3>Image Info</h3>
      <div id="imageInfo" style="font-size:12px; color:#888;">Loading...</div>
    </div>

    <div>
      <h3>Current Selection</h3>
      <div class="field"><label>X:</label><input type="number" id="cropX" value="0"><span>px</span></div>
      <div class="field"><label>Y:</label><input type="number" id="cropY" value="0"><span>px</span></div>
      <div class="field"><label>Width:</label><input type="number" id="cropW" value="0"><span>px</span></div>
      <div class="field"><label>Height:</label><input type="number" id="cropH" value="0"><span>px</span></div>
      <div class="ratio-lock">
        <input type="checkbox" id="lockRatio">
        <label for="lockRatio">Lock aspect ratio</label>
      </div>
      <div class="aspect-presets" style="margin-top:6px;">
        <button onclick="setPresetRatio(1,1)">1:1</button>
        <button onclick="setPresetRatio(4,3)">4:3</button>
        <button onclick="setPresetRatio(16,9)">16:9</button>
        <button onclick="setPresetRatio(9,16)">9:16</button>
        <button onclick="setPresetRatio(0,0)">Free</button>
      </div>
    </div>

    <div>
      <h3>Preview</h3>
      <div class="preview-box" id="previewBox">
        <span class="placeholder">Draw a crop region</span>
      </div>
      <div style="margin-top:8px; text-align:center;">
        <button id="btnAddCrop" class="primary" disabled style="width:100%; padding:10px;">+ Add This Crop</button>
      </div>
    </div>

    <div class="crop-list" id="cropList">
      <h3>Saved Crops <span id="cropCount" style="color:#888; font-weight:normal;">(0)</span></h3>
    </div>
  </div>
</div>

<div class="info-bar">
  <span id="mousePos">Mouse: &mdash;</span>
  <span id="selectionInfo">Selection: none</span>
  <span id="imgDims">Image: &mdash;</span>
</div>

<script>
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const fileInput = document.getElementById('fileInput');
const canvasArea = document.getElementById('canvasArea');

let img = null;
let zoom = 1;
let crops = [];
let activeCropIdx = -1;
let minDimension = {{MIN_DIMENSION}};

// Drawing state
let isDrawing = false;
let isDragging = false;
let isResizing = false;
let resizeHandle = null;
let startX = 0, startY = 0;
let cropRect = { x: 0, y: 0, w: 0, h: 0 };
let dragOffset = { x: 0, y: 0 };
let lockedRatio = null;

// ─── SIZE ENFORCEMENT LAYER 1 ──────────────────────────────────────────────────
function updateSizeEnforcement() {
  const rw = Math.abs(cropRect.w);
  const rh = Math.abs(cropRect.h);
  const dimensionsEl = document.getElementById('dimensionsDisplay');
  const bannerEl = document.getElementById('enforcementBanner');

  if (rw < 2 || rh < 2) {
    dimensionsEl.textContent = 'No selection';
    dimensionsEl.className = 'dimensions-display';
    bannerEl.style.display = 'none';
    return;
  }

  dimensionsEl.textContent = rw + ' × ' + rh + ' px';

  const shortest = Math.min(rw, rh);
  if (shortest < minDimension) {
    dimensionsEl.className = 'dimensions-display warning';
    bannerEl.className = 'size-enforcement-banner warning';
    bannerEl.innerHTML = '⚠ Too small for video production (' + shortest + 'px &lt; ' + minDimension + 'px minimum)';
    bannerEl.style.display = 'flex';
  } else {
    dimensionsEl.className = 'dimensions-display ready';
    bannerEl.className = 'size-enforcement-banner ready';
    bannerEl.innerHTML = '✅ Ready for production (' + rw + ' × ' + rh + ')';
    bannerEl.style.display = 'flex';
  }
}

function saveToFolder(name, dataUrl) {
  // Direct download — Chrome will prompt for save location
  const a = document.createElement('a');
  a.href = dataUrl;
  a.download = name + '.png';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  document.getElementById('folderStatus').textContent = '\u2705 Downloading: ' + name + '.png';
}

// Load image from file picker (allows swapping)
fileInput.addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (ev) => { loadImageFromSrc(ev.target.result, file.name); };
  reader.readAsDataURL(file);
});

function loadImageFromSrc(src, name) {
  img = new Image();
  img.onload = () => {
    fitZoom();
    cropRect = { x: 0, y: 0, w: 0, h: 0 };
    draw();
    document.getElementById('imageInfo').textContent = img.naturalWidth + ' \u00d7 ' + img.naturalHeight + 'px \u2014 ' + name;
    document.getElementById('imgDims').textContent = 'Image: ' + img.naturalWidth + '\u00d7' + img.naturalHeight;
  };
  img.src = src;
}

function fitZoom() {
  if (!img) return;
  const areaW = canvasArea.clientWidth - 40;
  const areaH = canvasArea.clientHeight - 40;
  zoom = Math.min(areaW / img.naturalWidth, areaH / img.naturalHeight, 1);
  zoom = Math.round(zoom * 100) / 100;
  updateCanvas();
}

function updateCanvas() {
  if (!img) return;
  canvas.width = Math.round(img.naturalWidth * zoom);
  canvas.height = Math.round(img.naturalHeight * zoom);
  document.getElementById('zoomLevel').textContent = Math.round(zoom * 100) + '%';
  draw();
}

document.getElementById('btnZoomIn').onclick = () => { zoom = Math.min(zoom + 0.1, 3); updateCanvas(); };
document.getElementById('btnZoomOut').onclick = () => { zoom = Math.max(zoom - 0.1, 0.1); updateCanvas(); };
document.getElementById('btnZoomFit').onclick = fitZoom;

function draw() {
  if (!img) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

  // Draw saved crops
  crops.forEach((c, i) => {
    ctx.strokeStyle = i === activeCropIdx ? '#e94560' : 'rgba(233,69,96,0.5)';
    ctx.lineWidth = i === activeCropIdx ? 2 : 1;
    ctx.setLineDash(i === activeCropIdx ? [] : [4, 4]);
    ctx.strokeRect(c.x * zoom, c.y * zoom, c.w * zoom, c.h * zoom);
    ctx.setLineDash([]);
    ctx.fillStyle = i === activeCropIdx ? '#e94560' : 'rgba(233,69,96,0.6)';
    ctx.font = Math.max(11, 13 * zoom) + 'px sans-serif';
    ctx.fillText(c.name || 'Crop ' + (i+1), c.x * zoom + 4, c.y * zoom - 4);
  });

  // Draw current selection
  if (cropRect.w !== 0 && cropRect.h !== 0) {
    const rx = Math.min(cropRect.x, cropRect.x + cropRect.w);
    const ry = Math.min(cropRect.y, cropRect.y + cropRect.h);
    const rw = Math.abs(cropRect.w);
    const rh = Math.abs(cropRect.h);

    // Dimming overlay
    ctx.fillStyle = 'rgba(0,0,0,0.45)';
    ctx.fillRect(0, 0, canvas.width, ry * zoom);
    ctx.fillRect(0, ry * zoom, rx * zoom, rh * zoom);
    ctx.fillRect((rx + rw) * zoom, ry * zoom, canvas.width - (rx + rw) * zoom, rh * zoom);
    ctx.fillRect(0, (ry + rh) * zoom, canvas.width, canvas.height - (ry + rh) * zoom);

    // Selection border
    ctx.strokeStyle = '#00ff88';
    ctx.lineWidth = 2;
    ctx.setLineDash([]);
    ctx.strokeRect(rx * zoom, ry * zoom, rw * zoom, rh * zoom);

    // Corner handles
    const hs = 6;
    ctx.fillStyle = '#00ff88';
    [[rx, ry], [rx + rw, ry], [rx, ry + rh], [rx + rw, ry + rh]].forEach(([hx, hy]) => {
      ctx.fillRect(hx * zoom - hs/2, hy * zoom - hs/2, hs, hs);
    });

    // Dimensions label
    ctx.fillStyle = '#00ff88';
    ctx.font = Math.max(12, 14 * zoom) + 'px monospace';
    ctx.fillText(rw + ' \u00d7 ' + rh, rx * zoom + 4, (ry + rh) * zoom + 16);
  }
}

function getImgCoords(e) {
  const rect = canvas.getBoundingClientRect();
  return { x: Math.round((e.clientX - rect.left) / zoom), y: Math.round((e.clientY - rect.top) / zoom) };
}

function getHandle(mx, my) {
  if (cropRect.w === 0 && cropRect.h === 0) return null;
  const rx = Math.min(cropRect.x, cropRect.x + cropRect.w);
  const ry = Math.min(cropRect.y, cropRect.y + cropRect.h);
  const rw = Math.abs(cropRect.w);
  const rh = Math.abs(cropRect.h);
  const t = 8 / zoom;
  const handles = [
    { name: 'tl', x: rx, y: ry }, { name: 'tr', x: rx + rw, y: ry },
    { name: 'bl', x: rx, y: ry + rh }, { name: 'br', x: rx + rw, y: ry + rh }
  ];
  for (const h of handles) { if (Math.abs(mx - h.x) < t && Math.abs(my - h.y) < t) return h.name; }
  return null;
}

function isInsideSelection(mx, my) {
  const rx = Math.min(cropRect.x, cropRect.x + cropRect.w);
  const ry = Math.min(cropRect.y, cropRect.y + cropRect.h);
  return mx >= rx && mx <= rx + Math.abs(cropRect.w) && my >= ry && my <= ry + Math.abs(cropRect.h);
}

canvas.addEventListener('mousedown', (e) => {
  if (!img) return;
  const { x, y } = getImgCoords(e);
  const handle = getHandle(x, y);
  if (handle) { isResizing = true; resizeHandle = handle; startX = x; startY = y; return; }
  if (isInsideSelection(x, y)) { isDragging = true; dragOffset.x = x - Math.min(cropRect.x, cropRect.x + cropRect.w); dragOffset.y = y - Math.min(cropRect.y, cropRect.y + cropRect.h); return; }
  isDrawing = true; cropRect.x = x; cropRect.y = y; cropRect.w = 0; cropRect.h = 0; startX = x; startY = y;
});

canvas.addEventListener('mousemove', (e) => {
  if (!img) return;
  const { x, y } = getImgCoords(e);
  document.getElementById('mousePos').textContent = 'Mouse: ' + x + ', ' + y;
  const handle = getHandle(x, y);
  if (handle) canvas.style.cursor = (handle === 'tl' || handle === 'br') ? 'nwse-resize' : 'nesw-resize';
  else if (isInsideSelection(x, y)) canvas.style.cursor = 'move';
  else canvas.style.cursor = 'crosshair';

  if (isDrawing) {
    let newW = x - cropRect.x, newH = y - cropRect.y;
    if (lockedRatio) newH = Math.round(Math.abs(newW) / lockedRatio) * (Math.sign(newH) || 1);
    cropRect.w = clampW(cropRect.x, newW); cropRect.h = clampH(cropRect.y, newH);
    draw(); updateFields(); updatePreview(); updateSizeEnforcement();
  }
  if (isDragging) {
    const rw = Math.abs(cropRect.w), rh = Math.abs(cropRect.h);
    let nx = Math.max(0, Math.min(x - dragOffset.x, img.naturalWidth - rw));
    let ny = Math.max(0, Math.min(y - dragOffset.y, img.naturalHeight - rh));
    cropRect.x = nx; cropRect.y = ny; cropRect.w = rw; cropRect.h = rh;
    draw(); updateFields(); updatePreview(); updateSizeEnforcement();
  }
  if (isResizing) {
    const rx = Math.min(cropRect.x, cropRect.x + cropRect.w), ry = Math.min(cropRect.y, cropRect.y + cropRect.h);
    const rw = Math.abs(cropRect.w), rh = Math.abs(cropRect.h);
    let nx = rx, ny = ry, nw = rw, nh = rh;
    if (resizeHandle.includes('l')) { nx = Math.max(0, x); nw = rx + rw - nx; }
    if (resizeHandle.includes('r')) { nw = Math.min(x - rx, img.naturalWidth - rx); }
    if (resizeHandle.includes('t')) { ny = Math.max(0, y); nh = ry + rh - ny; }
    if (resizeHandle.includes('b')) { nh = Math.min(y - ry, img.naturalHeight - ry); }
    if (lockedRatio) {
      if (resizeHandle.includes('l') || resizeHandle.includes('r')) { nh = Math.round(Math.abs(nw) / lockedRatio); if (resizeHandle.includes('t')) ny = ry + rh - nh; }
      else { nw = Math.round(Math.abs(nh) * lockedRatio); if (resizeHandle.includes('l')) nx = rx + rw - nw; }
    }
    if (nw > 0 && nh > 0) { cropRect.x = nx; cropRect.y = ny; cropRect.w = nw; cropRect.h = nh; }
    draw(); updateFields(); updatePreview(); updateSizeEnforcement();
  }
});

// mouseup on DOCUMENT so it fires even if cursor leaves canvas
document.addEventListener('mouseup', () => {
  if (!isDrawing && !isDragging && !isResizing) return;
  isDrawing = false; isDragging = false; isResizing = false;
  if (cropRect.w < 0) { cropRect.x += cropRect.w; cropRect.w = -cropRect.w; }
  if (cropRect.h < 0) { cropRect.y += cropRect.h; cropRect.h = -cropRect.h; }
  draw(); updateFields(); updatePreview(); updateSizeEnforcement();
  document.getElementById('btnAddCrop').disabled = (cropRect.w < 2 || cropRect.h < 2);
  document.getElementById('selectionInfo').textContent = cropRect.w > 0 ? 'Selection: ' + Math.abs(cropRect.w) + '\u00d7' + Math.abs(cropRect.h) + ' at (' + cropRect.x + ',' + cropRect.y + ')' : 'Selection: none';
});

// Also handle mouseleave on canvas to update coords safely
canvas.addEventListener('mouseleave', () => {
  if (isDrawing || isDragging || isResizing) {
    // Keep the operation going — mouseup on document will finalize
  }
});

function clampW(sx, w) { return w >= 0 ? Math.min(w, img.naturalWidth - sx) : Math.max(w, -sx); }
function clampH(sy, h) { return h >= 0 ? Math.min(h, img.naturalHeight - sy) : Math.max(h, -sy); }

function updateFields() {
  document.getElementById('cropX').value = Math.min(cropRect.x, cropRect.x + cropRect.w);
  document.getElementById('cropY').value = Math.min(cropRect.y, cropRect.y + cropRect.h);
  document.getElementById('cropW').value = Math.abs(cropRect.w);
  document.getElementById('cropH').value = Math.abs(cropRect.h);
}

function updatePreview() {
  const box = document.getElementById('previewBox');
  const rw = Math.abs(cropRect.w), rh = Math.abs(cropRect.h);
  if (rw < 2 || rh < 2 || !img) { box.innerHTML = '<span class="placeholder">Draw a crop region</span>'; return; }
  const rx = Math.min(cropRect.x, cropRect.x + cropRect.w), ry = Math.min(cropRect.y, cropRect.y + cropRect.h);
  const tc = document.createElement('canvas'); tc.width = rw; tc.height = rh;
  tc.getContext('2d').drawImage(img, rx, ry, rw, rh, 0, 0, rw, rh);
  box.innerHTML = '<img src="' + tc.toDataURL('image/png') + '" alt="Preview">';
}

['cropX','cropY','cropW','cropH'].forEach(id => {
  document.getElementById(id).addEventListener('change', () => {
    cropRect.x = parseInt(document.getElementById('cropX').value) || 0;
    cropRect.y = parseInt(document.getElementById('cropY').value) || 0;
    cropRect.w = parseInt(document.getElementById('cropW').value) || 0;
    cropRect.h = parseInt(document.getElementById('cropH').value) || 0;
    draw(); updatePreview(); updateSizeEnforcement();
    document.getElementById('btnAddCrop').disabled = (cropRect.w < 2 || cropRect.h < 2);
  });
});

function setPresetRatio(w, h) {
  if (w === 0 && h === 0) { lockedRatio = null; document.getElementById('lockRatio').checked = false; }
  else { lockedRatio = w / h; document.getElementById('lockRatio').checked = true; }
}

document.getElementById('lockRatio').addEventListener('change', (e) => {
  if (e.target.checked && cropRect.w > 0 && cropRect.h > 0) lockedRatio = Math.abs(cropRect.w) / Math.abs(cropRect.h);
  else if (!e.target.checked) lockedRatio = null;
});

document.getElementById('btnAddCrop').addEventListener('click', () => {
  const rw = Math.abs(cropRect.w), rh = Math.abs(cropRect.h);
  if (rw < 2 || rh < 2) return;
  const rx = Math.min(cropRect.x, cropRect.x + cropRect.w), ry = Math.min(cropRect.y, cropRect.y + cropRect.h);
  const name = prompt('Name this crop (e.g., "tessa_closeup", "guidebird_face"):', 'crop_' + (crops.length + 1));
  if (!name) return;
  const tc = document.createElement('canvas'); tc.width = rw; tc.height = rh;
  tc.getContext('2d').drawImage(img, rx, ry, rw, rh, 0, 0, rw, rh);
  crops.push({ x: rx, y: ry, w: rw, h: rh, name, dataUrl: tc.toDataURL('image/png') });
  activeCropIdx = crops.length - 1;
  renderCropList(); draw();
  document.getElementById('btnClear').disabled = false;
  document.getElementById('btnUndo').disabled = false;
  document.getElementById('btnSaveAll').disabled = false;
  document.getElementById('btnSaveAllWithManifest').disabled = false;
});

function renderCropList() {
  const list = document.getElementById('cropList');
  let html = '<h3>Saved Crops <span style="color:#888; font-weight:normal;">(' + crops.length + ')</span></h3>';
  crops.forEach((c, i) => {
    html += '<div class="crop-item ' + (i === activeCropIdx ? 'active' : '') + '" onclick="selectCrop(' + i + ')">'
      + '<div class="ci-header"><span class="ci-name">' + c.name + '</span><span class="ci-dims">' + c.w + '\u00d7' + c.h + '</span></div>'
      + '<img class="ci-thumb" src="' + c.dataUrl + '" alt="' + c.name + '">'
      + '<div class="ci-actions"><button onclick="event.stopPropagation(); saveSingle(' + i + ')">Save PNG</button>'
      + '<button onclick="event.stopPropagation(); renameCrop(' + i + ')">Rename</button>'
      + '<button onclick="event.stopPropagation(); deleteCrop(' + i + ')">Delete</button></div></div>';
  });
  list.innerHTML = html;
}

function selectCrop(i) {
  activeCropIdx = i; const c = crops[i];
  cropRect = { x: c.x, y: c.y, w: c.w, h: c.h };
  updateFields(); updatePreview(); draw(); renderCropList();
}
function renameCrop(i) { const n = prompt('New name:', crops[i].name); if (n) { crops[i].name = n; renderCropList(); draw(); } }
function deleteCrop(i) {
  crops.splice(i, 1); activeCropIdx = Math.min(activeCropIdx, crops.length - 1);
  renderCropList(); draw();
  if (!crops.length) { document.getElementById('btnClear').disabled = true; document.getElementById('btnUndo').disabled = true; document.getElementById('btnSaveAll').disabled = true; document.getElementById('btnSaveAllWithManifest').disabled = true; }
}
function saveSingle(i) { saveToFolder(crops[i].name, crops[i].dataUrl); }

document.getElementById('btnSaveAll').addEventListener('click', async () => {
  for (let i = 0; i < crops.length; i++) {
    await saveToFolder(crops[i].name, crops[i].dataUrl);
  }
  document.getElementById('folderStatus').textContent = '\u2705 All ' + crops.length + ' crops saved to ' + (saveDirHandle ? saveDirHandle.name : 'Downloads');
});

document.getElementById('btnSaveAllWithManifest').addEventListener('click', async () => {
  for (let i = 0; i < crops.length; i++) {
    await saveToFolder(crops[i].name, crops[i].dataUrl);
  }
  const manifest = crops.map(crop => ({
    name: crop.name,
    width: crop.w,
    height: crop.h,
    source_file: crop.name + '.png'
  }));
  const manifestJson = JSON.stringify(manifest, null, 2);
  const manifestBlob = new Blob([manifestJson], { type: 'application/json' });
  const manifestUrl = URL.createObjectURL(manifestBlob);
  const manifestLink = document.createElement('a');
  manifestLink.href = manifestUrl;
  manifestLink.download = 'crop_manifest.json';
  document.body.appendChild(manifestLink);
  manifestLink.click();
  document.body.removeChild(manifestLink);
  URL.revokeObjectURL(manifestUrl);
  document.getElementById('folderStatus').textContent = '\u2705 All ' + crops.length + ' crops + manifest.json saved to ' + (saveDirHandle ? saveDirHandle.name : 'Downloads');
});

document.getElementById('btnUndo').addEventListener('click', () => {
  if (crops.length) { crops.pop(); activeCropIdx = crops.length - 1; renderCropList(); draw(); }
  if (!crops.length) { document.getElementById('btnClear').disabled = true; document.getElementById('btnUndo').disabled = true; document.getElementById('btnSaveAll').disabled = true; document.getElementById('btnSaveAllWithManifest').disabled = true; }
});

document.getElementById('btnClear').addEventListener('click', () => {
  if (confirm('Clear all saved crops?')) {
    crops = []; activeCropIdx = -1; renderCropList(); draw();
    document.getElementById('btnClear').disabled = true; document.getElementById('btnUndo').disabled = true; document.getElementById('btnSaveAll').disabled = true; document.getElementById('btnSaveAllWithManifest').disabled = true;
  }
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { cropRect = { x: 0, y: 0, w: 0, h: 0 }; draw(); updateFields(); document.getElementById('previewBox').innerHTML = '<span class="placeholder">Draw a crop region</span>'; }
  if ((e.key === '+' || e.key === '=') && !e.target.closest('input')) { zoom = Math.min(zoom + 0.1, 3); updateCanvas(); }
  if (e.key === '-' && !e.target.closest('input')) { zoom = Math.max(zoom - 0.1, 0.1); updateCanvas(); }
});

// === DEFAULT: Lock to 4:3 for full-screen shots (iPad-optimized) ===
lockedRatio = 4 / 3;
document.getElementById('lockRatio').checked = true;

// === AUTO-PRELOAD ===
{{PRELOAD_BLOCK}}
</script>
</body>
</html>"""


# ─── DIRECTUS REGISTRATION ──────────────────────────────────────────────────

def read_directus_credentials():
    """
    Read Directus credentials from API_KEYS_MASTER.md.
    Script is at Production/tools/, so API_KEYS_MASTER.md is at ../API_KEYS_MASTER.md
    """
    script_dir = Path(__file__).parent
    keys_file = script_dir.parent / "API_KEYS_MASTER.md"

    if not keys_file.exists():
        raise FileNotFoundError(f"API_KEYS_MASTER.md not found at {keys_file}")

    with open(keys_file, 'r') as f:
        content = f.read()

    # Extract Directus email and password from markdown table
    email_match = re.search(r'\|\s*\*\*Directus\*\*.*?Admin Email\s*\|\s*`?([^`\|]+)`?\s*\|', content)
    pass_match = re.search(r'Admin Password\s*\|\s*`([^`]+)`', content)
    url_match = re.search(r'URL:\s*([^\s\)]+)', content)

    if not (email_match and pass_match and url_match):
        raise ValueError("Could not extract Directus credentials from API_KEYS_MASTER.md")

    return {
        'email': email_match.group(1).strip(),
        'password': pass_match.group(1).strip(),
        'url': url_match.group(1).strip()
    }


def register_build_in_directus(output_path: str, module_id: int, event_number: int, source_image: str):
    """
    Register cropper HTML build in Directus.

    Args:
        output_path: Path to the generated cropper HTML file
        module_id: M-number (module_id) in Directus (e.g., 1 for M1)
        event_number: Event number (e.g., 1 for Event 1)
        source_image: Source image filename (e.g., "master_shot_6.png")

    Returns:
        dict: Response from Directus (or None if registration skipped)
    """
    if requests is None:
        print("WARNING: requests library not found. Skipping Directus registration.", file=sys.stderr)
        return None

    try:
        creds = read_directus_credentials()
        directus_url = creds['url'].rstrip('/')

        # Authenticate
        auth_url = f"{directus_url}/auth/login"
        auth_payload = {
            'email': creds['email'],
            'password': creds['password']
        }

        auth_resp = requests.post(auth_url, json=auth_payload, timeout=10)
        auth_resp.raise_for_status()

        access_token = auth_resp.json().get('data', {}).get('access_token')
        if not access_token:
            print("ERROR: No access_token in Directus auth response", file=sys.stderr)
            return None

        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        # Check if cropper already exists in prod_visual_assets
        filename = Path(output_path).name
        query_url = f"{directus_url}/items/prod_visual_assets"
        query_params = {
            'filter': json.dumps({'filename': {'_eq': filename}}),
            'limit': 1
        }

        query_resp = requests.get(query_url, params=query_params, headers=headers, timeout=10)
        query_resp.raise_for_status()
        query_data = query_resp.json()
        existing = query_data.get('data', [])

        # Prepare visual asset record
        asset_payload = {
            'filename': filename,
            'asset_type': 'production_tool',
            'tool_type': 'cropper',
            'module_id': module_id,
            'event_number': event_number,
            'source_image': source_image,
            'status': 'built',
            'built_at': datetime.now(timezone.utc).isoformat()
        }

        if existing:
            # PATCH existing
            asset_id = existing[0]['id']
            patch_url = f"{directus_url}/items/prod_visual_assets/{asset_id}"
            asset_resp = requests.patch(patch_url, json=asset_payload, headers=headers, timeout=10)
            asset_resp.raise_for_status()
            print(f"✓ Directus: Updated prod_visual_assets/{asset_id} ({filename})")
        else:
            # POST new
            post_url = f"{directus_url}/items/prod_visual_assets"
            asset_resp = requests.post(post_url, json=asset_payload, headers=headers, timeout=10)
            asset_resp.raise_for_status()
            new_id = asset_resp.json().get('data', {}).get('id')
            print(f"✓ Directus: Created prod_visual_assets/{new_id} ({filename})")

        # Update prod_modules cropper tracking fields
        module_url = f"{directus_url}/items/prod_modules/{module_id}"
        module_payload = {
            'cropper_status': 'built',
            'cropper_version': 1,
            'cropper_built_at': datetime.now(timezone.utc).isoformat(),
            'cropper_source_image': source_image
        }

        module_resp = requests.patch(module_url, json=module_payload, headers=headers, timeout=10)
        module_resp.raise_for_status()
        print(f"✓ Directus: Updated prod_modules/{module_id} cropper tracking fields")

        # Log to prod_activity_log
        activity_payload = {
            'module_id': module_id,
            'event_number': event_number,
            'action': 'cropper_build',
            'details': json.dumps({
                'filename': filename,
                'source_image': source_image,
                'output_path': str(output_path),
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        }

        log_url = f"{directus_url}/items/prod_activity_log"
        log_resp = requests.post(log_url, json=activity_payload, headers=headers, timeout=10)
        log_resp.raise_for_status()
        print(f"✓ Directus: Logged cropper_build action to prod_activity_log")

        return asset_resp.json()

    except FileNotFoundError as e:
        print(f"WARNING: {e} — Skipping Directus registration.", file=sys.stderr)
        return None
    except Exception as e:
        print(f"WARNING: Directus registration failed: {e}", file=sys.stderr)
        return None


# ─── BUILD FUNCTION ─────────────────────────────────────────────────────────

def build_cropper(image_path: str, output_path: str, title: str = None, min_dimension: int = 600, module_id: int = None, event_number: int = None):
    """
    Build a self-contained HTML cropper tool with a preloaded image.

    Args:
        image_path: Path to the image file to embed
        output_path: Where to write the HTML file
        title: Optional title shown in the header subtitle
        min_dimension: Minimum shortest side dimension for production readiness (default 600px)
        module_id: Optional M-number for Directus registration (e.g., 1 for M1)
        event_number: Optional event number for Directus registration (e.g., 1 for Event 1)
    """
    image_path = Path(image_path).resolve()
    if not image_path.exists():
        print(f"ERROR: Image not found: {image_path}", file=sys.stderr)
        sys.exit(1)

    # Determine MIME type
    suffix = image_path.suffix.lower()
    mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.gif': 'image/gif'}
    mime = mime_map.get(suffix, 'image/png')

    # Read and encode image
    with open(image_path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode()

    img_name = image_path.name
    display_title = title or img_name

    # Build preload JS block
    preload_block = f"""window.addEventListener('DOMContentLoaded', () => {{
  loadImageFromSrc('data:{mime};base64,{b64}', '{img_name}');
}});"""

    # Fill template
    html = CROPPER_HTML
    html = html.replace('{{TITLE_SUFFIX}}', f' — {display_title}' if title else '')
    html = html.replace('{{SUBTITLE}}', f'Preloaded: {display_title} — draw crop boxes, name them, save PNGs')
    html = html.replace('{{PRELOAD_BLOCK}}', preload_block)
    html = html.replace('{{MIN_DIMENSION}}', str(min_dimension))

    # Write output
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(html)

    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"Cropper built: {output_path}")
    print(f"  Image: {img_name} ({image_path.stat().st_size / 1024:.0f} KB)")
    print(f"  Output: {file_size_mb:.1f} MB")

    # Post-build auto-registration in Directus (if module_id and event_number provided)
    if module_id is not None and event_number is not None:
        register_build_in_directus(str(output_path), module_id, event_number, img_name)

    return str(output_path)


# ─── CLI ────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Build a self-contained HTML cropper tool with a preloaded image.')
    parser.add_argument('--image', required=True, help='Path to the image to preload')
    parser.add_argument('--output', required=True, help='Output HTML file path')
    parser.add_argument('--title', default=None, help='Optional title for the header')
    parser.add_argument('--min-dimension', type=int, default=600, help='Minimum shortest side dimension for production readiness (default: 600px)')
    parser.add_argument('--module-id', type=int, default=None, help='Optional M-number for Directus registration (e.g., 1 for M1)')
    parser.add_argument('--event-number', type=int, default=None, help='Optional event number for Directus registration (e.g., 1 for Event 1)')
    args = parser.parse_args()
    build_cropper(args.image, args.output, args.title, args.min_dimension, args.module_id, args.event_number)
