/* MastHead for Horizon: sources, for New domain (Horizon's setup) and the editor's Sources step.
   Paste one or many sources; each line is read (kind from the text only, no site visited),
   then tested with Horizon's collector. Horizon can also suggest sources (one model call).
   In New domain the ticked sources are the selection handed to Horizon's build_config;
   in the editor they are added one by one, each entry made by Horizon. */
(() => {
  'use strict';
  const enc = encodeURIComponent;
  const KIND_LABEL = {
    rss: 'Feed', github_repo: 'GitHub releases', github_user: 'GitHub user',
    reddit_subreddit: 'Subreddit', reddit_user: 'Reddit user', telegram: 'Telegram channel', hackernews: 'Hacker News',
  };
  const RESULT = {
    ok: ['Works', 'ok', 'check'], empty: ['Nothing in 7 days', 'idle', 'dash'],
    failed: ['Failed', 'warn', 'block'], testing: ['Testing…', 'idle', 'dash'],
    unknown: ['Not a source', 'warn', 'block'],
  };
  const describe = (fields) => Object.values(fields || {}).join(' · ');
  let rowCount = 0;

  // One line to check: what it is, its test result, and a tick box once it can be kept.
  function checkRow(M, api, item) {
    rowCount += 1;
    const id = `src-check-${rowCount}`;
    const box = M.h('input', { type: 'checkbox', id, disabled: true });
    const status = M.h('span', { class: 'check-status' });
    const detail = M.h('div', { class: 'check-detail' });
    const label = M.h('label', { for: id, class: 'check-label' },
      M.h('span', { class: 'strong' }, item.kind ? KIND_LABEL[item.kind] : item.line.trim()),
      item.kind ? M.h('span', { class: 'mono' }, describe(item.fields)) : null);
    const row = M.h('li', { class: 'check-row' }, box, M.h('div', { class: 'check-body' }, label,
      item.description ? M.h('p', {}, item.description) : null,
      item.reason ? M.h('p', { class: 'hint' }, item.reason) : null,
      detail), status);
    const show = (key, text) => {
      const [name, kind, iconName] = RESULT[key];
      status.replaceChildren(M.pill(name, kind, iconName));
      detail.replaceChildren(...(text ? [M.h('p', { class: 'hint' }, text)] : []));
    };
    async function test() {
      if (!item.kind) { show('unknown', item.error); return; }
      show('testing');
      try {
        const result = await M.api.post(api.test, { type: item.kind, config: item.fields });
        const latest = result.latest ? `, latest ${M.when(result.latest)}` : '';
        const titles = result.titles && result.titles.length ? ` — ${result.titles.slice(0, 2).join(' · ')}` : '';
        show(result.status, result.status === 'failed' ? result.error
          : `${M.plural(result.items, 'story', 'stories')} in the last 7 days${latest}${titles}`);
        box.disabled = result.status === 'failed';
        box.checked = !box.disabled;
        if (api.onTick) api.onTick();
      } catch (error) { show('failed', error.message); }
    }
    box.addEventListener('change', () => { if (api.onTick) api.onTick(); });
    const source = () => ({ type: item.kind, config: item.fields });
    return { row, test, item, box, source };
  }

  /* The list of lines being checked. mode 'select' (New domain): lines accumulate and the
     ticked ones are the selection. mode 'add' (editor): ticked lines are added to the domain. */
  function checker(M, api, mode, onAdded) {
    const list = M.h('ul', { class: 'check-list' });
    const message = window.MastHeadKit.messageArea(M);
    const addButton = M.h('button', { type: 'button', class: 'btn primary', hidden: true }, 'Add the ticked sources');
    let rows = [];
    async function check(items) {
      const fresh = items.map((item) => checkRow(M, api, item));
      rows = mode === 'select' ? [...rows, ...fresh] : fresh;
      list.replaceChildren(...rows.map((r) => r.row));
      addButton.hidden = mode === 'select';
      message.clear();
      for (const r of fresh) await r.test();  // one after the other: one host at a time
    }
    const selected = () => rows.filter((r) => r.box.checked && !r.box.disabled).map((r) => r.source());
    addButton.addEventListener('click', async () => {
      const chosen = rows.filter((r) => r.box.checked && !r.box.disabled);
      if (!chosen.length) { message.error('Nothing ticked', 'Tick the sources to add. A source that failed its test cannot be added.'); return; }
      addButton.disabled = true;
      const problems = [];
      for (const r of chosen) {
        try {
          await M.api.post(api.add, r.source());
          r.box.checked = false;
          r.box.disabled = true;
          r.row.classList.add('added');
          r.row.querySelector('.check-status').replaceChildren(M.pill('Added', 'ok', 'check'));
        } catch (error) { problems.push(`${describe(r.item.fields)}: ${error.message}`); }
      }
      await onAdded();  // the list and the step states first, then the message
      addButton.disabled = false;
      if (problems.length) message.error('Some sources were not added', problems.join(' '));
      else message.info('Added', `${M.plural(chosen.length, 'source was', 'sources were')} added and switched on.`);
    });
    return { list, addButton, message, check, selected };
  }

  function pasteBox(M, api, check) {
    const text = M.h('textarea', {
      id: 'src-paste', rows: 4, spellcheck: 'false', autocapitalize: 'none', autocorrect: 'off',
      placeholder: 'https://example.com/feed\ngithub.com/owner/repository\nr/subreddit\nt.me/channel',
    });
    const message = window.MastHeadKit.messageArea(M);
    const button = M.h('button', { type: 'button', class: 'btn primary' }, 'Check these sources');
    button.addEventListener('click', async () => {
      message.clear();
      if (!text.value.trim()) { message.error('Nothing to check', 'Paste at least one source.'); text.focus(); return; }
      button.disabled = true;
      try {
        const parsed = await M.api.post(api.parse, { text: text.value });
        text.value = '';
        await check(parsed.lines);
      } catch (error) { message.error('Not checked', error.message); }
      button.disabled = false;
    });
    return M.h('div', { class: 'stack' },
      M.h('div', { class: 'field' },
        M.h('label', { for: 'src-paste' }, 'Paste sources, one per line'),
        text,
        M.h('span', { class: 'help' }, 'A feed address, a GitHub repository (its releases), a subreddit or a Telegram channel. To name a feed, write "Name | address". Each line is tested with Horizon’s collector over the last 7 days.')),
      M.h('div', {}, button), message.area);
  }

  /* Two ways Horizon's setup finds sources: its preset library, matched on the words typed
     (src/setup/presets.py, no model call, read from the copy shipped with MastHead), and its
     recommendation by the model (src/setup/ai_recommend.py). presets(interests) and ask(interests)
     do the calls; keyOk() says whether the model can be called. */
  function suggestions(M, { ask, presets, keyOk, keyHint, interests: start }, check) {
    const interests = M.h('textarea', { id: 'src-interests', rows: 2 }, start || '');
    const message = window.MastHeadKit.messageArea(M);
    const button = M.h('button', { type: 'button', class: 'btn' }, 'Ask Horizon');
    const presetButton = M.h('button', { type: 'button', class: 'btn' }, 'Search the presets');
    const toCheck = (list) => list.map((s) => ({ line: describe(s.config), kind: s.type, fields: s.config,
      description: s.description, reason: s.theme ? `From the preset list “${s.theme}”.` : s.reason, error: null }));
    presetButton.addEventListener('click', async () => {
      if (!interests.value.trim()) { message.error('Nothing to search', 'Describe what the domain follows, in a few words.'); interests.focus(); return; }
      presetButton.disabled = true;
      message.clear();
      try {
        const answer = await presets(interests.value);
        const problems = answer.problems && answer.problems.length ? ` Lists that could not be read: ${answer.problems.join('; ')}` : '';
        if (!answer.suggestions.length) {
          message.error('No preset matches these words', `The preset lists cover: ${answer.themes.join(', ')}. Paste your own sources, or ask Horizon.${problems}`);
        } else {
          message.info(`${M.plural(answer.suggestions.length, 'preset source', 'preset sources')}`, `Found in the preset lists, with no model call. They are tested in the list.${problems}`);
          await check(toCheck(answer.suggestions));
        }
      } catch (error) { message.error('No preset', error.message); }
      presetButton.disabled = false;
    });
    // Examples from Horizon's own setup (get_interests), plus one outside technology.
    const examples = M.h('span', { class: 'help', id: 'src-interests-examples' },
      'A few words or a sentence, in any language. For example: “LLM inference”, “Rust systems programming”, '
      + '“web security” (Horizon’s own examples), or “flight simulator add-ons, airliner and scenery releases”.');
    const help = M.h('span', { class: 'help', id: 'src-interests-help' });
    interests.setAttribute('aria-describedby', 'src-interests-examples src-interests-help');
    function gate() {
      button.disabled = !keyOk();
      help.textContent = keyOk()
        ? 'Horizon asks your model for sources, as its own setup does. It uses a few tokens; the count is shown after.'
        : keyHint();
    }
    button.addEventListener('click', async () => {
      if (!interests.value.trim()) { message.error('Nothing to ask', 'Describe what the domain follows, in a few words.'); interests.focus(); return; }
      button.disabled = true;
      message.info('Asking', 'Horizon is asking the model…');
      try {
        const answer = await ask(interests.value);
        const used = `Tokens used: ${M.number(answer.input_tokens)} in, ${M.number(answer.output_tokens)} out.`;
        if (!answer.suggestions.length) {
          message.error('No usable suggestion', `Horizon returned no source it can add. It also returns nothing when the call fails. ${used}`);
        } else {
          message.info(`${M.plural(answer.suggestions.length, 'suggestion', 'suggestions')}`, `${used} They are tested in the list above.`);
          await check(answer.suggestions.map((s) => ({ line: describe(s.config), kind: s.type, fields: s.config,
            description: s.description, reason: s.reason, error: null })));
        }
      } catch (error) { message.error('No suggestion', error.message); }
      gate();
    });
    gate();
    return {
      gate,
      node: M.h('div', { class: 'stack' },
        M.h('div', { class: 'field' }, M.h('label', { for: 'src-interests' }, 'What should this domain follow?'), interests, examples, help),
        M.h('div', { class: 'row-actions' }, presetButton, button),
        M.h('p', { class: 'hint' }, 'Search the presets: ready-made lists of sources (Horizon’s, MastHead’s and yours), matched on your words by Horizon, no model call, free. Ask Horizon: your model suggests sources.'),
        message.area),
    };
  }

  // The sources Horizon will read, with switches saved by one button.
  function currentSources(M, domainId, tracker, onSaved) {
    const holder = M.h('ul', { class: 'source-switches' });
    const message = window.MastHeadKit.messageArea(M);
    const pending = new Map();  // source key -> wanted state, until saved
    const save = M.h('button', { type: 'button', class: 'btn primary' }, 'Save the sources');
    function draw(sources) {
      if (!sources.length) { holder.replaceChildren(M.h('li', { class: 'hint' }, 'No source yet.')); return; }
      holder.replaceChildren(...sources.map((source, index) => {
        const on = pending.has(source.key) ? pending.get(source.key) : source.enabled;
        const input = M.h('input', { type: 'checkbox', role: 'switch', id: `src-on-${index}`, checked: on });
        input.addEventListener('change', () => {
          if (input.checked === source.enabled) pending.delete(source.key); else pending.set(source.key, input.checked);
          if (pending.size) tracker.mark(); else tracker.clean();
        });
        return M.h('li', { class: source.enabled ? '' : 'off' },
          M.h('label', { class: 'switch', for: `src-on-${index}` }, input, M.h('span', { class: 'track' }),
            M.h('span', { class: 'switch-text' },
              M.h('span', { class: 'src-name' }, source.label),
              M.h('span', { class: 'src-detail' }, `${source.kind_name} · ${source.detail}`))),
          source.implicit ? M.pill('On by default', 'warn', 'alert') : null);
      }));
    }
    save.addEventListener('click', async () => {
      if (!pending.size) { message.info('Nothing to save', 'No switch was changed.'); return; }
      save.disabled = true;
      try {
        await M.api.post(`/api/domains/${enc(domainId)}/sources-enabled`,
          { changes: [...pending].map(([key, enabled]) => ({ key, enabled })) });
        pending.clear();
        tracker.clean('Saved');
        message.clear();
        onSaved();
      } catch (error) { message.error('Not saved', error.message); }
      save.disabled = false;
    });
    return { holder, draw, save, message };
  }

  /* Share the domain's sources that are on as a preset list, in Horizon's preset format,
     written to the user's presets folder; the file can then be sent to someone else. */
  function shareBox(M, domainId, overview) {
    const Kit = window.MastHeadKit;
    const message = Kit.messageArea(M);
    const name = M.h('input', { type: 'text', id: 'share-name', maxlength: 80, 'aria-describedby': 'share-name-help' });
    const keywords = M.h('input', { type: 'text', id: 'share-keywords', 'aria-describedby': 'share-keywords-help' });
    const button = M.h('button', { type: 'button', class: 'btn' }, 'Write the preset list');
    const result = M.h('div', { class: 'stack' });
    async function send(replace) {
      return M.api.post(`/api/domains/${enc(domainId)}/preset-share`, { name: name.value, keywords: keywords.value, replace });
    }
    button.addEventListener('click', async () => {
      message.clear();
      result.replaceChildren();
      button.disabled = true;
      try {
        let written;
        try { written = await send(false); } catch (error) {
          if (error.status !== 409) throw error;
          const replace = await Kit.confirmDialog(M, {
            title: 'Replace your preset list?', body: error.message, confirm: 'Replace it', danger: true,
          });
          if (!replace) { button.disabled = false; return; }
          written = await send(true);
        }
        const download = M.h('a', { class: 'btn', download: written.file,
          href: URL.createObjectURL(new Blob([written.text], { type: 'application/json' })) }, 'Download the file');
        message.info('Preset list written', `${M.plural(written.sources, 'source', 'sources')} in ${written.path}. The search finds it from now on; send the file to share it.`);
        result.replaceChildren(...[
          written.left_out.length ? M.h('p', { class: 'hint' }, `Not in the list, because Horizon’s preset format has no place for them: ${written.left_out.join(', ')}.`) : null,
          M.h('div', {}, download)].filter(Boolean));
      } catch (error) { message.error('Not written', error.message); }
      button.disabled = false;
    });
    return M.h('details', { class: 'fold' }, M.h('summary', {}, 'Share these sources as a preset list'),
      M.h('div', { class: 'stack' },
        M.h('p', { class: 'hint' }, 'The sources switched on are written as a preset list, in Horizon’s own format, so that others can find them with Search the presets.'),
        M.h('div', { class: 'field' }, M.h('label', { for: 'share-name' }, 'Theme'), name,
          M.h('span', { class: 'help', id: 'share-name-help' }, `The name shown in the search, for example “Flight simulation”. The file is named after this domain (${overview.id}.json).`)),
        M.h('div', { class: 'field' }, M.h('label', { for: 'share-keywords' }, 'Keywords'), keywords,
          M.h('span', { class: 'help', id: 'share-keywords-help' }, 'Words someone would type to find this list, separated by commas. For example: flight simulator, msfs, x-plane, simulation de vol.')),
        M.h('div', {}, button), message.area, result));
  }

  // The editor's Sources step, for a domain that exists.
  function step(M, ctx) {
    const { domainId, overview, tracker, refresh } = ctx;
    const base = `/api/domains/${enc(domainId)}`;
    const api = { parse: `${base}/source-parse`, test: `${base}/source-test`, add: `${base}/source-add` };
    const current = currentSources(M, domainId, tracker, refresh);
    current.draw(overview.sources);
    const check = checker(M, api, 'add', refresh);
    let latest = overview;
    const suggest = suggestions(M, {
      ask: (interests) => M.api.post(`${base}/source-suggest`, { interests }),
      presets: (interests) => M.api.post(`${base}/source-presets`, { interests }),
      keyOk: () => latest.settings.ai.api_key_present,
      keyHint: () => 'This uses the model: enter the key in step Subject and AI first.',
      interests: overview.description || overview.name,
    }, check.check);
    return {
      redraw(fresh) { latest = fresh; current.draw(fresh.sources); suggest.gate(); },
      body: [
        M.h('section', { class: 'sub', 'aria-labelledby': 'src-add-title' },
          M.h('h3', { id: 'src-add-title' }, 'Add sources'),
          pasteBox(M, api, check.check),
          check.list, M.h('div', {}, check.addButton), check.message.area,
          M.h('details', { class: 'fold' }, M.h('summary', {}, 'Find sources with Horizon (presets or your model)'), suggest.node)),
        M.h('section', { class: 'sub', 'aria-labelledby': 'src-list-title' },
          M.h('h3', { id: 'src-list-title' }, 'Sources Horizon will read'),
          M.h('p', { class: 'hint' }, 'Every source Horizon will read is listed, including Hacker News, Reddit and Telegram when Horizon reads them.'),
          current.holder,
          M.h('div', { class: 'row-actions' }, current.save, tracker.indicator), current.message.area,
          shareBox(M, domainId, overview)),
      ],
    };
  }

  window.MastHeadEditorSources = { step, checker, pasteBox, suggestions, KIND_LABEL };
})();
