// LineDrive home page
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const resultDiv = $('result');
  const torrentResultsDiv = $('torrentResults');
  const toastEl = $('toast');

  // ---- Helpers ------------------------------------------------------------

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === 'class') node.className = v;
      else if (k === 'text') node.textContent = v;
      else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? '' : v);
    }
    for (const c of children.flat()) {
      if (c != null && c !== false) node.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return node;
  }

  function toast(msg, isError) {
    toastEl.textContent = msg;
    toastEl.classList.toggle('error', !!isError);
    toastEl.classList.add('show');
    clearTimeout(toast._t);
    // Long messages (a tuner-clash heads-up) stay up long enough to read
    toast._t = setTimeout(() => toastEl.classList.remove('show'), Math.max(4000, msg.length * 60));
  }

  async function postJSON(url, body) {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || data.message || 'Request failed (' + res.status + ')');
    return data;
  }

  function humanSize(bytes) {
    let n = typeof bytes === 'number' ? bytes : parseFloat(bytes);
    if (!isFinite(n)) return '—';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
    return n.toFixed(n >= 10 ? 0 : 1) + ' ' + units[i];
  }

  function withBusy(button, label, fn) {
    return async (...args) => {
      const original = button.textContent;
      button.disabled = true;
      if (label) button.textContent = label;
      try { return await fn(...args); }
      finally { button.disabled = false; button.textContent = original; }
    };
  }

  // ---- Live status ----------------------------------------------------------

  const statusCard = $('statusCard');

  function renderStatus(s) {
    const recs = s.recording || [];
    statusCard.classList.toggle('is-recording', recs.length > 0);
    statusCard.classList.toggle('is-idle', recs.length === 0);
    // Stop does nothing more once every recording is already being finalized
    $('stopBtn').hidden = !recs.some((r) => !r.finishing);

    if (recs.length) {
      const r = recs.find((x) => !x.finishing) || recs[0];
      $('statusLabel').textContent = recs.length > 1 ? 'Recording ' + recs.length + ' shows'
        : r.finishing ? 'Finishing…' : 'Recording now';
      $('statusTitle').textContent = r.title || 'Channel ' + r.channel_number;
      $('statusSub').textContent = r.channel_number + ' · ' + r.channel_name + ' · ' +
        (r.finishing ? 'saving the file, this can take a few minutes' : r.minutes_left + ' min left');
    } else if (s.next) {
      const n = s.next;
      $('statusLabel').textContent = 'Up next';
      $('statusTitle').textContent = n.title + (n.episode ? ': ' + n.episode : '');
      $('statusSub').textContent = n.when + ' · ' + n.channel_number + ' ' + n.channel_name;
    } else {
      $('statusLabel').textContent = 'Idle';
      $('statusTitle').textContent = 'Nothing scheduled';
      $('statusSub').textContent = 'Pick something from the guide to record it.';
    }

    renderUpcoming(s.upcoming || [], s);

    renderTuners(s.tuners, s.this_pc);

    const notices = s.notices || [];
    $('noticeBox').hidden = !notices.length;
    $('noticeList').replaceChildren(...notices.map((n) => el('p', { text: n.message })));

    const failures = s.failures || [];
    $('failureBox').hidden = !failures.length;
    $('failureList').replaceChildren(...failures.map((f) =>
      el('p', {}, el('strong', { text: 'Didn’t record ' + f.title }), ' (' + f.channel_number + ', ' + f.when + '): ' + f.reason)));

    const list = $('recentList');
    list.replaceChildren();
    if (!s.recent || !s.recent.length) {
      list.append(el('li', { class: 'muted', text: 'No recordings yet.' }));
    } else {
      for (const f of s.recent) {
        list.append(el('li', {},
          el('span', { class: 'recent-name', title: f.name, text: f.name }),
          el('span', { class: 'muted small', text: f.when + ' · ' + humanSize(f.size) })));
      }
    }
  }

  async function refreshStatus() {
    try {
      const res = await fetch('/api/status');
      if (res.ok) renderStatus(await res.json());
    } catch (e) {
      $('statusLabel').textContent = 'Offline';
      $('statusTitle').textContent = 'Can’t reach LineDrive';
      $('statusSub').textContent = '';
    }
  }

  // Tuners, with a kill switch for streams other apps left open
  function renderTuners(tuners, thisPc) {
    const list = $('tunerList');
    if (!tuners) {
      list.replaceChildren(el('li', { class: 'tuner warn', text: 'Can’t reach the HDHomeRun' }));
      return;
    }
    list.replaceChildren(...tuners.map((t) => {
      const label = 'Tuner ' + (t.index + 1) + ': ';
      if (!t.in_use) return el('li', { class: 'tuner' }, label, el('span', { class: 'tuner-free', text: 'free' }));
      const who = t.ours ? 'LineDrive' : (t.target_ip === thisPc ? 'another app on this PC' : 'another device (' + t.target_ip + ')');
      const item = el('li', { class: 'tuner' + (t.ours ? '' : ' other') },
        label, el('strong', { text: t.channel_number + ' ' + t.channel_name }), ' · ' + who);
      if (!t.ours) {
        item.append(' ', el('button', {
          type: 'button', class: 'btn btn-quiet btn-sm', text: 'Free up',
          title: 'Stop this stream so LineDrive can use the tuner',
          onclick: async (e) => {
            const where = t.target_ip === thisPc ? 'another app on this PC (like Jellyfin or Plex)' : t.target_ip;
            if (!confirm('Stop the ' + t.channel_number + ' ' + t.channel_name + ' stream used by ' + where +
                         '? Anyone watching it there will be cut off.')) return;
            e.currentTarget.disabled = true;
            try {
              const data = await postJSON('/api/tuners/' + t.index + '/release');
              toast(data.message || 'Tuner freed');
            } catch (err) { toast(err.message, true); }
            setTimeout(refreshStatus, 1500);
          },
        }));
      }
      return item;
    }));
  }

  $('dismissNotices').addEventListener('click', async () => {
    await postJSON('/api/status/dismiss_notices').catch(() => {});
    refreshStatus();
  });

  $('dismissFailures').addEventListener('click', async () => {
    await postJSON('/api/status/dismiss_failures').catch(() => {});
    refreshStatus();
  });

  $('stopBtn').addEventListener('click', async () => {
    if (!confirm('Stop the current recording? The file recorded so far is kept.')) return;
    try {
      const data = await postJSON('/stop_recording');
      toast(data.message || 'Stopping…');
      setTimeout(refreshStatus, 2500);
    } catch (e) { toast(e.message, true); }
  });

  // ---- Upcoming -------------------------------------------------------------

  // Keep/delete setting for a series: a small menu under its title
  function keepMenu(item, status) {
    const choices = (status.keep_choices || []).filter(([value]) =>
      status.jellyfin || !value.startsWith('watched:') || value === item.keep);
    if (!choices.some(([value]) => value === item.keep)) choices.push([item.keep, item.keep]);
    const select = el('select', { class: 'keep-select', 'aria-label': 'What to keep of ' + item.title,
      title: 'Removed recordings go to the .deleted folder in your recordings for 7 days',
      onchange: async (e) => {
        try {
          const data = await postJSON('/api/rules/' + item.id, { keep: e.target.value });
          toast(data.message);
          refreshStatus();
        } catch (err) { toast(err.message, true); e.target.value = item.keep; }
      } },
      choices.map(([value, label]) => el('option', { value, text: label, selected: value === item.keep })));
    return el('label', { class: 'keep' }, select);
  }

  function renderUpcoming(items, status) {
    status = status || {};
    const list = $('upcomingList');
    // The 30-second refresh would close a Keep menu someone has open
    if (document.activeElement && document.activeElement.tagName === 'SELECT' && list.contains(document.activeElement)) return;
    $('upcomingCount').textContent = items.length;
    $('upcomingEmpty').hidden = items.length > 0;
    list.hidden = items.length === 0;
    list.replaceChildren(...items.map((item) => {
      const cancel = el('button', { type: 'button', class: 'btn btn-quiet btn-sm', text: item.watch ? 'Stop watching' : 'Cancel' });
      cancel.addEventListener('click', () => cancelRecording(item));
      const kind = item.watch ? el('span', { class: 'tag tag-watch', text: 'Watching' })
        : el('span', { class: item.series ? 'tag tag-series' : 'tag', text: item.series ? 'Series' : 'Once' });
      const where = item.watch ? item.repeat
        : [item.channel_number + ' · ' + item.channel_name, item.repeat].filter(Boolean).join(' · ');
      let newOnly = null;
      if (item.series && !item.guide_series) {
        // Switch: record reruns too, or new episodes only
        newOnly = el('label', { class: 'switch', title: 'Skip airings the guide lists as reruns' },
          el('input', { type: 'checkbox', checked: item.new_only,
            onchange: async (e) => {
              try {
                const data = await postJSON('/api/rules/' + item.id, { new_only: e.target.checked });
                toast(data.message);
                refreshStatus();
              } catch (err) { toast(err.message, true); e.target.checked = !e.target.checked; }
            } }),
          el('span', { text: 'New only' }));
      }
      const clash = item.clash && el('span', { class: 'tag tag-clash', title: item.clash.message,
        text: 'No free tuner' + (item.clash.next ? '' : ' ' + item.clash.when) });
      return el('li', { class: 'up-item' + (item.airing ? ' is-airing' : '') + (item.skip ? ' is-skipped' : '') },
        el('div', { class: 'up-when' },
          el('span', { class: 'up-time', text: item.when }),
          !item.watch && el('span', { class: 'up-dur', text: item.duration + ' min' })),
        el('div', { class: 'up-body' },
          el('p', { class: 'up-title' }, item.title, kind,
            item.airing && el('span', { class: 'tag tag-live', text: 'On now' }),
            item.skip && el('span', { class: 'tag', text: item.skip_reason === 'already recorded' ? 'Already have it, will skip' : 'Rerun, will skip' }),
            clash),
          item.episode && el('p', { class: 'up-episode', text: item.episode }),
          item.clash && el('p', { class: 'up-clash small', text: item.clash.message }),
          el('p', { class: 'muted small', text: where }),
          (newOnly || (item.series && item.keep)) && el('div', { class: 'up-options' },
            newOnly, item.series && item.keep && keepMenu(item, status))),
        cancel);
    }));
  }

  async function cancelRecording(item) {
    const question = item.watch ? 'Stop watching for “' + item.title + '”?' : item.series
      ? 'Cancel the series recording for “' + item.title + '”? Future airings won’t be recorded.'
      : 'Cancel the recording of “' + item.title + '”?';
    if (!confirm(question)) return;
    try {
      const data = await postJSON('/api/guide/cancel', { job_id: item.id });
      toast(data.message || 'Cancelled');
      refreshStatus();
    } catch (e) { toast(e.message, true); }
  }

  // ---- Manual recording ---------------------------------------------------------

  const tabs = [[$('tabNow'), $('panelNow')], [$('tabRepeat'), $('panelRepeat')]];
  tabs.forEach(([tab, panel]) => {
    tab.addEventListener('click', () => {
      tabs.forEach(([t, p]) => {
        t.setAttribute('aria-selected', String(t === tab));
        p.hidden = p !== panel;
      });
    });
  });

  // Encoding comes from Settings -> Recording quality
  function encoding() {
    return {};
  }

  function chosenChannel() {
    const ch = $('channel').value;
    if (!ch) {
      toast('Choose a channel first', true);
      $('channel').focus();
    }
    return ch;
  }

  const recordNowBtn = $('recordNowBtn');
  recordNowBtn.addEventListener('click', withBusy(recordNowBtn, 'Starting…', async () => {
    const channel = chosenChannel();
    if (!channel) return;
    try {
      const data = await postJSON('/record_now', Object.assign({
        channel, duration: parseInt($('duration').value, 10) || 30,
      }, encoding()));
      toast(data.message || 'Recording started');
      setTimeout(refreshStatus, 1500);
    } catch (e) { toast(e.message, true); }
  }));

  const scheduleBtn = $('scheduleBtn');
  scheduleBtn.addEventListener('click', withBusy(scheduleBtn, 'Saving…', async () => {
    const channel = chosenChannel();
    if (!channel) return;
    const days = Array.from(document.querySelectorAll('input[name="days"]:checked')).map((cb) => cb.value);
    if (!days.length) return toast('Pick at least one day', true);
    if (!$('time').value) return toast('Pick a start time', true);
    try {
      const data = await postJSON('/schedule', Object.assign({
        channel, days, time: $('time').value, duration: parseInt($('repeatDuration').value, 10) || 30,
      }, encoding()));
      toast(data.message || 'Schedule saved');
      refreshStatus();
    } catch (e) { toast(e.message, true); }
  }));

  // ---- Settings / folder / downloads ----------------------------------------------

  $('openFolderBtn').addEventListener('click', async () => {
    try {
      const j = await postJSON('/open_recordings_folder');
      toast(j.status === 'ok' ? 'Opened on the LineDrive PC' : (j.error || 'Could not open folder'), j.status !== 'ok');
    } catch (e) { toast('Could not open folder: ' + e.message, true); }
  });

  const autoCatBtn = $('autoCategorizeBtn');
  if (autoCatBtn) {
    autoCatBtn.addEventListener('click', withBusy(autoCatBtn, 'Categorizing…', async () => {
      try {
        const data = await postJSON('/auto_categorize');
        toast(data.message || 'Done', !data.success);
      } catch (e) { toast(e.message, true); }
    }));
  }

  // ---- Ask LineDrive (natural-language commands) -------------------------------------

  function showResult(content, isError) {
    resultDiv.hidden = false;
    resultDiv.classList.toggle('error', !!isError);
    resultDiv.replaceChildren(...[].concat(content));
  }

  function showMessageOrRaw(data) {
    const r = data.result || {};
    const msg = r.message || r.error || data.message || data.error;
    if (msg) showResult(el('p', { text: msg }), !!(r.error || data.error));
    else showResult(el('pre', { text: JSON.stringify(data, null, 2) }));
  }

  async function sendCommand(command) {
    return postJSON('/nlp_command', { command });
  }

  const form = $('nlpForm');
  const input = $('commandInput');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const command = input.value.trim();
    if (!command) return;
    showResult(el('p', { class: 'muted', text: 'Working on it…' }));
    torrentResultsDiv.hidden = true;
    try {
      const data = await sendCommand(command);
      const r = data.result || {};
      if (r.status === 'guide_results') {
        renderGuideAnswer(r);
      } else if (r.status === 'media_results') {
        renderMediaResults(r);
      } else if (Array.isArray(r.episodes)) {
        renderEpisodeSelection(r);
      } else if (r.status === 'search_results' && r.torrents) {
        showResult(el('p', { text: r.message || '' }));
        renderTorrentCandidates(r);
      } else if (r.status === 'record_candidates') {
        renderRecordCandidates(r);
      } else {
        showMessageOrRaw(data);
        if (r.status && /schedul|record|rule/.test(r.status)) refreshStatus();
      }
    } catch (err) {
      showResult(el('p', { text: err.message }), true);
    }
  });

  // Speech recognition (Web Speech API)
  const micBtn = $('micBtn');
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (Recognition) {
    const recognition = new Recognition();
    recognition.lang = 'en-US';
    recognition.interimResults = false;
    micBtn.addEventListener('click', () => { recognition.start(); micBtn.classList.add('active'); });
    recognition.onresult = (event) => { input.value = event.results[0][0].transcript; };
    recognition.onend = recognition.onerror = () => micBtn.classList.remove('active');
  } else {
    micBtn.hidden = true;
  }

  // Example questions
  document.querySelectorAll('.chip[data-ask]').forEach((chip) => {
    chip.addEventListener('click', () => {
      input.value = chip.dataset.ask;
      form.requestSubmit();
    });
  });

  // "download X": Jellyseerr matches with Request buttons (+ TV airings this week, if any)
  function renderMediaResults(r) {
    const cards = r.items.map((m) => {
      const actions = el('div', { class: 'ans-actions' });
      if (m.status === 5) {
        actions.append(el('span', { class: 'media-have', text: '✓ In library' }));
      } else if (m.status_label) {
        actions.append(el('span', { class: 'ans-rec', text: m.status_label }));
      } else {
        const label = m.media_type === 'tv'
          ? (m.seasons ? 'Request season' + (m.seasons.length > 1 ? 's ' : ' ') + m.seasons.join(', ') : 'Request all seasons')
          : 'Request';
        actions.append(el('button', {
          type: 'button', class: 'btn btn-sm btn-primary', text: label,
          onclick: async (e) => {
            const btn = e.currentTarget;
            btn.disabled = true;
            try {
              const data = await postJSON('/api/media/request',
                { media_type: m.media_type, id: m.id, seasons: m.seasons, title: m.title });
              toast(data.message || 'Requested');
              actions.replaceChildren(el('span', { class: 'ans-rec', text: 'Requested' }));
            } catch (err) {
              toast(err.message, true);
              btn.disabled = false;
            }
          },
        }));
      }
      const poster = m.poster
        ? el('img', { class: 'media-poster', src: m.poster, alt: '', loading: 'lazy' })
        : el('div', { class: 'media-poster empty' });
      return el('li', { class: 'media-item' },
        poster,
        el('div', { class: 'ans-body' },
          el('p', { class: 'ans-title' }, m.title + (m.year ? ' (' + m.year + ')' : ''),
            el('span', { class: 'tag', text: m.media_type === 'tv' ? 'Show' : 'Movie' })),
          m.overview && el('p', { class: 'muted small media-overview', text: m.overview })),
        actions);
    });
    const parts = [el('p', { class: 'ans-message', text: r.message }), el('ul', { class: 'ans-list' }, cards)];
    if (r.airings && r.airings.length) {
      parts.push(el('p', { class: 'muted small', text: 'It’s also on TV this week, if you’d rather record it:' }),
        el('ul', { class: 'ans-list' }, guideCards(r.airings)));
    }
    showResult(parts);
  }

  // Answers from the guide: a sentence plus cards with Record / Series buttons
  function renderGuideAnswer(r) {
    const cards = guideCards(r.programs || []);
    const parts = [el('p', { class: 'ans-message', text: r.message })];
    if (cards.length) parts.push(el('ul', { class: 'ans-list' }, cards));
    if (r.total > cards.length) {
      parts.push(el('p', { class: 'muted small' }, 'Showing ' + cards.length + ' of ' + r.total + '. ',
        el('a', { href: '/guide', text: 'Browse the full guide' })));
    }
    showResult(parts);
  }

  // One card per guide airing, with Record / Series buttons
  function guideCards(programs) {
    return programs.map((p) => {
      const actions = el('div', { class: 'ans-actions' });
      const airing = p.start * 1000 <= Date.now() && Date.now() < p.end * 1000;
      const setRecorded = (label) => {
        actions.replaceChildren(el('span', { class: 'ans-rec', text: '● ' + label }));
      };
      const body = { channel_number: p.channel_number, date: p.date, time: p.time };
      const rec = (mode) => async (e) => {
        const btn = e.currentTarget;
        btn.disabled = true;
        try {
          const data = await postJSON('/api/guide/record', Object.assign({ mode }, body));
          toast(data.message || 'Scheduled');
          setRecorded(airing ? 'Recording now' : mode === 'series' ? 'Recording series' : 'Will record');
          refreshStatus();
        } catch (err) {
          toast(err.message, true);
          btn.disabled = false;
        }
      };
      if (p.recording_now) {
        setRecorded('Recording now');
      } else if (airing) {
        // On now: capture the rest of it (a scheduled rule or episode may have been missed)
        actions.append(el('button', { type: 'button', class: 'btn btn-sm btn-record', onclick: rec('episode'),
          text: 'Record rest', title: 'Start recording now through the end of the show' }));
        if (!p.recording || p.recording.kind !== 'series') {
          actions.append(el('button', { type: 'button', class: 'btn btn-sm', onclick: rec('series'), text: 'Series' }));
        }
      } else if (p.recording) {
        setRecorded(p.recording.kind === 'series' ? 'Recording series' : 'Will record');
      } else if (p.end * 1000 > Date.now()) {
        actions.append(el('button', { type: 'button', class: 'btn btn-sm btn-record', onclick: rec('episode'), text: 'Record' }));
        actions.append(el('button', { type: 'button', class: 'btn btn-sm', onclick: rec('series'), text: 'Series' }));
      }
      const tags = [];
      if (p.airing) tags.push(el('span', { class: 'tag tag-live', text: 'On now' }));
      (p.flags || []).filter((f) => f === 'Live' || f === 'New' || f === 'Premiere')
        .forEach((f) => tags.push(el('span', { class: 'tag', text: f })));
      const channels = p.channel_number + ' · ' + p.channel_name + (p.also_on.length ? ' (also ' + p.also_on.join(', ') + ')' : '');
      return el('li', { class: 'ans-item' },
        el('div', { class: 'ans-when', text: p.when }),
        el('div', { class: 'ans-body' },
          el('p', { class: 'ans-title' }, p.title, tags),
          p.episode_title && el('p', { class: 'ans-episode', text: p.episode_title }),
          el('p', { class: 'muted small', text: channels + ' · ' + p.duration + ' min' })),
        actions);
    });
  }

  // Recording candidates (e.g. which game the user meant)
  function renderRecordCandidates(r) {
    const candidates = r.candidates || [];
    if (!candidates.length) return showResult(el('p', { class: 'muted', text: 'No matching airings found.' }));
    const pick = (option, recurring) => async () => {
      showResult(el('p', { class: 'muted', text: recurring ? 'Creating series…' : 'Scheduling…' }));
      try {
        const data = await sendCommand((recurring ? 'record recurring option ' : 'record option ') + option);
        showMessageOrRaw(data);
        refreshStatus();
      } catch (e) { showResult(el('p', { text: e.message }), true); }
    };
    const rows = candidates.map((c) => [
      el('tr', { class: 'torrent-row-title' },
        el('td', { rowspan: 2, text: c.option || '?' }),
        el('td', {}, el('span', { class: 'full-title', text: c.title || 'Unknown show' })),
        el('td', { rowspan: 2 },
          el('button', { type: 'button', class: 'btn btn-sm btn-primary', onclick: pick(c.option, false), text: 'Once' }), ' ',
          el('button', { type: 'button', class: 'btn btn-sm', onclick: pick(c.option, true), text: 'Series' })),
        el('td', { rowspan: 2 })),
      el('tr', { class: 'torrent-row-meta' },
        el('td', {}, ['Date: ' + (c.date || '?'), 'Time: ' + (c.time || '?'), 'Channel: ' + (c.channel || '?'),
          'Length: ' + (c.duration || '?')].map((t) => el('span', { class: 'torrent-badge', text: t })))),
    ]);
    showResult([
      el('p', { class: 'muted small', text: r.message || 'Pick the airing you meant:' }),
      el('table', { class: 'torrent-table' },
        el('thead', {}, el('tr', {}, el('th', { text: '#' }), el('th', { text: 'Show' }), el('th'), el('th'))),
        el('tbody', {}, rows)),
    ]);
  }

  // Torrent search results
  function renderTorrentCandidates(r) {
    const torrents = r.torrents || [];
    torrentResultsDiv.hidden = false;
    if (!torrents.length) {
      torrentResultsDiv.replaceChildren(el('p', { class: 'muted', text: 'No results.' }));
      return;
    }
    const now = Date.now();
    const checks = [];
    const addOne = (option) => async () => {
      try {
        showMessageOrRaw(await sendCommand('download option ' + option));
      } catch (e) { toast(e.message, true); }
    };
    const rows = torrents.map((t) => {
      let age = '';
      if (t.time) {
        const hours = Math.round((now - new Date(t.time).getTime()) / 3600000);
        if (isFinite(hours)) age = hours < 24 ? hours + 'h' : Math.round(hours / 24) + 'd';
      }
      const cb = el('input', { type: 'checkbox', class: 'torrent-select', 'aria-label': 'Select option ' + t.option });
      cb.dataset.option = t.option;
      checks.push(cb);
      const badges = ['Seeds: ' + (t.seeders || t.seeds || 0), 'Size: ' + humanSize(t.size_bytes || t.size || (t.raw && t.raw.size)),
        'Uploader: ' + (t.uploader || (t.raw && t.raw.uploader) || 'Unknown')].concat(age ? ['Age: ' + age] : []);
      return [
        el('tr', { class: 'torrent-row-title' },
          el('td', { rowspan: 2, text: t.option || '?' }),
          el('td', {}, el('span', { class: 'full-title', text: t.title || '' })),
          el('td', { rowspan: 2 }, el('button', { type: 'button', class: 'btn btn-sm btn-primary', onclick: addOne(t.option), text: 'Get' })),
          el('td', { rowspan: 2 }, cb)),
        el('tr', { class: 'torrent-row-meta' }, el('td', {}, badges.map((b) => el('span', { class: 'torrent-badge', text: b })))),
      ];
    });
    const setAll = (v) => checks.forEach((c) => (c.checked = v));
    const addSelected = async () => {
      const selected = checks.filter((c) => c.checked).map((c) => c.dataset.option);
      if (!selected.length) return toast('Select at least one result', true);
      try {
        showMessageOrRaw(await sendCommand('download options ' + selected.join(',')));
      } catch (e) { toast(e.message, true); }
    };
    torrentResultsDiv.replaceChildren(
      el('h3', { text: 'Download results' }),
      el('div', { class: 'toolbar' },
        el('button', { type: 'button', class: 'btn btn-sm', onclick: () => setAll(true), text: 'Select all' }),
        el('button', { type: 'button', class: 'btn btn-sm', onclick: () => setAll(false), text: 'Clear' }),
        el('button', { type: 'button', class: 'btn btn-sm btn-primary', onclick: addSelected, text: 'Add selected' })),
      el('table', { class: 'torrent-table' },
        el('thead', {}, el('tr', {}, el('th', { text: '#' }), el('th', { text: 'Result' }), el('th'), el('th'))),
        el('tbody', {}, rows)));
  }

  // Season episode picker for series downloads
  function renderEpisodeSelection(r) {
    const episodes = r.episodes;
    const boxes = episodes.map((ep, i) => {
      const cb = el('input', { type: 'checkbox', id: 'episode_' + i, checked: !!ep.selected });
      const size = typeof ep.size === 'string' ? ep.size : humanSize(ep.size);
      return { cb, row: el('label', { class: 'episode-card', for: 'episode_' + i },
        cb,
        el('span', {}, el('strong', { text: ep.title || '' }), el('br'), el('span', { class: 'muted small', text: ep.name || '' })),
        el('span', { class: 'meta', text: [ep.quality, size, ep.seeders != null ? ep.seeders + ' seeds' : ''].filter(Boolean).join(' · ') })) };
    });
    const download = el('button', { type: 'button', class: 'btn btn-sm btn-primary', text: 'Download selected' });
    download.addEventListener('click', withBusy(download, 'Downloading…', async () => {
      const selected = episodes.filter((_, i) => boxes[i].cb.checked).map((ep) => Object.assign({}, ep, { selected: true }));
      if (!selected.length) return toast('Select at least one episode', true);
      try {
        const result = await postJSON('/bulk_download', { episodes: selected });
        toast(result.message || 'Download started', !result.success);
        if (result.results) {
          resultDiv.append(el('div', {}, result.results.map((x) =>
            el('p', { class: x.success ? '' : 'muted', text: (x.success ? '✓ ' : '✗ ') + x.title + ' — ' + x.message }))));
        }
      } catch (e) { toast(e.message, true); }
    }));
    showResult([
      el('h3', { text: (r.series || 'Series') + (r.season ? ' · Season ' + r.season : '') }),
      el('p', { class: 'muted small', text: episodes.length + ' episodes found' }),
      el('div', { class: 'toolbar' },
        el('button', { type: 'button', class: 'btn btn-sm', onclick: () => boxes.forEach((b) => (b.cb.checked = true)), text: 'Select all' }),
        el('button', { type: 'button', class: 'btn btn-sm', onclick: () => boxes.forEach((b) => (b.cb.checked = false)), text: 'Clear' }),
        download),
      el('div', { class: 'episode-list' }, boxes.map((b) => b.row)),
    ]);
  }

  // ---- Start ---------------------------------------------------------------------------

  refreshStatus();
  setInterval(() => { if (!document.hidden) refreshStatus(); }, 30 * 1000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshStatus(); });

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => navigator.serviceWorker.register('/static/sw.js'));
  }
})();
