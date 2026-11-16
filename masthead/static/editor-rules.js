/* MastHead for Horizon: the Editorial rules step of the domain editor.
   Two ways to write Horizon's profile files: a form, or the files themselves as text.
   The form starts empty; examples are help text, never written. Nothing is written
   before Save. A file changed outside the form is never replaced without a
   confirmation that names it, whatever the domain. One Save button for the step. */
(() => {
  'use strict';
  const enc = encodeURIComponent;
  const TIERS = ['9-10', '7-8', '5-6', '3-4', '0-2'];
  const TIER_EXAMPLES = [
    'Major news that changes things for most readers.',
    'Important developments worth prompt attention, with concrete details.',
    'Interesting but not urgent: incremental changes, useful guides.',
    'Routine updates, common knowledge, or mostly promotion.',
    'Noise: off-topic, trivial, or purely promotional.',
  ];
  const TEXT_FILES = ['match.md', 'analysis.md', 'enrichment.md'];
  const example = (text) => `For example: “${text}”`;

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
      goal: area('goal'), guidance: area('guidance'),
      profile_name: tracker.watch(M.h('input', { type: 'text', value: f.profile_name || '' })),
      editor_role: area('editor_role'), summary: area('summary'),
      background: toggle('background'), background_text: area('background_text'), web_search: toggle('web_search'),
      impact: toggle('impact'), impact_text: area('impact_text'), community: toggle('community'),
      community_text: area('community_text'), writing_rules: area('writing_rules'),
      analysis_max_chars: tracker.watch(M.h('input', {
        type: 'number', min: 500, max: 100000, step: 500, value: f.analysis_max_chars ?? '',
      })),
    };
    const tiers = TIERS.map((label, i) => tracker.watch(M.h('textarea', { rows: 1 }, (f.tiers || [])[i] || '')));
    const sw = (key, label) => M.h('div', { class: 'field' },
      M.h('label', { class: 'switch', for: `r-${key}` }, Object.assign(inputs[key], { id: `r-${key}` }),
        M.h('span', { class: 'track' }), M.h('span', { class: 'switch-text' }, label)));
    const values = () => {
      const out = {};
      for (const [key, input] of Object.entries(inputs)) {
        if (input.type === 'checkbox') out[key] = input.checked;
        else if (key === 'analysis_max_chars') out[key] = input.value === '' ? null : Number(input.value);
        else out[key] = input.value;
      }
      out.tiers = tiers.map((t) => t.value);
      return out;
    };
    const node = M.h('div', { class: 'stack' },
      M.h('p', { class: 'hint' }, 'Every field is optional and starts empty. Only what you type is written, when you press Save.'),
      M.h('fieldset', {}, M.h('legend', {}, 'How the model scores each story'),
        field(M, 'r-goal', 'Goal of the score', inputs.goal, example('Evaluate how important each item is for readers who follow boating.')),
        field(M, 'r-guidance', 'What makes a story important?', inputs.guidance,
          example('Consider novelty, likely impact for readers, source quality and concrete details. Do not reward exaggerated headlines.')),
        M.h('details', { class: 'fold' }, M.h('summary', {}, 'Scoring grid, and text read for scoring'),
          M.h('div', { class: 'stack' },
            ...tiers.map((t, i) => field(M, `r-tier-${i}`, `Score ${TIERS[i]}`, t, example(TIER_EXAMPLES[i]))),
            field(M, 'r-chars', 'Characters of each article read for scoring', inputs.analysis_max_chars,
              'From 500 to 100,000. Empty: Horizon’s default, 1,000, which can miss what an article says further down.')))),
      M.h('fieldset', {}, M.h('legend', {}, 'What the model writes for each kept story'),
        field(M, 'r-role', 'Role of the writer', inputs.editor_role,
          example('You are an editor helping readers understand important boating news accurately.')),
        field(M, 'r-summary', 'Summary', inputs.summary,
          example('In 2-4 sentences, lead with what changed and for whom. Include names, dates and prices.')),
        sw('background', 'Background paragraph'),
        field(M, 'r-bg', 'Background', inputs.background_text,
          example('In 1-3 sentences, explain the earlier development that makes this news understandable.')),
        sw('web_search', 'Let the model search the web for background'),
        sw('impact', 'Impact paragraph, when the source supports one'),
        field(M, 'r-impact', 'Impact', inputs.impact_text, example('State one concrete consequence for readers.')),
        sw('community', 'Community discussion, when comments say something useful'),
        field(M, 'r-comm', 'Community discussion', inputs.community_text,
          example('In 1-2 sentences, summarize the most useful point from the comments.')),
        field(M, 'r-rules', 'Writing rules', inputs.writing_rules,
          example('Use a short, accurate title of no more than 15 words. Do not invent details.'))),
      M.h('fieldset', {}, M.h('legend', {}, 'Name'),
        field(M, 'r-name', 'Profile name (optional)', inputs.profile_name,
          'Horizon shows it as a heading in the briefing. Empty: the domain’s name.')));
    return { node, values };
  }

  function filesMode(M, state, tracker) {
    const areas = {};
    const node = M.h('div', { class: 'stack' }, ...TEXT_FILES.filter((name) => state.files[name] !== undefined).map((name) => {
      areas[name] = tracker.watch(M.h('textarea', { rows: 8, class: 'mono', spellcheck: 'false' }, state.files[name]));
      const help = name === 'match.md'
        ? 'Horizon reads it only to choose a profile for sources that do not name one. Sources added in MastHead always name this domain’s profile.'
        : null;
      return field(M, `r-file-${name.replace('.', '-')}`, name, areas[name], help);
    }));
    const changed = () => Object.entries(areas).filter(([name, area]) => area.value !== state.files[name]);
    return { node, changed };
  }

  function preview(M, files) {
    const names = Object.keys(files);
    if (!names.length) return null;
    return M.h('details', { class: 'fold' }, M.h('summary', {}, 'Profile files, as Horizon reads them'),
      ...names.map((name) =>
        M.h('div', { class: 'stack' }, M.h('h4', {}, name), M.h('pre', { class: 'file-preview' }, files[name] || '(empty)'))));
  }

  async function postForm(M, Kit, domainId, fields) {
    const url = `/api/domains/${enc(domainId)}/profile-form`;
    try {
      return await M.api.post(url, { fields, replace: false });
    } catch (error) {
      const files = error.status === 409 && error.data && error.data.files;
      if (!files) throw error;
      const replace = await Kit.confirmDialog(M, {
        title: 'Replace files changed by hand?',
        body: M.h('div', { class: 'stack' },
          M.h('p', {}, 'These files were changed outside the form. Saving the form rewrites them and their current text is lost:'),
          M.h('ul', {}, ...files.map((name) => M.h('li', { class: 'mono' }, name)))),
        confirm: 'Replace them', danger: true,
      });
      return replace ? M.api.post(url, { fields, replace: true }) : null;
    }
  }

  function step(M, ctx) {
    const { domainId, rules, tracker } = ctx;
    const Kit = window.MastHeadKit;
    const message = Kit.messageArea(M);
    let state = rules;
    let mode = !state.exists || state.managed ? 'form' : 'files';
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
      const changed = state.changed_by_hand || [];
      if (mode === 'files' && !state.exists) {
        current = null;
        holder.replaceChildren(M.notice('No profile files yet',
          'Save the form once: Horizon needs the profile file before the files can be edited as text.', 'info'));
        return;
      }
      current = mode === 'form' ? formMode(M, state, tracker) : filesMode(M, state, tracker);
      // replaceChildren would print "null" for an absent block, so absent blocks are dropped.
      holder.replaceChildren(...[
        mode === 'form' && changed.length ? M.notice('Some files were changed outside the form',
          `${changed.join(', ')}: saving the form asks before replacing them.`) : null,
        mode === 'files' && state.managed ? M.notice('Editing the files directly',
          'If you save the form later, it asks before replacing the files you changed here.', 'info') : null,
        current.node,
        mode === 'form' ? preview(M, state.files) : null,
      ].filter(Boolean));
    }
    save.addEventListener('click', async () => {
      message.clear();
      if (!current) { message.info('Nothing to save', 'Save the form first.'); return; }
      save.disabled = true;
      try {
        if (mode === 'form') {
          const saved = await postForm(M, Kit, domainId, current.values());
          if (!saved) { save.disabled = false; return; }
          state = saved;
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
