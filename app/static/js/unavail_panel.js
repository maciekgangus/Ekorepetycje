/**
 * Shared unavailability panel logic — used by teacher and student calendars.
 *
 * Mirrors series_panel.js but for UnavailableBlock / RecurringUnavailSeries.
 * Prefix: "up-" (element IDs) and "up" (JS functions).
 */

const UP_DAY_NAMES = ['Pon', 'Wt', 'Śr', 'Czw', 'Pt', 'Sob', 'Nd'];
let _upIntervalWeeks = 1;

/** Read CSRF token from <meta name="csrf-token"> (injected by base.html). */
function _upCsrf() {
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
}

// ─── Panel open/close ────────────────────────────────────────────────────────

function openUnavailPanel() {
    const panel = document.getElementById('unavail-panel');
    panel.classList.remove('translate-x-full');
    document.getElementById('unavail-backdrop').classList.remove('hidden');
    document.getElementById('unavail-panel-title').textContent = 'Nowa seria niedostępności';
    document.getElementById('up-submit-btn').textContent = 'Utwórz serię niedostępności';
    document.getElementById('up-slots').innerHTML = '';
    window._upMode = 'create';
    _upSetInterval(1);
    upAddSlot();
    upUpdatePreview();
}

function openUnavailPanelEdit(seriesId, fromBlockId) {
    window._upMode = 'edit';
    window._upEditSeriesId = seriesId;
    window._upEditFromBlockId = fromBlockId;

    const panel = document.getElementById('unavail-panel');
    panel.classList.remove('translate-x-full');
    document.getElementById('unavail-backdrop').classList.remove('hidden');
    document.getElementById('unavail-panel-title').textContent = 'Edytuj niedostępność od tego bloku';
    document.getElementById('up-submit-btn').textContent = 'Zapisz zmiany';
    document.getElementById('up-slots').innerHTML = '';

    fetch(`/api/unavailability-series/${seriesId}`)
        .then(r => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            return r.json();
        })
        .then(data => _upPrefill(data))
        .catch(err => {
            const errEl = document.getElementById('up-error');
            document.getElementById('up-error-text').textContent = `Nie można załadować serii: ${err.message}`;
            errEl.classList.remove('hidden');
        });
}

function closeUnavailPanel() {
    document.getElementById('unavail-panel').classList.add('translate-x-full');
    document.getElementById('unavail-backdrop').classList.add('hidden');
    document.getElementById('up-slots').innerHTML = '';
    document.getElementById('up-error').classList.add('hidden');
}

// ─── Pre-fill for edit mode ──────────────────────────────────────────────────

function _upPrefill(data) {
    document.getElementById('up-note').value = data.note || '';
    document.getElementById('up-start-date').value = data.start_date;
    _upSetInterval(data.interval_weeks);

    document.getElementById('up-slots').innerHTML = '';
    data.day_slots.forEach(slot => upAddSlot(slot));

    if (data.end_count) {
        document.querySelector('input[name="up-end-type"][value="count"]').checked = true;
        document.getElementById('up-end-count').value = data.end_count;
        document.getElementById('up-end-count').disabled = false;
        document.getElementById('up-end-date').disabled = true;
    } else if (data.end_date) {
        document.querySelector('input[name="up-end-type"][value="date"]').checked = true;
        document.getElementById('up-end-date').value = data.end_date;
        document.getElementById('up-end-date').disabled = false;
        document.getElementById('up-end-count').disabled = true;
    }
    upUpdatePreview();
}

// ─── Interval selector ───────────────────────────────────────────────────────

function _upSetInterval(weeks) {
    _upIntervalWeeks = weeks;
    document.querySelectorAll('.up-interval-btn').forEach(btn => {
        const v = parseInt(btn.dataset.interval);
        const active = (v === weeks) || (v === 0 && weeks > 2);
        btn.classList.toggle('border-green-500', active);
        btn.classList.toggle('text-green-400', active);
        btn.classList.toggle('border-gray-700', !active);
        btn.classList.toggle('text-gray-300', !active);
    });
    const custom = document.getElementById('up-custom-interval');
    if (weeks === 0 || weeks > 2) {
        custom.classList.remove('hidden');
        if (weeks > 2) document.getElementById('up-interval-value').value = weeks;
    } else {
        custom.classList.add('hidden');
    }
    upUpdatePreview();
}

// Public wrapper so HTML onclick can call upSetInterval()
function upSetInterval(weeks) { _upSetInterval(weeks); }

// ─── Time slots ──────────────────────────────────────────────────────────────

function upAddSlot(prefill = null) {
    const container = document.getElementById('up-slots');
    const slot = document.createElement('div');
    slot.className = 'flex items-center gap-2 bg-gray-900 border border-gray-800 rounded-xl px-3 py-2';
    slot.innerHTML = `
        <select class="up-slot-day bg-gray-800 border border-gray-700 text-white text-sm px-2 py-1 rounded-lg focus:outline-none focus:ring-1 focus:ring-green-500 cursor-pointer" onchange="upUpdatePreview()">
            ${UP_DAY_NAMES.map((n, i) => `<option value="${i}"${prefill && prefill.day === i ? ' selected' : ''}>${n}</option>`).join('')}
        </select>
        <input type="time" class="up-slot-time bg-gray-800 border border-gray-700 text-white text-sm px-2 py-1 rounded-lg focus:outline-none focus:ring-1 focus:ring-green-500 w-28"
               value="${prefill ? String(prefill.hour).padStart(2,'0') + ':' + String(prefill.minute).padStart(2,'0') : '08:00'}"
               onchange="upUpdatePreview()">
        <input type="number" class="up-slot-duration bg-gray-800 border border-gray-700 text-white text-sm px-2 py-1 rounded-lg w-20 focus:outline-none focus:ring-1 focus:ring-green-500"
               value="${prefill ? prefill.duration_minutes : 90}" min="15" max="480"
               onchange="upUpdatePreview()">
        <span class="text-xs text-gray-500">min</span>
        <button type="button" onclick="this.parentElement.remove(); upUpdatePreview()"
                class="ml-auto text-gray-600 hover:text-red-400 transition-colors text-lg leading-none">&times;</button>
    `;
    container.appendChild(slot);
    upUpdatePreview();
}

// ─── End condition toggle ────────────────────────────────────────────────────

function upToggleEnd() {
    const type = document.querySelector('input[name="up-end-type"]:checked').value;
    document.getElementById('up-end-count').disabled = type !== 'count';
    document.getElementById('up-end-date').disabled = type !== 'date';
    upUpdatePreview();
}

// ─── Live preview ─────────────────────────────────────────────────────────────

function upUpdatePreview() {
    const slots = document.querySelectorAll('#up-slots > div').length;
    if (slots === 0) {
        document.getElementById('up-preview-count').textContent = '—';
        return;
    }

    const endType = document.querySelector('input[name="up-end-type"]:checked')?.value;
    let count = '—';

    if (endType === 'count') {
        count = parseInt(document.getElementById('up-end-count').value) || 0;
    } else if (endType === 'date') {
        const startVal = document.getElementById('up-start-date').value;
        const endVal = document.getElementById('up-end-date').value;
        const weeks = _upGetIntervalWeeks();
        if (startVal && endVal && weeks > 0) {
            const diffMs = new Date(endVal) - new Date(startVal);
            if (diffMs >= 0) {
                const iterations = Math.floor(Math.floor(diffMs / (7 * 24 * 3600 * 1000)) / weeks) + 1;
                count = iterations * slots;
            }
        }
    }
    document.getElementById('up-preview-count').textContent = count;
}

function _upGetIntervalWeeks() {
    if (_upIntervalWeeks > 0 && _upIntervalWeeks <= 2) return _upIntervalWeeks;
    return parseInt(document.getElementById('up-interval-value')?.value) || 1;
}

// ─── Build payload ────────────────────────────────────────────────────────────

function _upBuildPayload() {
    const panel = document.getElementById('unavail-panel');
    const userId = panel.dataset.userId;
    const note = document.getElementById('up-note').value.trim() || null;
    const startDate = document.getElementById('up-start-date').value;
    const intervalWeeks = _upGetIntervalWeeks();

    const slots = Array.from(document.querySelectorAll('#up-slots > div')).map(row => {
        const [h, m] = row.querySelector('.up-slot-time').value.split(':').map(Number);
        return {
            day: parseInt(row.querySelector('.up-slot-day').value),
            hour: h,
            minute: m,
            duration_minutes: parseInt(row.querySelector('.up-slot-duration').value),
        };
    });

    const endType = document.querySelector('input[name="up-end-type"]:checked').value;
    const endCount = endType === 'count' ? parseInt(document.getElementById('up-end-count').value) : null;
    const endDate = endType === 'date' ? document.getElementById('up-end-date').value : null;

    return { user_id: userId, note, start_date: startDate, interval_weeks: intervalWeeks, day_slots: slots, end_date: endDate, end_count: endCount };
}

// ─── Submit ───────────────────────────────────────────────────────────────────

async function upSubmit() {
    const payload = _upBuildPayload();
    const errEl = document.getElementById('up-error');
    const errText = document.getElementById('up-error-text');
    errEl.classList.add('hidden');

    let url = '/api/unavailability-series';
    let method = 'POST';

    if (window._upMode === 'edit') {
        url = `/api/unavailability-series/${window._upEditSeriesId}/from/${window._upEditFromBlockId}`;
        method = 'PATCH';
    }

    try {
        const resp = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': _upCsrf() },
            body: JSON.stringify(payload),
        });

        if (resp.ok) {
            closeUnavailPanel();
            if (window._calendar) window._calendar.refetchEvents();
        } else {
            const data = await resp.json();
            errText.textContent = data.detail || 'Błąd podczas zapisywania.';
            errEl.classList.remove('hidden');
        }
    } catch {
        errText.textContent = 'Błąd sieci. Sprawdź połączenie.';
        errEl.classList.remove('hidden');
    }
}
