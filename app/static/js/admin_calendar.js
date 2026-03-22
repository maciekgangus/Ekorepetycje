/**
 * FullCalendar initialization for the Ekorepetycje admin panel.
 * Fetches events from GET /api/events and handles CRUD + series context menu.
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

        eventClick: function (info) {
            _showContextMenu(info.event, info.jsEvent);
        },

        select: function () { calendar.unselect(); },
    });

    calendar.render();
    window._calendar = calendar;
});

// ─── PATCH single event (drag/resize) ───────────────────────────────────────

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

// ─── Context menu ────────────────────────────────────────────────────────────

let _activeMenu = null;

function _showContextMenu(event, jsEvent) {
    _closeContextMenu();

    const seriesId = event.extendedProps.series_id;
    const isSeries = !!seriesId;

    const menu = document.createElement('div');
    menu.id = 'fc-context-menu';
    menu.className = 'fixed z-50 bg-gray-900 border border-gray-700 rounded-xl shadow-2xl py-1 min-w-[220px] text-sm';
    menu.style.left = jsEvent.pageX + 'px';
    menu.style.top = jsEvent.pageY + 'px';

    const items = [];

    if (isSeries) {
        items.push({
            label: 'Edytuj tę lekcję',
            action: () => _editSingleEvent(event),
        });
        items.push({
            label: 'Edytuj tę i następne',
            action: () => openSeriesPanelEdit(seriesId, event.id),
        });
        items.push({ divider: true });
        items.push({
            label: 'Usuń tę lekcję',
            danger: true,
            action: async () => {
                if (!confirm(`Usuń lekcję "${event.title}"?`)) return;
                const resp = await fetch(`/api/events/${event.id}`, { method: 'DELETE' });
                if (resp.ok) event.remove();
            },
        });
        items.push({
            label: 'Usuń tę i następne',
            danger: true,
            action: async () => {
                if (!confirm(`Usuń tę i wszystkie następne lekcje z serii "${event.title}"?`)) return;
                const resp = await fetch(`/api/series/${seriesId}/from/${event.id}`, { method: 'DELETE' });
                if (resp.ok && window._calendar) window._calendar.refetchEvents();
            },
        });
    } else {
        items.push({
            label: 'Edytuj',
            action: () => _editSingleEvent(event),
        });
        items.push({ divider: true });
        items.push({
            label: 'Usuń',
            danger: true,
            action: async () => {
                if (!confirm(`Usuń lekcję "${event.title}"?`)) return;
                const resp = await fetch(`/api/events/${event.id}`, { method: 'DELETE' });
                if (resp.ok) event.remove();
            },
        });
    }

    items.forEach(item => {
        if (item.divider) {
            const hr = document.createElement('div');
            hr.className = 'border-t border-gray-800 my-1';
            menu.appendChild(hr);
            return;
        }
        const btn = document.createElement('button');
        btn.className = `w-full text-left px-4 py-2 transition-colors ${
            item.danger
                ? 'text-red-400 hover:bg-red-500/10'
                : 'text-gray-200 hover:bg-gray-800'
        }`;
        btn.textContent = item.label;
        btn.onclick = () => { _closeContextMenu(); item.action(); };
        menu.appendChild(btn);
    });

    document.body.appendChild(menu);
    _activeMenu = menu;

    // Adjust position if off-screen
    requestAnimationFrame(() => {
        const rect = menu.getBoundingClientRect();
        if (rect.right > window.innerWidth) {
            menu.style.left = (jsEvent.pageX - rect.width) + 'px';
        }
        if (rect.bottom > window.innerHeight) {
            menu.style.top = (jsEvent.pageY - rect.height) + 'px';
        }
    });

    setTimeout(() => document.addEventListener('click', _closeContextMenu, { once: true }), 0);
}

function _closeContextMenu() {
    if (_activeMenu) { _activeMenu.remove(); _activeMenu = null; }
}

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
