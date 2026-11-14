/* MastHead for Horizon: the Sources step of the domain editor.
   Paste one or many sources; each line is read (kind from the text only, no site visited),
   then tested with Horizon's collector. Tick and add. Switches are saved with one button. */
(() => {
  'use strict';
  const enc = encodeURIComponent;
  const KIND_LABEL = {
    rss: 'Feed', github_repo: 'GitHub releases', github_user: 'GitHub user',
    reddit_subreddit: 'Subreddit', telegram: 'Telegram channel',
  };
  const RESULT = {
    ok: ['Works', 'ok', 'check'], empty: ['Nothing in 7 days', 'idle', 'dash'],
    failed: ['Failed', 'warn', 'block'], testing: ['Testing…', 'idle', 'dash'],
    unknown: ['Not a source', 'warn', 'block'],
  };
  const describe = (fields) => Object.values(fields || {}).join(' · ');

  // One line to check: what it is, its test result, and a tick box once it can be added.
  function checkRow(M, domainId, item, index) {
    const box = M.h('input', { type: 'checkbox', id: `src-check-${index}`, disabled: true });
    const status = M.h('span', { class: 'check-status' });
    const detail = M.h('div', { class: 'check-detail' });
    const label = M.h('label', { for: `src-check-${index}`, class: 'check-label' },
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
        const result = await M.api.post(`/api/domains/${enc(domainId)}/source-test`, { kind: item.kind, ...item.fields });
        const latest = result.latest ? `, latest ${M.when(result.latest)}` : '';
        const titles = result.titles && result.titles.length ? ` — ${result.titles.slice(0, 2).join(' · ')}` : '';
        show(result.status, result.status === 'failed' ? result.error
          : `${M.plural(result.items, 'story', 'stories')} in the last 7 days${latest}${titles}`);
        box.disabled = result.status === 'failed';
        box.checked = !box.disabled;
      } catch (error) { show('failed', error.message); }
    }
    return { row, test, item, box };
  }

  function checker(M, domainId, onAdded) {
    const list = M.h('ul', { class: 'check-list' });
    const message = window.MastHeadKit.messageArea(M);
    const addButton = M.h('button', { type: 'button', class: 'btn primary', hidden: true }, 'Add the ticked sources');
    let rows = [];
    async function check(items) {
      rows = items.map((item, index) => checkRow(M, domainId, item, index));
      list.replaceChildren(...rows.map((r) => r.row));
      addButton.hidden = false;
      message.clear();
      for (const r of rows) await r.test();  // one after the other: one host at a time
    }
    addButton.addEventListener('click', async () => {
      const chosen = rows.filter((r) => r.box.checked && !r.box.disabled);
      if (!chosen.length) { message.error('Nothing ticked', 'Tick the sources to add. A source that failed its test cannot be added.'); return; }
      addButton.disabled = true;
      const problems = [];
      for (const r of chosen) {
        try {
          await M.api.post(`/api/domains/${enc(domainId)}/source-add`, { kind: r.item.kind, ...r.item.fields });
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
    return { list, addButton, message, check };
  }

  function pasteBox(M, domainId, check) {
    const text = M.h('textarea', {
      id: 'src-paste', rows: 4, spellcheck: 'false', autocapitalize: 'none', autocorrect: 'off',
      placeholder: 'https://example.com/feed\ngithub.com/owner/repository\nr/subreddit\nt.me/channel',
    });
    const message = window.MastHeadKit.messageArea(M);
    const button = M.h('button', { type: 'submit', class: 'btn primary' }, 'Check these sources');
    const form = M.h('form', {
      class: 'stack', 'aria-labelledby': 'src-paste-label', onsubmit: async (event) => {
        event.preventDefault();
        message.clear();
        if (!text.value.trim()) { message.error('Nothing to check', 'Paste at least one source.'); text.focus(); return; }
        button.disabled = true;
        try {
          const parsed = await M.api.post(`/api/domains/${enc(domainId)}/source-parse`, { text: text.value });
          await check(parsed.lines);
        } catch (error) { message.error('Not checked', error.message); }
        button.disabled = false;
      },
    },
      M.h('div', { class: 'field' },
        M.h('label', { for: 'src-paste', id: 'src-paste-label' }, 'Paste sources, one per line'),
        text,
        M.h('span', { class: 'help' }, 'A feed address, a GitHub repository (its releases), a subreddit or a Telegram channel. To name a feed, write "Name | address". Each line is tested with Horizon’s collector over the last 7 days.')),
      M.h('div', {}, button), message.area);
    return form;
  }

  function suggestions(M, domainId, overview, check) {
    const ai = overview.settings.ai;
    const interests = M.h('textarea', { id: 'src-interests', rows: 2 }, overview.description || overview.name);
    const message = window.MastHeadKit.messageArea(M);
    const button = M.h('button', { type: 'submit', class: 'btn', disabled: !ai.api_key_present }, 'Ask Horizon');
    const form = M.h('form', {
      class: 'stack', onsubmit: async (event) => {
        event.preventDefault();
        button.disabled = true;
        message.info('Asking', 'Horizon is asking the model…');
        try {
          const answer = await M.api.post(`/api/domains/${enc(domainId)}/source-suggest`, { interests: interests.value });
          const used = `Tokens used: ${M.number(answer.input_tokens)} in, ${M.number(answer.output_tokens)} out.`;
          if (!answer.suggestions.length) {
            message.error('No usable suggestion', `The model returned no source MastHead can add. ${used}`);
          } else {
            message.info(`${M.plural(answer.suggestions.length, 'suggestion', 'suggestions')}`, `${used} They are tested in the list above.`);
            await check(answer.suggestions.map((s) => ({ line: describe(s.fields), kind: s.kind, fields: s.fields,
              description: s.description, reason: s.reason, error: null })));
          }
        } catch (error) { message.error('No suggestion', error.message); }
        button.disabled = !ai.api_key_present;
      },
    },
      M.h('div', { class: 'field' }, M.h('label', { for: 'src-interests' }, 'What should this domain follow?'), interests,
        M.h('span', { class: 'help' }, ai.api_key_present
          ? 'Horizon asks your model for sources. It uses a few tokens; the count is shown after.'
          : `This uses the model: enter the key in step 1 first.`)),
      M.h('div', {}, button), message.area);
    return M.h('details', { class: 'fold' }, M.h('summary', {}, 'Ask Horizon for suggestions'), form);
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

  function step(M, ctx) {
    const { domainId, overview, tracker, refresh } = ctx;
    const current = currentSources(M, domainId, tracker, refresh);
    current.draw(overview.sources);
    const check = checker(M, domainId, refresh);
    return {
      redraw(fresh) { current.draw(fresh.sources); },
      body: [
        M.h('section', { class: 'sub', 'aria-labelledby': 'src-add-title' },
          M.h('h3', { id: 'src-add-title' }, 'Add sources'),
          pasteBox(M, domainId, check.check),
          check.list, M.h('div', {}, check.addButton), check.message.area,
          suggestions(M, domainId, overview, check.check)),
        M.h('section', { class: 'sub', 'aria-labelledby': 'src-list-title' },
          M.h('h3', { id: 'src-list-title' }, 'Sources Horizon will read'),
          M.h('p', { class: 'hint' }, 'Hacker News, Reddit and Telegram are read by Horizon unless switched off: they are listed here so you can see it.'),
          current.holder,
          M.h('div', { class: 'row-actions' }, current.save, tracker.indicator), current.message.area),
      ],
    };
  }

  window.MastHeadEditorSources = { step };
})();
