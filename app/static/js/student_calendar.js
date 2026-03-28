/**
 * FullCalendar initialization for the student calendar view.
 * window.USER_ID is injected from the template.
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
            right: 'dayGridMonth,timeGridWeek,timeGridDay',
        },
        locale: 'pl',
        height: 'auto',
        slotMinTime: '07:00:00',
        slotMaxTime: '22:00:00',
        allDaySlot: false,
        nowIndicator: true,
        editable: false,
        selectable: false,

        eventSources: [
            {
                url: `/api/events?student_id=${window.USER_ID}`,
                failure: function () { console.error('Failed to load events'); },
            },
            {
                url: `/api/availability/${window.USER_ID}`,
                display: 'background',
                color: '#6b7280',
                failure: function () { console.error('Failed to load availability'); },
            },
        ],

        eventDataTransform: function (rawEvent) {
            // Background events from /api/availability are already in FullCalendar format
            if (rawEvent.display === 'background') return rawEvent;
            return {
                id: rawEvent.id,
                title: rawEvent.title,
                start: rawEvent.start_time,
                end: rawEvent.end_time,
                extendedProps: {
                    status: rawEvent.status,
                    teacher_id: rawEvent.teacher_id,
                    series_id: rawEvent.series_id,
                },
                color: rawEvent.status === 'completed' ? '#4b5563' :
                       rawEvent.status === 'cancelled' ? '#ef4444' : '#22c55e',
                textColor: '#030712',
            };
        },

        // Click on event (lesson) → tooltip, no edits
        eventClick: function (info) { /* read-only for students */ },

        // Click/drag on empty slot → open unavailability panel
        selectable: true,
        selectMinDistance: 10,
        select: function (info) {
            const durationMin = Math.round((info.end - info.start) / 60000);
            const dateStr = info.startStr.split('T')[0];
            _openUnavailWithTime(dateStr, info.start.getHours(), info.start.getMinutes(), durationMin);
            calendar.unselect();
        },
        dateClick: function (info) {
            const dateStr = info.dateStr.split('T')[0];
            _openUnavailWithTime(dateStr, info.date.getHours(), info.date.getMinutes(), 90);
        },

        eventMouseEnter: function (info) { _showStudentTooltip(info.event, info.jsEvent); },
        eventMouseLeave: function () { _hideStudentTooltip(); },

        eventsSet: function (events) {
            const statsEl = document.getElementById('fc-week-stats');
            if (!statsEl) return;
            const view = calendar.view;
            const visible = events.filter(e => e.display !== 'background' && e.start >= view.activeStart && e.start < view.activeEnd);
            const totalMs = visible.reduce((s, e) => s + (e.end ? e.end - e.start : 3600000), 0);
            const h = Math.floor(totalMs / 3600000);
            const m = Math.floor((totalMs % 3600000) / 60000);
            statsEl.textContent = visible.length ? `${visible.length} zajęć · ${h}h${m > 0 ? ` ${m}min` : ''}` : '';
        },
    });

    calendar.render();
    window._calendar = calendar;

    calendarEl.addEventListener('contextmenu', function (e) {
        e.preventDefault();
        const slotEl = e.target.closest('.fc-timegrid-slot');
        const dataTime = slotEl ? slotEl.getAttribute('data-time') : '';
        const [h, m] = dataTime ? dataTime.slice(0, 5).split(':').map(Number) : [9, 0];
        const colEl = e.target.closest('[data-date]');
        const dateStr = colEl ? colEl.getAttribute('data-date') : new Date().toISOString().split('T')[0];
        _openUnavailWithTime(dateStr, h, m, 90);
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && typeof closeUnavailPanel === 'function') closeUnavailPanel();
    });
});

function _openUnavailWithTime(dateStr, hour, minute, durationMin) {
    openUnavailPanel();
    document.getElementById('up-start-date').value = dateStr;
    const rows = document.querySelectorAll('#up-slots > div');
    if (rows.length > 0) {
        const row = rows[0];
        const dow = (new Date(dateStr + 'T12:00:00').getDay() + 6) % 7;
        row.querySelector('.up-slot-day').value = dow;
        row.querySelector('.up-slot-time').value =
            String(hour).padStart(2, '0') + ':' + String(minute).padStart(2, '0');
        if (durationMin) row.querySelector('.up-slot-duration').value = Math.min(480, Math.max(15, durationMin));
    }
    upUpdatePreview();
}

// ─── Tooltip ─────────────────────────────────────────────────────────────────

function _showStudentTooltip(event, jsEvent) {
    let tip = document.getElementById('fc-tooltip');
    if (!tip) {
        tip = document.createElement('div');
        tip.id = 'fc-tooltip';
        tip.className = 'fixed z-[70] bg-gray-900 border border-gray-700 rounded-xl shadow-2xl px-4 py-3 text-sm pointer-events-none max-w-[240px]';
        document.body.appendChild(tip);
    }
    const status = event.extendedProps?.status;
    const statusPl = { scheduled: 'Zaplanowane', completed: 'Ukończone', cancelled: 'Odwołane' };
    const dotColor = status === 'completed' ? '#6b7280' : status === 'cancelled' ? '#ef4444' : '#22c55e';
    tip.innerHTML = `
        <p class="font-semibold text-white mb-1 leading-tight">${_h(event.title)}</p>
        ${status ? `<p class="text-xs text-gray-400 flex items-center gap-1.5">
            <span style="width:7px;height:7px;border-radius:50%;background:${dotColor};display:inline-block;flex-shrink:0"></span>
            ${_h(statusPl[status] || status)}</p>` : ''}
        ${event.extendedProps?.series_id ? '<p class="text-xs text-green-400 mt-1">↻ Zajęcia cykliczne</p>' : ''}
    `;
    tip.style.display = 'block';
    const x = jsEvent.clientX + 14;
    tip.style.left = (x + 240 > window.innerWidth ? x - 260 : x) + 'px';
    tip.style.top = Math.min(jsEvent.clientY - 10, window.innerHeight - 120) + 'px';
}

function _hideStudentTooltip() {
    const tip = document.getElementById('fc-tooltip');
    if (tip) tip.style.display = 'none';
}

// ─── Context menu for unavailability blocks ───────────────────────────────────

let _activeUnavailMenu = null;

function _showUnavailContextMenu(event, jsEvent) {
    if (_activeUnavailMenu) { _activeUnavailMenu.remove(); _activeUnavailMenu = null; }

    const seriesId = event.extendedProps?.series_id || event.id;
    // Background events from /api/availability don't carry series_id in extendedProps
    // We use event.id to identify the block, but we need the series_id from the block.
    // Since background events are FullCalendar background display, skip context menu for one-offs.
    if (!seriesId) return;

    const menu = document.createElement('div');
    menu.className = 'fixed z-50 bg-gray-900 border border-gray-700 rounded-xl shadow-2xl py-1 min-w-[220px] text-sm';
    menu.style.left = jsEvent.pageX + 'px';
    menu.style.top = jsEvent.pageY + 'px';

    const items = [
        {
            label: 'Usuń ten blok', danger: true,
            action: async () => {
                if (!confirm('Usuń ten blok niedostępności?')) return;
                // One-off delete — use block id from event.id
                const resp = await fetch(`/api/availability/${event.id}`, { method: 'DELETE', headers: { 'X-CSRF-Token': _csrf() } });
                if (resp.ok && window._calendar) window._calendar.refetchEvents();
            },
        },
    ];

    items.forEach(item => {
        const btn = document.createElement('button');
        btn.className = `w-full text-left px-4 py-2 transition-colors ${
            item.danger ? 'text-red-400 hover:bg-red-500/10' : 'text-gray-200 hover:bg-gray-800'
        }`;
        btn.textContent = item.label;
        btn.onclick = () => { menu.remove(); _activeUnavailMenu = null; item.action(); };
        menu.appendChild(btn);
    });

    document.body.appendChild(menu);
    _activeUnavailMenu = menu;

    requestAnimationFrame(() => {
        const rect = menu.getBoundingClientRect();
        if (rect.right > window.innerWidth) menu.style.left = (jsEvent.pageX - rect.width) + 'px';
        if (rect.bottom > window.innerHeight) menu.style.top = (jsEvent.pageY - rect.height) + 'px';
    });

    setTimeout(() => document.addEventListener('click', () => {
        if (_activeUnavailMenu) { _activeUnavailMenu.remove(); _activeUnavailMenu = null; }
    }, { once: true }), 0);
}
