const accountPanel = document.getElementById('accountPanel');
const panelContent = document.getElementById('panelContent');
const panelError = document.getElementById('panelError');
const chatMessages = [{ text: 'What service do you need, and where in Karachi? You can also include your preferred time.' }];
const requestStatuses = {
    confirmed: 'Confirmed',
    provider_notified: 'Provider notified',
    en_route: 'En route',
    completed: 'Completed'
};

let signedInAccount;
let panelVersion = 0;

async function accountApi(path, payload) {
    const options = payload === undefined ? {} : {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    };
    const response = await fetch(path, options);
    const data = await response.json();
    if (!response.ok) {
        const error = new Error(typeof data.detail === 'string' ? data.detail : 'Check the details and try again.');
        error.status = response.status;
        throw error;
    }
    return data;
}

function setAccount(account) {
    signedInAccount = account;
    document.getElementById('profileBtn').textContent = account ? 'Profile' : 'Log in';
}

function openPanel(title) {
    panelVersion += 1;
    document.getElementById('panelTitle').textContent = title;
    panelContent.replaceChildren();
    panelContent.classList.remove('request-list');
    panelError.textContent = '';
    if (!accountPanel.open) accountPanel.showModal();
    return panelVersion;
}

function showAccount(mode = 'login', onSuccess) {
    if (signedInAccount) {
        openPanel('Profile');
        panelContent.innerHTML = '<h3></h3><p class="subtle"></p><br><button type="button">Log out</button>';
        panelContent.querySelector('h3').textContent = signedInAccount.name;
        panelContent.querySelector('p').textContent = signedInAccount.email;
        panelContent.querySelector('button').onclick = async () => {
            try {
                await accountApi('/logout', {});
                setAccount(null);
                accountPanel.close();
            } catch (error) {
                panelError.textContent = error.message;
            }
        };
        return;
    }
    const signup = mode === 'signup';
    const view = openPanel(signup ? 'Create account' : 'Log in');
    panelContent.innerHTML = `
        <form>
            ${signup ? '<label>Name<input name="name" autocomplete="name" required maxlength="90"></label>' : ''}
            <label>Email<input name="email" type="email" autocomplete="email" required maxlength="254"></label>
            <label>Password<input name="password" type="password" autocomplete="${signup ? 'new-password' : 'current-password'}" required minlength="8" maxlength="128"></label>
            <button class="primary" type="submit">${signup ? 'Create account' : 'Log in'}</button>
            <button type="button" id="switchAccount">${signup ? 'Log in to an existing account' : 'Create an account'}</button>
        </form>`;
    document.getElementById('switchAccount').onclick = () => showAccount(signup ? 'login' : 'signup', onSuccess);
    panelContent.querySelector('form').onsubmit = async event => {
        event.preventDefault();
        const form = event.currentTarget;
        const submit = form.querySelector('[type=submit]');
        submit.disabled = true;
        panelError.textContent = '';
        try {
            setAccount(await accountApi('/account/' + mode, Object.fromEntries(new FormData(form))));
            if (view === panelVersion && accountPanel.open) {
                accountPanel.close();
                onSuccess?.();
            }
        } catch (error) {
            if (view === panelVersion) panelError.textContent = error.message;
        } finally {
            submit.disabled = false;
        }
    };
}

async function showRequests() {
    if (!signedInAccount) {
        showAccount('login', showRequests);
        return;
    }
    const view = openPanel('My requests');
    panelContent.textContent = 'Loading requests…';
    try {
        const requests = await accountApi('/requests');
        if (view !== panelVersion) return;
        panelContent.replaceChildren();
        if (!requests.length) {
            panelContent.textContent = 'Your booked services will appear here.';
            return;
        }
        panelContent.classList.add('request-list');
        for (const request of requests) {
            const card = document.createElement('article');
            card.className = 'request-item';
            card.innerHTML = '<h3></h3><p></p><small></small><span class="status-chip"></span>';
            card.querySelector('h3').textContent = request.service_type;
            card.querySelector('p').textContent = `${request.provider_name} · ${request.provider_area} · ${request.slot}`;
            card.querySelector('small').textContent = request.booking_id;
            card.querySelector('span').textContent = requestStatuses[request.status] || request.status;
            panelContent.append(card);
        }
    } catch (error) {
        if (view !== panelVersion) return;
        panelContent.replaceChildren();
        if (error.status === 401) {
            setAccount(null);
            showAccount('login', showRequests);
        } else {
            panelError.textContent = error.message;
        }
    }
}

function renderChat() {
    const log = document.getElementById('chatMessages');
    log.replaceChildren();
    for (const message of chatMessages) {
        const bubble = document.createElement('div');
        bubble.className = message.user ? 'chat-bubble user-message' : 'chat-bubble';
        const line = document.createElement('p');
        line.textContent = (message.user ? 'You: ' : 'Assistant: ') + message.text;
        bubble.append(line);
        if (message.query) {
            const link = document.createElement('a');
            link.href = '/?' + new URLSearchParams({ q: message.query });
            link.textContent = 'View providers and map';
            bubble.append(link);
        }
        log.append(bubble);
    }
    log.scrollTop = log.scrollHeight;
}

if (location.pathname === '/messages') {
    renderChat();
    const form = document.getElementById('chatForm');
    const input = document.getElementById('chatInput');
    const status = document.getElementById('chatStatus');
    form.onsubmit = async event => {
        event.preventDefault();
        const message = input.value.trim();
        const button = form.querySelector('button');
        if (!message || button.disabled) return;
        button.disabled = true;
        input.value = '';
        chatMessages.push({ text: message, user: true });
        renderChat();
        status.textContent = 'Assistant is replying…';
        try {
            const result = await accountApi('/chat', {
                messages: chatMessages.slice(1).slice(-9).map(item => ({
                    role: item.user ? 'user' : 'model',
                    text: item.text
                }))
            });
            chatMessages.push({ text: result.reply, query: result.query });
            document.getElementById('chatMode').textContent = result.mode === 'ai' ? 'AI assistant' : 'Guided service search';
        } catch (error) {
            status.textContent = error.message;
            input.value = message;
            chatMessages.pop();
            renderChat();
            return;
        } finally {
            button.disabled = false;
            input.focus();
        }
        status.textContent = '';
        renderChat();
    };
}

document.getElementById('profileBtn').onclick = () => showAccount();
document.getElementById('requestsBtn').onclick = showRequests;
document.getElementById('closePanel').onclick = () => accountPanel.close();
accountApi('/account').then(setAccount).catch(() => {});
