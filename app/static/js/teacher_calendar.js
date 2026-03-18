/**
 * FullCalendar initialization for the teacher calendar view.
 * Teacher ID is injected from the template as window.TEACHER_ID.
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
        editable: false,  // teachers don't drag-drop; they use proposals
        selectable: false,

        eventSources: [
            {
                url: `/api/events?teacher_id=${window.TEACHER_ID}`,
                failure: function () { console.error('Failed to load events'); },
            },
            {
                url: `/api/availability/${window.TEACHER_ID}`,
                display: 'background',
                color: '#6b7280',
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

        eventClick: function (info) {
            _showTeacherContextMenu(info.event, info.jsEvent);
        },
    });

    calendar.render();
    window._calendar = calendar;
});

// ─── Context menu (teacher-scoped) ───────────────────────────────────────────

let _activeMenu = null;

function _showTeacherContextMenu(event, jsEvent) {
    if (_activeMenu) { _activeMenu.remove(); _activeMenu = null; }

    const seriesId = event.extendedProps.series_id;
    const menu = document.createElement('div');
    menu.className = 'fixed z-50 bg-gray-900 border border-gray-700 rounded-xl shadow-2xl py-1 min-w-[220px] text-sm';
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
        btn.onclick = () => { menu.remove(); _activeMenu = null; item.action(); };
        menu.appendChild(btn);
    });

    document.body.appendChild(menu);
    _activeMenu = menu;

    // Adjust off-screen
    requestAnimationFrame(() => {
        const rect = menu.getBoundingClientRect();
        if (rect.right > window.innerWidth) {
            menu.style.left = (jsEvent.pageX - rect.width) + 'px';
        }
        if (rect.bottom > window.innerHeight) {
            menu.style.top = (jsEvent.pageY - rect.height) + 'px';
        }
    });

    setTimeout(() => document.addEventListener('click', () => {
        if (_activeMenu) { _activeMenu.remove(); _activeMenu = null; }
    }, { once: true }), 0);
}
