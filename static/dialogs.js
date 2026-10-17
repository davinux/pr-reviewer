/* Promise-based replacements for window.alert() and window.confirm().
 *
 * They use the Bootstrap modals defined in templates/_dialogs.html so dialogs
 * match the app's theme. If Bootstrap (or the markup) is missing, they fall
 * back to the native dialogs so nothing breaks.
 *
 *   await appAlert({ title, message })          // message: string | string[]
 *   if (await appConfirm({ message, okText })) { ... }
 *
 * A bare string is accepted as shorthand for { message }.
 */
(function () {
    'use strict';

    function bootstrapReady() {
        return typeof window.bootstrap !== 'undefined' && !!window.bootstrap.Modal;
    }

    function asOptions(value) {
        if (typeof value === 'string') return { message: value };
        return value || {};
    }

    // Render text safely (no HTML) as paragraphs or a bulleted list.
    function fillBody(container, content) {
        container.textContent = '';
        if (content == null || content === '') return;
        const lines = Array.isArray(content) ? content : [content];
        if (lines.length === 1) {
            const p = document.createElement('p');
            p.className = 'mb-0';
            p.textContent = lines[0];
            container.appendChild(p);
            return;
        }
        const list = document.createElement('ul');
        list.className = 'mb-0';
        lines.forEach((line) => {
            const li = document.createElement('li');
            li.textContent = line;
            list.appendChild(li);
        });
        container.appendChild(list);
    }

    window.appAlert = function (value) {
        const options = asOptions(value);
        const el = document.getElementById('appAlertModal');
        if (!el || !bootstrapReady()) {
            window.alert(Array.isArray(options.message) ? options.message.join('\n') : options.message);
            return Promise.resolve();
        }
        el.querySelector('[data-dialog-title]').textContent = options.title || 'Notice';
        fillBody(el.querySelector('[data-dialog-body]'), options.message);
        const ok = el.querySelector('[data-dialog-ok]');
        const close = el.querySelector('.btn-close');
        ok.textContent = options.okText || 'OK';
        const modal = bootstrap.Modal.getOrCreateInstance(el);

        return new Promise(function (resolve) {
            let settled = false;
            function done() {
                if (settled) return;
                settled = true;
                ok.removeEventListener('click', done);
                if (close) close.removeEventListener('click', done);
                el.removeEventListener('hidden.bs.modal', done);
                modal.hide();
                resolve();
            }
            ok.addEventListener('click', done);
            if (close) close.addEventListener('click', done);
            // Fallback for Escape / backdrop clicks.
            el.addEventListener('hidden.bs.modal', done);
            modal.show();
        });
    };

    window.appConfirm = function (value) {
        const options = asOptions(value);
        const el = document.getElementById('appConfirmModal');
        if (!el || !bootstrapReady()) {
            const message = Array.isArray(options.message)
                ? options.message.join('\n') : (options.message || '');
            return Promise.resolve(window.confirm(message));
        }
        el.querySelector('[data-dialog-title]').textContent = options.title || 'Please confirm';
        fillBody(el.querySelector('[data-dialog-body]'), options.message);
        const ok = el.querySelector('[data-dialog-ok]');
        const cancel = el.querySelector('[data-dialog-cancel]');
        const close = el.querySelector('.btn-close');
        ok.textContent = options.okText || 'Confirm';
        ok.className = 'btn ' + (options.okClass || 'btn-danger');
        cancel.textContent = options.cancelText || 'Cancel';
        const modal = bootstrap.Modal.getOrCreateInstance(el);

        return new Promise(function (resolve) {
            let settled = false;
            function done(result) {
                if (settled) return;
                settled = true;
                ok.removeEventListener('click', onOk);
                cancel.removeEventListener('click', onCancel);
                if (close) close.removeEventListener('click', onCancel);
                el.removeEventListener('hidden.bs.modal', onDismiss);
                modal.hide();
                resolve(result);
            }
            function onOk() { done(true); }
            function onCancel() { done(false); }
            // Fallback for Escape / backdrop clicks (and the header close button
            // that uses data-bs-dismiss).
            function onDismiss() { done(false); }
            ok.addEventListener('click', onOk);
            cancel.addEventListener('click', onCancel);
            if (close) close.addEventListener('click', onCancel);
            el.addEventListener('hidden.bs.modal', onDismiss);
            modal.show();
        });
    };
})();
