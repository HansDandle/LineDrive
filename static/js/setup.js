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
      $('stationBox').hidden = true;
    }
    markSelected();
  }

  // ---- Stations: out of market / hidden --------------------------------------------
  // One row per station (major number). Out of market: prefer local stations for the same show.
  // Hide: leave its channels out of the guide. A station with several channels expands (▸) so
  // single subchannels can be hidden; its own box is then half-ticked.

  let stations = [];
  let signals = {};
  const openStations = new Set();

  const stationRows = () => Array.from(document.querySelectorAll('#stationList .major'));

  function stationState() {
    const rows = stationRows();
    if (!rows.length) {
      return { distant: new Set((initial.distant_channels || []).map(String)),
               hidden: new Set((initial.hidden_channels || []).map(String)) };
    }
    const distant = new Set(), hidden = new Set();
    rows.forEach((r) => {
      if (r._distant.checked) distant.add(r._major);
      r._subs.forEach((s) => { if (s.box.checked) hidden.add(s.num); });
    });
    return { distant, hidden };
  }

  function signalNote(nums) {
    const s = nums.map((n) => signals[n]).filter(Boolean);
    return !s.length ? '' : s.every((x) => !x.locked) ? 'no signal' : s.some((x) => x.locked && x.weak) ? 'weak' : '';
  }

  function stationRow(m, distant, hidden) {
    const major = String(m.major);
    const subs = m.channels.map((c) => {
      const num = c.split(' ')[0];
      const box = el('input', { type: 'checkbox', checked: hidden.has(num), 'aria-label': 'Hide ' + num });
      const note = signalNote([num]);
      const row = el('div', { class: 'station sub' + (box.checked ? ' hidden-station' : '') },
        el('span', { class: 'station-name' }, el('strong', { text: num + ' ' }), c.slice(num.length).trim(),
          note && el('span', { class: 'sig-note small', text: ' · ' + note })),
        el('span'), el('label', {}, box));
      return { num, box, row };
    });
    const distantBox = el('input', { type: 'checkbox', checked: distant.has(major), 'aria-label': major + '.x out of market' });
    const hideBox = el('input', { type: 'checkbox', 'aria-label': 'Hide all of ' + major + '.x' });
    const multi = subs.length > 1;
    const toggle = multi ? el('button', { type: 'button', class: 'expand', 'aria-label': 'Show ' + major + '.x channels' }) : null;
    const note = signalNote(subs.map((s) => s.num));
    const row = el('div', { class: 'station major' },
      el('span', { class: 'station-name' }, toggle || el('span', { class: 'expand-space' }),
        el('strong', { text: major + '.x ' }),
        el('span', { class: 'muted small', text: m.channels.slice(0, 3).join(', ') + (m.channels.length > 3 ? '…' : '') }),
        note && el('span', { class: 'sig-note small', text: ' · ' + note })),
      el('label', {}, distantBox), el('label', {}, hideBox));
    const list = el('div', { class: 'subs' }, subs.map((s) => s.row));

    function sync() {
      const n = subs.filter((s) => s.box.checked).length;
      hideBox.checked = n === subs.length;
      hideBox.indeterminate = n > 0 && n < subs.length;
      row.classList.toggle('hidden-station', hideBox.checked);
      subs.forEach((s) => s.row.classList.toggle('hidden-station', s.box.checked));
    }
    function setOpen(open) {
      list.hidden = !open;
      if (toggle) {
        toggle.textContent = open ? '▾' : '▸';
        toggle.setAttribute('aria-expanded', String(open));
      }
      if (open) openStations.add(major); else openStations.delete(major);
    }
    row._setHidden = (on) => { subs.forEach((s) => { s.box.checked = on; }); sync(); };
    hideBox.addEventListener('change', () => { row._setHidden(hideBox.checked); saveStations(); });
    subs.forEach((s) => s.box.addEventListener('change', () => { sync(); saveStations(); }));
    distantBox.addEventListener('change', saveStations);
    if (toggle) toggle.addEventListener('click', () => setOpen(list.hidden));
    sync();
    // Open when only some of its channels are hidden, so that's visible
    setOpen(multi && (openStations.has(major) || hideBox.indeterminate));
    Object.assign(row, { _major: major, _nums: subs.map((s) => s.num), _subs: subs, _distant: distantBox, _hide: hideBox });
    return [row, list];
  }

  function showMajors(majors) {
    const { distant, hidden } = stationState();
    if (majors) stations = majors;
    const head = el('div', { class: 'station head' }, el('span'), el('span', { text: 'Out of market' }), el('span', { text: 'Hide' }));
    $('stationList').replaceChildren(head, ...stations.flatMap((m) => stationRow(m, distant, hidden)));
    $('stationBox').hidden = !stations.length;
  }

  // Each tick is saved straight away (these don't need a restart)
  async function saveStations() {
    const { distant, hidden } = stationState();
    try {
      await postJSON('/api/setup/stations', { distant_channels: Array.from(distant), hidden_channels: Array.from(hidden) });
      toast('Saved');
    } catch (err) {
      toast('Couldn’t save: ' + err.message, true);
    }
  }

  async function loadSignals() {
    try {
      signals = (await getJSON('/api/signal')).channels || {};
      if (stations.length) showMajors();
    } catch (e) { /* no readings yet */ }
  }

  loadSignals();

  $('checkTuner').addEventListener('click', checkTuner);
  ipInput.addEventListener('change', checkTuner);

  // ---- Signal scan -----------------------------------------------------------------

  async function scanSignal() {
    const button = $('scanSignal');
    const result = $('signalResult');
    button.disabled = true;
    try {
      await postJSON('/api/signal/scan', {});
      for (;;) {
        await new Promise((r) => setTimeout(r, 1500));
        const { channels, scan } = await getJSON('/api/signal');
        if (scan.scanning) {
          result.textContent = 'Checking… ' + scan.done + ' of ' + scan.total + ' channels';
          result.className = 'field-note';
          continue;
        }
        const all = Object.entries(channels);
        const weak = all.filter(([, s]) => s.locked && s.weak).map(([n]) => n);
        const none = all.filter(([, s]) => !s.locked).map(([n]) => n);
        result.textContent = '✓ Checked ' + all.length + ' channels. ' +
          (weak.length ? 'Weak: ' + weak.join(', ') + '. ' : '') +
          (none.length ? 'No signal: ' + none.join(', ') + '.' : '') +
          (!weak.length && !none.length ? 'All good.' : '');
        result.className = 'field-note ' + (weak.length || none.length ? 'warn' : 'ok');
        signals = channels;
        showMajors();
        const poor = stationRows()
          .filter((r) => !r._hide.checked && r._nums.some((n) => weak.includes(n) || none.includes(n)));
        if (poor.length) {
          const tick = el('button', { type: 'button', class: 'btn', text: 'Tick Hide on these ' + poor.length + ' stations' });
          tick.addEventListener('click', () => {
            poor.forEach((r) => r._setHidden(true));
            tick.remove();
            $('stationBox').scrollIntoView({ behavior: 'smooth', block: 'center' });
            saveStations();
          });
          result.append(' ', tick);
        }
        break;
      }
    } catch (e) {
      result.textContent = e.message;
      result.className = 'field-note bad';
    } finally {
      button.disabled = false;
    }
  }

  if ($('scanSignal')) $('scanSignal').addEventListener('click', scanSignal);

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
      quality: v('quality'),
      captions: $('captions').checked, nfo: $('nfo').checked,
      // Only once the tuner's stations are listed, so a tuner that didn't answer doesn't clear them
      distant_channels: stations.length ? Array.from(stationState().distant) : undefined,
      hidden_channels: stations.length ? Array.from(stationState().hidden) : undefined,
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
