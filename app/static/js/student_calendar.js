/**
 * FullCalendar initialization for the student calendar view.
 * window.USER_ID is injected from the template.
 */
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

        // Students can click to see unavailability series context menu on background blocks
        eventClick: function (info) {
            if (info.event.display === 'background') {
                _showUnavailContextMenu(info.event, info.jsEvent);
            }
        },
    });

    calendar.render();
    window._calendar = calendar;
});

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
                const resp = await fetch(`/api/availability/${event.id}`, { method: 'DELETE' });
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
