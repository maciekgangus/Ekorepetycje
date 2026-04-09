/**
 * FullCalendar initialization for the teacher calendar view.
 * window.TEACHER_ID is injected from the template.
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

document.addEventListener('DOMContentLoaded', function () {
    const calendarEl = document.getElementById('calendar');
    if (!calendarEl) return;

    const calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'timeGridWeek',
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
        locale: 'pl',
        height: 'auto',
        slotMinTime: '07:00:00',
        slotMaxTime: '22:00:00',
        allDaySlot: false,
        nowIndicator: true,
        editable: true,
        selectable: true,
        selectMinDistance: 10,
        eventAllow: function (dropInfo, draggedEvent) {
            return draggedEvent.extendedProps.status === 'scheduled';
        },

        eventSources: [
            {
                url: `/api/events?teacher_id=${window.TEACHER_ID}`,
                failure: function () { console.error('Failed to load events'); },
            },
            {
                url: `/api/availability/${window.TEACHER_ID}`,
                display: 'background',
                color: 'rgba(100,116,139,0.25)',
                failure: function () { console.error('Failed to load availability'); },
            },
        ],

        eventDataTransform: function (rawEvent) {
            // Availability background blocks already use start/end — pass through untouched.
            if (!rawEvent.start_time) return rawEvent;
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
                color: rawEvent.status === 'completed' ? '#334155' :
                       rawEvent.status === 'cancelled' ? '#b91c1c' : '#0d9488',
                textColor: rawEvent.status === 'completed' ? '#94a3b8' :
                           rawEvent.status === 'cancelled' ? '#fca5a5' : '#ccfbf1',
            };
        },

        select: function (info) {
            const durationMin = Math.round((info.end - info.start) / 60000);
            openSeriesPanelWithTime(
                info.startStr.split('T')[0],
                info.start.getHours(),
                info.start.getMinutes(),
                durationMin
            );
            calendar.unselect();
        },

        dateClick: function (info) {
            openSeriesPanelWithTime(
                info.dateStr.split('T')[0],
                info.date.getHours(),
                info.date.getMinutes(),
                60
            );
        },

        // ── Drag event to new slot → create change request ───────────────────
        eventDrop: async function (info) {
            const newStart = info.event.start.toISOString();
            const newEnd   = (info.event.end || new Date(info.event.start.getTime() + 3600000)).toISOString();

            let resp;
            try {
                resp = await fetch('/api/change-requests', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': _csrf() },
                    body: JSON.stringify({ event_id: info.event.id, new_start: newStart, new_end: newEnd }),
                });
            } catch {
                info.revert();
                _showDragToast('Błąd sieci — propozycja nie została wysłana.', true);
                return;
            }

            if (resp.ok) {
                info.event.setProp('color', '#f59e0b');
                info.event.setProp('textColor', '#1c1917');
                if (!info.event.title.endsWith(' ↻'))
                    info.event.setProp('title', info.event.title + ' ↻');
                _showDragToast('Propozycja wysłana — czeka na akceptację ucznia.');
            } else {
                info.revert();
                const data = await resp.json().catch(() => ({}));
                _showDragToast(data.detail || 'Nie udało się wysłać propozycji.', true);
            }
        },

        // ── Left-click on event → context menu ───────────────────────────────
        eventClick: function (info) {
            info.jsEvent.preventDefault();
            info.jsEvent.stopPropagation(); // prevents old { once } listener from closing new menu
            _showTeacherContextMenu(info.event, info.jsEvent);
        },

        eventMouseEnter: function (info) { _showTeacherTooltip(info.event, info.jsEvent); },
        eventMouseLeave: function ()      { _hideTeacherTooltip(); },

        eventsSet: function (events) { _updateTeacherWeekStats(events, calendar); },
    });

    calendar.render();
    window._calendar = calendar;

    // Right-click on empty slot → new series
    calendarEl.addEventListener('contextmenu', function (e) {
        e.preventDefault();
        _hideTeacherTooltip();
        if (!e.target.closest('.fc-event')) {
            const slotEl = e.target.closest('.fc-timegrid-slot');
            const t = slotEl ? slotEl.getAttribute('data-time') : '';
            const [h, m] = t ? t.slice(0, 5).split(':').map(Number) : [9, 0];
            const colEl = e.target.closest('[data-date]');
            const dateStr = colEl ? colEl.getAttribute('data-date') : new Date().toISOString().split('T')[0];
            openSeriesPanelWithTime(dateStr, h, m, 60);
        }
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            closeSeriesPanel();
            if (typeof closeUnavailPanel === 'function') closeUnavailPanel();
            _closeTeacherMenu();
        }
    });
});

// ─── Tooltip ──────────────────────────────────────────────────────────────────

const _T_STATUS_PL = { scheduled: 'Zaplanowane', completed: 'Ukończone', cancelled: 'Odwołane' };
const _T_STATUS_COLORS = {
    scheduled: '#0d9488',
    completed: '#475569',
    cancelled: '#ef4444',
};

function _showTeacherTooltip(event, jsEvent) {
    let tip = document.getElementById('fc-tooltip');
    if (!tip) {
        tip = document.createElement('div');
        tip.id = 'fc-tooltip';
        tip.style.cssText = 'position:fixed;z-index:9998;pointer-events:none;max-width:220px;';
        document.body.appendChild(tip);
    }
    const col = _T_STATUS_COLORS[event.extendedProps.status] || _T_STATUS_COLORS.scheduled;
    const statusLabel = _T_STATUS_PL[event.extendedProps.status] || event.extendedProps.status;
    tip.innerHTML = `
        <div style="background:rgba(10,15,30,0.97);backdrop-filter:blur(20px);border:1px solid rgba(255,255,255,0.1);border-radius:10px;box-shadow:0 12px 32px rgba(0,0,0,0.4);padding:10px 13px;">
            <p style="font-size:13px;font-weight:600;color:#f1f5f9;margin:0 0 4px;line-height:1.3">${_h(event.title)}</p>
            <p style="font-size:11px;color:#64748b;margin:0;display:flex;align-items:center;gap:5px">
                <span style="width:6px;height:6px;border-radius:50%;background:${col};flex-shrink:0;display:inline-block"></span>
                ${_h(statusLabel)}
            </p>
            ${event.extendedProps.series_id ? '<p style="font-size:11px;color:#38bdf8;margin:4px 0 0">↻ Zajęcia cykliczne</p>' : ''}
        </div>`;
    tip.style.display = 'block';
    const x = jsEvent.clientX + 14;
    const y = jsEvent.clientY - 10;
    tip.style.left = (x + 220 > window.innerWidth ? x - 240 : x) + 'px';
    tip.style.top  = Math.min(y, window.innerHeight - 100) + 'px';
}

function _hideTeacherTooltip() {
    const tip = document.getElementById('fc-tooltip');
    if (tip) tip.style.display = 'none';
}

// ─── Week stats ───────────────────────────────────────────────────────────────

function _updateTeacherWeekStats(events, calendar) {
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

// ─── Context menu ─────────────────────────────────────────────────────────────

let _activeTeacherMenu = null;

function _closeTeacherMenu() {
    if (_activeTeacherMenu) { _activeTeacherMenu.remove(); _activeTeacherMenu = null; }
}

const _T_ICO_SERIES = '<svg width="13" height="13" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>';
const _T_ICO_DEL   = '<svg width="13" height="13" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>';

function _showTeacherContextMenu(event, jsEvent) {
    _closeTeacherMenu();
    _hideTeacherTooltip();

    const seriesId = event.extendedProps.series_id;
    const menu = document.createElement('div');
    menu.style.cssText = [
        'position:fixed;z-index:9999;',
        'background:rgba(10,15,30,0.97);',
        'backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);',
        'border:1px solid rgba(255,255,255,0.1);',
        'border-radius:12px;',
        'box-shadow:0 24px 64px rgba(0,0,0,0.55),0 4px 16px rgba(0,0,0,0.3);',
        'padding:5px 0;min-width:228px;',
        'animation:fcMenuIn 0.15s cubic-bezier(0.22,1,0.36,1) forwards;',
    ].join('');
    menu.style.left = jsEvent.pageX + 'px';
    menu.style.top  = jsEvent.pageY + 'px';

    // Header
    const safe = event.title.replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const hdr = document.createElement('div');
    hdr.style.cssText = 'padding:9px 14px 8px;border-bottom:1px solid rgba(255,255,255,0.07);margin-bottom:3px;';
    hdr.innerHTML = `<p style="font-size:11px;font-weight:600;color:#64748b;letter-spacing:0.06em;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:200px;margin:0">${safe}</p>`;
    menu.appendChild(hdr);

    const _addItem = (iconSvg, label, danger, action) => {
        const clr = danger ? '#f87171' : '#e2e8f0';
        const hBg = danger ? 'rgba(239,68,68,0.09)' : 'rgba(255,255,255,0.07)';
        const btn = document.createElement('button');
        btn.style.cssText = `width:100%;display:flex;align-items:center;gap:9px;padding:7px 14px;font-size:13px;text-align:left;cursor:pointer;background:transparent;border:none;color:${clr};line-height:1.3;`;
        btn.onmouseenter = () => { btn.style.background = hBg; };
        btn.onmouseleave = () => { btn.style.background = 'transparent'; };
        btn.innerHTML = `<span style="flex-shrink:0;opacity:0.65;display:flex;align-items:center">${iconSvg}</span><span>${label}</span>`;
        btn.onclick = () => { _closeTeacherMenu(); action(); };
        menu.appendChild(btn);
    };

    if (seriesId) {
        _addItem(_T_ICO_SERIES, 'Edytuj tę i następne', false, () => openSeriesPanelEdit(seriesId, event.id));
        // Divider
        const div = document.createElement('div');
        div.style.cssText = 'height:1px;background:rgba(255,255,255,0.07);margin:4px 0;';
        menu.appendChild(div);
        _addItem(_T_ICO_DEL, 'Usuń tę lekcję', true, async () => {
            if (!confirm(`Usuń lekcję "${event.title}"?`)) return;
            const r = await fetch(`/api/events/${event.id}`, { method: 'DELETE', headers: { 'X-CSRF-Token': _csrf() } });
            if (r.ok) event.remove();
        });
        _addItem(_T_ICO_DEL, 'Usuń tę i następne', true, async () => {
            if (!confirm('Usuń tę i wszystkie następne lekcje z serii?')) return;
            const r = await fetch(`/api/series/${seriesId}/from/${event.id}`, { method: 'DELETE', headers: { 'X-CSRF-Token': _csrf() } });
            if (r.ok && window._calendar) window._calendar.refetchEvents();
        });
    } else {
        _addItem(_T_ICO_DEL, 'Usuń lekcję', true, async () => {
            if (!confirm(`Usuń lekcję "${event.title}"?`)) return;
            const r = await fetch(`/api/events/${event.id}`, { method: 'DELETE', headers: { 'X-CSRF-Token': _csrf() } });
            if (r.ok) event.remove();
        });
    }

    document.body.appendChild(menu);
    _activeTeacherMenu = menu;

    requestAnimationFrame(() => {
        const r = menu.getBoundingClientRect();
        if (r.right  > window.innerWidth)  menu.style.left = (jsEvent.pageX - r.width)  + 'px';
        if (r.bottom > window.innerHeight) menu.style.top  = (jsEvent.pageY - r.height) + 'px';
    });

    setTimeout(() => document.addEventListener('click', _closeTeacherMenu, { once: true }), 0);
}

// ─── Drag-drop toast ──────────────────────────────────────────────────────────

function _showDragToast(msg, isError = false) {
    let toast = document.getElementById('fc-drag-toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'fc-drag-toast';
        toast.style.cssText = 'position:fixed;bottom:28px;left:50%;transform:translateX(-50%);z-index:9999;padding:10px 20px;border-radius:10px;font-size:13px;font-weight:500;pointer-events:none;transition:opacity 0.4s;white-space:nowrap;';
        document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.style.background   = isError ? 'rgba(127,29,29,0.97)' : 'rgba(20,83,45,0.97)';
    toast.style.color        = isError ? '#fca5a5' : '#86efac';
    toast.style.border       = isError ? '1px solid #991b1b' : '1px solid #166534';
    toast.style.backdropFilter = 'blur(12px)';
    toast.style.opacity = '1';
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => { toast.style.opacity = '0'; }, 3500);
}
