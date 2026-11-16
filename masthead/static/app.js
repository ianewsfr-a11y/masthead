/* MastHead for Horizon: the interface. Plain JavaScript, no build step, no remote code.
   Every piece of text that comes from a feed or a model is inserted as text, never as HTML. */
(() => {
  'use strict';

  // ---------------------------------------------------------------- DOM helpers
  const SVG_NS = 'http://www.w3.org/2000/svg';

  function h(tag, attrs, ...children) {
    const el = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === null || value === undefined || value === false) continue;
      if (key === 'class') el.className = value;
      else if (key.startsWith('on')) el.addEventListener(key.slice(2), value);
      else if (key === 'text') el.textContent = value;
      else if (value === true) el.setAttribute(key, '');
      else el.setAttribute(key, value);
    }
    for (const child of children.flat(Infinity)) {
      if (child === null || child === undefined || child === false) continue;
      el.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return el;
  }

  const ICONS = {
    domains: [['rect', { x: 4, y: 4, width: 7, height: 7, rx: 1 }], ['rect', { x: 13, y: 4, width: 7, height: 7, rx: 1 }], ['rect', { x: 4, y: 13, width: 7, height: 7, rx: 1 }], ['rect', { x: 13, y: 13, width: 7, height: 7, rx: 1 }]],
    sources: [['path', { d: 'M4 11a9 9 0 0 1 9 9' }], ['path', { d: 'M4 4a16 16 0 0 1 16 16' }], ['circle', { cx: 5, cy: 19, r: 1.5 }]],
    runs: [['path', { d: 'M3 12h4l3-8 4 16 3-8h4' }]],
    briefing: [['path', { d: 'M5 4h11l3 3v13H5z' }], ['path', { d: 'M9 9h6' }], ['path', { d: 'M9 13h6' }], ['path', { d: 'M9 17h4' }]],
    play: [['path', { d: 'M7 5l12 7-12 7z' }]],
    check: [['path', { d: 'M5 12.5l4.5 4.5L19 7.5' }]],
    dash: [['path', { d: 'M6 12h12' }]],
    block: [['circle', { cx: 12, cy: 12, r: 8.5 }], ['path', { d: 'M6 6l12 12' }]],
    merge: [['path', { d: 'M6 4v6a6 6 0 0 0 6 6h6' }], ['path', { d: 'M6 20v-6' }], ['path', { d: 'M15 13l3 3-3 3' }]],
    alert: [['path', { d: 'M12 4l9 16H3z' }], ['path', { d: 'M12 10v4' }], ['path', { d: 'M12 17v.5' }]],
    info: [['circle', { cx: 12, cy: 12, r: 8.5 }], ['path', { d: 'M12 11v5' }], ['path', { d: 'M12 8v.5' }]],
    download: [['path', { d: 'M12 4v11' }], ['path', { d: 'M7 11l5 5 5-5' }], ['path', { d: 'M5 20h14' }]],
  };

  function icon(name, size = 18) {
    const svg = document.createElementNS(SVG_NS, 'svg');
    const attrs = { 'aria-hidden': 'true', width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 1.7, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' };
    for (const [key, value] of Object.entries(attrs)) svg.setAttribute(key, value);
    for (const [tag, shape] of ICONS[name] || []) {
      const node = document.createElementNS(SVG_NS, tag);
      for (const [key, value] of Object.entries(shape)) node.setAttribute(key, value);
      svg.append(node);
    }
    return svg;
  }

  const pill = (label, kind, iconName) => h('span', { class: `pill ${kind}` }, iconName ? icon(iconName, 14) : null, label);
  const notice = (title, body, kind = 'warn') =>
    h('div', { class: `notice ${kind === 'info' ? 'info' : ''}` }, icon(kind === 'info' ? 'info' : 'alert'), h('div', {}, h('strong', {}, title), h('span', {}, body)));
  const fact = (label, value) => h('li', {}, h('span', {}, label), h('span', {}, value));
  const panel = (title, ...children) => h('section', { class: 'panel' }, h('h2', {}, title), ...children);

  // ---------------------------------------------------------------- formatting
  const number = (value) => (typeof value === 'number' ? value.toLocaleString('en-US') : '0');
  const plural = (count, one, many) => `${number(count)} ${count === 1 ? one : many}`;
  const score = (value) => (typeof value === 'number' ? value.toFixed(1) : 'n/a');
  function when(iso) {
    if (!iso) return '';
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  }
  function longDate(iso) {
    const date = new Date(iso);
    if (!iso || Number.isNaN(date.getTime())) return '';
    return date.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  }
  function duration(seconds) {
    if (!seconds) return 'n/a';
    const minutes = Math.floor(seconds / 60);
    const rest = Math.round(seconds % 60);
    return minutes ? `${minutes} min ${rest} s` : `${rest} s`;
  }

  // ---------------------------------------------------------------- API
  async function request(path, options) {
    let response;
    try {
      response = await fetch(path, options);
    } catch (error) {
      throw new Error('MastHead is not answering. Is the server still running in your terminal?');
    }
    let data = null;
    try { data = await response.json(); } catch (error) { /* not JSON */ }
    if (!response.ok) throw new Error((data && data.error) || `Request failed (${response.status}).`);
    return data;
  }
  const api = {
    get: (path) => request(path),
    post: (path, body) => request(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) }),
  };

  // ---------------------------------------------------------------- state
  const state = { domains: [], domain: null, poll: null, token: 0 };
  const view = document.getElementById('view');
  const store = {
    get() { try { return window.localStorage.getItem('masthead.domain'); } catch (error) { return null; } },
    set(value) { try { window.localStorage.setItem('masthead.domain', value); } catch (error) { /* private mode */ } },
  };

  // replaceChildren would print "null" for an absent block, so absent blocks are dropped here.
  const show = (...nodes) => view.replaceChildren(...nodes.flat(Infinity).filter((node) => node !== null && node !== undefined && node !== false));

  let toastTimer = null;
  function toast(message, isError) {
    const el = document.getElementById('toast');
    el.textContent = message;
    el.className = `toast ${isError ? 'error' : ''}`;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, isError ? 9000 : 4000);
  }

  const domainPath = (rest = '') => `/api/domains/${encodeURIComponent(state.domain)}${rest}`;
  const currentDomain = () => state.domains.find((d) => d.id === state.domain);

  // ---------------------------------------------------------------- chrome
  const NAV = [
    ['domains', 'Domains', 'domains'],
    ['sources', 'Sources and settings', 'sources'],
    ['runs', 'Runs', 'runs'],
    ['briefing', 'Briefing', 'briefing'],
  ];

  function renderChrome(route) {
    const nav = document.getElementById('nav');
    nav.replaceChildren(...NAV.map(([id, label, iconName]) =>
      h('a', { href: `#/${id}`, 'aria-current': route === id ? 'page' : null }, icon(iconName), h('span', {}, label))));
    const list = document.getElementById('domain-list');
    list.replaceChildren(...state.domains.map((domain) =>
      h('li', {}, h('button', {
        type: 'button', 'aria-pressed': domain.id === state.domain ? 'true' : 'false',
        onclick: () => { selectDomain(domain.id); },
      }, h('span', {}, domain.name), domain.draft ? h('span', { class: 'tag' }, 'draft')
        : domain.id === state.domain ? h('span', { class: 'tag' }, 'active') : null))));
  }

  function selectDomain(id) {
    state.domain = id;
    store.set(id);
    const route = (window.location.hash.split('/')[1] || 'runs');
    if (route === 'domains') window.location.hash = '#/runs';
    else if (window.location.hash.split('/').length > 2) window.location.hash = `#/${route}`;
    else render();
  }

  function domainBar() {
    const domain = currentDomain();
    if (!domain) return null;
    const facts = [];
    if (typeof domain.sources_enabled === 'number') facts.push(plural(domain.sources_enabled, 'source on', 'sources on'));
    if (domain.languages) facts.push(plural(domain.languages.length, 'language', 'languages'));
    if (domain.model) facts.push(domain.model);
    return h('div', { class: 'panel domain-bar' },
      h('div', { class: 'spread' },
        h('div', { class: 'actions' }, h('span', { class: 'eyebrow' }, 'Domain'), h('span', { class: 'strong' }, domain.name),
          domain.draft ? pill('Draft', 'warn', 'alert') : null, h('span', { class: 'mono muted' }, facts.join(' · '))),
        domain.draft ? h('a', { href: `#/new/${encodeURIComponent(domain.id)}`, class: 'strong' }, 'Continue setting up')
          : h('a', { href: '#/domains', class: 'strong' }, 'All domains')));
  }

  function pageHead(title, lede, ...actions) {
    return h('header', { class: 'page-head' },
      h('div', {}, h('h1', {}, title), lede ? h('p', { class: 'lede' }, lede) : null),
      h('div', { class: 'actions' }, ...actions));
  }

  // ---------------------------------------------------------------- Domains
  async function viewDomains() {
    const cards = state.domains.map((domain) => h('section', { class: `panel card ${domain.id === state.domain ? 'active' : ''}` },
      h('div', { class: 'spread' }, h('h2', {}, domain.name),
        domain.draft ? pill('Draft', 'warn', 'alert') : domain.id === state.domain ? pill('Active', 'hot') : null),
      domain.description ? h('p', { class: 'hint' }, domain.description) : null,
      domain.problem
        ? notice('This domain cannot be loaded', domain.problem)
        : h('ul', { class: 'facts' },
          fact('Sources on', number(domain.sources_enabled)),
          fact('Languages', (domain.languages || []).join(', ')),
          fact('Model', domain.model || 'n/a'),
          fact('Runs', number(domain.runs)),
          fact('Last run', domain.last_run ? when(domain.last_run) : 'never')),
      h('div', { class: 'actions' },
        domain.draft ? h('a', { class: 'btn ghost', href: `#/new/${encodeURIComponent(domain.id)}` }, 'Continue setting up') : null,
        h('button', { type: 'button', class: 'btn primary', onclick: () => { state.domain = domain.id; store.set(domain.id); window.location.hash = '#/runs'; } }, 'Open'),
        h('a', { class: 'btn', href: '#/sources', onclick: () => { state.domain = domain.id; store.set(domain.id); } }, 'Sources and settings'))));

    show(
      pageHead('Domains', 'One domain per subject you follow. Each has its own sources, rules, languages, model and history.',
        h('a', { class: 'btn primary', href: '#/new' }, 'New domain')),
      h('div', { class: 'cards' }, ...cards),
      window.MastHeadAI.keysPanel(window.MastHead, await api.get('/api/ai'), viewDomains),
      panel('Bring an existing Horizon setup',
        h('p', { class: 'hint' }, 'If you already use Horizon from the command line, import its configuration from your terminal:'),
        h('pre', { class: 'cmd' }, 'masthead import --id boating --name "Boating" \\\n  --config path/to/config.json --profiles path/to/profiles'),
        h('p', { class: 'hint' }, 'Then reload this page.')));
  }

  // ---------------------------------------------------------------- Sources and settings
  let aiStatus = null;  // providers and key presence, for the AI panel; never a key
  async function viewSources() {
    const [overview, ai] = await Promise.all([api.get(domainPath()), api.get('/api/ai')]);
    aiStatus = ai;
    drawSources(overview);
  }

  function drawSources(overview) {
    const settings = overview.settings;
    const notices = [];
    if (overview.missing_env.length) {
      notices.push(notice('No AI key found',
        `This domain needs ${overview.missing_env.join(', ')}. Enter it in the AI panel below (it is then shared by every domain using this provider), or put it in a .env file in ${overview.folder}. Until then you can collect, but not score.`));
    }
    for (const source of overview.sources.filter((s) => s.implicit)) {
      notices.push(notice(`${source.label} is on by default`,
        'Horizon reads this source unless it is switched off. You did not choose it: switch it off below if it does not belong to this domain.'));
    }
    for (const profile of settings.profiles.filter((p) => p.analysis_max_chars <= 1000)) {
      notices.push(notice(`Stories are scored from their first ${number(profile.analysis_max_chars)} characters`,
        `This is Horizon's default for the profile "${profile.name}". Scores may miss what an article says further down. Raise analysis_max_chars in the profile to change it.`, 'info'));
    }
    for (const warning of overview.warnings) notices.push(notice('Horizon reports', warning, 'info'));

    const rows = overview.sources.map((source) => {
      const input = h('input', {
        type: 'checkbox', checked: source.enabled, 'aria-label': `${source.label}: ${source.enabled ? 'on' : 'off'}`,
        onchange: async () => {
          input.disabled = true;
          try {
            drawSources(await api.post(domainPath('/sources'), { key: source.key, enabled: input.checked }));
            await loadDomains();
            renderChrome('sources');
            toast(`${source.label} switched ${input.checked ? 'on' : 'off'}. Applies from the next run.`);
          } catch (error) { input.checked = !input.checked; input.disabled = false; toast(error.message, true); }
        },
      });
      return h('tr', { class: source.enabled ? '' : 'off' },
        h('td', {}, h('label', { class: 'switch' }, input, h('span', { class: 'track' }))),
        h('td', {}, h('div', { class: 'src-name' }, source.label), h('div', { class: 'src-detail' }, source.detail)),
        h('td', { class: 'meta' }, source.kind_name),
        h('td', { class: 'meta' }, source.category || 'none'),
        h('td', {}, source.implicit ? pill('On by default', 'warn', 'alert')
          : source.enabled && source.empty ? pill('Nothing to read', 'idle', 'dash')
            : source.enabled ? pill('On', 'ok', 'check') : pill('Off', 'idle', 'dash')));
    });

    const defaultProfile = settings.profiles.find((p) => p.default) || settings.profiles[0];
    const threshold = h('input', { id: 'set-threshold', type: 'number', min: 0, max: 10, step: 0.5, value: defaultProfile && defaultProfile.threshold !== null ? defaultProfile.threshold : '' });
    const maxItems = h('input', { id: 'set-max', type: 'number', min: 1, step: 1, value: settings.max_items || '' });
    const hours = h('input', { id: 'set-hours', type: 'number', min: 1, step: 1, value: settings.time_window_hours });
    const save = h('button', {
      type: 'submit', class: 'btn primary',
    }, 'Save settings');
    const form = h('form', {
      class: 'stack', onsubmit: async (event) => {
        event.preventDefault();
        const body = { time_window_hours: Number(hours.value) };
        body.threshold = threshold.value === '' ? null : Number(threshold.value);
        body.max_items = maxItems.value === '' ? null : Number(maxItems.value);
        save.disabled = true;
        try {
          drawSources(await api.post(domainPath('/settings'), body));
          toast('Settings saved. They apply from the next run.');
        } catch (error) { save.disabled = false; toast(error.message, true); }
      },
    },
      h('div', { class: 'field' }, h('label', { for: 'set-threshold' }, 'Minimum score'), threshold,
        h('span', { class: 'help' }, 'From 0 to 10. Stories scored below it are left out. Leave empty to keep everything.')),
      h('div', { class: 'field' }, h('label', { for: 'set-max' }, 'Stories per briefing'), maxItems,
        h('span', { class: 'help' }, 'The most stories a briefing can hold. Leave empty for no maximum.')),
      h('div', { class: 'field' }, h('label', { for: 'set-hours' }, 'Time window, in hours'), hours,
        h('span', { class: 'help' }, 'How far back each run looks for new stories.')),
      h('div', {}, save));

    const limits = settings.groups.length
      ? settings.groups.map((group) => fact(group.name, `at most ${group.limit}`))
      : [fact('Group limits', 'none')];

    show(
      domainBar(),
      pageHead('Sources and settings', 'What this domain reads, and the few settings that decide most of the result.'),
      ...notices,
      h('div', { class: 'cols' },
        h('div', { class: 'col-main' },
          panel('Sources',
            h('p', { class: 'hint' }, `${plural(overview.sources.filter((s) => s.enabled).length, 'source is', 'sources are')} on. Every source Horizon will read is listed here, including the ones it enables on its own.`),
            h('div', { class: 'table-wrap' }, h('table', {},
              h('thead', {}, h('tr', {}, ...['On', 'Source', 'Type', 'Group', 'State'].map((label) => h('th', { scope: 'col' }, label)))),
              h('tbody', {}, ...rows))))),
        h('div', { class: 'col-side' },
          panel('Essentials', form),
          window.MastHeadAI.modelPanel(window.MastHead, overview, aiStatus, (fresh, ai) => {
            if (ai) aiStatus = ai;
            if (fresh) drawSources(fresh); else viewSources();
          }),
          panel('Limits per group', h('ul', { class: 'facts' }, ...limits),
            h('p', { class: 'hint' }, 'A group gathers sources. Its limit keeps one family of sources from filling the briefing.')),
          panel('Folder', h('pre', { class: 'cmd' }, overview.folder)))));
  }

  // ---------------------------------------------------------------- Runs
  const OUTCOME = {
    kept: ['Kept', 'ok', 'check'],
    capped: ['Over limit', 'warn', 'block'],
    merged: ['Merged', 'warn', 'merge'],
    removed: ['Removed', 'warn', 'block'],
    below_score: ['Below score', 'idle', 'dash'],
    not_scored: ['Not scored', 'idle', 'dash'],
  };
  const RUN_STATUS = {
    done: ['Success', 'ok', 'check'], incomplete: ['Sources failed', 'warn', 'alert'], failed: ['Failed', 'warn', 'block'], cancelled: ['Stopped', 'idle', 'dash'],
    partial: ['Partial', 'idle', 'dash'], running: ['Running', 'hot', 'play'],
  };

  function stepsList(job) {
    return h('ol', { class: 'steps', 'aria-label': 'Run progress' }, ...job.stages.map((stage) =>
      h('li', { class: stage.status },
        h('span', { class: 'name' }, h('span', {}, stage.name), h('span', { class: 'dot', role: 'img', 'aria-label': stage.status })),
        h('span', { class: 'detail' }, stage.detail || (stage.status === 'skipped' ? 'Skipped' : stage.hint)),
        stage.seconds ? h('span', { class: 'detail mono' }, `${duration(stage.seconds)}${stage.input_tokens + stage.output_tokens ? ` · ${number(stage.input_tokens + stage.output_tokens)} tokens` : ''}`) : null)));
  }

  function watchJob(job, holder) {
    clearInterval(state.poll);
    const draw = (current) => {
      holder.replaceChildren(panel('Run in progress',
        h('p', { class: 'hint' }, 'You can leave this page: the run continues as long as MastHead is running in your terminal.'),
        stepsList(current),
        h('div', {}, h('button', { type: 'button', class: 'btn', onclick: async () => { try { await api.post(`/api/jobs/${current.id}/cancel`); } catch (error) { toast(error.message, true); } } }, 'Stop the run'))));
    };
    draw(job);
    const token = state.token;
    state.poll = setInterval(async () => {
      if (token !== state.token) { clearInterval(state.poll); return; }
      let current;
      try { current = await api.get(`/api/jobs/${job.id}`); } catch (error) { clearInterval(state.poll); toast(error.message, true); return; }
      if (current.status === 'running') { draw(current); return; }
      clearInterval(state.poll);
      if (current.status === 'failed') toast(`The run failed: ${current.error}`, true);
      else if (current.note) toast(current.note);
      else toast('Run finished.');
      await loadDomains();
      if (current.run_id) {
        const target = `#/runs/${current.run_id}`;
        if (window.location.hash === target) render(); else window.location.hash = target;
      } else { render(); }
    }, 1000);
  }

  async function startRun(until) {
    try {
      await api.post(domainPath('/runs'), { until });
      window.location.hash = '#/runs';
      render();
    } catch (error) { toast(error.message, true); }
  }

  function runButtons(busy) {
    return [
      h('button', { type: 'button', class: 'btn', disabled: busy, onclick: () => startRun('collect'), title: 'Reads the sources only. No model call, no cost.' }, icon('download'), h('span', {}, 'Collect only')),
      h('button', { type: 'button', class: 'btn primary', disabled: busy, onclick: () => startRun('full') }, icon('play'), h('span', {}, 'Run now')),
    ];
  }

  async function viewRuns(runId) {
    const listing = await api.get(domainPath('/runs'));
    const runs = listing.runs;
    const jobHolder = h('div', {});
    if (listing.active_job) watchJob(listing.active_job, jobHolder);
    const otherBusy = listing.busy && !listing.active_job
      ? notice('Another domain is running', 'MastHead runs one domain at a time. You can start this one when the other run ends.', 'info') : null;

    if (!runs.length) {
      show(domainBar(),
        pageHead('Runs', 'A run reads the sources, scores each story, selects the best and writes the briefing.', ...runButtons(listing.busy)),
        jobHolder, otherBusy,
        listing.active_job ? null : h('div', { class: 'empty' },
          h('strong', {}, 'No run yet for this domain.'),
          h('span', {}, '“Collect only” reads your sources without calling a model: a free way to check them. “Run now” does the whole pipeline and needs your AI key.'),
          h('span', {}, 'To explore the inspector first, stop MastHead and type: masthead demo')));
      return;
    }

    const current = runs.find((run) => run.run_id === runId) || runs[0];
    const detail = await api.get(domainPath(`/runs/${encodeURIComponent(current.run_id)}`));
    const meta = detail.meta;
    const own = meta.masthead || {};
    const status = RUN_STATUS[current.status] || RUN_STATUS.partial;

    const history = panel('History', h('ul', { class: 'history' }, ...runs.map((run) => {
      const st = RUN_STATUS[run.status] || RUN_STATUS.partial;
      const what = run.error ? 'Failed' : typeof run.kept === 'number' ? `${run.kept} kept`
        : typeof run.scored === 'number' ? `${run.scored} scored` : `${number(run.collected || 0)} collected`;
      return h('li', {}, h('a', { href: `#/runs/${run.run_id}`, 'aria-current': run.run_id === current.run_id ? 'true' : null },
        h('span', { class: 'num' }, `#${run.number}`),
        h('span', { class: 'when' }, when(run.created_at)),
        h('span', { class: 'what' }, what + (run.demo ? ' · demo' : '')),
        pill(st[0], st[1], st[2])));
    })));

    const head = pageHead(`Run #${detail.number}`,
      `${longDate(meta.created_at)}. What was collected, scored, merged and kept, and why.`,
      pill(status[0], status[1], status[2]), ...runButtons(listing.busy));
    const top = [domainBar(), head, jobHolder, otherBusy];
    if (detail.demo) top.push(notice('Demo run', 'These stories and scores are invented. The selection is real: Horizon’s own filtering, merging and limits. No model was called.', 'info'));
    if (own.error) top.push(notice('This run failed', own.error));
    else if (own.note && !detail.demo) top.push(notice('Note', own.note, 'info'));

    if (!detail.journal) {
      show(...top, ...collectedOnly(detail), history);
      return;
    }
    show(...top, ...inspector(detail, current, history));
  }

  function fetchReportPanel(meta) {
    const report = meta.fetch_report;
    if (!report || !report.sources) return null;
    const label = { success: ['Read', 'ok', 'check'], empty: ['Nothing new', 'idle', 'dash'], partial_failure: ['Partly failed', 'warn', 'alert'], failure: ['Failed', 'warn', 'block'] };
    return panel('Collection report',
      h('div', { class: 'table-wrap' }, h('table', {},
        h('thead', {}, h('tr', {}, ...['Source', 'Stories', 'Result', 'Detail'].map((t) => h('th', { scope: 'col' }, t)))),
        h('tbody', {}, ...report.sources.map((source) => {
          const st = label[source.status] || label.failure;
          const failures = source.failures ? Object.entries(source.failures).map(([name, why]) => `${name}: ${why}`).join(' · ') : (source.error || '');
          return h('tr', {}, h('td', { class: 'strong' }, source.source), h('td', { class: 'score' }, number(source.item_count)),
            h('td', {}, pill(st[0], st[1], st[2])), h('td', { class: 'src-detail' }, failures.split('\n')[0]));
        })))));
  }

  function collectedOnly(detail) {
    const meta = detail.meta;
    const scored = detail.stages.scored;
    const rows = detail.collected.map((item) => h('tr', {},
      scored ? h('td', { class: 'score' }, score(item.score)) : null,
      h('td', {}, item.url ? h('a', { href: item.url, target: '_blank', rel: 'noopener noreferrer' }, item.title) : item.title),
      h('td', { class: 'meta' }, item.source), h('td', { class: 'meta' }, when(item.published_at))));
    return [
      h('ol', { class: 'funnel', 'aria-label': 'Run funnel' },
        h('li', {}, h('span', { class: 'n' }, number(meta.raw_count_before_merge || 0)), h('span', { class: 'label' }, 'collected'),
          h('span', { class: 'note' }, `${number((meta.raw_count_before_merge || 0) - (meta.raw_count || 0))} repeated links removed`)),
        h('li', { class: 'final' }, h('span', { class: 'n' }, scored ? number(meta.scored_count) : '0'), h('span', { class: 'label' }, 'scored'),
          h('span', { class: 'note' }, scored ? 'Selection was not run' : 'This run stopped after collection'))),
      fetchReportPanel(meta),
      detail.collected.length ? panel(scored ? 'Scored stories' : 'Collected stories',
        h('div', { class: 'table-wrap' }, h('table', {},
          h('thead', {}, h('tr', {}, ...[scored ? 'Score' : null, 'Story', 'Source', 'Published'].filter(Boolean).map((t) => h('th', { scope: 'col' }, t)))),
          h('tbody', {}, ...rows)))) : null,
    ];
  }

  function inspector(detail, current, history) {
    const meta = detail.meta;
    const own = meta.masthead || {};
    const original = detail.journal;
    const thresholds = [...new Set(original.decisions.map((d) => d.threshold).filter((t) => t !== null && t !== undefined))];
    const baseThreshold = original.override !== null && original.override !== undefined ? original.override
      : thresholds.length === 1 ? thresholds[0] : null;

    const funnelHolder = h('div', {});
    const tableHolder = h('div', {});
    const whyHolder = h('div', {});
    const replayResult = h('div', { class: 'stack' });
    let journal = original;
    let selected = null;
    let showBelow = false;

    function drawFunnel() {
      const f = journal.funnel;
      const c = journal.counts;
      const preview = Boolean(journal.preview);
      const shown = preview ? journal.override : baseThreshold;
      const tiles = [
        [number(meta.raw_count_before_merge ?? f.scored), 'collected', meta.fetch_report ? `from ${plural(meta.fetch_report.attempted, 'source type', 'source types')}` : ''],
        [number(f.scored), 'scored', `${plural((meta.raw_count_before_merge ?? f.scored) - f.scored, 'repeated link', 'repeated links')} removed`],
        [number(f.passing), shown === null ? 'passed the score' : `at or above ${shown}`, `${number(c.below_score + c.not_scored)} below the score`],
        [journal.merge_recorded ? number(f.after_merge) : '?', 'after merging', journal.merge_recorded ? plural(c.merged, 'duplicate story', 'duplicate stories') : 'not recorded for this run'],
        [number(f.kept), 'in the briefing', journal.merge_recorded ? `${number(c.capped)} dropped by a limit` : `${number(c.removed)} merged or dropped`],
      ];
      funnelHolder.replaceChildren(h('ol', { class: `funnel ${preview ? 'preview' : ''}`, 'aria-label': preview ? 'Run funnel, replayed' : 'Run funnel' },
        ...tiles.map(([n, label, note], index) => h('li', { class: index === tiles.length - 1 ? 'final' : '' },
          h('span', { class: 'n' }, n), h('span', { class: 'label' }, label), h('span', { class: 'note' }, note)))));
    }

    function drawTable() {
      const visible = journal.decisions.filter((d) => showBelow || (d.outcome !== 'below_score' && d.outcome !== 'not_scored'));
      const hidden = journal.decisions.length - visible.length;
      const rows = visible.map((d) => {
        const o = OUTCOME[d.outcome];
        return h('tr', { class: d.outcome === 'kept' ? 'kept' : '', 'aria-selected': selected && selected.id === d.id ? 'true' : 'false', onclick: () => { selected = d; drawTable(); drawWhy(); } },
          h('td', { class: 'score' }, score(d.score)),
          h('td', { class: 'story' }, h('button', { type: 'button', class: 'row-btn' }, d.title)),
          h('td', { class: 'meta' }, d.source), h('td', { class: 'meta' }, d.stage),
          h('td', {}, pill(o[0], o[1], o[2])));
      });
      if (hidden || showBelow) {
        const below = journal.counts.below_score + journal.counts.not_scored;
        rows.push(h('tr', { class: 'more-row' }, h('td', { colspan: 5 },
          h('button', { type: 'button', class: 'link-btn', onclick: () => { showBelow = !showBelow; drawTable(); } },
            showBelow ? 'Hide the stories below the minimum score' : `Show the ${plural(below, 'story', 'stories')} below the minimum score`))));
      }
      tableHolder.replaceChildren(panel(journal.preview ? 'Every decision, replayed' : 'Every decision',
        h('div', { class: 'table-wrap' }, h('table', { class: 'decisions' },
          h('thead', {}, h('tr', {}, ...['Score', 'Story', 'Source', 'Decided at', 'Outcome'].map((t) => h('th', { scope: 'col' }, t)))),
          h('tbody', {}, ...rows)))));
    }

    function drawWhy() {
      const d = selected ? journal.decisions.find((x) => x.id === selected.id) || selected : journal.decisions[0];
      if (!d) { whyHolder.replaceChildren(); return; }
      const o = OUTCOME[d.outcome];
      whyHolder.replaceChildren(panel('Why this story',
        d.url ? h('a', { class: 'strong', href: d.url, target: '_blank', rel: 'noopener noreferrer' }, d.title) : h('span', { class: 'strong' }, d.title),
        h('ul', { class: 'facts' },
          fact('Score', score(d.score)),
          fact('Minimum score', d.threshold === null || d.threshold === undefined ? 'none' : String(d.threshold)),
          fact('Profile', d.profile), fact('Source', d.source), fact('Group', d.category || 'none'),
          fact('Outcome', o[0])),
        h('p', {}, d.detail),
        d.unchecked ? h('p', { class: 'hint' }, 'This story was below the score during the run, so it was never compared with the others for duplicates.') : null,
        h('div', { class: 'quote' }, h('span', { class: 'eyebrow' }, 'The model’s reason'), h('span', { class: 'muted' }, d.reason || 'The model gave no reason.')),
        d.tags && d.tags.length ? h('p', { class: 'mono muted' }, d.tags.map((tag) => `#${tag}`).join('  ')) : null));
    }

    // Replay
    const start = baseThreshold === null ? 5 : baseThreshold;
    const readout = h('span', { class: 'big-amber' }, String(start));
    const slider = h('input', { id: 'replay', type: 'range', min: 0, max: 10, step: 0.5, value: start });
    const apply = h('button', { type: 'button', class: 'btn primary', disabled: true }, 'Use this score from now on');
    let timer = null;
    let sequence = 0;

    function drawReplayResult() {
      const f = journal.funnel;
      const lines = [
        h('div', { class: 'boxed spread' }, h('span', {}, 'At or above the score'), h('span', { class: 'v' }, `${f.passing} / ${f.scored}`)),
        h('div', { class: 'boxed spread' }, h('span', {}, 'In the briefing'), h('span', { class: 'v' },
          journal.preview ? `${f.kept} (was ${original.funnel.kept})` : String(f.kept))),
      ];
      if (journal.preview && journal.unchecked_count) {
        lines.push(h('p', { class: 'hint' }, `${plural(journal.unchecked_count, 'story passes', 'stories pass')} only at this score and ${journal.unchecked_count === 1 ? 'was' : 'were'} never compared for duplicates. A real run could merge some of them.`));
      }
      replayResult.replaceChildren(...lines);
    }

    slider.addEventListener('input', () => {
      const value = Number(slider.value);
      readout.textContent = String(value);
      clearTimeout(timer);
      timer = setTimeout(async () => {
        const mine = ++sequence;
        try {
          const result = value === baseThreshold ? original
            : await api.post(domainPath(`/runs/${encodeURIComponent(detail.run_id)}/replay`), { threshold: value });
          if (mine !== sequence) return;
          journal = result;
          apply.disabled = value === baseThreshold;
          drawFunnel(); drawTable(); drawWhy(); drawReplayResult();
        } catch (error) { toast(error.message, true); }
      }, 120);
    });
    apply.addEventListener('click', async () => {
      apply.disabled = true;
      try {
        await api.post(domainPath('/settings'), { threshold: Number(slider.value) });
        toast(`Minimum score set to ${slider.value}. It applies from the next run; this run is unchanged.`);
      } catch (error) { apply.disabled = false; toast(error.message, true); }
    });

    const replay = panel('Replay at no cost',
      h('p', { class: 'hint' }, 'Scores are already stored. Moving the minimum recalculates the selection with no model call, and changes nothing in this run.'),
      h('div', { class: 'stack' }, h('div', { class: 'spread' }, h('label', { for: 'replay', class: 'strong' }, 'Minimum score tested'), readout), slider),
      replayResult, apply);

    // Usage
    const pricing = detail.pricing;
    const tokensIn = own.input_tokens || 0;
    const tokensOut = own.output_tokens || 0;
    let cost = null;
    if (pricing && typeof pricing.input_per_mtok === 'number' && typeof pricing.output_per_mtok === 'number') {
      cost = (tokensIn / 1e6) * pricing.input_per_mtok + (tokensOut / 1e6) * pricing.output_per_mtok;
    }
    const usage = panel('Usage',
      h('ul', { class: 'facts' },
        fact('Input tokens', number(tokensIn)), fact('Output tokens', number(tokensOut)),
        fact('Model', own.model || (detail.demo ? 'none (demo)' : 'not recorded')),
        fact('Duration', duration(own.seconds))),
      cost !== null
        ? h('div', { class: 'spread' }, h('span', { class: 'strong' }, 'Estimated cost'), h('span', { class: 'big-amber' }, `${pricing.currency || '$'}${cost.toFixed(2)}`))
        : h('p', { class: 'hint' }, detail.demo ? 'A demo run calls no model and costs nothing.'
          : 'To see a cost, add your model’s prices to domain.json in the domain folder: "pricing": {"input_per_mtok": …, "output_per_mtok": …}.'),
      detail.languages.length ? h('a', { class: 'btn', href: `#/briefing/${detail.run_id}` }, icon('briefing'), h('span', {}, 'Read the briefing')) : null);

    drawFunnel(); drawTable(); drawWhy(); drawReplayResult();
    return [
      funnelHolder,
      h('div', { class: 'cols' },
        h('div', { class: 'col-main' }, tableHolder, fetchReportPanel(meta), history),
        h('div', { class: 'col-side' }, whyHolder, replay, usage)),
    ];
  }

  // ---------------------------------------------------------------- Briefing
  function inline(text) {
    const out = [];
    const pattern = /\\([\\`*_{}[\]()#+\-.!>|~])|\*\*(.+?)\*\*|`([^`]+)`|\[((?:\\.|[^\]\\])+)\]\(([^)\s]+)\)/g;
    let last = 0;
    let match;
    while ((match = pattern.exec(text)) !== null) {
      if (match.index > last) out.push(text.slice(last, match.index));
      if (match[1] !== undefined) out.push(match[1]);
      else if (match[2] !== undefined) out.push(h('strong', {}, ...inline(match[2])));
      else if (match[3] !== undefined) out.push(h('code', {}, match[3]));
      else if (/^https?:\/\//i.test(match[5])) out.push(h('a', { href: match[5], target: '_blank', rel: 'noopener noreferrer' }, ...inline(match[4])));
      else out.push(...inline(match[4]));
      last = pattern.lastIndex;
    }
    if (last < text.length) out.push(text.slice(last));
    return out;
  }

  function markdown(source) {
    const root = h('div', { class: 'prose' });
    let paragraph = [];
    let list = null;
    const flush = () => {
      if (paragraph.length) { root.append(h('p', {}, ...inline(paragraph.join(' ')))); paragraph = []; }
      list = null;
    };
    for (const raw of source.split('\n')) {
      const line = raw.trimEnd();
      if (/^<a id="[^"]*"><\/a>$/.test(line.trim())) continue;
      let match;
      if (!line.trim()) { flush(); continue; }
      if (/^-{3,}$/.test(line.trim())) { flush(); root.append(h('hr', {})); continue; }
      if ((match = /^(#{1,4}) (.*)$/.exec(line))) { flush(); root.append(h(`h${Math.min(match[1].length + 1, 5)}`, {}, ...inline(match[2]))); continue; }
      if ((match = /^> ?(.*)$/.exec(line))) { flush(); root.append(h('blockquote', {}, ...inline(match[1]))); continue; }
      if ((match = /^(\d+)\. (.*)$/.exec(line)) || (match = /^([-*]) (.*)$/.exec(line))) {
        const tag = /\d/.test(match[1]) ? 'ol' : 'ul';
        if (paragraph.length) { root.append(h('p', {}, ...inline(paragraph.join(' ')))); paragraph = []; }
        if (!list || list.tagName.toLowerCase() !== tag) { list = h(tag, {}); root.append(list); }
        list.append(h('li', {}, ...inline(match[2])));
        continue;
      }
      list = null;
      paragraph.push(line.trim());
    }
    flush();
    return root;
  }

  async function viewBriefing(runId) {
    const listing = await api.get(domainPath('/runs'));
    const candidates = runId ? listing.runs.filter((run) => run.run_id === runId) : listing.runs.filter((run) => run.stages && run.stages.filtered);
    let detail = null;
    for (const run of candidates.slice(0, 5)) {
      const found = await api.get(domainPath(`/runs/${encodeURIComponent(run.run_id)}`));
      if (found.languages.length) { detail = found; break; }
    }
    if (!detail) {
      show(domainBar(), pageHead('Briefing', 'The briefing Horizon writes at the end of a run.'),
        h('div', { class: 'empty' }, h('strong', {}, 'No briefing yet.'), h('span', {}, 'A briefing is written when a run goes through every stage.'), h('a', { class: 'btn', href: '#/runs' }, 'Go to runs')));
      return;
    }
    const body = h('div', {});
    const tabs = h('div', { class: 'tabs', role: 'tablist', 'aria-label': 'Briefing language' });
    async function showLanguage(language) {
      tabs.replaceChildren(...detail.languages.map((code) => h('button', { type: 'button', role: 'tab', 'aria-selected': code === language ? 'true' : 'false', onclick: () => showLanguage(code) }, code)));
      try {
        const data = await api.get(domainPath(`/runs/${encodeURIComponent(detail.run_id)}/briefing?language=${encodeURIComponent(language)}`));
        body.replaceChildren(markdown(data.summary));
      } catch (error) { body.replaceChildren(notice('The briefing could not be read', error.message)); }
    }
    show(domainBar(),
      pageHead(`Briefing of run #${detail.number}`, `${longDate(detail.meta.created_at)}. The Markdown file Horizon produced, as written.`,
        h('a', { class: 'btn', href: `#/runs/${detail.run_id}` }, icon('runs'), h('span', {}, 'Inspect this run'))),
      detail.demo ? notice('Demo run', 'These stories are invented.', 'info') : null,
      detail.languages.length > 1 ? tabs : null,
      panel('Briefing', body));
    await showLanguage(detail.languages[0]);
  }

  // ---------------------------------------------------------------- router
  async function loadDomains() {
    const data = await api.get('/api/domains');
    state.domains = data.domains;
    const wanted = state.domain || store.get();
    state.domain = (state.domains.find((d) => d.id === wanted) || state.domains[0] || {}).id || null;
  }

  async function render() {
    state.token += 1;
    const token = state.token;
    clearInterval(state.poll);
    const [, route = 'runs', argument] = window.location.hash.split('/');
    try {
      await loadDomains();
      if (token !== state.token) return;
      renderChrome(route);
      if (!state.domain && route !== 'domains' && route !== 'new') { window.location.hash = '#/domains'; return; }
      if (route === 'domains') await viewDomains();
      else if (route === 'new') await window.MastHeadNewDomain.view(argument ? decodeURIComponent(argument) : null, token);
      else if (route === 'sources') await viewSources();
      else if (route === 'briefing') await viewBriefing(argument);
      else await viewRuns(argument);
    } catch (error) {
      if (token !== state.token) return;
      show(pageHead('Something went wrong', ''), notice('MastHead could not show this page', error.message),
        h('div', {}, h('button', { type: 'button', class: 'btn', onclick: render }, 'Try again')));
    }
  }

  // Shared with new-domain.js, which draws the New domain screen with the same helpers.
  window.MastHead = {
    h, icon, pill, notice, fact, panel, api, toast, show, pageHead, plural, number, when, state, store, RUN_STATUS,
    isCurrent: (token) => token === state.token,
    openDomain: (id, hash) => { state.domain = id; store.set(id); window.location.hash = hash; },
  };

  window.addEventListener('hashchange', render);
  render();
})();
