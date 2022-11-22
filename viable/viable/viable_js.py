viable_js = str(r'''
    async function call(...args) {
        const resp = await fetch('/call', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({...state(), args: [...args]}),
        })
        const body = await resp.json()
        if (body.query) {
            update_query(body.query)
        }
        if (body.session) {
            update_session(body.session)
        }
        if (body.push_state) {
            history.pushState(null, null)
        }
        await refresh()
    }
    function get_query() {
        return Object.fromEntries(new URL(location.href).searchParams)
    }
    function set_query(kvs) {
        let next = new URL(location.href)
        next.search = new URLSearchParams(kvs)
        history.replaceState(null, null, next.href)
    }
    function update_query(kvs) {
        return set_query({...get_query(), ...kvs})
    }
    function get_session() {
        try {
            return JSON.parse(sessionStorage.getItem('v'))
        } catch (e) {
            return {}
        }
    }
    function set_session(value) {
        sessionStorage.setItem('v', JSON.stringify(value))
    }
    function update_session(value) {
        set_session({...get_session(), ...value})
    }
    function has_session() {
        return Object.keys(get_session()).length > 0
    }
    function state() {
        return {query: get_query(), session: get_session()}
    }

    let current_refresh = null
    async function refresh() {
        if (!current_refresh) {
            current_refresh = refresh_worker()
        }
        try {
            return await current_refresh
        } finally {
            current_refresh = null
        }
    }
    async function refresh_worker() {
        const html = document.querySelector('html')
        html.setAttribute('loading', '1')
        try {
            const resp = await fetch(location.href, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(state()),
            })
            const text = await resp.text()
        } catch (e) {
            return {'ok': false}
        }
        if (text === null) {
            return {'ok': false}
        }
        try {
            const parser = new DOMParser()
            const doc = parser.parseFromString(text, "text/html")
            morph(document.head, doc.head)
            morph(document.body, doc.body)
            for (const script of document.querySelectorAll('script[eval]')) {
                (0, eval)(script.textContent)
            }
        } catch (e) {
            console.warn(e)
        }
        requestAnimationFrame(() => {
            if (!current_refresh) {
                html.setAttribute('loading', '0')
            }
        })
        return {'ok': true}
    }
    async function poll() {
        while (true) {
            try {
                const resp = await fetch('/ping', {method: 'POST'})
                const body = await resp.json()
                continue
            } catch (e) {
                console.warn('poll', e)
                let retries = 0
                while (true) {
                    const res = await refresh()
                    if (res.ok) {
                        break
                    }
                    const timeout_ms = retries < 100 ? 50 : 2000
                    await new Promise(x => setTimeout(x, timeout_ms))
                    retries += 1
                }
            }
        }
    }
    window.onpopstate = () => refresh()

    in_focus = true
    window.onfocus = () => { in_focus = true }
    window.onblur = () => { in_focus = false }
    function morph(prev, next) {
        if (
            prev.nodeType === Node.ELEMENT_NODE &&
            next.nodeType === Node.ELEMENT_NODE &&
            prev.tagName === next.tagName
        ) {
            if (prev.hasAttribute('nodiff')) {
                return
            }
            for (let name of prev.getAttributeNames()) {
                if (!next.hasAttribute(name)) {
                    prev.removeAttribute(name)
                }
            }
            for (let name of next.getAttributeNames()) {
                if (
                    !prev.hasAttribute(name) ||
                    next.getAttribute(name) !== prev.getAttribute(name)
                ) {
                    prev.setAttribute(name, next.getAttribute(name))
                }
            }
            if (prev.tagName === 'INPUT' && (document.activeElement !== prev || !in_focus || window.ignore_focus)) {
                if (prev.type == 'radio' && document.activeElement.name === prev.name) {
                    // pass
                } else {
                    if (next.value !== prev.value) {
                        prev.value = next.value
                    }
                    if (prev.checked !== next.hasAttribute('checked')) {
                        prev.checked = next.hasAttribute('checked')
                    }
                }
            }
            if (prev.tagName === 'TEXTAREA') {
                if (document.activeElement !== prev || !in_focus || window.ignore_focus) {
                    prev.value = next.textContent
                }
            } else {
                const pc = [...prev.childNodes]
                const nc = [...next.childNodes]
                const num_max = Math.max(pc.length, nc.length)
                for (let i = 0; i < num_max; ++i) {
                    if (i >= nc.length) {
                        prev.removeChild(pc[i])
                    } else if (i >= pc.length) {
                        prev.appendChild(nc[i])
                    } else {
                        morph(pc[i], nc[i])
                    }
                }
            }
        } else if (
            prev.nodeType === Node.TEXT_NODE &&
            next.nodeType === Node.TEXT_NODE
        ) {
            if (prev.textContent !== next.textContent) {
                prev.textContent = next.textContent
            }
        } else {
            prev.replaceWith(next)
        }
    }

    function queue_refresh(after_ms=100) {
        clearTimeout(window._qrt)
        window._qrt = setTimeout(
            () => requestAnimationFrame(() => refresh()),
            after_ms
        )
    }

    function replace_pathname(s) {
        // unused for now
        let next = new URL(location.href)
        next.pathname = s
        return next.href
    }
''')
