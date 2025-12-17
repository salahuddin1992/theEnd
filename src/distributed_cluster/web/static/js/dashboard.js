/**
 * Dashboard JavaScript - تحديثات حية وتفاعل
 */

class Dashboard {
    constructor() {
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 2000;

        this.init();
    }

    init() {
        this.connectWebSocket();
        this.updateLastUpdateTime();
        setInterval(() => this.updateLastUpdateTime(), 1000);
    }

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;

        try {
            this.ws = new WebSocket(wsUrl);

            this.ws.onopen = () => {
                console.log('WebSocket connected');
                this.reconnectAttempts = 0;
                this.updateConnectionStatus(true);
            };

            this.ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleUpdate(data);
            };

            this.ws.onclose = () => {
                console.log('WebSocket disconnected');
                this.updateConnectionStatus(false);
                this.attemptReconnect();
            };

            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
        } catch (error) {
            console.error('Failed to connect WebSocket:', error);
            this.attemptReconnect();
        }
    }

    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            console.log(`Reconnecting... attempt ${this.reconnectAttempts}`);
            setTimeout(() => this.connectWebSocket(), this.reconnectDelay);
        }
    }

    updateConnectionStatus(connected) {
        const statusEl = document.getElementById('connectionStatus');
        if (statusEl) {
            const dot = statusEl.querySelector('.status-dot');
            const text = statusEl.querySelector('span:last-child');

            if (connected) {
                dot.style.background = 'var(--success)';
                text.textContent = 'متصل';
            } else {
                dot.style.background = 'var(--danger)';
                text.textContent = 'غير متصل';
            }
        }
    }

    handleUpdate(data) {
        if (data.type === 'update') {
            this.updateStats(data.stats);
            this.updateWorkers(data.workers);
            this.updateJobs(data.jobs);
            this.lastUpdate = new Date(data.timestamp);
        }
    }

    updateStats(stats) {
        // تحديث الإحصائيات
        this.updateElement('totalWorkers', stats.total_workers);
        this.updateElement('totalJobs', stats.total_jobs);

        const cpuUsage = `${stats.used_cpu_cores}/${stats.total_cpu_cores}`;
        this.updateElement('cpuUsage', cpuUsage);

        const memUsage = `${stats.used_memory_gb}/${stats.total_memory_gb} GB`;
        this.updateElement('memoryUsage', memUsage);

        // تحديث أشرطة التقدم
        if (stats.total_cpu_cores > 0) {
            const cpuPercent = (stats.used_cpu_cores / stats.total_cpu_cores) * 100;
            this.updateProgressBar('cpu', cpuPercent);
        }

        if (stats.total_memory_gb > 0) {
            const memPercent = (stats.used_memory_gb / stats.total_memory_gb) * 100;
            this.updateProgressBar('memory', memPercent);
        }
    }

    updateWorkers(workers) {
        const container = document.getElementById('workersList');
        if (!container) return;

        container.innerHTML = workers.map(worker => `
            <div class="worker-item">
                <div class="worker-info">
                    <span class="worker-name">${worker.hostname}</span>
                    <span class="worker-id">${worker.worker_id}</span>
                </div>
                <div class="worker-status status-${worker.status}">
                    ${worker.status}
                </div>
                <div class="worker-resources">
                    <div class="resource">
                        <span class="label">CPU</span>
                        <div class="mini-progress">
                            <div class="bar" style="width: ${worker.current_usage.cpu_percent}%"></div>
                        </div>
                        <span class="value">${worker.current_usage.cpu_percent.toFixed(1)}%</span>
                    </div>
                    <div class="resource">
                        <span class="label">RAM</span>
                        <div class="mini-progress">
                            <div class="bar" style="width: ${worker.current_usage.memory_percent}%"></div>
                        </div>
                        <span class="value">${worker.current_usage.memory_percent.toFixed(1)}%</span>
                    </div>
                </div>
            </div>
        `).join('');
    }

    updateJobs(jobs) {
        const container = document.getElementById('jobsList');
        if (!container) return;

        container.innerHTML = jobs.slice(0, 5).map(job => `
            <div class="job-item">
                <div class="job-info">
                    <span class="job-name">${job.name || job.job_id}</span>
                    <span class="job-id">${job.job_id}</span>
                </div>
                <div class="job-status status-${job.status}">
                    ${job.status === 'running' ? '<span class="spinner"></span>' : ''}
                    ${job.status}
                </div>
                ${job.progress !== undefined ? `
                <div class="job-progress">
                    <div class="progress-bar-small">
                        <div class="bar" style="width: ${job.progress}%"></div>
                    </div>
                    <span class="progress-text">${job.progress}%</span>
                </div>
                ` : ''}
            </div>
        `).join('');
    }

    updateElement(id, value) {
        const el = document.getElementById(id);
        if (el) {
            el.textContent = value;
        }
    }

    updateProgressBar(type, percent) {
        const cards = document.querySelectorAll('.stat-card');
        cards.forEach(card => {
            if (card.querySelector(`.stat-icon.${type}`)) {
                const bar = card.querySelector('.progress-bar');
                if (bar) {
                    bar.style.width = `${percent}%`;
                }
            }
        });
    }

    updateLastUpdateTime() {
        const el = document.getElementById('lastUpdate');
        if (el) {
            const now = new Date();
            const time = now.toLocaleTimeString('ar-SA');
            el.textContent = `آخر تحديث: ${time}`;
        }
    }
}

// Worker details modal
function viewWorkerDetails(workerId) {
    alert(`عرض تفاصيل العامل: ${workerId}`);
}

// Job details modal
function viewJobDetails(jobId) {
    const modal = document.getElementById('jobModal');
    if (modal) {
        modal.style.display = 'flex';
        document.getElementById('jobModalBody').innerHTML = `
            <p>جاري تحميل تفاصيل المهمة...</p>
            <p><strong>معرف المهمة:</strong> ${jobId}</p>
        `;
    }
}

// Close modal
function closeModal() {
    const modal = document.getElementById('jobModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

// Cancel job
async function cancelJob(jobId) {
    if (!confirm('هل أنت متأكد من إلغاء هذه المهمة؟')) return;

    try {
        const response = await fetch(`/api/jobs/${jobId}/cancel`, {
            method: 'POST'
        });
        const result = await response.json();

        if (result.success) {
            location.reload();
        } else {
            alert('فشل إلغاء المهمة');
        }
    } catch (error) {
        console.error('Error canceling job:', error);
        alert('خطأ في الاتصال');
    }
}

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new Dashboard();
});

// Close modal on outside click
window.onclick = function(event) {
    const modal = document.getElementById('jobModal');
    if (event.target === modal) {
        closeModal();
    }
};

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeModal();
    }
});
