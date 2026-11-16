/* MastHead for Horizon: small shared pieces of interface.
   Built from Modern Web Guidance (dialog, forms): a native <dialog> for confirmations,
   and an "unsaved changes" tracker for forms that are saved with one button per step. */
(() => {
  'use strict';
  let dialogCount = 0;

  /* A modal confirmation. Resolves true only when the confirm button is pressed.
     Cancel has focus first; Esc closes it as a cancel. */
  function confirmDialog(M, { title, body, confirm, cancel = 'Cancel', danger = false }) {
    dialogCount += 1;
    const titleId = `confirm-title-${dialogCount}`;
    return new Promise((resolve) => {
      const cancelButton = M.h('button', { type: 'button', class: 'btn', autofocus: true }, cancel);
      const confirmButton = M.h('button', { type: 'button', class: danger ? 'btn danger' : 'btn primary' }, confirm);
      const dialog = M.h('dialog', { class: 'confirm', 'aria-labelledby': titleId },
        M.h('h2', { id: titleId }, title),
        typeof body === 'string' ? M.h('p', {}, body) : body,
        M.h('div', { class: 'row-actions' }, cancelButton, confirmButton));
      let answer = false;
      cancelButton.addEventListener('click', () => dialog.close());
      confirmButton.addEventListener('click', () => { answer = true; dialog.close(); });
      dialog.addEventListener('close', () => { dialog.remove(); resolve(answer); });
      document.body.append(dialog);
      dialog.showModal();
    });
  }

  /* Tracks whether a form has changes that are not saved yet, and shows it in words,
     not only in colour. Call mark() on input, clean() after a successful save. */
  function unsavedTracker(M, onChange) {
    let dirty = false;
    const indicator = M.h('span', { class: 'unsaved', role: 'status' });
    function draw() {
      indicator.replaceChildren(...(dirty
        ? [M.icon('alert', 14), M.h('span', {}, 'Unsaved changes')]
        : []));
      indicator.classList.toggle('on', dirty);
    }
    draw();
    return {
      indicator,
      get dirty() { return dirty; },
      mark() { if (!dirty) { dirty = true; draw(); onChange(); } },
      clean(savedText) {
        dirty = false;
        draw();
        if (savedText) indicator.replaceChildren(M.icon('check', 14), M.h('span', {}, savedText));
        onChange();
      },
      watch(element) {
        element.addEventListener('input', () => this.mark());
        element.addEventListener('change', () => this.mark());
        return element;
      },
    };
  }

  /* A message area that stays until replaced, announced politely. Errors stay next to the action. */
  function messageArea(M) {
    const area = M.h('div', { class: 'step-message', 'aria-live': 'polite' });
    return {
      area,
      error(title, text) { area.replaceChildren(M.notice(title, text)); },
      info(title, text) { area.replaceChildren(M.notice(title, text, 'info')); },
      clear() { area.replaceChildren(); },
    };
  }

  window.MastHeadKit = { confirmDialog, unsavedTracker, messageArea };
})();
