/**
 * Shared series panel logic — used by both admin and teacher calendars.
 *
 * Depends on:
 *   - #series-panel element (from series_panel.html component)
 *   - window._calendar  (FullCalendar instance, set by calendar init code)
 *   - window._seriesPanelMode: 'create' | 'edit'
 *   - window._editSeriesId, window._editFromEventId (for edit mode)
 */

const DAY_NAMES = ['Pon', 'Wt', 'Śr', 'Czw', 'Pt', 'Sob', 'Nd'];
let _currentIntervalWeeks = 1;
let _offerings = [];
let _teachers = [];
let _students = [];

/** Escape HTML special chars — prevents XSS when injecting user data into innerHTML. */
function _h(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/** Read CSRF token from <meta name="csrf-token"> (injected by base.html). */
function _csrf() {
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
}

// ─── Panel open/close ──────────────────────────────────────────────────────

function openSeriesPanel() {
    const panel = document.getElementById('series-panel');
    const backdrop = document.getElementById('series-backdrop');
    panel.classList.remove('translate-x-full');
    backdrop.classList.remove('hidden');
    document.getElementById('series-panel-title').textContent = 'Nowa seria zajęć';
    document.getElementById('sp-submit-btn').textContent = 'Utwórz serię';
    window._seriesPanelMode = 'create';
    document.getElementById('sp-slots').innerHTML = '';
    _spInitDropdowns();
    spAddSlot(); // add one default slot
    spUpdatePreview();
}

function openSeriesPanelEdit(seriesId, fromEventId) {
    window._seriesPanelMode = 'edit';
    window._editSeriesId = seriesId;
    window._editFromEventId = fromEventId;

    const panel = document.getElementById('series-panel');
    const backdrop = document.getElementById('series-backdrop');
    panel.classList.remove('translate-x-full');
    backdrop.classList.remove('hidden');
    document.getElementById('series-panel-title').textContent = 'Edytuj serię od tej lekcji';

    // Clear existing slots before loading data
    document.getElementById('sp-slots').innerHTML = '';
    document.getElementById('sp-submit-btn').textContent = 'Zapisz zmiany';

    // Load existing series data and pre-fill
    fetch(`/api/series/${seriesId}`)
        .then(r => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            return r.json();
        })
        .then(data => {
            _spInitDropdowns(data);
        })
        .catch(err => {
            const errEl = document.getElementById('sp-error');
            document.getElementById('sp-error-text').textContent = `Nie można załadować serii: ${err.message}`;
            errEl.classList.remove('hidden');
        });
}

/** Open series panel pre-filled with a specific date/time (from calendar drag or click). */
function openSeriesPanelWithTime(dateStr, hour, minute, durationMinutes) {
    openSeriesPanel();
    document.getElementById('sp-start-date').value = dateStr;
    const rows = document.querySelectorAll('#sp-slots > div');
    if (rows.length > 0) {
        const row = rows[0];
        // Map JS day (0=Sun) to our convention (0=Mon)
        const dow = (new Date(dateStr + 'T12:00:00').getDay() + 6) % 7;
        row.querySelector('.sp-slot-day').value = dow;
        row.querySelector('.sp-slot-time').value =
            String(hour).padStart(2, '0') + ':' + String(minute).padStart(2, '0');
        if (durationMinutes) row.querySelector('.sp-slot-duration').value = Math.min(480, Math.max(15, durationMinutes));
    }
    spUpdatePreview();
}

function closeSeriesPanel() {
    const panel = document.getElementById('series-panel');
    const backdrop = document.getElementById('series-backdrop');
    panel.classList.add('translate-x-full');
    backdrop.classList.add('hidden');
    // Clear slots
    document.getElementById('sp-slots').innerHTML = '';
    document.getElementById('sp-error').classList.add('hidden');
}

// ─── Dropdown population ────────────────────────────────────────────────────

async function _spInitDropdowns(prefill = null) {
    const panel = document.getElementById('series-panel');
    const isAdmin = panel.dataset.isAdmin === 'true';

    // Teachers (admin only)
    if (isAdmin) {
        document.getElementById('teacher-field').classList.remove('hidden');
        if (_teachers.length === 0) {
            const res = await fetch('/api/teachers');
            _teachers = await res.json();
        }
        const sel = document.getElementById('sp-teacher');
        sel.onchange = spOnTeacherChange;
        sel.innerHTML = '<option value="">Wybierz nauczyciela...</option>' +
            _teachers.map(t => `<option value="${_h(t.id)}">${_h(t.full_name)}</option>`).join('');
        if (prefill) sel.value = prefill.teacher_id;
    }

    // Students
    if (_students.length === 0) {
        const res = await fetch('/api/students');
        _students = await res.json();
    }
    const stuSel = document.getElementById('sp-student');
    stuSel.innerHTML = '<option value="">Brak / przypisz później</option>' +
        _students.map(s => `<option value="${_h(s.id)}">${_h(s.full_name)}</option>`).join('');
    if (prefill && prefill.student_id) stuSel.value = prefill.student_id;

    // Offerings — scoped to teacher
    const effectiveTeacherId = isAdmin
        ? document.getElementById('sp-teacher').value
        : panel.dataset.userId;
    await _loadOfferings(effectiveTeacherId);
    const offSel = document.getElementById('sp-offering');
    if (prefill) {
        offSel.value = prefill.offering_id;
        document.getElementById('sp-title').value = prefill.title;
        document.getElementById('sp-start-date').value = prefill.start_date;
        spSetInterval(prefill.interval_weeks);

        // Slots
        document.getElementById('sp-slots').innerHTML = '';
        prefill.day_slots.forEach(slot => spAddSlot(slot));

        // End condition
        if (prefill.end_count) {
            document.querySelector('input[name="sp-end-type"][value="count"]').checked = true;
            document.getElementById('sp-end-count').value = prefill.end_count;
            document.getElementById('sp-end-count').disabled = false;
            document.getElementById('sp-end-date').disabled = true;
        } else if (prefill.end_date) {
            document.querySelector('input[name="sp-end-type"][value="date"]').checked = true;
            document.getElementById('sp-end-date').value = prefill.end_date;
            document.getElementById('sp-end-date').disabled = false;
            document.getElementById('sp-end-count').disabled = true;
        }
    }
    spUpdatePreview();
}

// ─── Offerings loader ────────────────────────────────────────────────────────

async function _loadOfferings(teacherId) {
    const url = teacherId ? `/api/offerings?teacher_id=${encodeURIComponent(teacherId)}` : '/api/offerings';
    const res = await fetch(url);
    _offerings = await res.json();
    const offSel = document.getElementById('sp-offering');
    offSel.innerHTML = '<option value="">Wybierz ofertę...</option>' +
        _offerings.map(o => `<option value="${_h(o.id)}">${_h(o.title)}</option>`).join('');
}

async function spOnTeacherChange() {
    const teacherId = document.getElementById('sp-teacher').value;
    _offerings = [];
    await _loadOfferings(teacherId);
    document.getElementById('sp-offering').value = '';
    document.getElementById('sp-title').value = '';
}

// ─── Interval selector ──────────────────────────────────────────────────────

function spSetInterval(weeks) {
    _currentIntervalWeeks = weeks;
    document.querySelectorAll('.sp-interval-btn').forEach(btn => {
        const btnInterval = parseInt(btn.dataset.interval);
        const active = (btnInterval === weeks) || (btnInterval === 0 && weeks > 2);
        btn.classList.toggle('border-green-500', active);
        btn.classList.toggle('text-green-400', active);
        btn.classList.toggle('border-gray-700', !active);
        btn.classList.toggle('text-gray-300', !active);
    });
    const custom = document.getElementById('sp-custom-interval');
    if (weeks === 0 || weeks > 2) {
        custom.classList.remove('hidden');
        if (weeks > 2) document.getElementById('sp-interval-value').value = weeks;
    } else {
        custom.classList.add('hidden');
    }
    spUpdatePreview();
}

// ─── Day slots ──────────────────────────────────────────────────────────────

function spAddSlot(prefill = null) {
    const container = document.getElementById('sp-slots');
    const slot = document.createElement('div');
    slot.className = 'flex items-center gap-2 bg-gray-900 border border-gray-800 rounded-xl px-3 py-2';
    slot.innerHTML = `
        <select class="sp-slot-day bg-gray-800 border border-gray-700 text-white text-sm px-2 py-1 rounded-lg focus:outline-none focus:ring-1 focus:ring-green-500 cursor-pointer" onchange="spUpdatePreview()">
            ${DAY_NAMES.map((n, i) => `<option value="${i}"${prefill && prefill.day === i ? ' selected' : ''}>${n}</option>`).join('')}
        </select>
        <input type="time" class="sp-slot-time bg-gray-800 border border-gray-700 text-white text-sm px-2 py-1 rounded-lg focus:outline-none focus:ring-1 focus:ring-green-500 w-28"
               value="${prefill ? String(prefill.hour).padStart(2,'0') + ':' + String(prefill.minute).padStart(2,'0') : '17:00'}"
               onchange="spUpdatePreview()">
        <input type="number" class="sp-slot-duration bg-gray-800 border border-gray-700 text-white text-sm px-2 py-1 rounded-lg w-20 focus:outline-none focus:ring-1 focus:ring-green-500"
               value="${prefill ? prefill.duration_minutes : 60}" min="15" max="480" placeholder="min"
               onchange="spUpdatePreview()">
        <span class="text-xs text-gray-500">min</span>
        <button type="button" onclick="this.parentElement.remove(); spUpdatePreview()"
                class="ml-auto text-gray-600 hover:text-red-400 transition-colors text-lg leading-none">&times;</button>
    `;
    container.appendChild(slot);
    spUpdatePreview();
}

// ─── End condition toggle ────────────────────────────────────────────────────

function spToggleEnd() {
    const type = document.querySelector('input[name="sp-end-type"]:checked').value;
    document.getElementById('sp-end-count').disabled = type !== 'count';
    document.getElementById('sp-end-date').disabled = type !== 'date';
    spUpdatePreview();
}

// ─── Live preview ────────────────────────────────────────────────────────────

function spUpdatePreview() {
    const slots = document.querySelectorAll('#sp-slots > div').length;
    if (slots === 0) {
        document.getElementById('sp-preview-count').textContent = '—';
        return;
    }

    const endType = document.querySelector('input[name="sp-end-type"]:checked')?.value;
    let count = '—';

    if (endType === 'count') {
        const n = parseInt(document.getElementById('sp-end-count').value) || 0;
        count = n;
    } else if (endType === 'date') {
        const startVal = document.getElementById('sp-start-date').value;
        const endVal = document.getElementById('sp-end-date').value;
        const weeks = _getIntervalWeeks();
        if (startVal && endVal && weeks > 0) {
            const start = new Date(startVal);
            const end = new Date(endVal);
            const diffMs = end - start;
            if (diffMs >= 0) {
                const diffWeeks = Math.floor(diffMs / (7 * 24 * 3600 * 1000));
                const iterations = Math.floor(diffWeeks / weeks) + 1;
                count = iterations * slots;
            }
        }
    }
    document.getElementById('sp-preview-count').textContent = count;
}

function _getIntervalWeeks() {
    if (_currentIntervalWeeks > 0 && _currentIntervalWeeks <= 2) return _currentIntervalWeeks;
    return parseInt(document.getElementById('sp-interval-value')?.value) || 1;
}

// ─── Auto-fill title from offering ──────────────────────────────────────────

function spAutoFillTitle() {
    const offId = document.getElementById('sp-offering').value;
    const off = _offerings.find(o => o.id === offId);
    if (off) document.getElementById('sp-title').value = off.title;
}

// ─── Build payload ───────────────────────────────────────────────────────────

function _buildPayload() {
    const panel = document.getElementById('series-panel');
    const isAdmin = panel.dataset.isAdmin === 'true';
    const userId = panel.dataset.userId;

    const teacherId = isAdmin
        ? document.getElementById('sp-teacher').value
        : userId;
    const studentId = document.getElementById('sp-student').value || null;
    const offeringId = document.getElementById('sp-offering').value;
    const title = document.getElementById('sp-title').value.trim();
    const startDate = document.getElementById('sp-start-date').value;
    const intervalWeeks = _getIntervalWeeks();

    const slots = Array.from(document.querySelectorAll('#sp-slots > div')).map(row => {
        const [h, m] = row.querySelector('.sp-slot-time').value.split(':').map(Number);
        return {
            day: parseInt(row.querySelector('.sp-slot-day').value),
            hour: h,
            minute: m,
            duration_minutes: parseInt(row.querySelector('.sp-slot-duration').value),
        };
    });

    const endType = document.querySelector('input[name="sp-end-type"]:checked').value;
    const endCount = endType === 'count' ? parseInt(document.getElementById('sp-end-count').value) : null;
    const endDate = endType === 'date' ? document.getElementById('sp-end-date').value : null;

    return {
        teacher_id: teacherId,
        student_id: studentId,
        offering_id: offeringId,
        title,
        start_date: startDate,
        interval_weeks: intervalWeeks,
        day_slots: slots,
        end_date: endDate,
        end_count: endCount,
    };
}

// ─── Submit ──────────────────────────────────────────────────────────────────

async function spSubmit() {
    const payload = _buildPayload();
    const errEl = document.getElementById('sp-error');
    const errText = document.getElementById('sp-error-text');
    errEl.classList.add('hidden');

    let url = '/api/series';
    let method = 'POST';

    if (window._seriesPanelMode === 'edit') {
        url = `/api/series/${window._editSeriesId}/from/${window._editFromEventId}`;
        method = 'PATCH';
    }

    try {
        const resp = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': _csrf() },
            body: JSON.stringify(payload),
        });

        if (resp.ok) {
            const data = await resp.json();
            closeSeriesPanel();
            if (window._calendar) window._calendar.refetchEvents();
            if (data.conflicts && data.conflicts.length > 0) {
                const byPerson = { teacher: 0, student: 0 };
                data.conflicts.forEach(c => { byPerson[c.person] = (byPerson[c.person] || 0) + 1; });
                const parts = [];
                if (byPerson.teacher) parts.push(`${byPerson.teacher} kolizji z niedostępnością nauczyciela`);
                if (byPerson.student) parts.push(`${byPerson.student} kolizji z niedostępnością ucznia`);
                alert(`Seria utworzona, ale wykryto: ${parts.join(', ')}. Sprawdź kalendarz.`);
            }
        } else {
            const data = await resp.json();
            errText.textContent = data.detail || 'Błąd podczas zapisywania serii.';
            errEl.classList.remove('hidden');
        }
    } catch (err) {
        errText.textContent = 'Błąd sieci. Sprawdź połączenie.';
        errEl.classList.remove('hidden');
    }
}
