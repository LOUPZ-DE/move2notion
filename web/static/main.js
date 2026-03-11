/**
 * Allgemeine JavaScript-Funktionen für die Web-GUI
 */

// Utility-Funktion: API-Anfragen mit Fehlerbehandlung
async function apiRequest(url, options = {}) {
    try {
        const response = await fetch(url, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || `HTTP ${response.status}: ${response.statusText}`);
        }

        return data;
    } catch (error) {
        console.error('API Request failed:', error);
        throw error;
    }
}

// Fortschrittsbalken aktualisieren
function updateProgress(percentage, text) {
    var progressBar = document.querySelector('.progress-fill');
    var statusText = document.querySelector('.status-text');

    if (progressBar) {
        progressBar.style.width = percentage + '%';
        progressBar.textContent = Math.round(percentage) + '%';
    }

    if (statusText && text) {
        statusText.textContent = text;
    }
}

// Log-Ausgabe hinzufügen
function addLogEntry(message, type) {
    var logOutput = document.querySelector('.log-output');
    if (!logOutput) return;

    type = type || 'info';
    var timestamp = new Date().toLocaleTimeString('de-DE');
    var colorMap = {
        'info': '#569cd6',
        'success': '#4ec9b0',
        'warning': '#dcdcaa',
        'error': '#f48771'
    };

    var color = colorMap[type] || '#d4d4d4';
    var logEntry = document.createElement('div');
    logEntry.innerHTML = '<span style="color: #808080;">[' + timestamp + ']</span> <span style="color: ' + color + ';">' + escapeHtmlMain(message) + '</span>';

    logOutput.appendChild(logEntry);
    logOutput.scrollTop = logOutput.scrollHeight;
}

// Toast-Benachrichtigung anzeigen
function showToast(message, type) {
    type = type || 'info';
    var toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    toast.textContent = message;

    var bg = type === 'error' ? '#f44336' : type === 'success' ? '#00c853' : '#0066ff';
    toast.style.cssText = 'position:fixed;bottom:20px;right:20px;background:' + bg + ';color:white;padding:16px 24px;border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,0.2);z-index:1000;animation:slideIn 0.3s ease;max-width:400px;';

    document.body.appendChild(toast);

    setTimeout(function() {
        toast.style.animation = 'slideOut 0.3s ease';
        setTimeout(function() { toast.remove(); }, 300);
    }, 4000);
}

function escapeHtmlMain(text) {
    var div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}

// ===== SSE Migration Client =====

function SSEMigrationClient(options) {
    this.progressBar = document.querySelector(options.progressBarSelector);
    this.statusText = document.querySelector(options.statusTextSelector);
    this.logOutput = document.querySelector(options.logOutputSelector);
    this.phaseLabel = document.querySelector(options.phaseSelector);
    this.summaryDiv = document.querySelector(options.summarySelector);
    this.onComplete = options.onComplete || function() {};
    this.eventSource = null;
}

SSEMigrationClient.prototype.start = function(taskId) {
    var self = this;
    this.eventSource = new EventSource('/api/tasks/' + taskId + '/events');

    this.eventSource.onmessage = function(event) {
        var data = JSON.parse(event.data);

        if (data.type === 'progress') {
            self._updateProgress(data.progress, data.message);
            self._addLogEntry(data.message, data.log_type);
            if (data.phase) {
                self._updatePhase(data.phase);
            }
        } else if (data.type === 'complete') {
            var isSuccess = data.status === 'completed';
            self._updateProgress(100, 'Migration abgeschlossen');
            self._updatePhase(isSuccess ? 'Abgeschlossen' : 'Fehlgeschlagen');
            // Phase-Badge Farbe setzen
            if (self.phaseLabel) {
                self.phaseLabel.classList.add(isSuccess ? 'phase-done' : 'phase-error');
            }
            self._showSummary(data);
            self.eventSource.close();
            self.onComplete(data);
        }
    };

    this.eventSource.onerror = function() {
        if (self.eventSource.readyState === EventSource.CLOSED) {
            return;
        }
        self._addLogEntry('Verbindung unterbrochen, versuche erneut...', 'warning');
    };
};

SSEMigrationClient.prototype.stop = function() {
    if (this.eventSource) {
        this.eventSource.close();
    }
};

SSEMigrationClient.prototype._updateProgress = function(percentage, text) {
    if (this.progressBar) {
        this.progressBar.style.width = percentage + '%';
        this.progressBar.textContent = Math.round(percentage) + '%';
        // Streifen-Animation bei 100% stoppen
        if (percentage >= 100) {
            this.progressBar.classList.add('progress-complete');
        }
    }
    if (this.statusText && text) {
        this.statusText.textContent = text;
    }
};

SSEMigrationClient.prototype._addLogEntry = function(message, type) {
    if (!this.logOutput) return;
    type = type || 'info';
    var timestamp = new Date().toLocaleTimeString('de-DE');
    var colorMap = {
        'info': '#569cd6',
        'success': '#4ec9b0',
        'warning': '#dcdcaa',
        'error': '#f48771'
    };
    var color = colorMap[type] || '#d4d4d4';
    var entry = document.createElement('div');
    entry.innerHTML = '<span style="color: #808080;">[' + timestamp + ']</span> <span style="color: ' + color + ';">' + escapeHtmlMain(message) + '</span>';
    this.logOutput.appendChild(entry);
    this.logOutput.scrollTop = this.logOutput.scrollHeight;
};

SSEMigrationClient.prototype._updatePhase = function(phase) {
    if (this.phaseLabel) {
        this.phaseLabel.textContent = phase;
    }
};

SSEMigrationClient.prototype._showSummary = function(data) {
    var isSuccess = data.status === 'completed';
    var msg = isSuccess
        ? 'Migration erfolgreich: ' + data.success_count + ' erstellt, ' + data.error_count + ' Fehler'
        : 'Migration fehlgeschlagen: ' + data.success_count + ' erstellt, ' + data.error_count + ' Fehler';

    this._addLogEntry(msg, isSuccess ? 'success' : 'error');
    showToast(msg, isSuccess ? 'success' : 'error');

    // Summary-Box anzeigen
    if (this.summaryDiv) {
        this.summaryDiv.classList.remove('hidden');
        this.summaryDiv.innerHTML =
            '<h4>' + (isSuccess ? 'Migration abgeschlossen' : 'Migration fehlgeschlagen') + '</h4>' +
            '<div class="summary-stats">' +
                '<div class="summary-stat stat-success">' +
                    '<div class="stat-value">' + data.success_count + '</div>' +
                    '<div class="stat-label">Erfolgreich</div>' +
                '</div>' +
                '<div class="summary-stat stat-error">' +
                    '<div class="stat-value">' + data.error_count + '</div>' +
                    '<div class="stat-label">Fehler</div>' +
                '</div>' +
                '<div class="summary-stat stat-total">' +
                    '<div class="stat-value">' + (data.success_count + data.error_count) + '</div>' +
                    '<div class="stat-label">Gesamt</div>' +
                '</div>' +
            '</div>' +
            (data.errors && data.errors.length > 0
                ? '<div class="summary-errors">' +
                    '<h5>Fehler-Details:</h5>' +
                    data.errors.map(function(e) {
                        return '<div class="summary-error-item">' +
                            '<strong>' + escapeHtmlMain(e.task) + '</strong>: ' +
                            '<span>' + escapeHtmlMain(e.error) + '</span>' +
                        '</div>';
                    }).join('') +
                  '</div>'
                : '');
    }
};

// CSS für Toast-Animationen
var style = document.createElement('style');
style.textContent =
    '@keyframes slideIn { from { transform: translateX(400px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }' +
    '@keyframes slideOut { from { transform: translateX(0); opacity: 1; } to { transform: translateX(400px); opacity: 0; } }';
document.head.appendChild(style);

// ===== Notion ID Extraktion =====

/**
 * Extrahiert eine Notion-UUID aus einer URL oder rohen ID.
 * Akzeptiert:
 *   - Vollstaendige URL: https://www.notion.so/workspace/b28daac7a7bd4a3c8468bb229fc41d21?v=...
 *   - UUID ohne Bindestriche: b28daac7a7bd4a3c8468bb229fc41d21
 *   - UUID mit Bindestrichen: b28daac7-a7bd-4a3c-8468-bb229fc41d21
 * Gibt immer UUID mit Bindestrichen zurueck.
 */
function extractNotionId(input) {
    input = (input || '').trim();
    if (!input) return '';

    // 32-stellige Hex-ID aus URL oder Input extrahieren
    var match = input.match(/([0-9a-f]{32})/i);
    if (match) {
        var raw = match[1].toLowerCase();
        return raw.slice(0, 8) + '-' + raw.slice(8, 12) + '-' + raw.slice(12, 16) + '-' + raw.slice(16, 20) + '-' + raw.slice(20);
    }

    // Bereits korrekte UUID mit Bindestrichen?
    var uuidMatch = input.match(/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i);
    if (uuidMatch) {
        return uuidMatch[1].toLowerCase();
    }

    // Kein Match -- Eingabe unveraendert zurueckgeben
    return input;
}

/**
 * Bindet extractNotionId an ein Input-Feld (on blur / on paste).
 */
function bindNotionIdField(inputElement) {
    if (!inputElement) return;

    function normalize() {
        var extracted = extractNotionId(inputElement.value);
        if (extracted !== inputElement.value) {
            inputElement.value = extracted;
        }
    }

    inputElement.addEventListener('blur', normalize);
    inputElement.addEventListener('paste', function() {
        // Timeout damit der gepastete Wert erst im Input steht
        setTimeout(normalize, 0);
    });
}

// Export für Verwendung in anderen Skripten
window.app = {
    apiRequest: apiRequest,
    updateProgress: updateProgress,
    addLogEntry: addLogEntry,
    showToast: showToast,
    SSEMigrationClient: SSEMigrationClient,
    extractNotionId: extractNotionId,
    bindNotionIdField: bindNotionIdField
};
