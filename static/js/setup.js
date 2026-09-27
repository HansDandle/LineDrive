// LineDrive settings / first-run setup
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const initial = window.LINEDRIVE_SETTINGS || {};
  const toastEl = $('toast');

  function toast(msg, isError) {
    toastEl.textContent = msg;
    toastEl.classList.toggle('error', !!isError);
    toastEl.classList.add('show');
    clearTimeout(toast._t);
    toast._t = setTimeout(() => toastEl.classList.remove('show'), 4000);
  }

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === 'class') node.className = v;
      else if (k === 'text') node.textContent = v;
      else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? '' : v);
    }
    children.flat().forEach((c) => c != null && c !== false && node.append(c));
    return node;
  }

  async function getJSON(url) {
    const r = await fetch(url);
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || 'Request failed (' + r.status + ')');
    return data;
  }

  async function postJSON(url, body) {
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || 'Request failed (' + r.status + ')');
    return data;
  }

  // ---- Tuner ------------------------------------------------------------------

  const devicesBox = $('devices');
  const ipInput = $('hdhrIp');

  async function findTuners() {
    try {
      const { devices } = await getJSON('/api/setup/discover');
      devicesBox.replaceChildren();
      if (!devices.length) {
        devicesBox.append(el('p', { class: 'muted', text: 'No tuners found automatically. Type its address below (it’s in the HDHomeRun app or your router’s device list).' }));
        return;
      }
      devices.forEach((d) => {
        const pick = el('button', {
          type: 'button', class: 'device' + (d.ip === ipInput.value ? ' selected' : ''),
          onclick: () => { ipInput.value = d.ip; checkTuner(); markSelected(); },
        }, el('strong', { text: d.name }), el('span', { class: 'muted small', text: d.ip + ' · ' + d.tuners + ' tuners' + (d.model ? ' · ' + d.model : '') }));
        pick.dataset.ip = d.ip;
        devicesBox.append(pick);
      });
      if (!ipInput.value && devices.length === 1) {
        ipInput.value = devices[0].ip;
        checkTuner();
      }
      markSelected();
    } catch (e) {
      devicesBox.replaceChildren(el('p', { class: 'muted', text: 'Couldn’t search the network: ' + e.message }));
    }
  }

  function markSelected() {
    devicesBox.querySelectorAll('.device').forEach((b) => b.classList.toggle('selected', b.dataset.ip === ipInput.value.trim()));
  }

  async function checkTuner() {
    const ip = ipInput.value.trim();
    const result = $('tunerResult');
    if (!ip) return;
    result.textContent = 'Checking…';
    result.className = 'field-note';
    try {
      const data = await getJSON('/api/setup/lineup?ip=' + encodeURIComponent(ip));
      result.textContent = data.warning ? data.warning
        : '✓ ' + data.device.name + ': ' + data.device.tuners + ' tuners, ' + data.channels + ' channels';
      result.className = 'field-note ' + (data.warning ? 'warn' : 'ok');
      showMajors(data.majors);
    } catch (e) {
      result.textContent = e.message;
      result.className = 'field-note bad';
      $('distantBox').hidden = true;
    }
    markSelected();
  }

  function showMajors(majors) {
    const list = $('distantList');
    const chosen = new Set((initial.distant_channels || []).map(String));
    list.replaceChildren(...majors.map((m) => el('label', { class: 'check' },
      el('input', { type: 'checkbox', value: m.major, checked: chosen.has(String(m.major)) }),
      el('span', {}, el('strong', { text: m.major + '.x ' }), el('span', { class: 'muted small', text: m.channels.slice(0, 3).join(', ') + (m.channels.length > 3 ? '…' : '') })))));
    $('distantBox').hidden = majors.length < 2;
  }

  $('checkTuner').addEventListener('click', checkTuner);
  ipInput.addEventListener('change', checkTuner);

  // ---- Time zone ----------------------------------------------------------------

  const tzSelect = $('timezone');
  const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const zones = (Intl.supportedValuesOf && Intl.supportedValuesOf('timeZone')) || [browserTz];
  zones.forEach((z) => tzSelect.append(el('option', { value: z, text: z.replace(/_/g, ' ') })));
  tzSelect.value = tzSelect.dataset.value || '';
  $('tzNote').textContent = 'Leave as “This computer’s time zone” unless LineDrive runs somewhere with a different clock setting. Your browser is on ' + browserTz.replace(/_/g, ' ') + '.';

  // ---- Tests --------------------------------------------------------------------

  function values() {
    const v = (id) => ($(id) ? $(id).value.trim() : '');
    return {
      hdhr_ip: v('hdhrIp'), zip_code: v('zipCode'), timezone: tzSelect.value, recordings: v('recordings'),
      distant_channels: Array.from(document.querySelectorAll('#distantList input:checked')).map((c) => c.value),
      jellyfin: { url: v('jfUrl'), api_key: v('jfKey'), recordings_path: v('jfPath') },
      jellyseerr: { url: v('jsUrl'), api_key: v('jsKey') },
      mqtt: { host: v('mqHost'), port: v('mqPort'), username: v('mqUser'), password: v('mqPass') },
    };
  }

  document.querySelectorAll('.test-btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const kind = btn.dataset.kind;
      const out = document.querySelector('[data-result="' + kind + '"]');
      const all = values();
      const body = kind === 'zip' ? { zip_code: all.zip_code } : all[kind];
      out.textContent = 'Testing…';
      out.className = 'field-note';
      btn.disabled = true;
      try {
        const r = await postJSON('/api/setup/test', Object.assign({ kind }, body));
        out.textContent = (r.ok ? '✓ ' : '') + r.message;
        out.className = 'field-note ' + (r.ok ? 'ok' : 'bad');
      } catch (e) {
        out.textContent = e.message;
        out.className = 'field-note bad';
      } finally {
        btn.disabled = false;
      }
    });
  });

  // ---- Save ---------------------------------------------------------------------

  $('setupForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = $('saveBtn');
    const out = $('saveResult');
    btn.disabled = true;
    out.className = 'field-note';
    try {
      const r = await postJSON('/api/setup/save', values());
      out.textContent = r.message;
      // Wait for the restart, then go home
      await new Promise((ok) => setTimeout(ok, 2500));
      for (let i = 0; i < 40; i++) {
        try {
          const s = await fetch('/api/status', { cache: 'no-store' });
          if (s.ok) { location.href = '/'; return; }
        } catch (err) { /* still restarting */ }
        await new Promise((ok) => setTimeout(ok, 1000));
      }
      out.textContent = 'Saved, but LineDrive hasn’t come back yet. Check that it’s running, then reload.';
      out.className = 'field-note bad';
    } catch (err) {
      out.textContent = err.message;
      out.className = 'field-note bad';
      toast(err.message, true);
      btn.disabled = false;
    }
  });

  if (ipInput.value) checkTuner();
  findTuners();
})();
