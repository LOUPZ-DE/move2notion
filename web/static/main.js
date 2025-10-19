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
function updateProgress(percentage, text = '') {
    const progressBar = document.querySelector('.progress-fill');
    const statusText = document.querySelector('.status-text');
    
    if (progressBar) {
        progressBar.style.width = `${percentage}%`;
        progressBar.textContent = `${percentage}%`;
    }
    
    if (statusText && text) {
        statusText.textContent = text;
    }
}

// Log-Ausgabe hinzufügen
function addLogEntry(message, type = 'info') {
    const logOutput = document.querySelector('.log-output');
    
    if (!logOutput) return;
    
    const timestamp = new Date().toLocaleTimeString('de-DE');
    const colorMap = {
        'info': '#569cd6',
        'success': '#4ec9b0',
        'warning': '#dcdcaa',
        'error': '#f48771'
    };
    
    const color = colorMap[type] || '#d4d4d4';
    const logEntry = document.createElement('div');
    logEntry.innerHTML = `<span style="color: #808080;">[${timestamp}]</span> <span style="color: ${color};">${message}</span>`;
    
    logOutput.appendChild(logEntry);
    logOutput.scrollTop = logOutput.scrollHeight;
}

// Toast-Benachrichtigung anzeigen
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    
    toast.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        background: ${type === 'error' ? '#f44336' : type === 'success' ? '#00c853' : '#0066ff'};
        color: white;
        padding: 16px 24px;
        border-radius: 8px;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
        z-index: 1000;
        animation: slideIn 0.3s ease;
    `;
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// CSS für Toast-Animationen
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(400px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

// Export für Verwendung in anderen Skripten
window.app = {
    apiRequest,
    updateProgress,
    addLogEntry,
    showToast
};
