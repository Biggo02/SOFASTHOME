(function () {
  'use strict';

  function initPropertyCamera() {
    const form = document.getElementById('propertyForm');
    const plan = document.getElementById('photoPlan');
    if (!form || !plan || plan.dataset.cameraReady === '1') return;

    plan.dataset.cameraReady = '1';
    plan.innerHTML = '';

    const stores = new Map();
    let active = null;
    let stream = null;

    const style = document.createElement('style');
    style.textContent = `
      .pf-photo-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin-top:16px}
      .pf-photo-card{border:1px solid #dce5ec;border-radius:16px;padding:14px;background:#fbfcfd}
      .pf-photo-card h3{margin:0 0 4px;font-size:13px;color:#17212b}
      .pf-photo-card p{margin:0 0 11px;color:#66798a;font-size:10px}
      .pf-photo-actions{display:flex;gap:8px;flex-wrap:wrap}
      .pf-photo-actions button,.pf-photo-actions label{display:inline-flex;align-items:center;justify-content:center;border:1px solid #d3dee6;border-radius:10px;padding:9px 12px;font-size:11px;font-weight:800;cursor:pointer;background:#fff;color:#17212b}
      .pf-photo-actions button:hover,.pf-photo-actions label:hover{border-color:#173f68}
      .pf-photo-actions input{display:none}
      .pf-photo-status{margin-top:9px;font-size:10px;color:#587187;min-height:15px}
      .pf-thumbs{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
      .pf-thumb{width:54px;height:42px;object-fit:cover;border-radius:7px;border:1px solid #dce5ec}
      .pf-camera{position:fixed;inset:0;z-index:10000;background:rgba(5,15,25,.82);display:none;align-items:center;justify-content:center;padding:16px}
      .pf-camera.open{display:flex}
      .pf-camera-box{width:min(650px,100%);background:#fff;border-radius:18px;overflow:hidden;box-shadow:0 25px 80px rgba(0,0,0,.35)}
      .pf-camera-head{display:flex;justify-content:space-between;align-items:center;padding:14px 16px;border-bottom:1px solid #e4e9ed}
      .pf-camera-head strong{font-size:14px}
      .pf-camera-close{border:0;background:#f1f4f6;border-radius:9px;padding:8px 11px;cursor:pointer;font-weight:800}
      .pf-camera-view{background:#0b1219;aspect-ratio:4/3;position:relative;overflow:hidden}
      .pf-camera-view video{width:100%;height:100%;object-fit:cover;display:block}
      .pf-camera-message{padding:22px;text-align:center;color:#fff;font-size:12px}
      .pf-camera-foot{padding:14px 16px;display:flex;gap:9px;justify-content:center;align-items:center;flex-wrap:wrap}
      .pf-capture{border:0;border-radius:999px;background:#173f68;color:#fff;padding:12px 25px;font-weight:900;cursor:pointer;font-size:12px}
      .pf-capture:disabled{opacity:.5;cursor:not-allowed}
      .pf-camera-done{border:1px solid #d3dee6;border-radius:999px;background:#fff;padding:11px 20px;font-weight:800;cursor:pointer}
      .pf-camera-note{width:100%;text-align:center;color:#66798a;font-size:10px}
      @media(max-width:700px){.pf-photo-grid{grid-template-columns:1fr}.pf-camera{padding:0}.pf-camera-box{width:100%;height:100%;border-radius:0;display:flex;flex-direction:column}.pf-camera-view{flex:1;aspect-ratio:auto}.pf-camera-head{flex:none}.pf-camera-foot{flex:none}}
    `;
    document.head.appendChild(style);

    const modal = document.createElement('div');
    modal.className = 'pf-camera';
    modal.innerHTML = `
      <div class="pf-camera-box" role="dialog" aria-modal="true" aria-label="Appareil photo FASTHOME">
        <div class="pf-camera-head"><strong id="pfCameraTitle">Prendre une photo</strong><button type="button" class="pf-camera-close">Fermer</button></div>
        <div class="pf-camera-view"><video autoplay playsinline muted></video><div class="pf-camera-message" hidden></div></div>
        <div class="pf-camera-foot"><button type="button" class="pf-capture" disabled>● Prendre la photo</button><button type="button" class="pf-camera-done">Terminer</button><div class="pf-camera-note">La photo prise est automatiquement ajoutée à cette pièce.</div></div>
      </div>`;
    document.body.appendChild(modal);

    const video = modal.querySelector('video');
    const message = modal.querySelector('.pf-camera-message');
    const capture = modal.querySelector('.pf-capture');

    function closeCamera() {
      if (stream) stream.getTracks().forEach(t => t.stop());
      stream = null;
      video.srcObject = null;
      modal.classList.remove('open');
      active = null;
    }

    async function openCamera(card) {
      active = card;
      const title = card.dataset.roomName || 'Cette pièce';
      modal.querySelector('#pfCameraTitle').textContent = 'Photo — ' + title;
      message.hidden = true;
      message.textContent = '';
      capture.disabled = true;
      modal.classList.add('open');

      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        message.textContent = "La caméra n'est pas disponible dans ce navigateur. Utilisez « Choisir des photos ».";
        message.hidden = false;
        return;
      }

      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false });
        video.srcObject = stream;
        await video.play();
        capture.disabled = false;
      } catch (err) {
        message.textContent = "Impossible d'accéder à la caméra. Autorisez la caméra dans votre navigateur puis réessayez.";
        message.hidden = false;
      }
    }

    function filesFor(card) {
      const input = card.querySelector('input[type=file]');
      if (!stores.has(card)) stores.set(card, new DataTransfer());
      const dt = stores.get(card);
      if (input && input.files.length && dt.files.length === 0) {
        Array.from(input.files).forEach(file => dt.items.add(file));
      }
      return { input, dt };
    }

    function refreshCard(card) {
      const { input, dt } = filesFor(card);
      if (input) input.files = dt.files;
      const count = dt.files.length;
      const status = card.querySelector('.pf-photo-status');
      const thumbs = card.querySelector('.pf-thumbs');
      status.textContent = count ? `${count} photo${count > 1 ? 's' : ''} prête${count > 1 ? 's' : ''} à être téléversée` : 'Aucune photo sélectionnée';
      thumbs.innerHTML = '';
      Array.from(dt.files).forEach(file => {
        const img = document.createElement('img');
        img.className = 'pf-thumb';
        img.alt = 'Aperçu';
        img.src = URL.createObjectURL(file);
        img.onload = () => URL.revokeObjectURL(img.src);
        thumbs.appendChild(img);
      });
    }

    function addFile(card, file) {
      const { dt } = filesFor(card);
      if (dt.files.length >= 5) {
        alert('Maximum 5 photos pour cette pièce.');
        return false;
      }
      const total = Array.from(stores.values()).reduce((sum, x) => sum + x.files.length, 0);
      if (total >= 40) {
        alert('Maximum 40 photos pour le bien.');
        return false;
      }
      dt.items.add(file);
      refreshCard(card);
      return true;
    }

    capture.addEventListener('click', function () {
      if (!active || !stream || video.readyState < 2) return;
      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth || 1280;
      canvas.height = video.videoHeight || 960;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(function (blob) {
        if (!blob) return;
        const stamp = new Date().toISOString().replace(/[:.]/g, '-');
        const safe = (active.dataset.roomName || 'piece').toLowerCase().replace(/[^a-z0-9]+/gi, '-');
        const file = new File([blob], `${safe}-${stamp}.jpg`, { type: 'image/jpeg', lastModified: Date.now() });
        addFile(active, file);
      }, 'image/jpeg', 0.88);
    });

    modal.querySelector('.pf-camera-close').addEventListener('click', closeCamera);
    modal.querySelector('.pf-camera-done').addEventListener('click', closeCamera);
    modal.addEventListener('click', e => { if (e.target === modal) closeCamera(); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && modal.classList.contains('open')) closeCamera(); });

    function counts() {
      const get = n => Math.max(0, parseInt(form.querySelector(`[name="${n}"]`)?.value || '0', 10) || 0);
      return [['Chambre', get('bedrooms')], ['Salon', get('salons')], ['Cuisine', get('kitchens')], ['Salle de bain', get('bathrooms')], ['Toilette', get('toilets')]];
    }

    function render() {
      const previous = new Map();
      plan.querySelectorAll('.pf-photo-card').forEach(card => {
        previous.set(card.dataset.roomKey, stores.get(card));
      });
      plan.innerHTML = '';
      stores.clear();
      const grid = document.createElement('div');
      grid.className = 'pf-photo-grid';
      let number = 0;

      counts().forEach(([type, amount]) => {
        for (let i = 1; i <= amount; i++) {
          number++;
          const key = `${type}-${i}`;
          const card = document.createElement('div');
          card.className = 'pf-photo-card';
          card.dataset.roomKey = key;
          card.dataset.roomName = `${type} ${i}`;
          card.innerHTML = `
            <h3>📷 ${type} ${i}</h3>
            <p>Ajoutez jusqu'à 5 photos de cette pièce.</p>
            <div class="pf-photo-actions">
              <button type="button" class="pf-camera-button">📸 Prendre une photo</button>
              <label>🖼️ Choisir des photos<input type="file" name="photos" accept="image/*" multiple></label>
            </div>
            <div class="pf-photo-status">Aucune photo sélectionnée</div>
            <div class="pf-thumbs"></div>`;

          const saved = previous.get(key);
          if (saved) stores.set(card, saved);
          else stores.set(card, new DataTransfer());

          card.querySelector('.pf-camera-button').addEventListener('click', () => openCamera(card));
          card.querySelector('input[type=file]').addEventListener('change', function () {
            const { dt } = filesFor(card);
            dt.items.clear();
            Array.from(this.files).slice(0, 5).forEach(file => dt.items.add(file));
            this.files = dt.files;
            refreshCard(card);
          });
          refreshCard(card);
          grid.appendChild(card);
        }
      });

      if (!number) {
        const empty = document.createElement('div');
        empty.className = 'section-note';
        empty.textContent = 'Renseignez d’abord le nombre de chambres, salons, cuisines, salles de bain ou toilettes pour faire apparaître les espaces à photographier.';
        plan.appendChild(empty);
      } else {
        plan.appendChild(grid);
      }
    }

    ['bedrooms', 'salons', 'kitchens', 'bathrooms', 'toilets'].forEach(name => {
      const input = form.querySelector(`[name="${name}"]`);
      input?.addEventListener('input', render);
      input?.addEventListener('change', render);
    });

    render();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(initPropertyCamera, 0));
  else setTimeout(initPropertyCamera, 0);
})();
