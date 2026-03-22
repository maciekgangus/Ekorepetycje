/**
 * FullCalendar initialization for the Ekorepetycje admin panel.
 */
document.addEventListener('DOMContentLoaded', function () {
    const calendarEl = document.getElementById('calendar');
    if (!calendarEl) return;

    const calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'timeGridWeek',
        locale: 'pl',
        headerToolbar: {
            left: 'prev,next today',
            center: 'title',
            right: 'newSeries dayGridMonth,timeGridWeek,timeGridDay',
        },
        customButtons: {
            newSeries: {
                text: '+ Nowa seria',
                click: function () { openSeriesPanel(); },
            },
        },
        height: 'auto',
        slotMinTime: '07:00:00',
        slotMaxTime: '22:00:00',
        allDaySlot: false,
        nowIndicator: true,
        editable: true,
        selectable: true,
        selectMinDistance: 10,      // require slight drag before triggering select
        unselectAuto: true,
        eventColor: '#22c55e',
        eventTextColor: '#030712',

        events: {
            url: '/api/events',
            method: 'GET',
            failure: function () { console.error('Failed to load events'); },
        },

        eventDataTransform: function (rawEvent) {
            return {
                id: rawEvent.id,
                title: rawEvent.title,
                start: rawEvent.start_time,
                end: rawEvent.end_time,
                extendedProps: {
                    status: rawEvent.status,
                    offering_id: rawEvent.offering_id,
                    teacher_id: rawEvent.teacher_id,
                    student_id: rawEvent.student_id,
                    series_id: rawEvent.series_id,
                },
                color: rawEvent.status === 'completed' ? '#4b5563' :
                       rawEvent.status === 'cancelled' ? '#ef4444' : '#22c55e',
            };
        },

        // ── Drag-to-create: drag on empty slot → pre-fill series panel ────────
        select: function (info) {
            const durationMin = Math.round((info.end - info.start) / 60000);
            const dateStr = info.startStr.split('T')[0];
            openSeriesPanelWithTime(dateStr, info.start.getHours(), info.start.getMinutes(), durationMin);
            calendar.unselect();
        },

        // ── Single click on empty slot → pre-fill series panel ────────────────
        dateClick: function (info) {
            openSeriesPanelWithTime(
                info.dateStr.split('T')[0],
                info.date.getHours(),
                info.date.getMinutes(),
                60
            );
        },

        // ── Left-click on event → context menu ───────────────────────────────
        eventClick: function (info) {
            info.jsEvent.preventDefault();
            _showContextMenu(info.event, info.jsEvent);
        },

        // ── Drag/resize existing event ────────────────────────────────────────
        eventDrop: async function (info) {
            if (info.event.extendedProps.series_id) {
                if (!confirm('Ta lekcja należy do serii. Czy przenieść tylko tę lekcję (odłączy ją od serii)?')) {
                    info.revert();
                    return;
                }
            }
            const ok = await _patchEvent(info.event);
            if (!ok) info.revert();
        },

        eventResize: async function (info) {
            if (info.event.extendedProps.series_id) {
                if (!confirm('Ta lekcja należy do serii. Czy zmienić czas tylko tej lekcji (odłączy ją od serii)?')) {
                    info.revert();
                    return;
                }
            }
            const ok = await _patchEvent(info.event);
            if (!ok) info.revert();
        },

        // ── Hover tooltip ─────────────────────────────────────────────────────
        eventMouseEnter: function (info) {
            _showTooltip(info.event, info.jsEvent);
        },
        eventMouseLeave: function () {
            _hideTooltip();
        },

        // ── Week stats ────────────────────────────────────────────────────────
        eventsSet: function (events) {
            _updateWeekStats(events, calendar);
        },
    });

    calendar.render();
    window._calendar = calendar;

    // ── Right-click on calendar (empty slot or event) ─────────────────────
    calendarEl.addEventListener('contextmenu', function (e) {
        e.preventDefault();
        _hideTooltip();
        const eventEl = e.target.closest('.fc-event');
        if (eventEl) {
            // Right-click on event → same context menu
            const fcEvent = calendar.getEventById(eventEl.getAttribute('data-event-id')) ||
                            calendar.getEvents().find(ev => eventEl.contains(document.querySelector(`[data-event-id="${ev.id}"]`)));
            // Fall back: dispatch to context menu via event title match
            _showContextMenuFromEl(eventEl, e, calendar);
        } else {
            _showEmptySlotMenu(e, calendar);
        }
    });

    // ── ESC closes all panels ─────────────────────────────────────────────
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            closeSeriesPanel();
            if (typeof closeUnavailPanel === 'function') closeUnavailPanel();
            _closeContextMenu();
        }
    });
});

// ─── PATCH single event ───────────────────────────────────────────────────────

async function _patchEvent(event) {
    try {
        const resp = await fetch(`/api/events/${event.id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                title: event.title,
                start_time: event.start.toISOString(),
                end_time: event.end.toISOString(),
                offering_id: event.extendedProps.offering_id,
                teacher_id: event.extendedProps.teacher_id,
                student_id: event.extendedProps.student_id,
                status: event.extendedProps.status,
            }),
        });
        return resp.ok;
    } catch { return false; }
}

// ─── Tooltip ─────────────────────────────────────────────────────────────────

const _STATUS_PL = { scheduled: 'Zaplanowane', completed: 'Ukończone', cancelled: 'Odwołane' };

function _showTooltip(event, jsEvent) {
    let tip = document.getElementById('fc-tooltip');
    if (!tip) {
        tip = document.createElement('div');
        tip.id = 'fc-tooltip';
        tip.className = 'fixed z-[70] bg-gray-900 border border-gray-700 rounded-xl shadow-2xl px-4 py-3 text-sm pointer-events-none max-w-[240px]';
        document.body.appendChild(tip);
    }
    const status = event.extendedProps.status;
    const dotColor = status === 'completed' ? '#6b7280' : status === 'cancelled' ? '#ef4444' : '#22c55e';
    tip.innerHTML = `
        <p class="font-semibold text-white mb-1 leading-tight">${event.title}</p>
        <p class="text-xs text-gray-400 flex items-center gap-1.5">
            <span style="width:7px;height:7px;border-radius:50%;background:${dotColor};display:inline-block;flex-shrink:0"></span>
            ${_STATUS_PL[status] || status}
        </p>
        ${event.extendedProps.series_id ? '<p class="text-xs text-green-400 mt-1">↻ Zajęcia cykliczne</p>' : ''}
        <p class="text-xs text-gray-600 mt-1.5">Kliknij, aby edytować</p>
    `;
    tip.style.display = 'block';
    _positionTooltip(tip, jsEvent);
}

function _positionTooltip(tip, jsEvent) {
    const x = jsEvent.clientX + 14;
    const y = jsEvent.clientY - 10;
    tip.style.left = (x + tip.offsetWidth > window.innerWidth ? x - tip.offsetWidth - 20 : x) + 'px';
    tip.style.top = Math.min(y, window.innerHeight - 120) + 'px';
}

function _hideTooltip() {
    const tip = document.getElementById('fc-tooltip');
    if (tip) tip.style.display = 'none';
}

// ─── Week stats ───────────────────────────────────────────────────────────────

function _updateWeekStats(events, calendar) {
    const statsEl = document.getElementById('fc-week-stats');
    if (!statsEl) return;
    const view = calendar.view;
    const rangeStart = view.activeStart;
    const rangeEnd = view.activeEnd;

    const visible = events.filter(e =>
        e.display !== 'background' &&
        e.start >= rangeStart &&
        e.start < rangeEnd
    );
    const totalMs = visible.reduce((s, e) => s + (e.end ? e.end - e.start : 3600000), 0);
    const h = Math.floor(totalMs / 3600000);
    const m = Math.floor((totalMs % 3600000) / 60000);
    statsEl.textContent = `${visible.length} zajęć · ${h}h${m > 0 ? ` ${m}min` : ''}`;
}

// ─── Empty-slot right-click menu ─────────────────────────────────────────────

function _showEmptySlotMenu(e, calendar) {
    _closeContextMenu();

    // Try to figure out what time was clicked from FC's slot grid
    const slotEl = e.target.closest('.fc-timegrid-slot');
    let hintTime = '';
    if (slotEl) {
        const dataTime = slotEl.getAttribute('data-time');
        if (dataTime) hintTime = ' o ' + dataTime.slice(0, 5);
    }

    const menu = _makeMenu();
    menu.style.left = e.pageX + 'px';
    menu.style.top = e.pageY + 'px';

    _addMenuItem(menu, `+ Nowe zajęcia${hintTime}`, false, () => {
        // Try to extract date from column header
        const colEl = e.target.closest('[data-date]') || e.target.closest('.fc-timegrid-col[data-date]');
        const dateStr = colEl ? colEl.getAttribute('data-date') : new Date().toISOString().split('T')[0];
        const [h, m] = hintTime ? hintTime.slice(3).split(':').map(Number) : [9, 0];
        openSeriesPanelWithTime(dateStr || new Date().toISOString().split('T')[0], h || 9, m || 0, 60);
    });
    _addMenuItem(menu, '+ Nowa seria zajęć', false, () => openSeriesPanel());

    document.body.appendChild(menu);
    _activeMenu = menu;
    _adjustMenuPosition(menu, e);
    setTimeout(() => document.addEventListener('click', _closeContextMenu, { once: true }), 0);
}

// ─── Event context menu ───────────────────────────────────────────────────────

function _showContextMenuFromEl(eventEl, e, calendar) {
    _closeContextMenu();
    // Find FC event matching the clicked element by traversing FC events
    const allEvents = calendar.getEvents();
    let matched = null;
    for (const ev of allEvents) {
        const els = document.querySelectorAll(`[data-event-id="${ev.id}"]`);
        for (const el of els) {
            if (el === eventEl || el.contains(eventEl) || eventEl.contains(el)) {
                matched = ev;
                break;
            }
        }
        if (matched) break;
    }
    if (matched) _showContextMenu(matched, e);
    else _showEmptySlotMenu(e, calendar);
}

let _activeMenu = null;

function _showContextMenu(event, jsEvent) {
    _closeContextMenu();
    _hideTooltip();

    const seriesId = event.extendedProps.series_id;
    const menu = _makeMenu();
    menu.style.left = jsEvent.pageX + 'px';
    menu.style.top = jsEvent.pageY + 'px';

    if (seriesId) {
        _addMenuItem(menu, 'Edytuj tę lekcję', false, () => _editSingleEvent(event));
        _addMenuItem(menu, 'Edytuj tę i następne', false, () => openSeriesPanelEdit(seriesId, event.id));
        _addDivider(menu);
        _addMenuItem(menu, 'Usuń tę lekcję', true, async () => {
            if (!confirm(`Usuń lekcję "${event.title}"?`)) return;
            const r = await fetch(`/api/events/${event.id}`, { method: 'DELETE' });
            if (r.ok) event.remove();
        });
        _addMenuItem(menu, 'Usuń tę i następne', true, async () => {
            if (!confirm(`Usuń tę i wszystkie następne lekcje z serii "${event.title}"?`)) return;
            const r = await fetch(`/api/series/${seriesId}/from/${event.id}`, { method: 'DELETE' });
            if (r.ok && window._calendar) window._calendar.refetchEvents();
        });
    } else {
        _addMenuItem(menu, 'Edytuj', false, () => _editSingleEvent(event));
        _addDivider(menu);
        _addMenuItem(menu, 'Usuń', true, async () => {
            if (!confirm(`Usuń lekcję "${event.title}"?`)) return;
            const r = await fetch(`/api/events/${event.id}`, { method: 'DELETE' });
            if (r.ok) event.remove();
        });
    }

    document.body.appendChild(menu);
    _activeMenu = menu;
    _adjustMenuPosition(menu, jsEvent);
    setTimeout(() => document.addEventListener('click', _closeContextMenu, { once: true }), 0);
}

function _closeContextMenu() {
    if (_activeMenu) { _activeMenu.remove(); _activeMenu = null; }
}

// ─── Context menu helpers ─────────────────────────────────────────────────────

function _makeMenu() {
    const m = document.createElement('div');
    m.id = 'fc-context-menu';
    m.className = 'fixed z-50 bg-gray-900 border border-gray-700 rounded-xl shadow-2xl py-1.5 min-w-[220px] text-sm';
    return m;
}

function _addMenuItem(menu, label, danger, action) {
    const btn = document.createElement('button');
    btn.className = `w-full text-left px-4 py-2 transition-colors ${
        danger ? 'text-red-400 hover:bg-red-500/10' : 'text-gray-200 hover:bg-gray-800'
    }`;
    btn.textContent = label;
    btn.onclick = () => { _closeContextMenu(); action(); };
    menu.appendChild(btn);
}

function _addDivider(menu) {
    const hr = document.createElement('div');
    hr.className = 'border-t border-gray-800 my-1';
    menu.appendChild(hr);
}

function _adjustMenuPosition(menu, e) {
    requestAnimationFrame(() => {
        const rect = menu.getBoundingClientRect();
        if (rect.right > window.innerWidth) menu.style.left = (e.pageX - rect.width) + 'px';
        if (rect.bottom > window.innerHeight) menu.style.top = (e.pageY - rect.height) + 'px';
    });
}

// ─── Edit single event (prompt) ───────────────────────────────────────────────

function _editSingleEvent(event) {
    const newTitle = prompt('Tytuł zajęć:', event.title);
    if (newTitle && newTitle.trim()) {
        fetch(`/api/events/${event.id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                title: newTitle.trim(),
                start_time: event.start.toISOString(),
                end_time: event.end.toISOString(),
                offering_id: event.extendedProps.offering_id,
                teacher_id: event.extendedProps.teacher_id,
                student_id: event.extendedProps.student_id,
                status: event.extendedProps.status,
            }),
        }).then(r => { if (r.ok) event.setProp('title', newTitle.trim()); });
    }
}
