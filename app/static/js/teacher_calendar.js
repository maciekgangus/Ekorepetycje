/**
 * FullCalendar initialization for the teacher calendar view.
 * window.TEACHER_ID is injected from the template.
 */
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
        editable: false,
        selectable: true,
        selectMinDistance: 10,

        eventSources: [
            {
                url: `/api/events?teacher_id=${window.TEACHER_ID}`,
                failure: function () { console.error('Failed to load events'); },
            },
            {
                url: `/api/availability/${window.TEACHER_ID}`,
                display: 'background',
                color: '#6b7280',
                failure: function () { console.error('Failed to load availability'); },
            },
        ],

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
                textColor: '#030712',
            };
        },

        // ── Drag-to-create on empty slot ──────────────────────────────────────
        select: function (info) {
            const durationMin = Math.round((info.end - info.start) / 60000);
            const dateStr = info.startStr.split('T')[0];
            openSeriesPanelWithTime(dateStr, info.start.getHours(), info.start.getMinutes(), durationMin);
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

        eventClick: function (info) {
            info.jsEvent.preventDefault();
            _showTeacherContextMenu(info.event, info.jsEvent);
        },

        eventMouseEnter: function (info) { _showTeacherTooltip(info.event, info.jsEvent); },
        eventMouseLeave: function () { _hideTeacherTooltip(); },

        eventsSet: function (events) { _updateTeacherWeekStats(events, calendar); },
    });

    calendar.render();
    window._calendar = calendar;

    // Right-click on empty slot → new series
    calendarEl.addEventListener('contextmenu', function (e) {
        e.preventDefault();
        _hideTeacherTooltip();
        const eventEl = e.target.closest('.fc-event');
        if (!eventEl) {
            const slotEl = e.target.closest('.fc-timegrid-slot');
            const dataTime = slotEl ? slotEl.getAttribute('data-time') : '';
            const [h, m] = dataTime ? dataTime.slice(0, 5).split(':').map(Number) : [9, 0];
            const colEl = e.target.closest('[data-date]');
            const dateStr = colEl ? colEl.getAttribute('data-date') : new Date().toISOString().split('T')[0];
            openSeriesPanelWithTime(dateStr, h, m, 60);
        }
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            closeSeriesPanel();
            if (typeof closeUnavailPanel === 'function') closeUnavailPanel();
        }
    });
});

// ─── Tooltip ─────────────────────────────────────────────────────────────────

const _T_STATUS_PL = { scheduled: 'Zaplanowane', completed: 'Ukończone', cancelled: 'Odwołane' };

function _showTeacherTooltip(event, jsEvent) {
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
            ${_T_STATUS_PL[status] || status}
        </p>
        ${event.extendedProps.series_id ? '<p class="text-xs text-green-400 mt-1">↻ Zajęcia cykliczne</p>' : ''}
    `;
    tip.style.display = 'block';
    const x = jsEvent.clientX + 14;
    const y = jsEvent.clientY - 10;
    tip.style.left = (x + 240 > window.innerWidth ? x - 260 : x) + 'px';
    tip.style.top = Math.min(y, window.innerHeight - 120) + 'px';
}

function _hideTeacherTooltip() {
    const tip = document.getElementById('fc-tooltip');
    if (tip) tip.style.display = 'none';
}

// ─── Week stats ───────────────────────────────────────────────────────────────

function _updateTeacherWeekStats(events, calendar) {
    const statsEl = document.getElementById('fc-week-stats');
    if (!statsEl) return;
    const view = calendar.view;
    const visible = events.filter(e =>
        e.display !== 'background' && e.start >= view.activeStart && e.start < view.activeEnd
    );
    const totalMs = visible.reduce((s, e) => s + (e.end ? e.end - e.start : 3600000), 0);
    const h = Math.floor(totalMs / 3600000);
    const m = Math.floor((totalMs % 3600000) / 60000);
    statsEl.textContent = `${visible.length} zajęć · ${h}h${m > 0 ? ` ${m}min` : ''}`;
}

// ─── Context menu ─────────────────────────────────────────────────────────────

let _activeTeacherMenu = null;

function _showTeacherContextMenu(event, jsEvent) {
    if (_activeTeacherMenu) { _activeTeacherMenu.remove(); _activeTeacherMenu = null; }
    _hideTeacherTooltip();

    const seriesId = event.extendedProps.series_id;
    const menu = document.createElement('div');
    menu.className = 'fixed z-50 bg-gray-900 border border-gray-700 rounded-xl shadow-2xl py-1.5 min-w-[220px] text-sm';
    menu.style.left = jsEvent.pageX + 'px';
    menu.style.top = jsEvent.pageY + 'px';

    const items = seriesId ? [
        { label: 'Edytuj tę i następne', action: () => openSeriesPanelEdit(seriesId, event.id) },
        { divider: true },
        {
            label: 'Usuń tę lekcję', danger: true,
            action: async () => {
                if (!confirm(`Usuń lekcję "${event.title}"?`)) return;
                const r = await fetch(`/api/events/${event.id}`, { method: 'DELETE' });
                if (r.ok) event.remove();
            },
        },
        {
            label: 'Usuń tę i następne', danger: true,
            action: async () => {
                if (!confirm('Usuń tę i wszystkie następne lekcje z serii?')) return;
                const r = await fetch(`/api/series/${seriesId}/from/${event.id}`, { method: 'DELETE' });
                if (r.ok && window._calendar) window._calendar.refetchEvents();
            },
        },
    ] : [
        {
            label: 'Usuń lekcję', danger: true,
            action: async () => {
                if (!confirm(`Usuń lekcję "${event.title}"?`)) return;
                const r = await fetch(`/api/events/${event.id}`, { method: 'DELETE' });
                if (r.ok) event.remove();
            },
        },
    ];

    items.forEach(item => {
        if (item.divider) {
            const hr = document.createElement('div');
            hr.className = 'border-t border-gray-800 my-1';
            menu.appendChild(hr);
            return;
        }
        const btn = document.createElement('button');
        btn.className = `w-full text-left px-4 py-2 transition-colors ${
            item.danger ? 'text-red-400 hover:bg-red-500/10' : 'text-gray-200 hover:bg-gray-800'
        }`;
        btn.textContent = item.label;
        btn.onclick = () => { menu.remove(); _activeTeacherMenu = null; item.action(); };
        menu.appendChild(btn);
    });

    document.body.appendChild(menu);
    _activeTeacherMenu = menu;

    requestAnimationFrame(() => {
        const rect = menu.getBoundingClientRect();
        if (rect.right > window.innerWidth) menu.style.left = (jsEvent.pageX - rect.width) + 'px';
        if (rect.bottom > window.innerHeight) menu.style.top = (jsEvent.pageY - rect.height) + 'px';
    });

    setTimeout(() => document.addEventListener('click', () => {
        if (_activeTeacherMenu) { _activeTeacherMenu.remove(); _activeTeacherMenu = null; }
    }, { once: true }), 0);
}
