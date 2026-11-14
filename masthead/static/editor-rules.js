/* MastHead for Horizon: the Editorial rules step of the domain editor.
   Two ways to write Horizon's profile files: a short form (three essential questions,
   the rest folded under Advanced), or the files themselves as text. A domain imported
   with hand-written files opens on the files, and the form never overwrites them
   without an explicit confirmation. One Save button for the step. */
(() => {
  'use strict';
  const enc = encodeURIComponent;
  const TIERS = ['9-10', '7-8', '5-6', '3-4', '0-2'];
  const TEXT_FILES = ['match.md', 'analysis.md', 'enrichment.md'];

  function field(M, id, label, input, help) {
    input.id = id;
    const helpId = help ? `${id}-help` : null;
    if (helpId) input.setAttribute('aria-describedby', helpId);
    return M.h('div', { class: 'field' }, M.h('label', { for: id }, label), input,
      help ? M.h('span', { class: 'help', id: helpId }, help) : null);
  }

  function formMode(M, state, tracker) {
    const f = state.fields;
    const area = (key) => tracker.watch(M.h('textarea', { rows: 2 }, f[key] || ''));
    const toggle = (key) => tracker.watch(M.h('input', { type: 'checkbox', role: 'switch', checked: Boolean(f[key]) }));
    const inputs = {
      belongs: area('belongs'), excluded: area('excluded'), guidance: area('guidance'),
      profile_name: tracker.watch(M.h('input', { type: 'text', value: f.profile_name || '' })),
      typical: area('typical'), goal: area('goal'), editor_role: area('editor_role'), summary: area('summary'),
      background: toggle('background'), background_text: area('background_text'), web_search: toggle('web_search'),
      impact: toggle('impact'), impact_text: area('impact_text'), community: toggle('community'),
      community_text: area('community_text'), writing_rules: area('writing_rules'),
      analysis_max_chars: tracker.watch(M.h('input', { type: 'number', min: 500, max: 100000, step: 500, required: true, value: f.analysis_max_chars })),
    };
    const tiers = TIERS.map((label, i) => tracker.watch(M.h('textarea', { rows: 1 }, (f.tiers || [])[i] || '')));
    const sw = (key, label) => M.h('div', { class: 'field' },
      M.h('label', { class: 'switch', for: `r-${key}` }, Object.assign(inputs[key], { id: `r-${key}` }),
        M.h('span', { class: 'track' }), M.h('span', { class: 'switch-text' }, label)));
    const values = () => {
      const out = {};
      for (const [key, input] of Object.entries(inputs)) {
        out[key] = input.type === 'checkbox' ? input.checked : key === 'analysis_max_chars' ? Number(input.value) : input.value;
      }
      out.tiers = tiers.map((t) => t.value);
      return out;
    };
    const node = M.h('div', { class: 'stack' },
      M.h('fieldset', {}, M.h('legend', {}, 'The essentials'),
        field(M, 'r-belongs', 'What does this domain cover?', inputs.belongs, 'The subjects, products or events a story must be about.'),
        field(M, 'r-excluded', 'What does not belong?', inputs.excluded, 'Stories to leave out even when they mention the subject.'),
        field(M, 'r-guidance', 'What makes a story important?', inputs.guidance, 'What the model should weigh when it gives a score from 0 to 10.')),
      M.h('details', { class: 'fold' }, M.h('summary', {}, 'Advanced: scoring grid, writing, text read'),
        M.h('div', { class: 'stack' },
          M.h('fieldset', {}, M.h('legend', {}, 'Profile'),
            field(M, 'r-name', 'Profile name', inputs.profile_name),
            field(M, 'r-typical', 'Typical stories', inputs.typical)),
          M.h('fieldset', {}, M.h('legend', {}, 'Score from 0 to 10'),
            field(M, 'r-goal', 'Goal of the score', inputs.goal),
            ...tiers.map((t, i) => field(M, `r-tier-${i}`, `Score ${TIERS[i]}`, t)),
            field(M, 'r-chars', 'Characters of each article read for scoring', inputs.analysis_max_chars,
              'From 500 to 100,000. Horizon reads 1,000 by default, which can miss what an article says further down.')),
          M.h('fieldset', {}, M.h('legend', {}, 'What to write for each kept story'),
            field(M, 'r-role', 'Role of the writer', inputs.editor_role),
            field(M, 'r-summary', 'Summary', inputs.summary),
            sw('background', 'Background paragraph'), field(M, 'r-bg', 'Background', inputs.background_text),
            sw('web_search', 'Let the model search the web for background'),
            sw('impact', 'Impact paragraph, when supported'), field(M, 'r-impact', 'Impact', inputs.impact_text),
            sw('community', 'Community discussion, when comments say something useful'),
            field(M, 'r-comm', 'Community discussion', inputs.community_text),
            field(M, 'r-rules', 'Writing rules', inputs.writing_rules)))));
    return { node, values, form: node };
  }

  function filesMode(M, state, tracker) {
    const areas = {};
    const node = M.h('div', { class: 'stack' }, ...TEXT_FILES.filter((name) => state.files[name] !== undefined).map((name) => {
      areas[name] = tracker.watch(M.h('textarea', { rows: 8, class: 'mono', spellcheck: 'false' }, state.files[name]));
      return field(M, `r-file-${name.replace('.', '-')}`, name, areas[name]);
    }));
    const changed = () => Object.entries(areas).filter(([name, area]) => area.value !== state.files[name]);
    return { node, changed };
  }

  function preview(M, files) {
    return M.h('details', { class: 'fold' }, M.h('summary', {}, 'Profile files, as Horizon reads them'),
      ...Object.entries(files).map(([name, text]) =>
        M.h('div', { class: 'stack' }, M.h('h4', {}, name), M.h('pre', { class: 'file-preview' }, text))));
  }

  function step(M, ctx) {
    const { domainId, rules, tracker } = ctx;
    const Kit = window.MastHeadKit;
    const message = Kit.messageArea(M);
    let state = rules;
    let mode = state.managed ? 'form' : 'files';
    const holder = M.h('div', {});
    const save = M.h('button', { type: 'button', class: 'btn primary' }, 'Save the rules');
    const modeName = 'rules-mode';
    const radio = (value, label) => {
      const input = M.h('input', { type: 'radio', name: modeName, id: `rules-mode-${value}`, value, checked: mode === value });
      input.addEventListener('change', async () => {
        if (!input.checked) return;
        if (tracker.dirty && !await Kit.confirmDialog(M, {
          title: 'Discard the unsaved changes?',
          body: 'Changing how you write the rules discards what you typed and did not save.',
          confirm: 'Discard them', danger: true,
        })) {
          document.getElementById(`rules-mode-${mode}`).checked = true;
          return;
        }
        mode = value;
        tracker.clean();
        draw();
      });
      return M.h('label', { for: `rules-mode-${value}`, class: 'radio' }, input, M.h('span', {}, label));
    };
    let current = null;
    function draw() {
      current = mode === 'form' ? formMode(M, state, tracker) : filesMode(M, state, tracker);
      // replaceChildren would print "null" for an absent block, so absent blocks are dropped.
      holder.replaceChildren(...[
        mode === 'form' && !state.managed ? M.notice('These rules were written by hand',
          'Saving the form replaces the hand-written files of this domain. You will be asked to confirm.') : null,
        mode === 'files' && state.managed ? M.notice('Editing the files directly',
          'If you save the form again later, it rewrites these files.', 'info') : null,
        current.node,
        mode === 'form' ? preview(M, state.files) : null,
      ].filter(Boolean));
    }
    save.addEventListener('click', async () => {
      message.clear();
      save.disabled = true;
      try {
        if (mode === 'form') {
          let replace = false;
          if (!state.managed) {
            replace = await Kit.confirmDialog(M, {
              title: 'Replace the hand-written rules?',
              body: `The files of profile "${state.profile_id}" will be rewritten from the form. The current text is lost.`,
              confirm: 'Replace them', danger: true,
            });
            if (!replace) { save.disabled = false; return; }
          }
          state = await M.api.post(`/api/domains/${enc(domainId)}/profile-form`, { fields: current.values(), replace });
        } else {
          const changed = current.changed();
          if (!changed.length) { message.info('Nothing to save', 'No file was changed.'); save.disabled = false; return; }
          for (const [name, area] of changed) {
            state = await M.api.post(`/api/domains/${enc(domainId)}/profile-file`, { file: name, text: area.value });
          }
        }
        tracker.clean('Saved');
        draw();
        ctx.onSaved(state);
      } catch (error) { message.error('Not saved', error.message); }
      save.disabled = false;
    });
    draw();
    return {
      body: [
        M.h('fieldset', { class: 'mode' }, M.h('legend', {}, 'Write the rules with'),
          radio('form', 'The form'), radio('files', 'The files, as text')),
        holder,
        M.h('div', { class: 'row-actions' }, save, tracker.indicator),
        message.area,
      ],
    };
  }

  window.MastHeadEditorRules = { step };
})();
