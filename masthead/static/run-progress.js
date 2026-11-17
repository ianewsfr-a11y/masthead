// The scoring as it goes: how many stories Horizon has scored, the measured pace, and each
// story's profile, score and reason as soon as Horizon has them. Used by the Runs page and
// by the trial run of the domain editor. Text from feeds and the model is inserted as text.
(() => {
  'use strict';

  function roughDuration(seconds) {
    if (seconds < 90) return `${Math.max(1, Math.round(seconds))} s`;
    const minutes = Math.round(seconds / 60);
    if (minutes < 90) return `${minutes} min`;
    return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
  }

  function row(M, item) {
    const verdict = item.failed
      ? M.pill('Failed', 'warn', 'alert')
      : M.h('span', { class: 'pill idle mono' }, `Score ${item.score}`);
    const title = item.url
      ? M.h('a', { class: 'strong', href: item.url, target: '_blank', rel: 'noopener noreferrer' }, item.title)
      : M.h('span', { class: 'strong' }, item.title);
    return M.h('li', {},
      M.h('div', { class: 'scored-head' }, verdict, title),
      M.h('span', { class: 'hint' }, [item.source, item.profile].filter(Boolean).join(' · ')),
      item.reason ? M.h('span', { class: 'scored-reason' }, item.failed ? `Horizon: ${item.reason}` : item.reason) : null);
  }

  function scoring(M) {
    const count = M.h('p', { class: 'progress-count', role: 'status' });
    const bar = M.h('progress', { max: '1', value: '0', 'aria-label': 'Stories scored' });
    const pace = M.h('p', { class: 'hint mono' });
    const list = M.h('ol', { class: 'scored-list', 'aria-label': 'Stories scored so far, newest first' });
    const el = M.h('section', { class: 'scoring', hidden: true },
      M.h('h3', {}, 'Scoring'), count, bar, pace,
      M.h('p', { class: 'hint' }, 'Each story with the score the model gave it. The selection (minimum score, duplicates, limits) comes after scoring.'),
      list);
    let shown = 0;

    function update(job) {
      const stage = job && (job.stages || []).find((s) => s.id === 'score');
      const p = stage && stage.progress;
      if (!p || !p.total) { el.hidden = true; return; }
      el.hidden = false;
      bar.max = p.total;
      bar.value = p.done;
      const text = `${p.done} of ${p.total} stories scored${p.failed ? `, ${p.failed} failed` : ''}`;
      if (count.textContent !== text) count.textContent = text;
      if (p.done) {
        const each = p.seconds / p.done;
        const left = p.total - p.done;
        pace.textContent = `Measured: about ${roughDuration(each)} per story.`
          + (left && stage.status === 'running' ? ` Estimated time left: about ${roughDuration(each * left)}.` : '');
      } else {
        pace.textContent = 'Waiting for the first story to be scored.';
      }
      for (const item of p.items.slice(shown)) list.prepend(row(M, item));
      shown = p.items.length;
    }

    return { el, update };
  }

  window.MastHeadProgress = { scoring };
})();
