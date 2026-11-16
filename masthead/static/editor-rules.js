/* MastHead for Horizon: the Editorial rules step of the domain editor.
   A domain starts with Horizon's built-in profiles, as Horizon's own setup leaves it. They are
   shown as they are. "Customize the profiles" copies them into the domain's folder; they are
   then edited as text, each file checked by Horizon's loader before it is kept. MastHead
   writes no rule of its own. One Save button for the step. */
(() => {
  'use strict';
  const enc = encodeURIComponent;
  const FILES = ['match.md', 'analysis.md', 'enrichment.md'];
  const FILE_HELP = {
    'match.md': 'Which stories belong to this profile. Horizon’s model reads it to choose a profile for each story.',
    'analysis.md': 'How the model scores a story from 0 to 10.',
    'enrichment.md': 'What the model writes for each kept story.',
  };

  function readOnly(M, profile) {
    return M.h('details', { class: 'fold' },
      M.h('summary', {}, `${profile.name}${profile.default ? ' (default profile)' : ''}`),
      ...FILES.filter((name) => profile.files[name] !== undefined).map((name) =>
        M.h('div', { class: 'stack' }, M.h('h4', {}, name), M.h('pre', { class: 'file-preview' }, profile.files[name] || '(empty)'))));
  }

  function editable(M, profile, tracker, areas) {
    return M.h('details', { class: 'fold', open: profile.default },
      M.h('summary', {}, `${profile.name}${profile.default ? ' (default profile)' : ''}`),
      ...FILES.filter((name) => profile.files[name] !== undefined).map((name) => {
        const id = `r-${profile.folder}-${name.replace('.', '-')}`;
        const area = tracker.watch(M.h('textarea', { id, rows: 8, class: 'mono', spellcheck: 'false', 'aria-describedby': `${id}-help` }, profile.files[name]));
        areas.push({ profile: profile.folder, name, area, before: profile.files[name] });
        return M.h('div', { class: 'field' }, M.h('label', { for: id }, name), area,
          M.h('span', { class: 'help', id: `${id}-help` }, FILE_HELP[name]));
      }));
  }

  function step(M, ctx) {
    const { domainId, tracker } = ctx;
    const Kit = window.MastHeadKit;
    const message = Kit.messageArea(M);
    const holder = M.h('div', { class: 'stack' });
    const save = M.h('button', { type: 'button', class: 'btn primary' }, 'Save the rules');
    const customize = M.h('button', { type: 'button', class: 'btn' }, 'Customize the profiles');
    let state = ctx.rules;
    let areas = [];

    function draw() {
      areas = [];
      const names = state.profiles.map((p) => p.name).join(', ');
      if (state.builtin) {
        holder.replaceChildren(
          M.notice('Horizon’s built-in profiles', `This domain uses the profiles Horizon ships with (${names}), as Horizon’s own setup leaves it. `
            + 'For each story, Horizon’s model chooses the profile that fits, which is one model call per story. To change the rules, customize the profiles: they are copied into this domain and you edit them as text.', 'info'),
          ...state.profiles.map((profile) => readOnly(M, profile)),
          M.h('div', {}, customize));
        save.hidden = true;
      } else {
        holder.replaceChildren(
          M.h('p', { class: 'hint' }, `This domain’s own profiles, in ${state.folder}. Each file is checked by Horizon before it is kept.`),
          ...state.profiles.map((profile) => editable(M, profile, tracker, areas)));
        save.hidden = false;
      }
    }

    customize.addEventListener('click', async () => {
      message.clear();
      const ok = await Kit.confirmDialog(M, {
        title: 'Customize the profiles?',
        body: 'Horizon’s built-in profiles are copied into this domain’s folder. From then on, this domain reads its own copies, which you can edit. Nothing else changes.',
        confirm: 'Copy them',
      });
      if (!ok) return;
      customize.disabled = true;
      try {
        state = await M.api.post(`/api/domains/${enc(domainId)}/profiles/customize`, {});
        draw();
        ctx.onSaved(state);
        message.info('Copied', 'The profiles are now this domain’s own. Edit them below.');
      } catch (error) { message.error('Not copied', error.message); }
      customize.disabled = false;
    });

    save.addEventListener('click', async () => {
      message.clear();
      const changed = areas.filter((a) => a.area.value !== a.before);
      if (!changed.length) { message.info('Nothing to save', 'No file was changed.'); return; }
      save.disabled = true;
      try {
        for (const a of changed) {
          state = await M.api.post(`/api/domains/${enc(domainId)}/profile-file`, { profile: a.profile, file: a.name, text: a.area.value });
          a.before = a.area.value;
        }
        tracker.clean('Saved');
        ctx.onSaved(state);
      } catch (error) { message.error('Not saved', error.message); }
      save.disabled = false;
    });

    draw();
    return { body: [holder, M.h('div', { class: 'row-actions' }, save, tracker.indicator), message.area] };
  }

  window.MastHeadEditorRules = { step };
})();
