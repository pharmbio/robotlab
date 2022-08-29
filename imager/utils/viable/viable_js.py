viable_js = str(r'''
    last_gen = 0
    async function execute(body) {
        if (body && typeof body === 'object') {
            if (body.log) {
                console.log(body.log)
            }
            if (body.eval) {
                (0, eval)(body.eval)
            }
            if (body.set_query) {
                set_query(body.set_query)
            }
            if (body.update_query) {
                update_query(body.update_query)
            }
            if (body.replace) {
                history.replaceState(null, null, with_pathname(body.replace))
            }
            if (body.goto) {
                history.pushState(null, null, with_pathname(body.goto))
            }
            if (body.refresh) {
                await refresh()
            } else if (body.gen && body.gen != last_gen) {
                last_gen = body.gen
                await refresh()
            }
        }
    }
    async function call(py_name_and_args, js_args) {
        const resp = await fetch('/call', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify([py_name_and_args, js_args]),
        })
        const body = await resp.json()
        await execute(body)
        return resp
    }
    function get_query() {
        return Object.fromEntries(new URL(location.href).searchParams)
    }
    function update_query(kvs, reload=true) {
        return set_query({...get_query(), ...kvs}, reload)
    }
    function set_query_immediately(kvs, reload=true) {
        let next = new URL(location.href)
        next.search = new URLSearchParams(kvs)
        history.replaceState(null, null, next.href)
        if (reload) {
            refresh()
        }
    }
    function with_pathname(s) {
        let next = new URL(location.href)
        next.pathname = s
        return next.href
    }
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
            if (prev.tagName === 'INPUT' && (document.activeElement !== prev || !in_focus)) {
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
    let current
    let rejected = false
    async function refresh() {
        if (current) {
            rejected = true
            return current
        }
        let resolve, reject
        current = new Promise((a, b) => {
            resolve = a;
            reject = b
        })
        rejected = false
        const html = document.querySelector('html')
        html.setAttribute('loading', '1')
        do {
            rejected = false
            let text = null
            let retries = 0
            while (text === null) {
                try {
                    const resp = await fetch(location.href)
                    text = await resp.text()
                } catch (e) {
                    retries++
                    await new Promise(x => setTimeout(x, retries < 100 ? 50 : 1000))
                    if (retries > 500) {
                        console.warn('timeout', e)
                        reject('timeout')
                        throw new Error('timeout')
                    }
                }
            }
            try {
                const parser = new DOMParser()
                const doc = parser.parseFromString(text, "text/html")
                morph(document.head, doc.head)
                morph(document.body, doc.body)
                for (const script of document.querySelectorAll('script[eval]')) {
                    (0, eval)(script.textContent)
                }
            } catch(e) {
                console.warn(e)
            }
        } while (rejected);
        requestAnimationFrame(() => {
            if (!current) {
                html.setAttribute('loading', '0')
            }
        })
        current = undefined
        resolve()
    }
    async function poll() {
        while (true) {
            try {
                const resp = await fetch('/ping', {method: 'POST'})
                body = await resp.json()
                await execute(body)
            } catch (e) {
                console.warn('poll', e)
                await refresh(600)
            }
        }
    }
    window.onpopstate = () => refresh()
    function input_values() {
        const inputs = document.querySelectorAll('input:not([type=radio]),input[type=radio]:checked,select')
        const vals = {}
        for (let i of inputs) {
            if (i.getAttribute('truth') == 'server') {
                continue
            }
            if (!i.name) {
                console.error(i, 'has no name attribute')
                continue
            }
            if (i.type == 'radio') {
                console.assert(i.checked)
                vals[i.name] = i.value
            } else if (i.type == 'checkbox') {
                vals[i.name] = i.checked
            } else {
                vals[i.name] = i.value
            }
        }
        return vals
    }
    function throttle(f, ms=150) {
        let last
        let timer
        return (...args) => {
            if (!timer) {
                f(...args)
                timer = setTimeout(() => {
                    let _last = last
                    timer = undefined
                    last = undefined
                    if (_last) {
                        f(..._last)
                    }
                }, ms)
            } else {
                last = [...args]
            }
        }
    }
    set_query = throttle(set_query_immediately)
    function debounce(f, ms=200, leading=true, trailing=true) {
        let timer;
        let called;
        return (...args) => {
            if (!timer && leading) {
                f.apply(this, args)
                called = true
            } else {
                called = false
            }
            clearTimeout(timer)
            timer = setTimeout(() => {
                let _called = called;
                timer = undefined;
                called = false;
                if (!_called && trailing) {
                    f.apply(this, args)
                }
            }, ms)
        }
    }
''')
