/* MastHead for Horizon: choosing a domain's AI, and the AI keys entered in the interface.
   A key typed here goes to MastHead on this computer and is never shown again: the
   screens only say whether a key is present and where it comes from. */
(() => {
  'use strict';
  const enc = encodeURIComponent;
  const SOURCE_TEXT = {
    environment: 'From the environment MastHead was started with (for example a Windows variable). It is used before any key entered here.',
    domain: 'From this domain’s own .env file. It is used before the shared key.',
    shared: 'Saved in MastHead, shared by every domain that uses this provider.',
  };

  function keyStatus(M, present, source) {
    return M.h('div', { class: 'key-status' },
      present ? M.pill('Key found', 'ok', 'check') : M.pill('No key', 'warn', 'alert'),
      source ? M.h('span', { class: 'hint' }, SOURCE_TEXT[source]) : null);
  }

  // A form to save (or delete) the shared key of one provider, and its extra settings (Azure endpoint).
  function keyForm(M, provider, onSaved, prefix = 'key') {
    const id = `${prefix}-${provider.id}`;
    const input = M.h('input', { type: 'password', id, autocomplete: 'off', spellcheck: 'false' });
    async function send(path, body, message) {
      try {
        const status = await M.api.post(path, body);
        M.toast(message);
        onSaved(status);
      } catch (error) { M.toast(error.message, true); }
    }
    const save = M.h('button', {
      type: 'submit', class: 'btn primary',
    }, provider.key_source === 'shared' ? 'Replace the key' : 'Save the key');
    const form = M.h('form', {
      class: 'stack', onsubmit: (event) => {
        event.preventDefault();
        const value = input.value;
        input.value = '';  // the key does not stay on screen
        if (!value.trim()) { M.toast('Paste the key first.', true); return; }
        send('/api/ai/keys', { name: provider.key_env, value }, `${provider.label} key saved. It is not shown again.`);
      },
    },
      M.h('div', { class: 'field' },
        M.h('label', { for: id }, `${provider.label} key (${provider.key_env})`), input,
        M.h('span', { class: 'help' }, 'Paste it here. MastHead keeps it on this computer and never shows it again.')),
      M.h('div', { class: 'row-actions' }, save,
        provider.key_source === 'shared' ? M.h('button', {
          type: 'button', class: 'btn', onclick: () => {
            if (!window.confirm(`Delete the saved ${provider.label} key? Domains using this provider will have no key unless they have their own.`)) return;
            send('/api/ai/keys/delete', { name: provider.key_env }, `${provider.label} key deleted.`);
          },
        }, 'Delete the saved key') : null));
    const extras = provider.extra_env.map((name) => {
      const extra = M.h('input', { type: 'text', id: `${id}-${name}`, autocomplete: 'off' });
      return M.h('form', {
        class: 'stack', onsubmit: (event) => {
          event.preventDefault();
          const value = extra.value;
          extra.value = '';
          send('/api/ai/keys', { name, value }, `${name} saved.`);
        },
      },
        M.h('div', { class: 'field' }, M.h('label', { for: `${id}-${name}` }, `Endpoint (${name})`), extra,
          M.h('span', { class: 'help' }, provider.extra_present[name] ? 'Set. Type a new value to replace it.' : 'Not set yet.')),
        M.h('div', {}, M.h('button', { type: 'submit', class: 'btn' }, 'Save the endpoint')));
    });
    return M.h('div', { class: 'stack' }, form, ...extras);
  }

  // Domains screen: every provider that needs a key, with its state.
  function keysPanel(M, status, refresh) {
    const rows = status.providers.filter((p) => p.needs_key).map((provider) =>
      M.h('details', { class: 'key-row' },
        M.h('summary', {},
          M.h('span', { class: 'strong' }, provider.label),
          provider.key_present ? M.pill(provider.key_source === 'environment' ? 'From environment' : 'Saved', 'ok', 'check')
            : M.pill('No key', 'idle', 'dash')),
        provider.key_source ? M.h('p', { class: 'hint' }, SOURCE_TEXT[provider.key_source]) : null,
        keyForm(M, provider, () => refresh(), 'keys')));
    return M.panel('AI keys',
      M.h('p', { class: 'hint' }, `One key per provider, shared by every domain that uses it. Saved in ${status.keys_file} on this computer and never shown again. A domain's own .env file overrides it; a variable in the environment MastHead was started with overrides both.`),
      M.h('div', { class: 'stack' }, ...rows),
      M.h('p', { class: 'hint' }, 'Ollama runs a model on your own computer and needs no key.'));
  }

  // Provider and model fields, shared by the AI panel and the New domain screen.
  function modelFields(M, providers, current, prefix) {
    const listed = providers.some((p) => p.id === current.provider);
    const select = M.h('select', { id: `${prefix}-provider` },
      ...(listed ? [] : [M.h('option', { value: current.provider, disabled: true, selected: true }, `${current.provider} (set outside MastHead)`)]),
      ...providers.map((p) => M.h('option', { value: p.id, selected: p.id === current.provider }, p.label)));
    const model = M.h('input', { type: 'text', id: `${prefix}-model`, autocomplete: 'off', class: 'mono', value: current.model || '' });
    const example = M.h('span', { class: 'help' });
    const address = M.h('input', { type: 'text', id: `${prefix}-address`, autocomplete: 'off', class: 'mono', value: current.base_url || '' });
    const addressHelp = M.h('span', { class: 'help' });
    const version = M.h('input', { type: 'text', id: `${prefix}-version`, autocomplete: 'off', class: 'mono', value: current.api_version || '' });
    const versionField = M.h('div', { class: 'field' }, M.h('label', { for: `${prefix}-version` }, 'API version'), version);
    const chosen = () => providers.find((p) => p.id === select.value);
    function update(initial) {
      const p = chosen();
      if (!p) return;
      example.textContent = `For example ${p.example_model} (Horizon's example). Write the name exactly as your provider does.`;
      if (!initial) {
        model.value = '';
        address.value = p.id === 'ollama' ? p.base_url : '';
        version.value = p.api_version || '';
      }
      addressHelp.textContent = p.id === 'ollama' ? 'Where your Ollama answers.'
        : `Optional. Leave empty to use Horizon's address for ${p.label}.`;
      versionField.hidden = p.id !== 'azure';
    }
    select.addEventListener('change', () => update(false));
    update(true);
    const nodes = [
      M.h('div', { class: 'field' }, M.h('label', { for: `${prefix}-provider` }, 'AI provider'), select),
      M.h('div', { class: 'field' }, M.h('label', { for: `${prefix}-model` }, 'Model'), model, example),
      M.h('div', { class: 'field' }, M.h('label', { for: `${prefix}-address` }, 'Address'), address, addressHelp),
      versionField,
    ];
    const values = () => ({ provider: select.value, model: model.value.trim(), base_url: address.value.trim(), api_version: version.value.trim() });
    return { nodes, values, chosen };
  }

  // Sources and settings: the domain's AI, editable, and its key.
  function modelPanel(M, overview, status, onSaved) {
    const ai = overview.settings.ai;
    if (!status) return M.panel('AI', M.h('p', { class: 'hint' }, 'Loading…'));
    const fields = modelFields(M, status.providers, ai, 'ai');
    const save = M.h('button', { type: 'submit', class: 'btn primary' }, 'Save the AI choice');
    const form = M.h('form', {
      class: 'stack', onsubmit: async (event) => {
        event.preventDefault();
        save.disabled = true;
        try {
          const fresh = await M.api.post(`/api/domains/${enc(overview.id)}/model`, fields.values());
          M.toast('AI choice saved. It applies from the next run.');
          onSaved(fresh, null);
        } catch (error) { save.disabled = false; M.toast(error.message, true); }
      },
    }, ...fields.nodes, M.h('div', {}, save));
    const provider = status.providers.find((p) => p.id === ai.provider);
    const needsKey = provider ? provider.needs_key : Boolean(ai.api_key_env);
    return M.panel('AI',
      form,
      M.h('ul', { class: 'facts' },
        M.fact('Languages', ai.languages.join(', ')),
        M.fact('Temperature', String(ai.temperature))),
      needsKey ? M.h('h3', {}, 'Key') : null,
      needsKey ? keyStatus(M, ai.api_key_present, ai.key_source) : M.h('p', { class: 'hint' }, 'This provider needs no key.'),
      needsKey && provider ? keyForm(M, provider, (fresh) => onSaved(null, fresh), 'ai-key') : null);
  }

  window.MastHeadAI = { keysPanel, modelPanel, modelFields, keyForm, keyStatus };
})();
