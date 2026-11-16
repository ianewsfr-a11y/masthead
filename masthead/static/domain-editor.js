/* MastHead for Horizon: the domain editor, one screen to create a domain and to change it.
   Steps on the side (Subject and AI, Sources, Editorial rules, Settings, Trial run), one
   shown at a time; moving between steps keeps what was typed; each step has its own Save
   button and says in words when it has unsaved changes. Built from Modern Web Guidance
   (forms: multi-page forms; dialog). Text from feeds and models is inserted as text only. */
(() => {
  'use strict';
  const enc = encodeURIComponent;
  const STEPS = [
    ['subject', 'Subject and AI'],
    ['sources', 'Sources'],
    ['rules', 'Editorial rules'],
    ['settings', 'Settings'],
    ['trial', 'Trial run'],
  ];
  const remember = {
    get(id) { try { return window.sessionStorage.getItem(`masthead.step.${id}`); } catch (error) { return null; } },
    set(id, step) { try { window.sessionStorage.setItem(`masthead.step.${id}`, step); } catch (error) { /* private mode */ } },
  };

  function slug(text) {
    return text.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
      .replace(/[^a-z0-9]+/g, '-').replace(/^[^a-z]+/, '').replace(/-+$/, '').slice(0, 41);
  }

  function field(M, id, label, input, help) {
    input.id = id;
    if (help) input.setAttribute('aria-describedby', `${id}-help`);
    return M.h('div', { class: 'field' }, M.h('label', { for: id }, label), input,
      help ? M.h('span', { class: 'help', id: `${id}-help` }, help) : null);
  }

  // ------------------------------------------------------------ creating a domain: Horizon's own setup
  /* The steps of horizon-wizard on one page: subject, AI, interests and suggestions, sources.
     Nothing is pre-filled. "Create the draft" hands the answers to Horizon's build_config,
     which writes the configuration; MastHead writes no setting of its own. */
  async function viewNew(token) {
    const M = window.MastHead;
    let status = await M.api.get('/api/ai');
    if (!M.isCurrent(token)) return;
    const Sources = window.MastHeadEditorSources;
    const plain = { autocomplete: 'off', spellcheck: 'false', autocapitalize: 'none', autocorrect: 'off' };
    const name = M.h('input', { type: 'text', required: true, autocomplete: 'off', maxlength: 80 });
    const id = M.h('input', { type: 'text', required: true, class: 'mono', pattern: '[a-z][a-z0-9\\-]{0,40}', ...plain });
    const description = M.h('input', { type: 'text', maxlength: 200 });
    const languages = M.h('input', { type: 'text', class: 'mono', required: true, ...plain });
    const ai = window.MastHeadAI.modelFields(M, status.providers, { provider: '', model: '' }, 'nd-ai');
    let idEdited = false;
    name.addEventListener('input', () => { if (!idEdited) id.value = slug(name.value); });
    id.addEventListener('input', () => { idEdited = true; });

    const languageList = () => languages.value.split(',').map((x) => x.trim()).filter(Boolean);
    const aiValues = () => ({ ...ai.values(), languages: languageList() });
    const chosenProvider = () => status.providers.find((p) => p.id === ai.values().provider);

    // The key of the chosen provider, entered here so that Horizon's suggestions can run.
    const keyHolder = M.h('div', { class: 'stack' });
    function drawKey() {
      const provider = chosenProvider();
      if (!provider) { keyHolder.replaceChildren(); return; }
      if (!provider.needs_key) { keyHolder.replaceChildren(M.h('p', { class: 'hint' }, `${provider.label} needs no key.`)); return; }
      keyHolder.replaceChildren(window.MastHeadAI.keyStatus(M, provider.key_present, provider.key_source),
        window.MastHeadAI.keyForm(M, provider, async () => {
          status = await M.api.get('/api/ai');
          drawKey();
          suggest.gate();
        }, 'nd-key'));
    }
    const providerSelect = ai.nodes[0].querySelector('select');
    const modelInput = ai.nodes[1].querySelector('input');
    providerSelect.addEventListener('change', () => { drawKey(); suggest.gate(); });

    const selectedNote = M.h('p', { class: 'hint', role: 'status' });
    const check = Sources.checker(M, { parse: '/api/setup/parse', test: '/api/setup/test', onTick: () => countSelected() }, 'select');
    function countSelected() {
      const count = check.selected().length;
      selectedNote.textContent = count
        ? `${M.plural(count, 'source is', 'sources are')} ticked. Horizon builds the configuration from them.`
        : 'No source ticked yet. If you create the draft without any, Horizon switches Hacker News on, as its own setup does.';
    }
    const suggest = Sources.suggestions(M, {
      ask: (interests) => M.api.post('/api/setup/suggest', { ai: aiValues(), interests, existing: check.selected() }),
      presets: (interests) => M.api.post('/api/setup/presets', { interests }),
      keyOk: () => {
        const provider = chosenProvider();
        return Boolean(provider && ai.values().model && languageList().length && (!provider.needs_key || provider.key_present));
      },
      keyHint: () => 'This uses the model: choose the AI, its model and the languages, and enter its key, in step 2.',
    }, check.check);
    for (const input of [languages, modelInput]) input.addEventListener('input', () => suggest.gate());
    countSelected();

    const message = window.MastHeadKit.messageArea(M);
    const create = M.h('button', { type: 'button', class: 'btn primary' }, 'Create the draft');
    create.addEventListener('click', async () => {
      message.clear();
      const invalid = [name, id, providerSelect, modelInput, languages]
        .find((input) => !input.checkValidity());
      if (invalid) { invalid.reportValidity(); invalid.focus(); return; }
      create.disabled = true;
      try {
        const made = await M.api.post('/api/new-domain', {
          id: id.value.trim(), name: name.value.trim(), description: description.value.trim(),
          ...aiValues(), sources: check.selected(),
        });
        M.openDomain(made.id, `#/edit/${enc(made.id)}`);
      } catch (error) { create.disabled = false; message.error('The draft was not created', error.message); }
    });

    const section = (number, title, lede, ...body) => M.h('section', { class: 'panel', 'aria-labelledby': `nd-step-${number}` },
      M.h('h2', { id: `nd-step-${number}` }, `${number}. ${title}`), lede ? M.h('p', { class: 'hint' }, lede) : null, ...body);
    M.show(M.pageHead('New domain', 'Horizon’s own setup, on screen: the AI, what you follow, the sources. Horizon then writes the configuration. Nothing is pre-filled.'),
      section(1, 'Subject', null,
        field(M, 'nd-name', 'Name', name, 'What you follow, for example "Boating".'),
        field(M, 'nd-id', 'Short id', id, 'Lowercase letters, digits and dashes, starting with a letter. It names the folder and cannot change later.'),
        field(M, 'nd-description', 'Description (optional)', description, 'One line, shown on the Domains screen. For example: “News for flight simulator pilots: aircraft, scenery, simulator updates.”')),
      section(2, 'AI', 'As in Horizon’s setup: provider, model, address, output languages.',
        ...ai.nodes,
        field(M, 'nd-languages', 'Output languages', languages, 'Codes separated by commas, such as en, fr. Each kept story is written once per language. Horizon’s setup proposes zh, en.'),
        keyHolder),
      section(3, 'What should this domain follow?', 'Horizon finds sources from its preset library (free) or asks your model (one call; the tokens are shown). Optional.',
        suggest.node),
      section(4, 'Sources', 'Tick the sources Horizon should read. Each is tested with Horizon’s collector first; a source that fails cannot be ticked.',
        Sources.pasteBox(M, { parse: '/api/setup/parse' }, check.check),
        check.list, selectedNote),
      M.h('div', { class: 'row-actions' }, create), message.area);
    name.focus();
  }

  // ------------------------------------------------------------ step: subject and AI
  function subjectStep(M, ctx) {
    const { overview, tracker, status } = ctx;
    const ai = overview.settings.ai;
    const name = M.h('input', { type: 'text', required: true, maxlength: 80, value: overview.name });
    const description = M.h('input', { type: 'text', maxlength: 200, value: overview.description || '' });
    const languages = M.h('input', { type: 'text', class: 'mono', required: true, spellcheck: 'false', value: ai.languages.join(', ') });
    const fields = window.MastHeadAI.modelFields(M, status.providers, ai, 'ed-ai');
    const message = window.MastHeadKit.messageArea(M);
    const save = M.h('button', { type: 'submit', class: 'btn primary' }, 'Save subject and AI');
    const form = tracker.watch(M.h('form', {
      class: 'stack wide-form', onsubmit: async (event) => {
        event.preventDefault();
        save.disabled = true;
        message.clear();
        try {
          await M.api.post(`/api/domains/${enc(ctx.domainId)}/subject`, {
            name: name.value, description: description.value,
            languages: languages.value.split(',').map((x) => x.trim()).filter(Boolean),
          });
          await M.api.post(`/api/domains/${enc(ctx.domainId)}/model`, fields.values());
          tracker.clean('Saved');
          await ctx.refresh();
          await M.refreshChrome();
        } catch (error) { message.error('Not saved', error.message); }
        save.disabled = false;
      },
    },
      M.h('fieldset', {}, M.h('legend', {}, 'Subject'),
        M.h('ul', { class: 'facts' }, M.fact('Short id', overview.id)),
        field(M, 'ed-name', 'Name', name),
        field(M, 'ed-description', 'Description (optional)', description, 'One line, shown on the Domains screen. For example: “News for flight simulator pilots: aircraft, scenery, simulator updates.”'),
        field(M, 'ed-languages', 'Languages', languages, 'Codes separated by commas, such as en, fr. Each kept story is written once per language.')),
      M.h('fieldset', {}, M.h('legend', {}, 'AI'), ...fields.nodes),
      M.h('div', { class: 'row-actions' }, save, tracker.indicator), message.area));

    // The key part follows the AI chosen in the list at once, saved or not: choosing Ollama
    // must not leave the previous provider's key on screen.
    const keyHolder = M.h('div', { class: 'stack' });
    const providerSelect = form.querySelector('#ed-ai-provider');
    let latest = { overview, status };
    function drawKey(fresh, freshStatus) {
      latest = { overview: fresh, status: freshStatus };
      const savedAi = fresh.settings.ai;
      const chosenId = providerSelect ? providerSelect.value : savedAi.provider;
      const provider = freshStatus.providers.find((p) => p.id === chosenId);
      const saved = chosenId === savedAi.provider;
      const notSaved = saved ? null : M.h('p', { class: 'hint' },
        `${provider ? provider.label : chosenId} is chosen above but not saved yet: this domain still uses ${savedAi.provider} until you press Save subject and AI.`);
      if (!provider || !provider.needs_key) {
        keyHolder.replaceChildren(...[notSaved,
          M.h('p', { class: 'hint' }, `${provider ? provider.label : 'This AI'} needs no key.`)].filter(Boolean));
        return;
      }
      // For the saved provider the domain's own .env counts; for another one, only what MastHead knows for all domains.
      const present = saved ? savedAi.api_key_present : provider.key_present;
      const source = saved ? savedAi.key_source : provider.key_source;
      keyHolder.replaceChildren(...[notSaved,
        window.MastHeadAI.keyStatus(M, present, source),
        window.MastHeadAI.keyForm(M, provider, () => ctx.refresh(), 'ed-key')].filter(Boolean));
    }
    if (providerSelect) providerSelect.addEventListener('change', () => drawKey(latest.overview, latest.status));
    drawKey(overview, status);
    return {
      redraw: drawKey,
      body: [form, M.h('section', { class: 'sub', 'aria-labelledby': 'ed-key-title' },
        M.h('h3', { id: 'ed-key-title' }, 'Key'),
        M.h('p', { class: 'hint' }, 'The key is saved on its own, at once: it is shared by every domain using this provider and never shown again.'),
        keyHolder)],
    };
  }

  // ------------------------------------------------------------ step: settings
  function settingsStep(M, ctx) {
    const { overview, tracker } = ctx;
    const settings = overview.settings;
    const profile = settings.profiles.find((p) => p.default) || settings.profiles[0];
    const threshold = M.h('input', { type: 'number', min: 0, max: 10, step: 0.5, value: profile && profile.threshold !== null ? profile.threshold : '' });
    const maxItems = M.h('input', { type: 'number', min: 1, step: 1, value: settings.max_items || '' });
    const hours = M.h('input', { type: 'number', min: 1, step: 1, required: true, value: settings.time_window_hours });
    const message = window.MastHeadKit.messageArea(M);
    const save = M.h('button', { type: 'submit', class: 'btn primary' }, 'Save the settings');
    const form = tracker.watch(M.h('form', {
      class: 'stack wide-form', onsubmit: async (event) => {
        event.preventDefault();
        save.disabled = true;
        message.clear();
        try {
          await M.api.post(`/api/domains/${enc(ctx.domainId)}/settings`, {
            time_window_hours: Number(hours.value),
            profile: profile ? profile.id : undefined,
            threshold: threshold.value === '' ? null : Number(threshold.value),
            max_items: maxItems.value === '' ? null : Number(maxItems.value),
          });
          tracker.clean('Saved');
          await ctx.refresh();
        } catch (error) { message.error('Not saved', error.message); }
        save.disabled = false;
      },
    },
      field(M, 'set-threshold', 'Minimum score', threshold, settings.profiles.length > 1 && profile
        ? `From 0 to 10, for profile “${profile.name}”. The other profiles keep their own minimum. Leave empty to keep everything.`
        : 'From 0 to 10. Stories scored below it are left out. Leave empty to keep everything.'),
      field(M, 'set-max', 'Stories per briefing', maxItems, 'The most stories a briefing can hold. Leave empty for no maximum.'),
      field(M, 'set-hours', 'Time window, in hours', hours, 'How far back each run looks for new stories.'),
      M.h('div', { class: 'row-actions' }, save, tracker.indicator), message.area));
    const limits = settings.groups.length
      ? settings.groups.map((group) => M.fact(group.name, `at most ${group.limit}`))
      : [M.fact('Group limits', 'none')];
    return {
      body: [form,
        overview.warnings.length ? M.h('section', { class: 'sub' }, M.h('h3', {}, 'Horizon reports'),
          ...overview.warnings.map((w) => M.notice('Horizon reports', w, 'info'))) : null,
        M.h('section', { class: 'sub' }, M.h('h3', {}, 'Limits per group'), M.h('ul', { class: 'facts' }, ...limits),
          M.h('p', { class: 'hint' }, 'A group gathers sources. Its limit keeps one family of sources from filling the briefing. Set in data/config.json for now.')),
        M.h('section', { class: 'sub' }, M.h('h3', {}, 'Folder'), M.h('pre', { class: 'cmd' }, overview.folder))].filter(Boolean),
    };
  }

  // ------------------------------------------------------------ step: trial run
  function trialStep(M, ctx) {
    const out = M.h('div', { class: 'stack', 'aria-live': 'polite' });
    const reason = M.h('p', { class: 'hint' });
    const collect = M.h('button', { type: 'button', class: 'btn' }, 'Collect only');
    const score = M.h('button', { type: 'button', class: 'btn primary' }, 'Score and select');
    function gate(fresh) {
      const sources = fresh.sources.filter((s) => s.enabled).length;
      const key = fresh.settings.ai.api_key_present;
      const rules = !fresh.rules_missing;
      collect.disabled = !sources || !rules;
      score.disabled = !sources || !key || !rules;
      reason.textContent = !sources ? 'Switch on at least one source first (step Sources).'
        : !rules ? 'Horizon cannot read this domain’s profiles (step Editorial rules), so no run can start.'
        : !key ? 'Collect only works now. Score and select needs the key of the AI (step Subject and AI).'
          : 'Collect only calls no model. Score and select uses the model to score; nothing is written and no briefing is produced.';
    }
    async function start(until) {
      collect.disabled = true;
      score.disabled = true;
      try {
        let job = await M.api.post(`/api/domains/${enc(ctx.domainId)}/runs`, { until });
        while (job.status === 'running') {
          out.replaceChildren(stages(M, job));
          await new Promise((resolve) => setTimeout(resolve, 1500));
          if (!M.isCurrent(ctx.token)) return;
          job = await M.api.get(`/api/jobs/${enc(job.id)}`);
        }
        out.replaceChildren(...[stages(M, job),
          job.error ? M.notice('The trial stopped', job.error) : null,
          job.run_id ? M.h('div', {}, M.h('button', {
            type: 'button', class: 'btn', onclick: () => M.openDomain(ctx.domainId, `#/runs/${enc(job.run_id)}`),
          }, 'Open in the inspector')) : null].filter(Boolean));
      } catch (error) { out.replaceChildren(M.notice('The trial did not start', error.message)); }
      gate(ctx.overview);
    }
    collect.addEventListener('click', () => start('collect'));
    score.addEventListener('click', () => start('select'));
    gate(ctx.overview);
    return { redraw: gate, body: [reason, M.h('div', { class: 'row-actions' }, collect, score), out] };
  }

  function stages(M, job) {
    const tokensIn = job.stages.reduce((sum, s) => sum + (s.input_tokens || 0), 0);
    const tokensOut = job.stages.reduce((sum, s) => sum + (s.output_tokens || 0), 0);
    return M.h('div', { class: 'stack' },
      M.h('ul', { class: 'facts' }, ...job.stages.filter((s) => s.status !== 'skipped').map((s) =>
        M.h('li', {}, M.h('span', {}, s.name), M.h('span', {}, s.detail || s.status)))),
      M.h('p', { class: 'hint mono' }, `Tokens used: ${M.number(tokensIn)} in, ${M.number(tokensOut)} out.`));
  }

  // ------------------------------------------------------------ what is missing, create, discard
  function missing(overview, rules) {
    const items = [];
    const ai = overview.settings.ai;
    if (!ai.api_key_present) items.push(['subject', `No key for the AI (${ai.api_key_env}): scoring and suggestions cannot run.`]);
    if (!overview.sources.some((s) => s.enabled)) items.push(['sources', 'No source is switched on.']);
    if (overview.rules_missing) items.push(['rules', 'Horizon cannot read this domain’s profiles: see Editorial rules.']);
    return items;
  }

  function draftActions(M, ctx) {
    const message = window.MastHeadKit.messageArea(M);
    const create = M.h('button', { type: 'button', class: 'btn primary' }, 'Create the domain');
    const discard = M.h('button', { type: 'button', class: 'btn danger' }, 'Discard the draft');
    create.addEventListener('click', async () => {
      message.clear();
      if (ctx.isDirty() && !await window.MastHeadKit.confirmDialog(M, {
        title: 'Create with unsaved changes?', body: `Unsaved changes in: ${ctx.dirtySteps().join(', ')} are not included.`,
        confirm: 'Create anyway',
      })) return;
      try {
        await M.api.post(`/api/domains/${enc(ctx.domainId)}/publish`, {});
        ctx.forget();
        M.openDomain(ctx.domainId, '#/runs');
      } catch (error) { message.error('Not created yet', error.message); }
    });
    discard.addEventListener('click', async () => {
      const sure = await window.MastHeadKit.confirmDialog(M, {
        title: `Discard the draft "${ctx.overview.name}"?`,
        body: 'Its folder, sources, rules and trial runs are deleted. This cannot be undone.',
        confirm: 'Discard the draft', danger: true,
      });
      if (!sure) return;
      try {
        await M.api.post(`/api/domains/${enc(ctx.domainId)}/discard`, {});
        ctx.forget();
        M.state.domain = null;
        M.store.set('');
        window.location.hash = '#/domains';
      } catch (error) { message.error('Not discarded', error.message); }
    });
    return M.h('div', { class: 'stack' }, M.h('div', { class: 'row-actions' }, create, discard), message.area);
  }

  // ------------------------------------------------------------ the editor
  async function view(domainId, token) {
    const M = window.MastHead;
    const base = `/api/domains/${enc(domainId)}`;
    const [first, rules, status] = await Promise.all([M.api.get(base), M.api.get(`${base}/profiles`), M.api.get('/api/ai')]);
    if (!M.isCurrent(token)) return;
    M.state.domain = domainId;
    M.store.set(domainId);

    const trackers = {};
    const ctx = {
      domainId, token, status, overview: first, rules,
      isDirty: () => Object.values(trackers).some((t) => t.dirty),
      dirtySteps: () => STEPS.filter(([id]) => trackers[id] && trackers[id].dirty).map(([, title]) => title),
      forget: () => Object.values(trackers).forEach((t) => t.clean()),
    };
    for (const [id] of STEPS) trackers[id] = window.MastHeadKit.unsavedTracker(M, () => drawNav());

    const steps = {};
    // Each step sees the shared context through its prototype, so ctx.overview stays current after a refresh.
    const build = (id, maker) => {
      const own = Object.assign(Object.create(ctx), {
        tracker: trackers[id],
        refresh: () => refresh(),
        // Saving the rules for the first time is what lets a run start: refresh the whole editor.
        onSaved: (state) => { ctx.rules = state; refresh(); },
      });
      steps[id] = maker(M, own);
    };
    build('subject', subjectStep);
    build('sources', window.MastHeadEditorSources.step);
    build('rules', window.MastHeadEditorRules.step);
    build('settings', settingsStep);
    build('trial', trialStep);

    let active = remember.get(domainId) || (first.sources.some((s) => s.enabled) ? 'subject' : 'sources');
    if (!steps[active]) active = 'subject';
    const sections = {};
    for (const [id, title] of STEPS) {
      const heading = M.h('h2', { id: `step-title-${id}`, tabindex: '-1' }, title);
      sections[id] = M.h('section', { class: 'panel editor-step', 'aria-labelledby': `step-title-${id}`, hidden: id !== active },
        heading, ...steps[id].body.filter(Boolean));
    }

    const nav = M.h('ol', { class: 'editor-steps' });
    function stepState(id) {
      const o = ctx.overview;
      if (id === 'subject') return o.settings.ai.api_key_present ? `${o.settings.ai.provider} · ${o.settings.ai.model}` : 'Key missing';
      if (id === 'sources') return M.plural(o.sources.filter((s) => s.enabled).length, 'source on', 'sources on');
      if (id === 'rules') return ctx.rules.builtin ? 'Horizon’s built-in profiles' : 'The domain’s own profiles';
      if (id === 'settings') {
        const main = o.settings.profiles.find((p) => p.default) || o.settings.profiles[0];
        return `Minimum score ${main && main.threshold !== null ? main.threshold : 'none'}`;
      }
      return 'Collect, then score';
    }
    function drawNav() {
      nav.replaceChildren(...STEPS.map(([id, title], index) => M.h('li', {},
        M.h('button', {
          type: 'button', class: 'step-button', 'aria-current': id === active ? 'step' : null,
          onclick: () => go(id),
        },
          M.h('span', { class: 'step-number' }, String(index + 1)),
          M.h('span', { class: 'step-text' },
            M.h('span', { class: 'step-title' }, title),
            M.h('span', { class: 'step-state' }, stepState(id)),
            trackers[id].dirty ? M.h('span', { class: 'step-unsaved' }, M.icon('alert', 12), ' Unsaved changes') : null)))));
    }
    function go(id) {
      sections[active].hidden = true;
      active = id;
      remember.set(domainId, id);
      sections[id].hidden = false;
      drawNav();
      document.getElementById(`step-title-${id}`).focus();
    }

    const missingHolder = M.h('div', {});
    function drawMissing() {
      const items = missing(ctx.overview, ctx.rules);
      missingHolder.replaceChildren(items.length
        ? M.h('div', { class: 'readiness' }, M.h('strong', {}, 'What is missing'),
          M.h('ul', {}, ...items.map(([step, text]) => M.h('li', {}, M.icon('alert', 14), M.h('span', {}, text),
            M.h('button', { type: 'button', class: 'link', onclick: () => go(step) }, `Go to ${STEPS.find(([id]) => id === step)[1]}`)))))
        : M.h('div', { class: 'readiness ready' }, M.icon('check', 16), M.h('span', {}, 'Ready: you can run a trial.')));
    }

    let titleOf = () => null;
    async function refresh() {
      ctx.overview = await M.api.get(base);
      ctx.status = await M.api.get('/api/ai');
      const title = titleOf();
      if (title) title.textContent = `${ctx.overview.draft ? 'New domain' : 'Edit domain'}: ${ctx.overview.name}`;
      for (const step of Object.values(steps)) if (step.redraw) step.redraw(ctx.overview, ctx.status);
      drawNav();
      drawMissing();
    }

    drawNav();
    drawMissing();
    window.MastHeadEditor = { domainId, isDirty: ctx.isDirty, dirtySteps: ctx.dirtySteps, forget: ctx.forget };
    const head = M.pageHead(first.draft ? `New domain: ${first.name}` : `Edit domain: ${first.name}`,
      first.draft ? 'A draft until you create it. Go through the steps in any order; each step has its own Save button.'
        : 'Each step has its own Save button. Changes apply from the next run.');
    titleOf = () => head.querySelector('h1');
    M.show(
      head,
      missingHolder,
      first.draft ? draftActions(M, ctx) : null,
      M.h('div', { class: 'editor' },
        M.h('nav', { class: 'editor-nav', 'aria-label': 'Steps' }, nav),
        M.h('div', { class: 'editor-body' }, ...STEPS.map(([id]) => sections[id]))));
  }

  window.MastHeadDomainEditor = { view, viewNew };
})();
