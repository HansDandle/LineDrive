// LineDrive program guide: scrollable channel x time grid with one-tap recording
(function () {
  'use strict';

  const grid = document.getElementById('grid');
  const daysNav = document.getElementById('days');
  const search = document.getElementById('search');
  const toastEl = document.getElementById('toast');

  const state = {
    day: 0,
    data: null,
    days: [],
    selected: null,   // { channel, program }
    query: '',
    loading: false,
  };

  const pxPerMin = () => (window.matchMedia('(max-width: 700px)').matches ? 4 : 5);
  const chanWidth = () => parseFloat(getComputedStyle(document.body).getPropertyValue('--chan-w')) || 128;
  const nowSec = () => Date.now() / 1000;

  // TV mode (Fire TV Silk and other TV browsers, or ?tv=1): those browsers scroll the page with a
  // pointer or the D-pad and can't reach an inner scroll box, so the page scrolls vertically and
  // time moves with Earlier/Later buttons, the D-pad, and rewind/fast-forward.
  const params = new URLSearchParams(location.search);
  const TV = params.get('tv') === '1' ||
    (params.get('tv') !== '0' && /\b(AFT\w*|Silk|CrKey|SMART-TV|SmartTV|Tizen|Web0S|WebOS|BRAVIA|Android TV)\b/i.test(navigator.userAgent));
  if (TV) document.body.classList.add('tv');
  state.offset = 0; // TV mode: how far the time window has slid, in px

  // The time ruler pins just below the (pinned) header in TV mode
  function measureHeader() {
    const h = document.querySelector('.guide-header').offsetHeight;
    document.documentElement.style.setProperty('--header-h', h + 'px');
  }
  if (TV) {
    measureHeader();
    window.addEventListener('resize', measureHeader);
  }

  function getX() {
    return TV ? state.offset : grid.scrollLeft;
  }

  function setX(x) {
    if (!TV) {
      grid.scrollLeft = x;
      return;
    }
    const canvas = grid.querySelector('.canvas');
    const trackW = state.trackW || 0;
    const visible = grid.clientWidth - chanWidth();
    state.offset = Math.max(0, Math.min(Math.round(x), Math.max(0, trackW - visible)));
    if (canvas) canvas.style.setProperty('--offset', state.offset + 'px');
    pinLabels();
    updateNow();
  }

  function getY() {
    return TV ? window.scrollY : grid.scrollTop;
  }

  function setY(y) {
    if (TV) window.scrollTo(0, y);
    else grid.scrollTop = y;
  }

  function pageTime(minutes) {
    setX(getX() + minutes * pxPerMin());
  }

  // Bring a show into view: scroll vertically as needed and shift the time window horizontally
  function ensureVisible(b) {
    b.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    const visible = grid.clientWidth - chanWidth();
    const x = getX();
    if (b._x < x) setX(b._x - 20);
    else if (b._x + Math.min(b._w, visible - 40) > x + visible) setX(b._x + Math.min(b._w, visible - 40) - visible + 20);
  }

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  function fmt(epochSec, opts) {
    const tz = state.data && state.data.timezone;
    try {
      return new Intl.DateTimeFormat(undefined, Object.assign({ timeZone: tz }, opts)).format(new Date(epochSec * 1000));
    } catch (e) {
      return new Intl.DateTimeFormat(undefined, opts).format(new Date(epochSec * 1000));
    }
  }

  function toast(msg, isError) {
    toastEl.textContent = msg;
    toastEl.classList.toggle('error', !!isError);
    toastEl.classList.add('show');
    clearTimeout(toast._t);
    toast._t = setTimeout(() => toastEl.classList.remove('show'), 3500);
  }

  // ---- Data -------------------------------------------------------------

  async function load(day, opts) {
    opts = opts || {};
    if (state.loading) return;
    state.loading = true;
    const keepScroll = opts.keepScroll ? { x: getX(), y: getY() } : null;
    if (!opts.silent) showStatus('Loading guide…');
    try {
      const res = await fetch('/api/guide?day=' + day + '&hours=24');
      if (!res.ok) throw new Error('Guide request failed (' + res.status + ')');
      const data = await res.json();
      state.day = day;
      state.data = data;
      buildDays();
      render();
      if (keepScroll) {
        setX(keepScroll.x);
        setY(keepScroll.y);
      } else if (day === 0) {
        scrollToNow();
      } else {
        setX(0);
      }
      if (TV && !opts.silent) focusFirst();
    } catch (err) {
      showStatus('Couldn’t load the guide. ' + err.message, true);
    } finally {
      state.loading = false;
    }
  }

  async function post(url, body) {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || data.message || 'Request failed');
    return data;
  }

  // ---- Rendering --------------------------------------------------------

  function showStatus(msg, withRetry) {
    grid.replaceChildren();
    const box = el('div', 'status', msg);
    if (withRetry) {
      const retry = el('button', 'btn-ghost', 'Try again');
      retry.type = 'button';
      retry.addEventListener('click', () => load(state.day));
      box.append(el('br'), retry);
    }
    grid.append(box);
  }

  function buildDays() {
    const data = state.data;
    const count = data.guide_end ? Math.max(1, Math.ceil((data.guide_end - (data.window.start - state.day * 86400)) / 86400)) : 1;
    const firstMidnight = data.window.start - state.day * 86400;
    daysNav.replaceChildren();
    for (let i = 0; i < Math.min(count, 14); i++) {
      const b = el('button', 'day');
      b.type = 'button';
      const t = firstMidnight + i * 86400 + 12 * 3600; // noon avoids DST edge cases
      b.textContent = i === 0 ? 'Today' : i === 1 ? 'Tomorrow' : fmt(t, { weekday: 'short', month: 'short', day: 'numeric' });
      b.setAttribute('aria-pressed', String(i === state.day));
      b.addEventListener('click', () => { if (i !== state.day) load(i); });
      daysNav.append(b);
    }
    if (TV) measureHeader();
  }

  function render() {
    const data = state.data;
    const ppm = pxPerMin();
    const winStart = data.window.start;
    const winEnd = data.window.end;
    const trackW = Math.round(((winEnd - winStart) / 60) * ppm);
    const now = nowSec();

    const canvas = el('div', 'canvas');
    state.trackW = trackW;
    // TV mode: the canvas is screen-wide and the tracks slide by --offset; otherwise it's
    // full width and the grid scrolls natively
    if (!TV) canvas.style.width = chanWidth() + trackW + 'px';

    // Time ruler
    const ruler = el('div', 'ruler');
    const corner = el('div', 'corner', fmt(winStart + 43200, { weekday: 'short' }) + ' ' + fmt(winStart + 43200, { day: 'numeric' }));
    if (TV) {
      corner.textContent = '';
      const earlier = el('button', 'page-btn', '◀');
      earlier.type = 'button';
      earlier.title = 'Earlier';
      earlier.addEventListener('click', () => pageTime(-120));
      const later = el('button', 'page-btn', '▶');
      later.type = 'button';
      later.title = 'Later';
      later.addEventListener('click', () => pageTime(120));
      corner.append(earlier, later);
    }
    ruler.append(corner);
    const ticks = el('div', 'ticks');
    ticks.style.width = trackW + 'px';
    for (let t = winStart; t < winEnd; t += 1800) {
      const tick = el('div', 'tick' + ((t - winStart) % 3600 ? ' half' : ''), fmt(t, { hour: 'numeric', minute: '2-digit' }));
      tick.style.left = Math.round(((t - winStart) / 60) * ppm) + 'px';
      ticks.append(tick);
    }
    ruler.append(ticks);
    canvas.append(ruler);

    if (!data.channels.length) {
      grid.replaceChildren(canvas);
      canvas.append(el('div', 'status', 'No channels found. Check the HDHomeRun connection in setup.'));
      return;
    }

    // Channels without listings go last so the grid opens on watchable rows
    const ordered = data.channels.filter((c) => c.programs.length).concat(data.channels.filter((c) => !c.programs.length));
    state.rows = [];
    for (const ch of ordered) {
      const row = el('div', 'row');
      const rowBlocks = [];
      state.rows.push(rowBlocks);
      const chan = el('div', 'chan');
      const num = el('span', 'chan-num', ch.number);
      if (ch.signal) num.append(signalBars(ch.signal));
      chan.append(num, el('span', 'chan-name', ch.name));
      chan.title = ch.call_sign ? ch.name + ' (' + ch.call_sign + ')' : ch.name;
      const track = el('div', 'track' + (ch.programs.length ? '' : ' empty'));
      track.style.width = trackW + 'px';

      for (const p of ch.programs) {
        const left = Math.max(p.start, winStart);
        const right = Math.min(p.end, winEnd);
        const x = Math.round(((left - winStart) / 60) * ppm);
        const w = Math.max(Math.round(((right - left) / 60) * ppm) - 3, 8);
        const b = el('button', 'prog');
        b.type = 'button';
        b.style.left = x + 'px';
        b.style.width = w + 'px';
        if (w < 90) b.classList.add('tiny');
        const label = el('span', 'label');
        label.append(el('span', 't', p.title || 'Untitled'));
        label.append(el('span', 's', p.episode_title ? shortTime(p.time) + ' · ' + p.episode_title : shortTime(p.time)));
        b.append(label);
        b.title = p.title + (p.episode_title ? ' — ' + p.episode_title : '') + '\n' + shortTime(p.time) + ' (' + p.duration + ' min)';
        b._x = x;
        b._w = w;
        b._label = label;
        b._prog = p;
        b._chan = ch;
        b._row = state.rows.length - 1;
        b._col = rowBlocks.length;
        rowBlocks.push(b);
        classify(b, now);
        b.addEventListener('click', () => openPanel(ch, p, b));
        track.append(b);
      }
      row.append(chan, track);
      canvas.append(row);
    }

    const line = el('div', 'now-line');
    line.id = 'nowLine';
    canvas.append(line);

    grid.replaceChildren(canvas);
    state.blocks = Array.from(grid.querySelectorAll('.prog'));
    if (TV) canvas.style.setProperty('--offset', state.offset + 'px');
    applySearch();
    updateNow();
    pinLabels();
  }

  function signalBars(s) {
    const bars = el('span', 'sig' + (!s.locked ? ' none' : s.weak ? ' weak' : ''));
    for (let i = 1; i <= 4; i++) bars.append(el('i', i <= Math.max(s.bars, s.locked ? 0 : 1) ? 'on' : ''));
    bars.title = signalText(s);
    return bars;
  }

  function signalText(s) {
    if (!s.locked) return 'No signal when last checked';
    const level = ['', 'Poor', 'Weak', 'Good', 'Excellent'][s.bars];
    return level + ' signal · quality ' + s.snq + '%, strength ' + s.ss + '%' +
      (s.seq < 100 ? ', some errors' : '');
  }

  function renderSignal(ch) {
    const box = panelEls.signal;
    const s = ch.signal;
    box.replaceChildren();
    box.classList.toggle('weak', !!(s && s.weak));
    let text = s ? signalText(s) : 'Signal not checked yet';
    if (s && s.weak) text += ' — recordings may break up';
    if (s && s.at) text += ' · ' + ago(s.at);
    box.append(document.createTextNode(text));
    const check = el('button', 'link', 'Check now');
    check.type = 'button';
    check.addEventListener('click', async () => {
      check.disabled = true;
      check.textContent = 'Checking…';
      try {
        const res = await post('/api/signal/check', { channel: ch.number });
        ch.signal = res.signal;
        renderSignal(ch);
        load(state.day, { keepScroll: true, silent: true });
      } catch (err) {
        toast(err.message, true);
        check.disabled = false;
        check.textContent = 'Check now';
      }
    });
    box.append(check);
  }

  function ago(iso) {
    const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
    if (mins < 2) return 'just now';
    if (mins < 90) return mins + ' min ago';
    if (mins < 36 * 60) return Math.round(mins / 60) + ' h ago';
    return Math.round(mins / 1440) + ' days ago';
  }

  // ---- D-pad / arrow-key navigation between shows -------------------------

  function focusProg(b) {
    if (!b) return;
    b.focus({ preventScroll: true });
    ensureVisible(b);
  }

  // The show in another row that's on at the same time as `b` (or the closest one)
  function sameTimeIn(rowIndex, b) {
    const row = state.rows[rowIndex];
    if (!row || !row.length) return null;
    const mid = b._x + Math.min(b._w, 200) / 2;
    return row.find((o) => o._x <= mid && mid < o._x + o._w) ||
      row.reduce((best, o) => (Math.abs(o._x - mid) < Math.abs(best._x - mid) ? o : best), row[0]);
  }

  function focusFirst() {
    const now = nowSec();
    const row = (state.rows || []).find((r) => r.length);
    if (!row) return;
    const b = row.find((o) => o._prog.start <= now && now < o._prog.end) || row[0];
    b.focus({ preventScroll: true });
  }

  grid.addEventListener('keydown', (e) => {
    const b = e.target.closest && e.target.closest('.prog');
    if (!b || !state.rows) return;
    let next = null;
    if (e.key === 'ArrowRight') next = state.rows[b._row][b._col + 1];
    else if (e.key === 'ArrowLeft') next = state.rows[b._row][b._col - 1];
    else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      const step = e.key === 'ArrowDown' ? 1 : -1;
      for (let r = b._row + step; r >= 0 && r < state.rows.length; r += step) {
        next = sameTimeIn(r, b);
        if (next) break;
      }
      if (!next && step < 0) {
        // Past the top row: go up to the day tabs / Earlier-Later buttons
        e.preventDefault();
        const up = grid.querySelector('.page-btn') || daysNav.querySelector('[aria-pressed="true"]');
        if (up) up.focus();
        return;
      }
    } else {
      return;
    }
    e.preventDefault();
    focusProg(next);
  });

  // Keep the title of a show that started off-screen visible at the left edge
  function pinLabels() {
    const edge = getX();
    for (const b of state.blocks || []) {
      const shift = edge > b._x && edge < b._x + b._w - 60 ? Math.min(edge - b._x, b._w - 60) : 0;
      if (b._shift !== shift) {
        b._label.style.transform = shift ? 'translateX(' + shift + 'px)' : '';
        b._shift = shift;
      }
    }
  }
  let pinQueued = false;
  grid.addEventListener('scroll', () => {
    if (pinQueued) return;
    pinQueued = true;
    requestAnimationFrame(() => { pinQueued = false; pinLabels(); });
  }, { passive: true });

  function shortTime(t) {
    return (t || '').replace(/^0/, '');
  }

  function classify(b, now) {
    const p = b._prog;
    b.classList.toggle('past', p.end <= now);
    b.classList.toggle('airing', p.start <= now && now < p.end);
    b.classList.toggle('rec', !!p.recording);
    b.classList.toggle('series', !!(p.recording && p.recording.kind === 'series'));
  }

  function updateNow() {
    const line = document.getElementById('nowLine');
    if (!line || !state.data) return;
    const now = nowSec();
    const { start, end } = state.data.window;
    if (now < start || now >= end) {
      line.style.display = 'none';
    } else {
      const x = Math.round(((now - start) / 60) * pxPerMin()) - (TV ? state.offset : 0);
      line.style.display = TV && x < 0 ? 'none' : '';
      line.style.left = chanWidth() + x + 'px';
      line.style.top = getComputedStyle(document.documentElement).getPropertyValue('--ruler-h');
    }
    grid.querySelectorAll('.prog').forEach((b) => classify(b, now));
  }

  function scrollToNow() {
    if (!state.data) return;
    const { start, end } = state.data.window;
    const now = nowSec();
    if (now < start || now >= end) return;
    const x = ((now - start) / 60) * pxPerMin();
    setX(Math.max(0, x - 30 * pxPerMin()));
  }

  // ---- Search -----------------------------------------------------------

  function applySearch() {
    const canvas = grid.querySelector('.canvas');
    if (!canvas) return;
    const q = state.query;
    canvas.classList.toggle('searching', !!q);
    let first = null;
    grid.querySelectorAll('.prog').forEach((b) => {
      const p = b._prog;
      const hit = !!q && ((p.title || '').toLowerCase().includes(q) || (p.episode_title || '').toLowerCase().includes(q));
      b.classList.toggle('match', hit);
      if (hit && !first && p.end > nowSec()) first = b;
    });
    return first;
  }

  search.addEventListener('input', () => {
    state.query = search.value.trim().toLowerCase();
    applySearch();
  });
  search.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    const first = applySearch();
    if (first) {
      if (TV) focusProg(first);
      else {
        first.scrollIntoView({ block: 'center', inline: 'center', behavior: 'smooth' });
        first.focus({ preventScroll: true });
      }
    } else if (state.query) {
      toast('No upcoming match on this day');
    }
  });

  // ---- Details panel ----------------------------------------------------

  const panelEls = {
    channel: document.getElementById('pChannel'),
    title: document.getElementById('pTitle'),
    episode: document.getElementById('pEpisode'),
    when: document.getElementById('pWhen'),
    meta: document.getElementById('pMeta'),
    recording: document.getElementById('pRecording'),
    signal: document.getElementById('pSignal'),
    art: document.getElementById('pArt'),
    desc: document.getElementById('pDesc'),
    actions: document.getElementById('pActions'),
  };

  function actionButton(label, sub, cls, handler) {
    const b = el('button', cls || '');
    b.type = 'button';
    b.append(document.createTextNode(label));
    if (sub) b.append(el('small', '', sub));
    b.addEventListener('click', async () => {
      panelEls.actions.querySelectorAll('button').forEach((x) => (x.disabled = true));
      try {
        const res = await handler();
        if (res === false) return;
        toast(res.message || 'Done');
        closePanel();
        await load(state.day, { keepScroll: true, silent: true });
      } catch (err) {
        toast(err.message, true);
      } finally {
        panelEls.actions.querySelectorAll('button').forEach((x) => (x.disabled = false));
      }
    });
    return b;
  }

  function openPanel(ch, p, btn) {
    grid.querySelectorAll('.prog.selected').forEach((b) => b.classList.remove('selected'));
    btn.classList.add('selected');
    state.selected = { ch, p, btn };

    panelEls.channel.textContent = ch.number + ' · ' + ch.name;
    panelEls.title.textContent = p.title || 'Untitled';
    const se = [p.season && 'S' + p.season, p.episode && 'E' + p.episode].filter(Boolean).join(' ');
    panelEls.episode.textContent = [se, p.episode_title].filter(Boolean).join(' · ');
    panelEls.when.textContent =
      fmt(p.start, { weekday: 'long', month: 'short', day: 'numeric' }) + ', ' +
      fmt(p.start, { hour: 'numeric', minute: '2-digit' }) + '–' + fmt(p.end, { hour: 'numeric', minute: '2-digit' }) +
      ' (' + p.duration + ' min)';
    panelEls.meta.textContent = [p.new && 'New', p.genre, p.rating].filter(Boolean).join(' · ');
    panelEls.desc.textContent = p.description || '';
    panelEls.art.hidden = !p.image;
    if (p.image) {
      panelEls.art.onerror = () => { panelEls.art.hidden = true; };
      panelEls.art.src = p.image;
    } else {
      panelEls.art.removeAttribute('src');
    }
    renderSignal(ch);

    const now = nowSec();
    const rec = p.recording;
    const airing = p.start <= now && now < p.end;
    panelEls.recording.textContent = p.recording_now ? '● Recording now' : !rec ? '' :
      rec.kind === 'series' ? '● Recording as a series' + (rec.description ? ': ' + rec.description : '') :
      '● Scheduled to record';

    const actions = panelEls.actions;
    actions.replaceChildren();
    const body = { channel_number: ch.number, date: p.date, time: p.time };
    const minutesLeft = Math.max(1, Math.ceil((p.end - now) / 60));

    if (p.end <= now) {
      actions.append(el('p', 'p-meta', 'This has already aired.'));
    } else {
      if (airing && !p.recording_now) {
        actions.append(actionButton('Record the rest', 'Starts now · ' + minutesLeft + ' min left', 'primary',
          () => post('/api/guide/record', Object.assign({ mode: 'episode' }, body))));
      } else if (airing) {
        actions.append(el('p', 'p-meta', 'Recording now. Stop it from the home page.'));
      }
      if (rec && rec.kind === 'series') {
        actions.append(actionButton('Cancel series', 'Stops all future recordings of this time slot', 'danger', () => {
          if (!confirm('Cancel the series recording for “' + p.title + '”?')) return false;
          return post('/api/guide/cancel', { job_id: rec.job_id });
        }));
        return openPanelFinish(actions);
      }
      if (rec && !airing) {
        actions.append(actionButton('Cancel this recording', null, 'danger', () => post('/api/guide/cancel', { job_id: rec.job_id })));
      } else if (!airing) {
        actions.append(actionButton('Record this episode', fmt(p.start, { weekday: 'short' }) + ' ' + shortTime(p.time) + ' on ' + ch.number, 'primary',
          () => post('/api/guide/record', Object.assign({ mode: 'episode' }, body))));
      }
      actions.append(actionButton('Record series', 'Every airing of “' + p.title + '” on ' + ch.number + ' in this time slot'
        + (airing && !p.recording_now ? ', starting with this one' : ''), '',
        () => post('/api/guide/record', Object.assign({ mode: 'series' }, body))));
    }
    openPanelFinish(actions);
  }

  function openPanelFinish(actions) {
    document.body.classList.add('panel-open');
    document.getElementById('panel').setAttribute('aria-hidden', 'false');
    const first = actions.querySelector('button') || document.getElementById('panelClose');
    first.focus({ preventScroll: true });
    // On a TV the remote's Back button means "browser back": make it close the panel instead
    if (!state.panelHistory) {
      history.pushState({ panel: true }, '');
      state.panelHistory = true;
    }
  }

  window.addEventListener('popstate', () => {
    if (state.panelHistory) {
      state.panelHistory = false;
      closePanel();
    }
  });

  function closePanel() {
    if (state.panelHistory) {
      // Closed with a button/Escape: drop the history entry the panel added (popstate re-enters here)
      history.back();
      return;
    }
    document.body.classList.remove('panel-open');
    document.getElementById('panel').setAttribute('aria-hidden', 'true');
    if (state.selected && state.selected.btn.isConnected) state.selected.btn.focus({ preventScroll: true });
    grid.querySelectorAll('.prog.selected').forEach((b) => b.classList.remove('selected'));
    state.selected = null;
  }

  document.getElementById('panelClose').addEventListener('click', closePanel);
  document.getElementById('scrim').addEventListener('click', closePanel);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && document.body.classList.contains('panel-open')) closePanel();
    // Remote rewind / fast-forward (Fire TV sends key codes 227 / 228): three hours earlier / later
    const rewind = e.key === 'MediaRewind' || e.keyCode === 227;
    const ffwd = e.key === 'MediaFastForward' || e.keyCode === 228;
    if ((rewind || ffwd) && !document.body.classList.contains('panel-open')) {
      e.preventDefault();
      pageTime(rewind ? -180 : 180);
      return;
    }
    if (e.key === '/' && document.activeElement !== search) {
      e.preventDefault();
      search.focus();
    }
  });

  document.getElementById('nowBtn').addEventListener('click', () => {
    if (state.day !== 0) load(0);
    else scrollToNow();
  });

  // Keep the now-line and airing states current; refresh schedule badges periodically
  setInterval(updateNow, 30 * 1000);
  setInterval(() => {
    if (!document.hidden && !document.body.classList.contains('panel-open')) load(state.day, { keepScroll: true, silent: true });
  }, 5 * 60 * 1000);

  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { if (state.data) render(); }, 150);
  });

  load(0);
})();
