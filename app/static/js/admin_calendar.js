/**
 * FullCalendar initialization for the Ekorepetycje admin panel.
 * Fetches events from GET /api/events and handles create/update/delete.
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
            right: 'dayGridMonth,timeGridWeek,timeGridDay',
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

        // Load events from the backend
        events: {
            url: '/api/events',
            method: 'GET',
            extraParams: {},
            failure: function () {
                console.error('Failed to load events from /api/events');
            },
        },

        // Transform backend event format to FullCalendar format
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
                },
                color: rawEvent.status === 'completed' ? '#4b5563' :
                       rawEvent.status === 'cancelled' ? '#ef4444' : '#22c55e',
            };
        },

        // Handle drag-and-drop reschedule
        eventDrop: async function (info) {
            try {
                const response = await fetch(`/api/events/${info.event.id}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        title: info.event.title,
                        start_time: info.event.start.toISOString(),
                        end_time: info.event.end.toISOString(),
                        offering_id: info.event.extendedProps.offering_id,
                        teacher_id: info.event.extendedProps.teacher_id,
                        student_id: info.event.extendedProps.student_id,
                        status: info.event.extendedProps.status,
                    }),
                });
                if (!response.ok) {
                    info.revert();
                    console.error('Failed to update event:', await response.text());
                }
            } catch (err) {
                info.revert();
                console.error('Network error updating event:', err);
            }
        },

        // Handle event resize
        eventResize: async function (info) {
            try {
                const response = await fetch(`/api/events/${info.event.id}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        title: info.event.title,
                        start_time: info.event.start.toISOString(),
                        end_time: info.event.end.toISOString(),
                        offering_id: info.event.extendedProps.offering_id,
                        teacher_id: info.event.extendedProps.teacher_id,
                        student_id: info.event.extendedProps.student_id,
                        status: info.event.extendedProps.status,
                    }),
                });
                if (!response.ok) {
                    info.revert();
                    console.error('Failed to resize event:', await response.text());
                }
            } catch (err) {
                info.revert();
                console.error('Network error resizing event:', err);
            }
        },

        // Handle click on existing event (show delete option)
        eventClick: async function (info) {
            if (confirm(`Usuń wydarzenie: "${info.event.title}"?`)) {
                try {
                    const response = await fetch(`/api/events/${info.event.id}`, {
                        method: 'DELETE',
                    });
                    if (response.ok) {
                        info.event.remove();
                    } else {
                        console.error('Failed to delete event:', await response.text());
                    }
                } catch (err) {
                    console.error('Network error deleting event:', err);
                }
            }
        },

        // Handle date range selection (create new event)
        select: function (info) {
            // MVP: creating events requires selecting a teacher and offering.
            // This interaction is not yet implemented via the calendar UI.
            // Use the admin dashboard form to create offerings first.
            calendar.unselect();
        },
    });

    calendar.render();
});
