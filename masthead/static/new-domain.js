/* MastHead for Horizon: the New domain screen.
   Step 1 creates a draft domain. Then: sources (added by hand or suggested by Horizon,
   each tested with Horizon's collector), editorial rules (a form that fills Horizon's
   profile files), a trial run that stops before writing, then create or discard.
   Text from feeds and from the model is always inserted as text, never as HTML. */
(() => {
  'use strict';

  const KINDS = [
    ['rss', 'RSS or Atom feed', [['name', 'Name'], ['url', 'Feed address (URL)']]],
    ['github_repo', 'GitHub repository releases', [['owner', 'Owner'], ['repo', 'Repository']]],
    ['github_user', 'GitHub user activity', [['username', 'User name']]],
    ['reddit_subreddit', 'Subreddit', [['subreddit', 'Subreddit name']]],
    ['telegram', 'Telegram channel', [['channel', 'Channel name']]],
  ];
  const kindOf = (id) => KINDS.find(([kind]) => kind === id) || KINDS[0];
  const TEST_STATUS = {
    ok: ['Works', 'ok', 'check'], empty: ['Nothing in 7 days', 'idle', 'dash'], failed: ['Failed', 'warn', 'block'],
  };
  const TIERS = ['9-10', '7-8', '5-6', '3-4', '0-2'];
  const enc = encodeURIComponent;

  function slug(text) {
    return text.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
      .replace(/[^a-z0-9]+/g, '-').replace(/^[^a-z]+/, '').replace(/-+$/, '').slice(0, 41);
  }

  function field(M, id, label, input, help) {
    input.id = id;
    return M.h('div', { class: 'field' }, M.h('label', { for: id }, label), input,
      help ? M.h('span', { class: 'help' }, help) : null);
  }

  // ------------------------------------------------------------ step 1: subject
  function viewSubject(M) {
    const domains = M.state.domains.filter((d) => !d.draft);
    const name = M.h('input', { type: 'text', required: true, autocomplete: 'off' });
    const id = M.h('input', { type: 'text', required: true, autocomplete: 'off', class: 'mono' });
    const description = M.h('input', { type: 'text' });
    const copyFrom = M.h('select', {}, ...domains.map((d) => M.h('option', { value: d.id }, d.name)));
    const languages = M.h('input', { type: 'text', class: 'mono' });
    const model = M.h('input', { type: 'text', class: 'mono' });
    let idEdited = false;
    name.addEventListener('input', () => { if (!idEdited) id.value = slug(name.value); });
    id.addEventListener('input', () => { idEdited = true; });
    const fillFrom = () => {
      const source = domains.find((d) => d.id === copyFrom.value);
      languages.value = source && source.languages ? source.languages.join(', ') : 'en';
      model.value = source && source.model ? source.model : '';
    };
    copyFrom.addEventListener('change', fillFrom);
    fillFrom();

    const submit = M.h('button', { type: 'submit', class: 'btn primary' }, 'Create the draft');
    const form = M.h('form', {
      class: 'stack wide-form', onsubmit: async (event) => {
        event.preventDefault();
        submit.disabled = true;
        try {
          const body = {
            id: id.value.trim(), name: name.value.trim(), description: description.value.trim(),
            languages: languages.value.split(',').map((x) => x.trim()).filter(Boolean),
            copy_from: copyFrom.value || null, model: model.value.trim(),
          };
          const made = await M.api.post('/api/new-domain', body);
          M.openDomain(made.id, `#/new/${enc(made.id)}`);
        } catch (error) { submit.disabled = false; M.toast(error.message, true); }
      },
    },
      field(M, 'nd-name', 'Name', name, 'What you follow, for example "Boating".'),
      field(M, 'nd-id', 'Short id', id, 'Lowercase letters, digits and dashes. It names the domain folder.'),
      field(M, 'nd-description', 'Description', description, 'One line. Optional.'),
      domains.length ? field(M, 'nd-copy', 'Model settings from', copyFrom, 'The provider, model and key name are copied. The key itself is never copied.') : null,
      field(M, 'nd-languages', 'Languages', languages, 'Codes separated by commas, such as en, fr. Each kept story is written once per language.'),
      field(M, 'nd-model', 'Model', model, 'As your provider names it.'),
      M.h('div', {}, submit));

    M.show(
      M.pageHead('New domain', 'Step 1 of 4: the subject. Nothing is read and no model is called yet.'),
      M.panel('Subject', form));
    name.focus();
  }

  // ------------------------------------------------------------ step 2: sources
  function resultView(M, result) {
    if (!result) return null;
    const [label, kind, iconName] = TEST_STATUS[result.status] || TEST_STATUS.failed;
    return M.h('div', { class: 'test-result' },
      M.pill(label, kind, iconName),
      M.h('span', {}, `${M.plural(result.items, 'story', 'stories')} in the last 7 days`
        + (result.latest ? `, latest ${M.when(result.latest)}` : '')),
      result.titles && result.titles.length ? M.h('ul', { class: 'titles' }, ...result.titles.map((t) => M.h('li', {}, t))) : null,
      result.error ? M.h('p', { class: 'hint' }, result.error) : null);
  }

  function sourceTester(M, domainId, kind, fields, onAdded) {
    // Add stays off until these exact values were tested and did not fail.
    const out = M.h('div', {});
    const test = M.h('button', { type: 'button', class: 'btn' }, 'Test');
    const add = M.h('button', { type: 'button', class: 'btn primary', disabled: true }, 'Add');
    let tested = null;
    const current = () => JSON.stringify([kind(), fields()]);
    async function run() {
      test.disabled = true;
      add.disabled = true;
      out.replaceChildren(M.h('p', { class: 'hint' }, 'Testing with Horizon’s collector…'));
      try {
        const result = await M.api.post(`/api/domains/${enc(domainId)}/source-test`, { kind: kind(), ...fields() });
        out.replaceChildren(resultView(M, result));
        tested = result.status === 'failed' ? null : current();
        add.disabled = tested === null;
      } catch (error) { out.replaceChildren(M.notice('Not tested', error.message)); }
      test.disabled = false;
    }
    test.addEventListener('click', run);
    add.addEventListener('click', async () => {
      if (tested !== current()) { add.disabled = true; return; }
      add.disabled = true;
      try {
        await M.api.post(`/api/domains/${enc(domainId)}/source-add`, { kind: kind(), ...fields() });
        M.toast('Source added.');
        onAdded();
      } catch (error) { add.disabled = false; M.toast(error.message, true); }
    });
    return { test, add, out, run, changed: () => { add.disabled = tested !== current(); } };
  }

  function manualAdd(M, domainId, onAdded) {
    const select = M.h('select', {}, ...KINDS.map(([id, label]) => M.h('option', { value: id }, label)));
    const holder = M.h('div', { class: 'stack' });
    let inputs = {};
    const tester = sourceTester(M, domainId, () => select.value,
      () => Object.fromEntries(Object.entries(inputs).map(([key, input]) => [key, input.value.trim()])), onAdded);
    function drawFields() {
      inputs = {};
      holder.replaceChildren(...kindOf(select.value)[2].map(([key, label]) => {
        inputs[key] = M.h('input', { type: 'text', autocomplete: 'off' });
        inputs[key].addEventListener('input', tester.changed);
        return field(M, `nd-src-${key}`, label, inputs[key]);
      }));
      tester.changed();
    }
    select.addEventListener('change', drawFields);
    drawFields();
    return M.h('div', { class: 'stack' },
      M.h('h3', {}, 'Add by hand'),
      field(M, 'nd-src-kind', 'Kind', select),
      holder,
      M.h('div', { class: 'row-actions' }, tester.test, tester.add),
      tester.out);
  }

  function suggestions(M, domainId, overview, onAdded) {
    const keyOk = overview.settings.ai.api_key_present;
    const interests = M.h('textarea', { rows: 3 }, overview.description || overview.name);
    const ask = M.h('button', { type: 'button', class: 'btn', disabled: !keyOk }, 'Ask Horizon for suggestions');
    const list = M.h('div', { class: 'stack' });
    ask.addEventListener('click', async () => {
      ask.disabled = true;
      list.replaceChildren(M.h('p', { class: 'hint' }, 'Horizon is asking the model…'));
      try {
        const answer = await M.api.post(`/api/domains/${enc(domainId)}/source-suggest`, { interests: interests.value });
        const used = M.h('p', { class: 'hint mono' },
          `Tokens used: ${M.number(answer.input_tokens)} in, ${M.number(answer.output_tokens)} out.`);
        if (!answer.suggestions.length) {
          list.replaceChildren(used, M.notice('No usable suggestion',
            'The model returned no source MastHead can add. Add sources by hand, or try other words.'));
        } else {
          const cards = answer.suggestions.map((item) => suggestionCard(M, domainId, item, onAdded));
          list.replaceChildren(used, ...cards.map((card) => card.node));
          for (const card of cards) await card.tester.run();  // one after the other
        }
      } catch (error) { list.replaceChildren(M.notice('No suggestion', error.message)); }
      ask.disabled = !keyOk;
    });
    return M.h('div', { class: 'stack' },
      M.h('h3', {}, 'Suggestions from Horizon'),
      field(M, 'nd-interests', 'What should this domain follow?', interests,
        keyOk ? 'Horizon asks your model for sources. It uses a few tokens; the count is shown after. Each suggestion is then tested.'
          : `This uses the model: put ${overview.settings.ai.api_key_env} in the domain's .env first.`),
      M.h('div', {}, ask),
      list);
  }

  function suggestionCard(M, domainId, item, onAdded) {
    const tester = sourceTester(M, domainId, () => item.kind, () => item.fields, onAdded);
    const node = M.h('div', { class: 'suggestion' },
      M.h('div', { class: 'spread' }, M.h('strong', {}, kindOf(item.kind)[1]), M.h('span', { class: 'mono' }, Object.values(item.fields).join(' · '))),
      item.description ? M.h('p', {}, item.description) : null,
      item.reason ? M.h('p', { class: 'hint' }, item.reason) : null,
      tester.out,
      M.h('div', { class: 'row-actions' }, tester.test, tester.add));
    return { node, tester };
  }

  function sourcesList(M, domainId, overview, refresh) {
    if (!overview.sources.length) return M.h('p', { class: 'hint' }, 'No source yet.');
    return M.h('ul', { class: 'facts source-list' }, ...overview.sources.map((source) => {
      const input = M.h('input', {
        type: 'checkbox', checked: source.enabled, 'aria-label': `${source.label}: ${source.enabled ? 'on' : 'off'}`,
        onchange: async () => {
          input.disabled = true;
          try { await M.api.post(`/api/domains/${enc(domainId)}/sources`, { key: source.key, enabled: input.checked }); refresh(); } catch (error) { input.checked = !input.checked; input.disabled = false; M.toast(error.message, true); }
        },
      });
      return M.h('li', {},
        M.h('span', { class: 'src-line' }, M.h('label', { class: 'switch' }, input, M.h('span', { class: 'track' })),
          M.h('span', {}, M.h('span', { class: 'src-name' }, source.label), M.h('span', { class: 'src-detail' }, `${source.kind_name} · ${source.detail}`))),
        source.enabled ? M.pill('On', 'ok', 'check') : M.pill('Off', 'idle', 'dash'));
    }));
  }

  // ------------------------------------------------------------ step 3: editorial rules
  function rulesPanel(M, domainId, state) {
    const f = state.fields;
    const area = (key, rows = 3) => M.h('textarea', { rows }, f[key] || '');
    const box = (key) => M.h('input', { type: 'checkbox', checked: Boolean(f[key]) });
    const inputs = {
      profile_name: M.h('input', { type: 'text' }), belongs: area('belongs'), typical: area('typical', 2),
      excluded: area('excluded', 2), goal: area('goal', 2), guidance: area('guidance'), editor_role: area('editor_role', 2),
      summary: area('summary'), background: box('background'), background_text: area('background_text'),
      web_search: box('web_search'), impact: box('impact'), impact_text: area('impact_text', 2),
      community: box('community'), community_text: area('community_text', 2), writing_rules: area('writing_rules'),
      analysis_max_chars: M.h('input', { type: 'number', min: 500, max: 100000, step: 500 }),
    };
    inputs.profile_name.value = f.profile_name || '';
    inputs.analysis_max_chars.value = f.analysis_max_chars;
    const tiers = TIERS.map((label, index) => M.h('textarea', { rows: 2 }, (f.tiers || [])[index] || ''));
    const check = (key, label) => M.h('div', { class: 'field switch-field' },
      M.h('label', { class: 'switch' }, inputs[key], M.h('span', { class: 'track' })), M.h('span', {}, label));

    const filesHolder = M.h('div', {});
    const save = M.h('button', { type: 'submit', class: 'btn primary' }, 'Save the rules');
    const form = M.h('form', {
      class: 'stack wide-form', onsubmit: async (event) => {
        event.preventDefault();
        const fields = {};
        for (const [key, input] of Object.entries(inputs)) {
          fields[key] = input.type === 'checkbox' ? input.checked : key === 'analysis_max_chars' ? Number(input.value) : input.value;
        }
        fields.tiers = tiers.map((t) => t.value);
        save.disabled = true;
        try {
          const saved = await M.api.post(`/api/domains/${enc(domainId)}/profile-form`, { fields });
          drawFiles(M, domainId, saved.files, filesHolder);
          M.toast('Rules saved in the profile files.');
        } catch (error) { M.toast(error.message, true); }
        save.disabled = false;
      },
    },
      M.h('h3', {}, 'What belongs'),
      field(M, 'nd-r-name', 'Profile name', inputs.profile_name),
      field(M, 'nd-r-belongs', 'What this domain covers', inputs.belongs),
      field(M, 'nd-r-typical', 'Typical stories', inputs.typical),
      field(M, 'nd-r-excluded', 'What does not belong', inputs.excluded),
      M.h('h3', {}, 'How to score, from 0 to 10'),
      field(M, 'nd-r-goal', 'Goal of the score', inputs.goal),
      ...tiers.map((tier, index) => field(M, `nd-r-tier-${index}`, `Score ${TIERS[index]}`, tier)),
      field(M, 'nd-r-guidance', 'What to weigh', inputs.guidance),
      field(M, 'nd-r-chars', 'Characters of each article read for scoring', inputs.analysis_max_chars,
        'Horizon reads 1,000 by default, which can miss what an article says further down.'),
      M.h('h3', {}, 'What to write for each kept story'),
      field(M, 'nd-r-role', 'Role of the writer', inputs.editor_role),
      field(M, 'nd-r-summary', 'Summary', inputs.summary),
      check('background', 'Background paragraph'), field(M, 'nd-r-bg', 'Background', inputs.background_text),
      check('web_search', 'Let the model search the web for background'),
      check('impact', 'Impact paragraph, when supported'), field(M, 'nd-r-impact', 'Impact', inputs.impact_text),
      check('community', 'Community discussion, when comments say something useful'), field(M, 'nd-r-comm', 'Community discussion', inputs.community_text),
      field(M, 'nd-r-rules', 'Writing rules', inputs.writing_rules),
      M.h('div', {}, save));
    drawFiles(M, domainId, state.files, filesHolder);
    return M.h('div', { class: 'stack' }, form, M.h('h3', {}, 'Profile files, as Horizon reads them'), filesHolder);
  }

  function drawFiles(M, domainId, files, holder) {
    const names = Object.keys(files);
    const body = M.h('div', {});
    const tabs = M.h('div', { class: 'tabs', role: 'tablist' }, ...names.map((name) => M.h('button', {
      type: 'button', role: 'tab', onclick: (event) => select(name, event.currentTarget),
    }, name)));
    function select(name, button) {
      for (const tab of tabs.children) tab.setAttribute('aria-selected', String(tab === button));
      const text = M.h('textarea', { rows: 14, class: 'mono', readonly: name === 'profile.json', 'aria-label': name }, files[name]);
      const save = name === 'profile.json' ? M.h('p', { class: 'hint' }, 'Written from the form; not edited here.')
        : M.h('button', {
          type: 'button', class: 'btn', onclick: async () => {
            try {
              const saved = await M.api.post(`/api/domains/${enc(domainId)}/profile-file`, { file: name, text: text.value });
              Object.assign(files, saved.files);
              M.toast(`${name} saved. Saving the form again rewrites it.`);
            } catch (error) { M.toast(error.message, true); }
          },
        }, `Save ${name}`);
      body.replaceChildren(text, M.h('div', {}, save));
    }
    holder.replaceChildren(tabs, body);
    if (tabs.firstChild) select(names[0], tabs.firstChild);
  }

  // ------------------------------------------------------------ step 4: trial, then create or discard
  function trialPanel(M, domainId, token) {
    const out = M.h('div', { class: 'stack' });
    const buttons = [
      ['collect', 'Collect only', 'No model call.'],
      ['select', 'Score and select', 'Uses the model to score; nothing is written.'],
    ].map(([until, label]) => M.h('button', {
      type: 'button', class: until === 'select' ? 'btn primary' : 'btn', onclick: () => start(until),
    }, label));
    async function start(until) {
      buttons.forEach((b) => { b.disabled = true; });
      try {
        let job = await M.api.post(`/api/domains/${enc(domainId)}/runs`, { until });
        while (job.status === 'running') {
          out.replaceChildren(stages(M, job));
          await new Promise((resolve) => setTimeout(resolve, 1500));
          if (!M.isCurrent(token)) return;
          job = await M.api.get(`/api/jobs/${enc(job.id)}`);
        }
        // replaceChildren would print "null" for an absent block, so absent blocks are dropped.
        out.replaceChildren(...[stages(M, job),
          job.error ? M.notice('The trial stopped', job.error) : null,
          job.run_id ? M.h('div', {}, M.h('button', {
            type: 'button', class: 'btn', onclick: () => M.openDomain(domainId, `#/runs/${enc(job.run_id)}`),
          }, 'Open in the inspector')) : null].filter(Boolean));
      } catch (error) { M.toast(error.message, true); }
      buttons.forEach((b) => { b.disabled = false; });
    }
    return M.h('div', { class: 'stack' },
      M.h('p', { class: 'hint' }, 'A trial stops before writing: the briefing is not produced. Collect only calls no model; Score and select uses it to score.'),
      M.h('div', { class: 'row-actions' }, ...buttons), out);
  }

  function stages(M, job) {
    const tokensIn = job.stages.reduce((sum, s) => sum + (s.input_tokens || 0), 0);
    const tokensOut = job.stages.reduce((sum, s) => sum + (s.output_tokens || 0), 0);
    return M.h('div', { class: 'stack' },
      M.h('ul', { class: 'facts' }, ...job.stages.filter((s) => s.status !== 'skipped').map((s) =>
        M.h('li', {}, M.h('span', {}, s.name), M.h('span', {}, s.detail || s.status)))),
      M.h('p', { class: 'hint mono' }, `Tokens used: ${M.number(tokensIn)} in, ${M.number(tokensOut)} out.`));
  }

  function finishPanel(M, domainId, overview) {
    const create = M.h('button', {
      type: 'button', class: 'btn primary', onclick: async () => {
        try {
          await M.api.post(`/api/domains/${enc(domainId)}/publish`, {});
          M.toast(`${overview.name} is created.`);
          M.openDomain(domainId, '#/runs');
        } catch (error) { M.toast(error.message, true); }
      },
    }, 'Create the domain');
    const discard = M.h('button', {
      type: 'button', class: 'btn', onclick: async () => {
        if (!window.confirm(`Discard the draft "${overview.name}"? Its folder, sources, rules and trial runs are deleted.`)) return;
        try {
          await M.api.post(`/api/domains/${enc(domainId)}/discard`, {});
          M.toast('Draft discarded.');
          M.state.domain = null;
          M.store.set('');
          window.location.hash = '#/domains';
        } catch (error) { M.toast(error.message, true); }
      },
    }, 'Discard this draft');
    return M.h('div', { class: 'stack' },
      M.h('p', { class: 'hint' }, 'Creating keeps everything as it is now and removes the draft mark. You can change sources and rules later.'),
      M.h('div', { class: 'row-actions' }, create, discard));
  }

  // ------------------------------------------------------------ the draft page
  async function viewDraft(M, domainId, token) {
    M.state.domain = domainId;
    M.store.set(domainId);
    const base = `/api/domains/${enc(domainId)}`;
    const [overview, rules] = await Promise.all([M.api.get(base), M.api.get(`${base}/profile-form`)]);
    if (!M.isCurrent(token)) return;
    if (!overview.draft) {
      M.show(M.pageHead(overview.name, 'This domain is already created.'),
        M.h('a', { class: 'btn primary', href: '#/sources' }, 'Sources and settings'));
      return;
    }
    const listHolder = M.h('div', {});
    async function refreshSources() {
      const fresh = await M.api.get(base);
      listHolder.replaceChildren(sourcesList(M, domainId, fresh, refreshSources));
    }
    listHolder.replaceChildren(sourcesList(M, domainId, overview, refreshSources));
    const ai = overview.settings.ai;
    const keyFact = ai.api_key_present ? 'found' : `not found (${ai.api_key_env})`;

    M.show(
      M.pageHead(`New domain: ${overview.name}`, 'A draft until you create it. Steps 2 to 4 can be done in any order and repeated.'),
      ai.api_key_present ? null : M.notice('No AI key for this domain yet',
        `Put ${ai.api_key_env}=... in a .env file in ${overview.folder}. MastHead never asks for it and never shows it. You can test and add sources without it.`),
      M.panel('1. Subject', M.h('ul', { class: 'facts' },
        M.fact('Name', overview.name), M.fact('Id', overview.id), M.fact('Languages', ai.languages.join(', ')),
        M.fact('Model', `${ai.provider} · ${ai.model}`), M.fact('AI key', keyFact))),
      M.panel('2. Sources',
        M.h('p', { class: 'hint' }, 'Hacker News, Reddit and Telegram are read by Horizon unless switched off: this draft switches them off until you add a subreddit or a channel.'),
        listHolder, manualAdd(M, domainId, refreshSources), suggestions(M, domainId, overview, refreshSources)),
      M.panel('3. Editorial rules', rulesPanel(M, domainId, rules)),
      M.panel('4. Trial run', trialPanel(M, domainId, token)),
      M.panel('Create or discard', finishPanel(M, domainId, overview)));
  }

  window.MastHeadNewDomain = {
    view: (domainId, token) => {
      const M = window.MastHead;
      return domainId ? viewDraft(M, domainId, token) : viewSubject(M);
    },
  };
})();
