// Sign-in page for server mode. The password is sent once, as JSON, and never stored here.
(function () {
  'use strict';
  const form = document.getElementById('login-form');
  const input = document.getElementById('password');
  const error = document.getElementById('login-error');
  const button = form.querySelector('button');

  function showError(message) {
    error.textContent = message; // text, never HTML
    error.hidden = false;
    input.setAttribute('aria-invalid', 'true');
    input.focus();
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!input.value) { showError('Type the password.'); return; }
    button.disabled = true;
    try {
      const response = await fetch('/api/login', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ password: input.value }),
      });
      if (response.ok) { window.location.replace('/'); return; }
      const body = await response.json().catch(() => ({}));
      if (response.status === 429) {
        const minutes = Math.ceil(Number(response.headers.get('retry-after') || 60) / 60);
        showError(`Too many attempts. Try again in ${minutes} minute${minutes > 1 ? 's' : ''}.`);
      } else {
        showError(body.error || 'Sign-in failed.');
      }
      input.value = '';
    } catch (_) {
      showError('The server cannot be reached.');
    } finally {
      button.disabled = false;
    }
  });
  input.focus();
}());
