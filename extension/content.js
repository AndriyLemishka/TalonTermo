(() => {
  'use strict';

  if (document.getElementById('talonauto-open-btn')) return;

  // 1. Add "Імпорт з PDF" button in the CRM header actions
  const actionsBar = document.querySelector('.section-head__actions');
  if (!actionsBar) return;

  const openBtn = document.createElement('button');
  openBtn.id = 'talonauto-open-btn';
  openBtn.type = 'button';
  openBtn.className = 'btn btn--primary';
  openBtn.innerHTML = '📄 Імпорт з PDF';
  actionsBar.prepend(openBtn);

  // 2. Create isolated Shadow DOM modal so CRM styles never conflict
  const host = document.createElement('div');
  host.id = 'talonauto-host';
  document.body.appendChild(host);
  const shadow = host.attachShadow({ mode: 'open' });

  shadow.innerHTML = `
    <style>
      .overlay {
        position: fixed; inset: 0; background: rgba(11, 31, 51, 0.65);
        display: none; align-items: center; justify-content: center;
        z-index: 999999; padding: 20px; font-family: system-ui, -apple-system, sans-serif;
      }
      .overlay.open { display: flex; }
      .modal {
        background: #fff; color: #162235; border-radius: 16px;
        width: min(1240px, 96vw); max-height: 92vh;
        display: flex; flex-direction: column; overflow: hidden;
        box-shadow: 0 24px 60px rgba(0,0,0,0.3);
      }
      .head {
        background: #0f253e; color: #fff; padding: 14px 20px;
        display: flex; align-items: center; justify-content: space-between;
      }
      .head h2 { margin: 0; font-size: 17px; }
      .close-btn {
        background: rgba(255,255,255,0.14); color: #fff; border: none;
        border-radius: 8px; padding: 6px 12px; cursor: pointer; font-size: 14px;
      }
      .body { padding: 18px 20px; overflow-y: auto; flex: 1; }
      .upload-row { display: flex; flex-direction: column; gap: 12px; margin-bottom: 16px; }
      .step-box {
        background: #f8fafc; border: 1px solid #dde3ec; border-radius: 12px; padding: 12px 14px;
      }
      .step-title { font-size: 13px; font-weight: 700; color: #162235; margin-bottom: 8px; }
      .fuel-pills { display: flex; flex-wrap: wrap; gap: 8px; }
      .fuel-pill {
        border: 2px solid #dde3ec; background: #fff; color: #162235;
        border-radius: 9px; padding: 8px 18px; font-size: 14px; font-weight: 700;
        cursor: pointer; transition: 0.12s all;
      }
      .fuel-pill:hover { border-color: #e86b1a; }
      .fuel-pill.active { background: #e86b1a; border-color: #e86b1a; color: #fff; }
      .dropzone {
        border: 2px dashed #b9c5d6; border-radius: 12px; padding: 20px;
        text-align: center; cursor: pointer; background: #fafbfd;
      }
      .dropzone.dragover { border-color: #e86b1a; background: #fff6f0; }
      .dropzone strong { display: block; font-size: 15px; margin-bottom: 4px; }
      .dropzone span { font-size: 12px; color: #5d6c80; }
      label { display: block; font-size: 12px; font-weight: 600; color: #5d6c80; margin-bottom: 4px; }
      select, input {
        width: 100%; padding: 7px 9px; border: 1px solid #dde3ec;
        border-radius: 7px; font-size: 13px; box-sizing: border-box; background: #fff;
      }
      select.missing, input.missing { border-color: #f59e0b; background: #fffbeb; }
      .toolbar {
        display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end;
        justify-content: space-between; margin-bottom: 12px;
        padding: 12px; background: #f4f6f9; border-radius: 10px;
      }
      .bulk { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; }
      .bulk > div { min-width: 135px; }
      .btn {
        border: none; border-radius: 8px; padding: 9px 14px; font-size: 13px;
        font-weight: 600; cursor: pointer;
      }
      .btn:disabled { opacity: 0.5; cursor: not-allowed; }
      .btn-primary { background: #e86b1a; color: #fff; }
      .btn-ghost { background: #e2e8f0; color: #162235; }
      .btn-danger { background: #fee2e2; color: #b91c1c; padding: 5px 9px; font-size: 12px; }
      .status {
        padding: 10px 14px; border-radius: 9px; background: #f1f5f9;
        margin-bottom: 12px; font-size: 13px; display: none;
      }
      .status.visible { display: block; }
      .bar { height: 6px; background: #dbe3ee; border-radius: 99px; margin-top: 6px; overflow: hidden; }
      .fill { height: 100%; background: #e86b1a; width: 0%; transition: width 0.2s; }
      table { width: 100%; border-collapse: collapse; font-size: 13px; }
      th { text-align: left; padding: 8px 6px; border-bottom: 2px solid #dde3ec; font-size: 12px; color: #5d6c80; }
      td { padding: 8px 6px; border-bottom: 1px solid #dde3ec; vertical-align: middle; }
      .thumb { width: 56px; height: 74px; object-fit: contain; border: 1px solid #dde3ec; border-radius: 5px; background: #fff; }
      .update-banner {
        display: none; align-items: center; justify-content: space-between; gap: 12px;
        background: #fffbeb; border: 1px solid #fcd34d; color: #92400e;
        padding: 10px 14px; border-radius: 10px; margin-bottom: 12px; font-size: 13px;
      }
      .update-banner.visible { display: flex; }
      .btn-update { background: #d97706; color: #fff; padding: 6px 12px; font-size: 12px; }
    </style>

    <div class="overlay" id="overlay">
      <div class="modal">
        <div class="head">
          <h2>📄 Імпорт талонів з PDF у TermoUnion CRM</h2>
          <button class="close-btn" id="closeBtn">✕ Закрити</button>
        </div>
        <div class="body">
          <div class="update-banner" id="updateBanner">
            <span id="updateText">🔔 Доступне оновлення розширення</span>
            <button type="button" class="btn btn-update" id="copyUpdateBtn">Скопіювати команду оновлення (CMD)</button>
          </div>
          <div class="upload-row">
            <div class="step-box">
              <div class="step-title">Крок 1. Обери тип пального для цього PDF</div>
              <div class="fuel-pills" id="fuelPills">
                <button type="button" class="fuel-pill" data-fuel="ДП">ДП</button>
                <button type="button" class="fuel-pill" data-fuel="А-95">А-95</button>
                <button type="button" class="fuel-pill" data-fuel="А-92">А-92</button>
                <button type="button" class="fuel-pill" data-fuel="Газ">Газ</button>
              </div>
              <input type="hidden" id="defaultFuel" value="" />
            </div>
            <div class="dropzone" id="dropzone">
              <strong>Крок 2. Перетягни PDF з талонами сюди або натисни для вибору</strong>
              <span>Працює прямо в браузері (3×3, 1×1, будь-яка кількість сторінок)</span>
              <input type="file" id="fileInput" accept="application/pdf" hidden />
            </div>
          </div>

          <div class="status" id="statusBox">
            <div id="statusText"></div>
            <div class="bar"><div class="fill" id="progressFill"></div></div>
          </div>

          <div id="tableWrap" style="display: none;">
            <div class="toolbar">
              <div class="bulk">
                <div>
                  <label>Масово: Пальне</label>
                  <select id="bulkFuel">
                    <option value="">Оберіть...</option>
                    <option value="ДП">ДП</option>
                    <option value="А-95">А-95</option>
                    <option value="А-92">А-92</option>
                    <option value="Газ">Газ</option>
                  </select>
                </div>
                <div>
                  <label>Масово: АЗС</label>
                  <select id="bulkAzs">
                    <option value="">Оберіть...</option>
                    <option value="ОККО">ОККО</option>
                    <option value="WOG">WOG</option>
                    <option value="УКРНАФТА">УКРНАФТА</option>
                  </select>
                </div>
                <div>
                  <label>Масово: Примітка</label>
                  <input type="text" id="bulkNote" placeholder="Необов'язково" />
                </div>
                <button class="btn btn-ghost" id="applyBulkBtn">Застосувати до всіх</button>
              </div>
              <button class="btn btn-primary" id="uploadBtn">Залити всі в CRM (0)</button>
            </div>

            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Скрін</th>
                  <th>Пальне *</th>
                  <th>АЗС *</th>
                  <th>Номінал *</th>
                  <th>Термін *</th>
                  <th>К-сть</th>
                  <th>Номер талона</th>
                  <th>Примітка</th>
                  <th></th>
                </tr>
              </thead>
              <tbody id="tbody"></tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  `;

  const $ = (id) => shadow.getElementById(id);
  let coupons = [];

  shadow.querySelectorAll('.fuel-pill').forEach((btn) => {
    btn.addEventListener('click', () => {
      const val = btn.dataset.fuel;
      const isSame = $('defaultFuel').value === val;
      shadow.querySelectorAll('.fuel-pill').forEach((b) => b.classList.remove('active'));
      if (isSame) {
        $('defaultFuel').value = '';
      } else {
        btn.classList.add('active');
        $('defaultFuel').value = val;
        if (coupons.length) {
          coupons.forEach((c) => { c.fuel_type = val; });
          renderTable();
        }
      }
    });
  });

  const CURRENT_VERSION = (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.getManifest)
    ? chrome.runtime.getManifest().version
    : '1.0.0';
  const UPDATE_CMD = 'powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/AndriyLemishka/TalonTermo/main/install.ps1 | iex"';
  let updateChecked = false;

  async function checkForUpdates() {
    if (updateChecked) return;
    updateChecked = true;
    try {
      const res = await fetch(`https://raw.githubusercontent.com/AndriyLemishka/TalonTermo/main/extension/manifest.json?t=${Date.now()}`, {
        cache: 'no-store',
      });
      if (!res.ok) return;
      const remote = await res.json();
      if (remote.version && remote.version !== CURRENT_VERSION) {
        $('updateText').textContent = `🔔 Доступна нова версія v${remote.version} (зараз v${CURRENT_VERSION}). Запусти команду в CMD для оновлення:`;
        $('updateBanner').classList.add('visible');
      }
    } catch {
      // Ignore offline / network errors silently
    }
  }

  $('copyUpdateBtn').addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(UPDATE_CMD);
      $('copyUpdateBtn').textContent = '✓ Скопійовано!';
      setTimeout(() => { $('copyUpdateBtn').textContent = 'Скопіювати команду оновлення (CMD)'; }, 2500);
    } catch {
      window.prompt('Скопіюй команду і встав у CMD:', UPDATE_CMD);
    }
  });

  openBtn.addEventListener('click', () => {
    $('overlay').classList.add('open');
    checkForUpdates();
  });
  $('closeBtn').addEventListener('click', () => $('overlay').classList.remove('open'));
  $('dropzone').addEventListener('click', () => $('fileInput').click());
  $('dropzone').addEventListener('dragover', (e) => { e.preventDefault(); $('dropzone').classList.add('dragover'); });
  $('dropzone').addEventListener('dragleave', () => $('dropzone').classList.remove('dragover'));
  $('dropzone').addEventListener('drop', (e) => {
    e.preventDefault();
    $('dropzone').classList.remove('dragover');
    if (e.dataTransfer.files[0]) processPdf(e.dataTransfer.files[0]);
  });
  $('fileInput').addEventListener('change', () => {
    const file = $('fileInput').files[0];
    $('fileInput').value = '';
    if (file) processPdf(file);
  });

  function setStatus(text, pct) {
    $('statusBox').classList.add('visible');
    $('statusText').textContent = text;
    $('progressFill').style.width = `${pct}%`;
  }

  function findSegments(hasInkArr, minSize) {
    const segs = [];
    let start = null;
    let gap = 0;
    for (let i = 0; i < hasInkArr.length; i++) {
      if (hasInkArr[i]) {
        if (start === null) start = i;
        gap = 0;
      } else if (start !== null) {
        gap++;
        if (gap > 10) {
          const end = i - gap;
          if (end - start >= minSize) segs.push([start, end]);
          start = null;
          gap = 0;
        }
      }
    }
    if (start !== null) {
      const end = hasInkArr.length - 1;
      if (end - start >= minSize) segs.push([start, end]);
    }
    return segs;
  }

  function detectCardBoxes(canvas) {
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    const w = canvas.width;
    const h = canvas.height;
    const data = ctx.getImageData(0, 0, w, h).data;

    const rowInk = new Array(h).fill(false);
    for (let y = 0; y < h; y++) {
      const rowOffset = y * w * 4;
      for (let x = 0; x < w; x++) {
        const idx = rowOffset + x * 4;
        if (data[idx] < 245 || data[idx + 1] < 245 || data[idx + 2] < 245) {
          rowInk[y] = true;
          break;
        }
      }
    }

    const rows = findSegments(rowInk, Math.floor(h * 0.12));
    const boxes = [];

    for (const [y0, y1] of rows) {
      const colInk = new Array(w).fill(false);
      for (let x = 0; x < w; x++) {
        for (let y = y0; y <= y1; y++) {
          const idx = (y * w + x) * 4;
          if (data[idx] < 245 || data[idx + 1] < 245 || data[idx + 2] < 245) {
            colInk[x] = true;
            break;
          }
        }
      }
      const cols = findSegments(colInk, Math.floor(w * 0.15));
      for (const [x0, x1] of cols) {
        // Tighten top/bottom bounds specifically inside [x0..x1]
        let ty0 = y0;
        let ty1 = y1;
        for (let y = y0; y <= y1; y++) {
          let ink = false;
          const rowOffset = y * w * 4;
          for (let x = x0; x <= x1; x++) {
            const idx = rowOffset + x * 4;
            if (data[idx] < 245 || data[idx + 1] < 245 || data[idx + 2] < 245) {
              ink = true;
              break;
            }
          }
          if (ink) { ty0 = y; break; }
        }
        for (let y = y1; y >= ty0; y--) {
          let ink = false;
          const rowOffset = y * w * 4;
          for (let x = x0; x <= x1; x++) {
            const idx = rowOffset + x * 4;
            if (data[idx] < 245 || data[idx + 1] < 245 || data[idx + 2] < 245) {
              ink = true;
              break;
            }
          }
          if (ink) { ty1 = y; break; }
        }
        boxes.push({ x0, y0: ty0, x1, y1: ty1 });
      }
    }
    return boxes;
  }

  function detectBannerFuelType(cropCanvas) {
    const ctx = cropCanvas.getContext('2d', { willReadFrequently: true });
    const bw = cropCanvas.width;
    const bh = Math.max(1, Math.floor(cropCanvas.height * 0.45));
    const data = ctx.getImageData(0, 0, bw, bh).data;
    let total = 0;
    let yellow = 0;
    let cyanBlue = 0;

    for (let y = 0; y < bh; y += 2) {
      const rowOffset = y * bw * 4;
      for (let x = 0; x < bw; x += 2) {
        const idx = rowOffset + x * 4;
        const r = data[idx];
        const g = data[idx + 1];
        const b = data[idx + 2];
        total++;
        if (r > 200 && g > 180 && b < 70) yellow++;
        else if (b > 175 && g > 110 && r < 70) cyanBlue++;
      }
    }

    const threshold = total * 0.02;
    if (yellow > threshold && yellow >= cyanBlue) return 'ДП';
    if (cyanBlue > threshold && cyanBlue > yellow) return 'А-95';
    return '';
  }

  function extractFields(text) {
    const clean = text.replace(/\u00a0/g, ' ');
    const upper = clean.toUpperCase();

    let azs = '';
    if (upper.includes('ОККО') || upper.includes('OKKO')) azs = 'ОККО';
    else if (upper.includes('WOG') || upper.includes('ВОГ')) azs = 'WOG';
    else if (upper.includes('УКРНАФТА') || upper.includes('UKRNAFTA')) azs = 'УКРНАФТА';

    let fuel_type = '';
    if (/(?:^|[^а-яіїєґa-z0-9])(?:ДП|ДИЗЕЛЬ|DIESEL)(?![а-яіїєґa-z0-9])/i.test(upper)) fuel_type = 'ДП';
    else if (/(?:А-?95|A-?95|PULLS\s*95)/i.test(upper)) fuel_type = 'А-95';
    else if (/(?:А-?92|A-?92)/i.test(upper)) fuel_type = 'А-92';
    else if (/(?:^|[^а-яіїєґa-z0-9])(?:ГАЗ|LPG)(?![а-яіїєґa-z0-9])/i.test(upper)) fuel_type = 'Газ';

    let nominal = '';
    const mNom = clean.match(/(?:^|[^\d.,])(\d+(?:[.,]\d+)?)\s*(?:л|l|літр)(?![а-яіїєґa-z])/i);
    if (mNom) nominal = mNom[1].replace(',', '.');

    let expires_at = '';
    let mExp = clean.match(/(?:дійсний\s+до|термін\s+(?:дії|придатності)|придатний\s+до|до)\s*[:\-]?\s*(\d{2})\.(\d{2})\.(\d{4})/i);
    if (!mExp) mExp = clean.match(/\b(\d{2})\.(\d{2})\.(\d{4})\b/);
    if (mExp) expires_at = `${mExp[3]}-${mExp[2]}-${mExp[1]}`;

    let serial_number = '';
    for (const line of clean.split(/\r?\n/)) {
      const s = line.trim();
      if (/^\d{6,28}$/.test(s)) { serial_number = s; break; }
    }
    if (!serial_number) {
      const mSer = clean.match(/\b(\d{10,28})\b/);
      if (mSer) serial_number = mSer[1];
    }

    return { azs, fuel_type, nominal, expires_at, serial_number };
  }

  async function processPdf(file) {
    coupons = [];
    setStatus(`Читаю ${file.name}...`, 10);
    const buf = await file.arrayBuffer();
    const pdf = await pdfjsLib.getDocument({ data: buf }).promise;
    const defaultFuel = $('defaultFuel').value;

    for (let p = 1; p <= pdf.numPages; p++) {
      setStatus(`Обробка сторінки ${p} з ${pdf.numPages}...`, Math.round((p / pdf.numPages) * 90));
      const page = await pdf.getPage(p);
      const scale = 2.5;
      const viewport = page.getViewport({ scale });

      const canvas = document.createElement('canvas');
      canvas.width = Math.floor(viewport.width);
      canvas.height = Math.floor(viewport.height);
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      await page.render({ canvasContext: ctx, viewport }).promise;

      const textContent = await page.getTextContent();
      const boxes = detectCardBoxes(canvas);

      for (const box of boxes) {
        // Collect text items inside this box (in viewport pixel coordinates)
        const itemsInBox = [];
        for (const item of textContent.items) {
          const tx = pdfjsLib.Util.transform(viewport.transform, item.transform);
          const ix = tx[4];
          const iy = tx[5];
          if (ix >= box.x0 - 15 && ix <= box.x1 + 15 && iy >= box.y0 - 15 && iy <= box.y1 + 15) {
            itemsInBox.push({ str: item.str, x: ix, y: iy });
          }
        }
        // Sort top-to-bottom, left-to-right and join into lines
        itemsInBox.sort((a, b) => Math.abs(a.y - b.y) > 4 ? a.y - b.y : a.x - b.x);
        let text = '';
        let prevY = null;
        for (const it of itemsInBox) {
          if (prevY !== null && Math.abs(it.y - prevY) > 4) text += '\n';
          else if (text.length && !text.endsWith('\n')) text += ' ';
          text += it.str;
          prevY = it.y;
        }

        const fields = extractFields(text);
        if (!fields.serial_number && !fields.nominal) continue;

        // Crop box with small padding & ensure longest side >= 950px
        const pad = 6;
        const sx = Math.max(0, box.x0 - pad);
        const sy = Math.max(0, box.y0 - pad);
        const sw = Math.min(canvas.width - sx, (box.x1 - box.x0) + pad * 2);
        const sh = Math.min(canvas.height - sy, (box.y1 - box.y0) + pad * 2);

        const longest = Math.max(sw, sh);
        const upScale = longest < 950 ? 950 / longest : 1;

        const cropCanvas = document.createElement('canvas');
        cropCanvas.width = Math.round(sw * upScale);
        cropCanvas.height = Math.round(sh * upScale);
        const cropCtx = cropCanvas.getContext('2d');
        cropCtx.drawImage(canvas, sx, sy, sw, sh, 0, 0, cropCanvas.width, cropCanvas.height);

        const bannerFuel = detectBannerFuelType(cropCanvas);
        coupons.push({
          fuel_type: defaultFuel || fields.fuel_type || bannerFuel,
          azs: fields.azs,
          nominal: fields.nominal,
          expires_at: fields.expires_at,
          quantity: 1,
          serial_number: fields.serial_number,
          note: '',
          image_base64: cropCanvas.toDataURL('image/png'),
        });
      }
    }

    if (!defaultFuel && coupons.length) {
      const fuels = new Set(coupons.map((c) => c.fuel_type).filter(Boolean));
      if (fuels.size === 1) {
        const autoFuel = Array.from(fuels)[0];
        $('defaultFuel').value = autoFuel;
        shadow.querySelectorAll('.fuel-pill').forEach((b) => {
          b.classList.toggle('active', b.dataset.fuel === autoFuel);
        });
      }
    }

    renderTable();
    setStatus(`Готово! Розпізнано талонів: ${coupons.length}. Перевір поля і натисни «Залити всі в CRM».`, 100);
  }

  function renderTable() {
    $('tableWrap').style.display = coupons.length ? 'block' : 'none';
    $('uploadBtn').textContent = `Залити всі в CRM (${coupons.length})`;
    const tbody = $('tbody');
    tbody.innerHTML = '';

    coupons.forEach((c, idx) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${idx + 1}</td>
        <td><img class="thumb" src="${c.image_base64}" /></td>
        <td>
          <select class="${!c.fuel_type ? 'missing' : ''}" data-k="fuel_type">
            <option value="">Оберіть...</option>
            ${['ДП', 'А-95', 'А-92', 'Газ'].map(v => `<option value="${v}" ${c.fuel_type === v ? 'selected' : ''}>${v}</option>`).join('')}
          </select>
        </td>
        <td>
          <select class="${!c.azs ? 'missing' : ''}" data-k="azs">
            <option value="">Оберіть...</option>
            ${['ОККО', 'WOG', 'УКРНАФТА'].map(v => `<option value="${v}" ${c.azs === v ? 'selected' : ''}>${v}</option>`).join('')}
          </select>
        </td>
        <td style="width: 82px;"><input type="number" step="0.01" class="${!c.nominal ? 'missing' : ''}" data-k="nominal" value="${c.nominal}" /></td>
        <td style="width: 135px;"><input type="date" class="${!c.expires_at ? 'missing' : ''}" data-k="expires_at" value="${c.expires_at}" /></td>
        <td style="width: 65px;"><input type="number" min="1" max="20" data-k="quantity" value="${c.quantity}" /></td>
        <td style="min-width: 175px;"><input type="text" data-k="serial_number" value="${c.serial_number}" /></td>
        <td style="min-width: 120px;"><input type="text" data-k="note" value="${c.note}" placeholder="Необов'язково" /></td>
        <td><button class="btn btn-danger" data-del="${idx}">✕</button></td>
      `;
      tr.querySelectorAll('[data-k]').forEach((el) => {
        el.addEventListener('change', () => {
          const k = el.dataset.k;
          coupons[idx][k] = k === 'quantity' ? Number(el.value) : el.value;
          el.classList.toggle('missing', !el.value && k !== 'note' && k !== 'serial_number');
        });
      });
      tr.querySelector('[data-del]').addEventListener('click', () => {
        coupons.splice(idx, 1);
        renderTable();
      });
      tbody.appendChild(tr);
    });
  }

  $('applyBulkBtn').addEventListener('click', () => {
    const f = $('bulkFuel').value;
    const a = $('bulkAzs').value;
    const n = $('bulkNote').value;
    coupons.forEach((c) => {
      if (f) c.fuel_type = f;
      if (a) c.azs = a;
      if (n !== '') c.note = n;
    });
    renderTable();
  });

  $('uploadBtn').addEventListener('click', async () => {
    const invalid = coupons.findIndex(c => !c.fuel_type || !c.azs || !c.nominal || !c.expires_at);
    if (invalid !== -1) {
      alert(`Заповни обов'язкові поля у рядку #${invalid + 1} (або скористайся «Застосувати до всіх»).`);
      return;
    }
    const form = document.querySelector('form[action$="/admin/tickets"]');
    const tokenInput = form?.querySelector('input[name="_token"]') || document.querySelector('input[name="_token"]');
    if (!tokenInput || !tokenInput.value) {
      alert('Не знайдено CSRF _token на сторінці. Онови сторінку та спробуй ще раз.');
      return;
    }
    if (!confirm(`Додати ${coupons.length} талон(ів) у базу TermoUnion CRM?`)) return;

    const postUrl = form?.getAttribute('action') || '/admin/tickets';
    let currentToken = tokenInput.value;

    $('uploadBtn').disabled = true;
    let ok = 0;
    let fail = 0;

    for (let i = 0; i < coupons.length; i++) {
      const c = coupons[i];
      setStatus(`Завантажую ${i + 1} з ${coupons.length} (${c.serial_number})...`, Math.round(((i + 1) / coupons.length) * 100));

      const body = new URLSearchParams({
        _token: currentToken,
        fuel_type: c.fuel_type,
        azs: c.azs,
        nominal: String(c.nominal),
        expires_at: c.expires_at,
        quantity: String(c.quantity || 1),
        serial_number: c.serial_number || '',
        note: c.note || '',
        photo_data: c.image_base64 || '',
      });

      try {
        const res = await fetch(postUrl, {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: body.toString(),
        });
        if (res.ok) {
          ok++;
          const html = await res.text();
          const mTok = html.match(/name=["']_token["'][^>]*value=["']([^"']+)["']/i)
            || html.match(/value=["']([^"']+)["'][^>]*name=["']_token["']/i);
          if (mTok && mTok[1]) currentToken = mTok[1];
        } else {
          fail++;
        }
      } catch {
        fail++;
      }
    }

    setStatus(`Готово! Додано: ${ok}, помилок: ${fail}. Оновлюю сторінку...`, 100);
    setTimeout(() => window.location.reload(), 1200);
  });
})();
