/**
 * FullCalendar initialization for the Ekorepetycje admin panel.
 */

/** Escape HTML special chars — prevents XSS when injecting user data into innerHTML. */
function _h(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/** Read CSRF token from <meta name="csrf-token"> (injected by base.html). */
function _csrf() {
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
}

// ─── Teacher colour palette ────────────────────────────────────────────────────
// 5 vivid colours that work on a dark background, one per teacher slot.
const _TEACHER_PALETTE = [
    { r: 59,  g: 130, b: 246 },   // blue
    { r: 168, g: 85,  b: 247 },   // purple
    { r: 245, g: 158, b: 11  },   // amber
    { r: 236, g: 72,  b: 153 },   // pink
    { r: 6,   g: 182, b: 212 },   // cyan
];

// Stable UUID → palette index (uses first 8 hex chars as uint32).
function _teacherPaletteIdx(teacher_id) {
    if (!teacher_id) return 0;
    return parseInt(teacher_id.replace(/-/g, '').slice(0, 8), 16) % _TEACHER_PALETTE.length;
}

// Returns { bg, text } based on teacher identity + event status.
function _eventColors(teacher_id, status) {
    if (status === 'cancelled') return { bg: 'rgba(185,28,28,0.85)',  text: '#fca5a5' };
    const { r, g, b } = _TEACHER_PALETTE[_teacherPaletteIdx(teacher_id)];
    if (status === 'completed') return { bg: `rgba(${r},${g},${b},0.28)`, text: `rgba(${r},${g},${b},0.6)` };
    return { bg: `rgba(${r},${g},${b},0.82)`, text: '#ffffff' };
}

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
        selectMinDistance: 10,
        unselectAuto: true,
        eventColor: '#0d9488',
        eventTextColor: '#ccfbf1',

        events: function (fetchInfo, successCallback, failureCallback) {
            const params = new URLSearchParams();
            const sel = document.getElementById('fc-user-filter');
            if (sel && sel.value) {
                const [type, id] = sel.value.split(':');
                if (type === 'teacher') params.set('teacher_id', id);
                else if (type === 'student') params.set('student_id', id);
            }
            fetch('/api/events?' + params.toString())
                .then(r => r.json())
                .then(data => successCallback(data.map(function (rawEvent) {
                    const col = _eventColors(rawEvent.teacher_id, rawEvent.status);
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
                        color: col.bg,
                        textColor: col.text,
                    };
                })))
                .catch(failureCallback);
        },

        // ── Drag-to-create ────────────────────────────────────────────────────
        select: function (info) {
            if (_activeMenu) { _closeContextMenu(); calendar.unselect(); return; }
            const durationMin = Math.round((info.end - info.start) / 60000);
            const dateStr = info.startStr.split('T')[0];
            openSeriesPanelWithTime(dateStr, info.start.getHours(), info.start.getMinutes(), durationMin);
            calendar.unselect();
        },

        // ── Click on empty slot ───────────────────────────────────────────────
        dateClick: function (info) {
            if (_activeMenu) { _closeContextMenu(); return; }
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
            info.jsEvent.stopPropagation();
            if (_activeMenu) { _closeContextMenu(); return; }
            _showContextMenu(info.event, info.jsEvent);
        },

        // ── Drag / resize ─────────────────────────────────────────────────────
        eventDrop: async function (info) {
            if (info.event.extendedProps.series_id) {
                if (!confirm('Ta lekcja należy do serii. Czy przenieść tylko tę lekcję (odłączy ją od serii)?')) {
                    info.revert(); return;
                }
            }
            const ok = await _patchEvent(info.event);
            if (!ok) info.revert();
        },

        eventResize: async function (info) {
            if (info.event.extendedProps.series_id) {
                if (!confirm('Ta lekcja należy do serii. Czy zmienić czas tylko tej lekcji (odłączy ją od serii)?')) {
                    info.revert(); return;
                }
            }
            const ok = await _patchEvent(info.event);
            if (!ok) info.revert();
        },

        // ── Tooltip ───────────────────────────────────────────────────────────
        eventMouseEnter: function (info) { _showTooltip(info.event, info.jsEvent); },
        eventMouseLeave: function () { _hideTooltip(); },

        // ── Week stats ────────────────────────────────────────────────────────
        eventsSet: function (events) { _updateWeekStats(events, calendar); },
    });

    calendar.render();
    window._calendar = calendar;

    // ── User filter dropdown ──────────────────────────────────────────────────
    const filterSel = document.getElementById('fc-user-filter');
    if (filterSel) {
        filterSel.addEventListener('change', function () {
            calendar.refetchEvents();
        });
    }

    // ── Right-click ───────────────────────────────────────────────────────────
    calendarEl.addEventListener('contextmenu', function (e) {
        e.preventDefault();
        _hideTooltip();
        const eventEl = e.target.closest('.fc-event');
        if (eventEl) {
            _showContextMenuFromEl(eventEl, e, calendar);
        } else {
            _showEmptySlotMenu(e, calendar);
        }
    });

    // ── ESC closes everything ─────────────────────────────────────────────────
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            closeSeriesPanel();
            if (typeof closeUnavailPanel === 'function') closeUnavailPanel();
            _closeContextMenu();
            _closeEditModal();
        }
    });
});

// ─── PATCH event ──────────────────────────────────────────────────────────────

async function _patchEvent(event) {
    try {
        const resp = await fetch(`/api/events/${event.id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': _csrf() },
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

// ─── Status change ────────────────────────────────────────────────────────────

const _STATUS_COLORS = {
    scheduled: { bg: '#0d9488', text: '#ccfbf1' },
    completed:  { bg: '#334155', text: '#94a3b8' },
    cancelled:  { bg: '#b91c1c', text: '#fca5a5' },
};
const _STATUS_PL = { scheduled: 'Zaplanowane', completed: 'Ukończone', cancelled: 'Odwołane' };

async function _changeStatus(event, newStatus) {
    const r = await fetch(`/api/events/${event.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': _csrf() },
        body: JSON.stringify({
            title: event.title,
            start_time: event.start.toISOString(),
            end_time: event.end.toISOString(),
            offering_id: event.extendedProps.offering_id,
            teacher_id: event.extendedProps.teacher_id,
            student_id: event.extendedProps.student_id,
            status: newStatus,
        }),
    });
    if (r.ok) {
        event.setExtendedProp('status', newStatus);
        const col = _eventColors(event.extendedProps.teacher_id, newStatus);
        event.setProp('color', col.bg);
        event.setProp('textColor', col.text);
    }
}

// ─── Tooltip ──────────────────────────────────────────────────────────────────

function _showTooltip(event, jsEvent) {
    let tip = document.getElementById('fc-tooltip');
    if (!tip) {
        tip = document.createElement('div');
        tip.id = 'fc-tooltip';
        tip.style.cssText = 'position:fixed;z-index:9998;pointer-events:none;max-width:220px;';
        document.body.appendChild(tip);
    }
    const col = _eventColors(event.extendedProps.teacher_id, event.extendedProps.status);
    const statusLabel = _STATUS_PL[event.extendedProps.status] || event.extendedProps.status;
    tip.innerHTML = `
        <div style="background:rgba(10,15,30,0.97);backdrop-filter:blur(20px);border:1px solid rgba(255,255,255,0.1);border-radius:10px;box-shadow:0 12px 32px rgba(0,0,0,0.4);padding:10px 13px;">
            <p style="font-size:13px;font-weight:600;color:#f1f5f9;margin:0 0 4px;line-height:1.3">${_h(event.title)}</p>
            <p style="font-size:11px;color:#64748b;margin:0;display:flex;align-items:center;gap:5px">
                <span style="width:6px;height:6px;border-radius:50%;background:${col.bg};flex-shrink:0;display:inline-block"></span>
                ${_h(statusLabel)}
            </p>
            ${event.extendedProps.series_id ? '<p style="font-size:11px;color:#38bdf8;margin:4px 0 0">↻ Zajęcia cykliczne</p>' : ''}
            <p style="font-size:10px;color:#334155;margin:5px 0 0">Kliknij aby edytować</p>
        </div>`;
    tip.style.display = 'block';
    const x = jsEvent.clientX + 14;
    const y = jsEvent.clientY - 10;
    tip.style.left = (x + 220 > window.innerWidth ? x - 240 : x) + 'px';
    tip.style.top = Math.min(y, window.innerHeight - 100) + 'px';
}

function _hideTooltip() {
    const tip = document.getElementById('fc-tooltip');
    if (tip) tip.style.display = 'none';
}

// ─── Week stats ───────────────────────────────────────────────────────────────

function _updateWeekStats(events, calendar) {
    const statsEl = document.getElementById('fc-week-stats');
    if (!statsEl) return;
    const { activeStart, activeEnd } = calendar.view;
    const visible = events.filter(e =>
        e.display !== 'background' && e.start >= activeStart && e.start < activeEnd
    );
    const totalMs = visible.reduce((s, e) => s + (e.end ? e.end - e.start : 3600000), 0);
    const h = Math.floor(totalMs / 3600000);
    const m = Math.floor((totalMs % 3600000) / 60000);
    statsEl.textContent = `${visible.length} zajęć · ${h}h${m > 0 ? ` ${m}min` : ''}`;
}

// ─── Empty-slot right-click menu ──────────────────────────────────────────────

function _showEmptySlotMenu(e, calendar) {
    _closeContextMenu();
    const slotEl = e.target.closest('.fc-timegrid-slot');
    let hintTime = '';
    if (slotEl) {
        const t = slotEl.getAttribute('data-time');
        if (t) hintTime = ' o ' + t.slice(0, 5);
    }
    const menu = _makeMenu();
    menu.style.left = e.pageX + 'px';
    menu.style.top  = e.pageY + 'px';

    _addMenuItem(menu, _ICO_PLUS, `Nowe zajęcia${hintTime}`, false, () => {
        const colEl  = e.target.closest('[data-date]');
        const dateStr = colEl ? colEl.getAttribute('data-date') : new Date().toISOString().split('T')[0];
        const [h, m] = hintTime ? hintTime.slice(3).split(':').map(Number) : [9, 0];
        openSeriesPanelWithTime(dateStr, h || 9, m || 0, 60);
    });
    _addMenuItem(menu, _ICO_SERIES, 'Nowa seria zajęć', false, () => openSeriesPanel());

    document.body.appendChild(menu);
    _activeMenu = menu;
    _adjustMenuPos(menu, e);
    _registerMenuDismiss();
}

// ─── Event context menu ───────────────────────────────────────────────────────

function _showContextMenuFromEl(eventEl, e, calendar) {
    _closeContextMenu();
    const allEvents = calendar.getEvents();
    let matched = null;
    for (const ev of allEvents) {
        for (const el of document.querySelectorAll(`[data-event-id="${ev.id}"]`)) {
            if (el === eventEl || el.contains(eventEl) || eventEl.contains(el)) {
                matched = ev; break;
            }
        }
        if (matched) break;
    }
    if (matched) _showContextMenu(matched, e);
    else _showEmptySlotMenu(e, calendar);
}

let _activeMenu = null;
let _menuOutsideHandler = null;

function _registerMenuDismiss() {
    _menuOutsideHandler = function (e) {
        if (!_activeMenu) return;
        if (_activeMenu.contains(e.target)) return; // click was inside the menu — let it through
        _closeContextMenu();
        e.stopPropagation(); // swallow the click so FullCalendar never sees it
    };
    // setTimeout keeps the RIGHT-CLICK that opened the menu from immediately closing it
    setTimeout(() => document.addEventListener('click', _menuOutsideHandler, true), 0);
}

function _showContextMenu(event, jsEvent) {
    _closeContextMenu();
    _hideTooltip();

    const seriesId     = event.extendedProps.series_id;
    const currentStatus = event.extendedProps.status;
    const menu = _makeMenu();
    menu.style.left = jsEvent.pageX + 'px';
    menu.style.top  = jsEvent.pageY + 'px';

    // Header — event title
    _addMenuHeader(menu, event.title);

    // Edit actions
    if (seriesId) {
        _addMenuItem(menu, _ICO_EDIT,   'Edytuj tę lekcję',     false, () => _editSingleEvent(event));
        _addMenuItem(menu, _ICO_SERIES, 'Edytuj tę i następne', false, () => openSeriesPanelEdit(seriesId, event.id));
    } else {
        _addMenuItem(menu, _ICO_EDIT, 'Edytuj', false, () => _editSingleEvent(event));
    }

    // Status section
    _addSectionLabel(menu, 'Status');
    [
        { status: 'scheduled', label: 'Zaplanowane', dot: '#0d9488' },
        { status: 'completed', label: 'Ukończone',   dot: '#475569' },
        { status: 'cancelled', label: 'Odwołane',    dot: '#ef4444' },
    ].forEach(({ status, label, dot }) => {
        _addStatusItem(menu, label, dot, currentStatus === status,
            () => _changeStatus(event, status));
    });

    // Delete section
    _addDivider(menu);
    if (seriesId) {
        _addMenuItem(menu, _ICO_DEL, 'Usuń tę lekcję', true, async () => {
            if (!confirm(`Usuń lekcję "${event.title}"?`)) return;
            const r = await fetch(`/api/events/${event.id}`, { method: 'DELETE', headers: { 'X-CSRF-Token': _csrf() } });
            if (r.ok) event.remove();
        });
        _addMenuItem(menu, _ICO_DEL, 'Usuń tę i następne', true, async () => {
            if (!confirm(`Usuń tę i wszystkie następne lekcje z serii "${event.title}"?`)) return;
            const r = await fetch(`/api/series/${seriesId}/from/${event.id}`, { method: 'DELETE', headers: { 'X-CSRF-Token': _csrf() } });
            if (r.ok && window._calendar) window._calendar.refetchEvents();
        });
    } else {
        _addMenuItem(menu, _ICO_DEL, 'Usuń', true, async () => {
            if (!confirm(`Usuń lekcję "${event.title}"?`)) return;
            const r = await fetch(`/api/events/${event.id}`, { method: 'DELETE', headers: { 'X-CSRF-Token': _csrf() } });
            if (r.ok) event.remove();
        });
    }

    document.body.appendChild(menu);
    _activeMenu = menu;
    _adjustMenuPos(menu, jsEvent);
    _registerMenuDismiss();
}

function _closeContextMenu() {
    if (_menuOutsideHandler) {
        document.removeEventListener('click', _menuOutsideHandler, true);
        _menuOutsideHandler = null;
    }
    if (_activeMenu) { _activeMenu.remove(); _activeMenu = null; }
}

// ─── Context menu builders ─────────────────────────────────────────────────────

// SVG icon strings
const _ICO_EDIT   = '<svg width="13" height="13" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/></svg>';
const _ICO_SERIES = '<svg width="13" height="13" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>';
const _ICO_DEL    = '<svg width="13" height="13" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>';
const _ICO_PLUS   = '<svg width="13" height="13" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>';

function _makeMenu() {
    const m = document.createElement('div');
    m.id = 'fc-context-menu';
    m.style.cssText = [
        'position:fixed;z-index:9999;',
        'background:rgba(10,15,30,0.97);',
        'backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);',
        'border:1px solid rgba(255,255,255,0.1);',
        'border-radius:12px;',
        'box-shadow:0 24px 64px rgba(0,0,0,0.55),0 4px 16px rgba(0,0,0,0.3);',
        'padding:5px 0;min-width:228px;',
        'animation:fcMenuIn 0.15s cubic-bezier(0.22,1,0.36,1) forwards;',
    ].join('');
    return m;
}

function _addMenuHeader(menu, title) {
    const h = document.createElement('div');
    h.style.cssText = 'padding:9px 14px 8px;border-bottom:1px solid rgba(255,255,255,0.07);margin-bottom:3px;';
    const safe = title.replace(/</g, '&lt;').replace(/>/g, '&gt;');
    h.innerHTML = `<p style="font-size:11px;font-weight:600;color:#64748b;letter-spacing:0.06em;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:200px;margin:0">${safe}</p>`;
    menu.appendChild(h);
}

function _addMenuItem(menu, iconSvg, label, danger, action) {
    const clr     = danger ? '#f87171' : '#e2e8f0';
    const hoverBg = danger ? 'rgba(239,68,68,0.09)' : 'rgba(255,255,255,0.07)';
    const btn = document.createElement('button');
    btn.style.cssText = `width:100%;display:flex;align-items:center;gap:9px;padding:7px 14px;font-size:13px;text-align:left;cursor:pointer;background:transparent;border:none;color:${clr};line-height:1.3;`;
    btn.onmouseenter = () => { btn.style.background = hoverBg; };
    btn.onmouseleave = () => { btn.style.background = 'transparent'; };
    btn.innerHTML = `<span style="flex-shrink:0;opacity:0.65;display:flex;align-items:center">${iconSvg}</span><span>${label}</span>`;
    btn.onclick = () => { _closeContextMenu(); action(); };
    menu.appendChild(btn);
}

function _addSectionLabel(menu, label) {
    const d = document.createElement('div');
    d.style.cssText = 'padding:8px 14px 3px;border-top:1px solid rgba(255,255,255,0.07);margin-top:3px;';
    d.innerHTML = `<p style="font-size:10px;font-weight:700;color:#334155;letter-spacing:0.08em;text-transform:uppercase;margin:0">${label}</p>`;
    menu.appendChild(d);
}

function _addDivider(menu) {
    const d = document.createElement('div');
    d.style.cssText = 'height:1px;background:rgba(255,255,255,0.07);margin:4px 0;';
    menu.appendChild(d);
}

function _addStatusItem(menu, label, dotColor, isActive, action) {
    const btn = document.createElement('button');
    btn.style.cssText = `width:100%;display:flex;align-items:center;gap:9px;padding:6px 14px;font-size:13px;text-align:left;cursor:${isActive ? 'default' : 'pointer'};background:transparent;border:none;color:${isActive ? '#e2e8f0' : '#475569'};font-weight:${isActive ? '600' : '400'};`;
    btn.onmouseenter = () => { if (!isActive) btn.style.background = 'rgba(255,255,255,0.07)'; };
    btn.onmouseleave = () => { btn.style.background = 'transparent'; };
    const check = isActive
        ? `<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><polyline points="2,7 5,10 10,3" stroke="${dotColor}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>`
        : '<span style="width:12px;height:12px;display:inline-block"></span>';
    btn.innerHTML = `<span style="display:flex;align-items:center;flex-shrink:0">${check}</span><span style="display:flex;align-items:center;gap:7px"><span style="width:7px;height:7px;border-radius:50%;background:${dotColor};flex-shrink:0;display:inline-block"></span>${label}</span>`;
    if (!isActive) btn.onclick = () => { _closeContextMenu(); action(); };
    menu.appendChild(btn);
}

function _adjustMenuPos(menu, e) {
    requestAnimationFrame(() => {
        const r = menu.getBoundingClientRect();
        if (r.right  > window.innerWidth)  menu.style.left = (e.pageX - r.width)  + 'px';
        if (r.bottom > window.innerHeight) menu.style.top  = (e.pageY - r.height) + 'px';
    });
}

// ─── Edit modal (replaces browser prompt) ─────────────────────────────────────

function _closeEditModal() {
    const m = document.getElementById('fc-edit-modal');
    if (m) m.remove();
}

function _editSingleEvent(event) {
    _closeEditModal();

    const overlay = document.createElement('div');
    overlay.id = 'fc-edit-modal';
    overlay.style.cssText = 'position:fixed;inset:0;z-index:10000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.5);backdrop-filter:blur(6px);';

    const safeTitle = event.title.replace(/"/g, '&quot;').replace(/</g, '&lt;');
    overlay.innerHTML = `
        <div style="background:#0f172a;border:1px solid rgba(255,255,255,0.12);border-radius:14px;padding:22px;width:320px;box-shadow:0 32px 80px rgba(0,0,0,0.6);animation:fcMenuIn 0.18s cubic-bezier(0.22,1,0.36,1) forwards;">
            <div style="display:flex;align-items:center;margin-bottom:16px;">
                <p style="font-size:14px;font-weight:600;color:#f1f5f9;flex:1;margin:0">Edytuj zajęcia</p>
                <button id="fc-edit-close" style="background:transparent;border:none;cursor:pointer;color:#475569;font-size:22px;line-height:1;padding:0;display:flex;align-items:center;">×</button>
            </div>
            <label style="display:block;font-size:10px;font-weight:700;color:#475569;letter-spacing:0.07em;text-transform:uppercase;margin-bottom:6px;">Tytuł</label>
            <input id="fc-edit-input" type="text" value="${safeTitle}"
                   style="width:100%;box-sizing:border-box;background:#1e293b;border:1px solid rgba(255,255,255,0.12);border-radius:8px;padding:9px 12px;font-size:13px;color:#f1f5f9;outline:none;margin-bottom:14px;transition:border-color 0.15s;">
            <div style="display:flex;gap:8px;">
                <button id="fc-edit-cancel" style="flex:1;padding:9px;border:1px solid rgba(255,255,255,0.12);border-radius:8px;background:transparent;color:#94a3b8;font-size:13px;cursor:pointer;transition:background 0.15s;">Anuluj</button>
                <button id="fc-edit-save"   style="flex:1;padding:9px;border:none;border-radius:8px;background:#1d4ed8;color:#eff6ff;font-size:13px;font-weight:600;cursor:pointer;transition:background 0.15s;">Zapisz</button>
            </div>
        </div>`;

    document.body.appendChild(overlay);

    const input = document.getElementById('fc-edit-input');
    input.focus(); input.select();
    input.addEventListener('focus', () => { input.style.borderColor = 'rgba(59,130,246,0.6)'; });
    input.addEventListener('blur',  () => { input.style.borderColor = 'rgba(255,255,255,0.12)'; });

    const btnCancel = document.getElementById('fc-edit-cancel');
    const btnSave   = document.getElementById('fc-edit-save');
    btnCancel.onmouseenter = () => { btnCancel.style.background = 'rgba(255,255,255,0.07)'; };
    btnCancel.onmouseleave = () => { btnCancel.style.background = 'transparent'; };
    btnSave.onmouseenter   = () => { btnSave.style.background = '#1e40af'; };
    btnSave.onmouseleave   = () => { btnSave.style.background = '#1d4ed8'; };

    const save = async () => {
        const newTitle = input.value.trim();
        if (!newTitle) { input.style.borderColor = '#ef4444'; input.focus(); return; }
        const r = await fetch(`/api/events/${event.id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': _csrf() },
            body: JSON.stringify({
                title: newTitle,
                start_time: event.start.toISOString(),
                end_time: event.end.toISOString(),
                offering_id: event.extendedProps.offering_id,
                teacher_id: event.extendedProps.teacher_id,
                student_id: event.extendedProps.student_id,
                status: event.extendedProps.status,
            }),
        });
        if (r.ok) event.setProp('title', newTitle);
        overlay.remove();
    };

    document.getElementById('fc-edit-close').onclick  = () => overlay.remove();
    btnCancel.onclick = () => overlay.remove();
    btnSave.onclick   = save;
    overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
    input.addEventListener('keydown', e => {
        if (e.key === 'Enter')  save();
        if (e.key === 'Escape') overlay.remove();
    });
}
