/**
 * Whisper Subtitle Generator - Frontend Application
 */

// ============================================================================
// State Management
// ============================================================================
const state = {
    authenticated: false,
    jobs: [],
    settings: null,
    currentTab: 'upload',
    selectedFile: null,
    selectedTorrent: null,
    pollInterval: null,
    trackSelectionJob: null,
    // Torrent file selection
    torrentFiles: [],
    selectedFileIndices: [],
    pendingTorrentData: null  // Stores form data while showing file selection
};

// ============================================================================
// API Client
// ============================================================================
const api = {
    async request(method, url, data = null, isFormData = false) {
        const options = {
            method,
            headers: {},
            credentials: 'include'
        };

        if (data) {
            if (isFormData) {
                options.body = data;
            } else {
                options.headers['Content-Type'] = 'application/json';
                options.body = JSON.stringify(data);
            }
        }

        const response = await fetch(url, options);

        if (response.status === 401) {
            state.authenticated = false;
            showScreen('login');
            throw new Error('Unauthorized');
        }

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || 'Request failed');
        }

        return result;
    },

    // Auth
    async login(username, password) {
        return this.request('POST', '/api/auth/login', { username, password });
    },

    async logout() {
        return this.request('POST', '/api/auth/logout');
    },

    async checkAuth() {
        return this.request('GET', '/api/auth/me');
    },

    // Settings
    async getSettings() {
        return this.request('GET', '/api/settings');
    },

    async updateSettings(settings) {
        return this.request('POST', '/api/settings', settings);
    },

    async changePassword(currentPassword, newPassword) {
        return this.request('POST', '/api/settings/password', {
            current_password: currentPassword,
            new_password: newPassword
        });
    },

    // Jobs
    async getJobs() {
        return this.request('GET', '/api/jobs');
    },

    async getJob(id) {
        return this.request('GET', `/api/jobs/${id}`);
    },

    async createJob(formData) {
        return this.request('POST', '/api/jobs', formData, true);
    },

    async selectTrack(jobId, trackIndex, applyToAll = false) {
        return this.request('POST', `/api/jobs/${jobId}/select-track`, {
            track_index: trackIndex,
            apply_to_all: applyToAll
        });
    },

    async deleteJob(id) {
        return this.request('DELETE', `/api/jobs/${id}`);
    },

    async getTorrentFiles(formData) {
        return this.request('POST', '/api/torrent-files', formData, true);
    }
};

// ============================================================================
// UI Helpers
// ============================================================================
function $(selector) {
    return document.querySelector(selector);
}

function $$(selector) {
    return document.querySelectorAll(selector);
}

function showScreen(screenId) {
    $$('.screen').forEach(s => s.classList.add('hidden'));
    $(`#${screenId === 'login' ? 'login-screen' : 'dashboard'}`).classList.remove('hidden');
}

function showModal(modalId) {
    $(`#${modalId}`).classList.remove('hidden');
}

function hideModal(modalId) {
    $(`#${modalId}`).classList.add('hidden');
}

function showToast(message, type = 'info') {
    const container = $('#toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

function formatStatus(status) {
    return i18n.t(`jobs.status.${status}`) || status;
}

function formatDate(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

// ============================================================================
// Authentication
// ============================================================================
async function handleLogin(e) {
    e.preventDefault();

    const username = $('#username').value;
    const password = $('#password').value;
    const errorEl = $('#login-error');

    try {
        await api.login(username, password);
        state.authenticated = true;
        showScreen('dashboard');
        await loadDashboard();
    } catch (err) {
        errorEl.textContent = i18n.t('toast.login.invalid');
    }
}

async function handleLogout() {
    try {
        await api.logout();
    } catch (err) {
        // Ignore
    }
    state.authenticated = false;
    showScreen('login');
    stopPolling();
}

async function checkAuth() {
    try {
        await api.checkAuth();
        state.authenticated = true;
        showScreen('dashboard');
        await loadDashboard();
    } catch (err) {
        state.authenticated = false;
        showScreen('login');
    }
}

// ============================================================================
// Dashboard
// ============================================================================
async function loadDashboard() {
    await Promise.all([
        loadSettings(),
        loadJobs()
    ]);
    startPolling();
}

async function loadSettings() {
    try {
        state.settings = await api.getSettings();
        renderSettings();
    } catch (err) {
        showToast(i18n.t('toast.error.load_settings'), 'error');
    }
}

function renderSettings() {
    if (!state.settings) return;

    const modelSelect = $('#setting-model');
    modelSelect.innerHTML = '';

    for (const [key, model] of Object.entries(state.settings.available_models)) {
        const option = document.createElement('option');
        option.value = key;
        option.textContent = `${model.name} (${model.size})`;
        if (key === state.settings.model) {
            option.selected = true;
        }
        modelSelect.appendChild(option);
    }

    updateModelDescription();

    $('#setting-threads').value = state.settings.cpu_threads;
    $('#threads-value').textContent = state.settings.cpu_threads || i18n.t('settings.threads.auto');

    $('#setting-language').value = state.settings.language;
}

function updateModelDescription() {
    const modelKey = $('#setting-model').value;
    const model = state.settings?.available_models[modelKey];
    if (model) {
        // Try to get translated description, fallback to API value
        const translatedDesc = i18n.t(`settings.model.descriptions.${modelKey}`);
        const description = translatedDesc !== `settings.model.descriptions.${modelKey}`
            ? translatedDesc
            : model.description;
        $('#model-description').textContent = description;
    }
}

async function handleSaveSettings() {
    try {
        const settings = {
            model: $('#setting-model').value,
            cpu_threads: parseInt($('#setting-threads').value),
            language: $('#setting-language').value
        };

        state.settings = await api.updateSettings(settings);
        showToast(i18n.t('toast.success.settings_saved'), 'success');
        hideModal('settings-modal');
    } catch (err) {
        showToast(i18n.t('toast.error.save_settings'), 'error');
    }
}

async function handleChangePassword(e) {
    e.preventDefault();

    const currentPassword = $('#current-password').value;
    const newPassword = $('#new-password').value;
    const messageEl = $('#password-message');

    try {
        await api.changePassword(currentPassword, newPassword);
        messageEl.textContent = i18n.t('toast.success.password_changed');
        messageEl.className = 'message success';
        $('#current-password').value = '';
        $('#new-password').value = '';
    } catch (err) {
        messageEl.textContent = err.message || i18n.t('toast.error.change_password');
        messageEl.className = 'message error';
    }
}

// ============================================================================
// Jobs
// ============================================================================
async function loadJobs() {
    try {
        const result = await api.getJobs();
        state.jobs = result.jobs;
        renderJobs();
        checkForTrackSelection();
    } catch (err) {
        showToast(i18n.t('toast.error.load_jobs'), 'error');
    }
}

function renderJobs() {
    const container = $('#jobs-list');

    if (state.jobs.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <span>📭</span>
                <p>${i18n.t('jobs.empty')}</p>
            </div>
        `;
        return;
    }

    container.innerHTML = state.jobs.map(job => renderJobCard(job)).join('');

    // Add event listeners
    container.querySelectorAll('[data-action]').forEach(btn => {
        btn.addEventListener('click', handleJobAction);
    });
}

function renderJobCard(job) {
    const isGroup = job.is_group && job.files.length > 1;
    const progress = job.files.length > 0
        ? job.files.reduce((sum, f) => sum + f.progress, 0) / job.files.length
        : job.progress;

    let actions = '';

    // For multi-file jobs, DON'T show job-level buttons - only per-file buttons
    // Job-level buttons only for single-file jobs
    const showJobLevelButtons = !isGroup;

    if (job.status === 'downloading') {
        const pauseIcon = job.is_paused ? '▶️' : '⏸️';
        const pauseText = job.is_paused ? i18n.t('jobs.actions.resume') : i18n.t('jobs.actions.pause');
        const pauseClass = job.is_paused ? 'btn-success' : 'btn-warning';
        actions = `
            <button class="btn ${pauseClass} btn-sm" data-action="toggle-pause" data-job-id="${job.id}">
                ${pauseIcon} ${pauseText}
            </button>
        `;
    } else if (job.status === 'awaiting_track') {
        actions = `
            <button class="btn btn-primary btn-sm" data-action="select-track" data-job-id="${job.id}">
                🎵 ${i18n.t('jobs.actions.select_track')}
            </button>
        `;
    } else if (showJobLevelButtons && (job.status === 'converting' || job.status === 'completed' || job.status === 'embedding')) {
        // Single file jobs only - show download buttons at job level
        const canWatch = job.status === 'completed';
        actions = `
            <button class="btn btn-primary btn-sm" data-action="download-srt" data-job-id="${job.id}">
                📄 ${i18n.t('jobs.actions.download_srt')}
            </button>
            <button class="btn btn-secondary btn-sm" data-action="download-video" data-job-id="${job.id}">
                🎬 ${i18n.t('jobs.actions.download_video')}
            </button>
            ${canWatch ? `
                <button class="btn btn-secondary btn-sm" data-action="watch-online" data-job-id="${job.id}">
                    ▶️ ${i18n.t('jobs.actions.watch_online')}
                </button>
            ` : `
                <button class="btn btn-secondary btn-sm" disabled title="">
                    ⏳ ${i18n.t('jobs.actions.pending_conversion')}
                </button>
            `}
        `;
    }

    let filesHtml = '';
    if (isGroup) {
        filesHtml = `
            <div class="job-group-files">
                ${job.files.map(f => `
                    <div class="job-file">
                        <span class="job-file-name">${f.filename}</span>
                        <span class="job-file-status status-${f.status}">${formatStatus(f.status)}</span>
                        ${f.status === 'completed' || f.status === 'converting' || f.status === 'embedding' ? `
                            <div class="job-file-actions">
                                ${f.srt_path ? `<button class="btn btn-xs" data-action="download-srt" data-job-id="${job.id}" data-file-id="${f.id}" title="${i18n.t('jobs.actions.download_srt')}">📄</button>` : ''}
                                ${f.output_path ? `<button class="btn btn-xs" data-action="download-video" data-job-id="${job.id}" data-file-id="${f.id}" title="${i18n.t('jobs.actions.download_video')}">🎬</button>` : ''}
                                ${f.streaming_path && f.status === 'completed' ? `<button class="btn btn-xs" data-action="watch-online" data-job-id="${job.id}" data-file-id="${f.id}" title="${i18n.t('jobs.actions.watch_online')}">▶️</button>` : ''}
                            </div>
                        ` : ''}
                    </div>
                `).join('')}
            </div>
        `;
    }

    return `
        <div class="job-card ${isGroup ? 'job-group' : ''}" data-job-id="${job.id}">
            <button class="btn-delete" data-action="delete" data-job-id="${job.id}" title="${i18n.t('jobs.actions.delete')}">✕</button>
            <div class="job-card-header">
                <div>
                    <div class="job-card-title">${job.source || i18n.t('jobs.unknown')}</div>
                    <div class="job-card-type">${getJobTypeLabel(job.type)}</div>
                </div>
                <span class="job-card-status status-${job.status}">${formatStatus(job.status)}</span>
            </div>
            ${job.status !== 'completed' && job.status !== 'failed' ? `
                <div class="job-card-progress">
                    <div class="progress-bar">
                        <div class="progress-bar-fill" style="width: ${progress}%"></div>
                    </div>
                    <div class="progress-text">
                        ${Math.round(progress)}%
                        ${job.status === 'downloading' && job.download_speed ? ` • ${job.download_speed}` : ''}
                        ${job.status === 'downloading' && job.eta ? ` • ⏱ ${job.eta}` : ''}
                    </div>
                </div>
            ` : ''}
            ${job.error ? `<div class="text-error" style="margin-bottom: 12px; font-size: 13px;">${job.error}</div>` : ''}
            ${filesHtml}
            ${actions ? `<div class="job-card-actions">${actions}</div>` : ''}
        </div>
    `;
}

function getJobTypeLabel(type) {
    return i18n.t(`jobs.type.${type}`) || type;
}

async function handleJobAction(e) {
    const action = e.target.dataset.action;
    const jobId = e.target.dataset.jobId;
    const fileId = e.target.dataset.fileId;  // Optional for per-file actions

    switch (action) {
        case 'select-track':
            await showTrackSelection(jobId);
            break;
        case 'download-srt':
            const srtUrl = fileId
                ? `/api/jobs/${jobId}/download/srt?file_id=${fileId}`
                : `/api/jobs/${jobId}/download/srt`;
            window.location.href = srtUrl;
            break;
        case 'download-video':
            const videoUrl = fileId
                ? `/api/jobs/${jobId}/download/video?file_id=${fileId}`
                : `/api/jobs/${jobId}/download/video`;
            window.location.href = videoUrl;
            break;
        case 'watch-online':
            await prepareAndPlayStreaming(jobId, fileId);
            break;
        case 'toggle-pause':
            try {
                const response = await fetch(`/api/jobs/${jobId}/pause`, {
                    method: 'POST',
                    credentials: 'include'
                });
                if (response.ok) {
                    const data = await response.json();
                    showToast(data.is_paused ? i18n.t('toast.success.download_paused') : i18n.t('toast.success.download_resumed'), 'success');
                    await loadJobs();
                } else {
                    showToast(i18n.t('toast.error.pause'), 'error');
                }
            } catch (err) {
                showToast(i18n.t('toast.error.pause'), 'error');
            }
            break;
        case 'delete':
            if (confirm(i18n.t('jobs.delete_confirm'))) {
                try {
                    await api.deleteJob(jobId);
                    showToast(i18n.t('toast.success.job_deleted'), 'success');
                    await loadJobs();
                } catch (err) {
                    showToast(i18n.t('toast.error.delete'), 'error');
                }
            }
            break;
    }
}

function checkForTrackSelection() {
    // Only auto-show modal if it's hidden
    const modal = $('#track-modal');
    const isModalVisible = !modal.classList.contains('hidden');

    if (!isModalVisible) {
        const awaitingJob = state.jobs.find(j => j.status === 'awaiting_track');
        if (awaitingJob) {
            showTrackSelection(awaitingJob.id);
        }
    }
}

// ============================================================================
// Track Selection
// ============================================================================
async function showTrackSelection(jobId) {
    try {
        const job = await api.getJob(jobId);
        state.trackSelectionJob = job;

        // Find file awaiting track selection
        const file = job.files.find(f => f.status === 'awaiting_track') || job.files[0];

        $('#track-file-name').textContent = file.filename;

        const trackList = $('#track-list');
        trackList.innerHTML = file.audio_tracks.map((track, i) => `
            <label class="track-item" data-track-index="${track.index}">
                <input type="radio" name="track" value="${track.index}" ${i === 0 ? 'checked' : ''}>
                <div class="track-info">
                    <div class="track-title">
                        ${track.title || i18n.t('tracks.track_n', { n: i + 1 })}
                        ${track.default ? ' ⭐' : ''}
                    </div>
                    <div class="track-details">
                        ${track.language || i18n.t('tracks.unknown_language')} • 
                        ${track.codec.toUpperCase()} • 
                        ${track.channels} ${track.channels === 1 ? i18n.t('tracks.channels.one') : track.channels < 5 ? i18n.t('tracks.channels.few') : i18n.t('tracks.channels.many')}
                    </div>
                </div>
            </label>
        `).join('');

        // Show "apply to all" only for multi-file jobs
        const applyAllContainer = $('#apply-all-container');
        const multiFile = job.files.filter(f => f.status === 'awaiting_track').length > 1;
        applyAllContainer.style.display = multiFile ? 'flex' : 'none';
        $('#apply-to-all').checked = multiFile;

        $('#confirm-track').disabled = false;

        showModal('track-modal');
    } catch (err) {
        showToast(i18n.t('toast.error.load_tracks'), 'error');
    }
}

async function handleTrackConfirm() {
    const selectedRadio = $('input[name="track"]:checked');
    if (!selectedRadio || !state.trackSelectionJob) return;

    const trackIndex = parseInt(selectedRadio.value);
    const applyToAll = $('#apply-to-all').checked;

    try {
        const result = await api.selectTrack(state.trackSelectionJob.id, trackIndex, applyToAll);

        // Check if there are more files awaiting track selection
        const stillAwaiting = result.files.filter(f => f.status === 'awaiting_track');

        if (stillAwaiting.length > 0 && !applyToAll) {
            // More files need track selection - update modal for next file
            showToast(i18n.t('toast.info.track_remaining', { count: stillAwaiting.length }), 'info');
            state.trackSelectionJob = result;

            // Update modal to show next file
            const nextFile = stillAwaiting[0];
            $('#track-file-name').textContent = nextFile.filename;

            const trackList = $('#track-list');
            trackList.innerHTML = nextFile.audio_tracks.map((track, i) => `
                <label class="track-item" data-track-index="${track.index}">
                    <input type="radio" name="track" value="${track.index}" ${i === 0 ? 'checked' : ''}>
                    <div class="track-info">
                        <div class="track-title">
                            ${track.title || i18n.t('tracks.track_n', { n: i + 1 })}
                            ${track.default ? ' ⭐' : ''}
                        </div>
                        <div class="track-details">
                            ${track.language || i18n.t('tracks.unknown_language')} • 
                            ${track.codec.toUpperCase()} • 
                            ${track.channels} ${track.channels === 1 ? i18n.t('tracks.channels.one') : track.channels < 5 ? i18n.t('tracks.channels.few') : i18n.t('tracks.channels.many')}
                        </div>
                    </div>
                </label>
            `).join('');

            // Keep modal open
        } else {
            // All files have tracks selected - close modal
            hideModal('track-modal');
            showToast(i18n.t('toast.success.all_tracks_selected'), 'success');
        }

        await loadJobs();
    } catch (err) {
        showToast(i18n.t('toast.error.select_track'), 'error');
    }
}

// ============================================================================
// Job Creation
// ============================================================================
async function handleCreateJob(e) {
    e.preventDefault();

    const formData = new FormData();
    formData.append('job_type', state.currentTab);
    formData.append('embed_subtitles', true);  // Always embed subtitles
    formData.append('language', state.settings?.language || 'auto');

    switch (state.currentTab) {
        case 'upload':
            if (!state.selectedFile) {
                showToast(i18n.t('toast.error.select_file'), 'warning');
                return;
            }
            formData.append('file', state.selectedFile);
            break;

        case 'url':
            const url = $('#url-input').value.trim();
            if (!url) {
                showToast(i18n.t('toast.error.enter_url'), 'warning');
                return;
            }
            formData.append('source', url);
            break;

        case 'magnet':
            const magnet = $('#magnet-input').value.trim();
            if (!magnet) {
                showToast(i18n.t('toast.error.enter_magnet'), 'warning');
                return;
            }
            // For magnet, show file selection first
            await showFileSelectionForMagnet(magnet);
            return;

        case 'torrent':
            if (!state.selectedTorrent) {
                showToast(i18n.t('toast.error.select_torrent'), 'warning');
                return;
            }
            // For torrent, show file selection first
            await showFileSelectionForTorrent(state.selectedTorrent);
            return;
    }

    await createJobWithFormData(formData);
}

async function createJobWithFormData(formData, selectedIndices = null) {
    try {
        if (selectedIndices && selectedIndices.length > 0) {
            formData.append('selected_indices', JSON.stringify(selectedIndices));
        }

        // Check if we're uploading a file (show progress for file uploads)
        const hasFile = formData.has('file');
        const file = formData.get('file');

        if (hasFile && file && file.size > 5 * 1024 * 1024) {  // Show progress for files > 5MB
            await uploadWithProgress(formData, file);
        } else {
            await api.createJob(formData);
        }

        showToast(i18n.t('toast.success.job_created'), 'success');

        // Reset form
        state.selectedFile = null;
        state.selectedTorrent = null;
        state.pendingTorrentData = null;
        $('#selected-file').textContent = '';
        $('#selected-torrent').textContent = '';
        $('#url-input').value = '';
        $('#magnet-input').value = '';

        await loadJobs();
    } catch (err) {
        showToast(err.message || i18n.t('toast.error.create_job'), 'error');
    }
}

async function uploadWithProgress(formData, file) {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        const progressDiv = $('#upload-progress');
        const progressBar = $('#upload-progress-bar');
        const filenameSpan = $('#upload-filename');
        const percentSpan = $('#upload-percent');
        const loadedSpan = $('#upload-loaded');
        const totalSpan = $('#upload-total');
        const speedSpan = $('#upload-speed');

        let startTime = Date.now();
        let lastLoaded = 0;
        let lastTime = startTime;

        // Show progress UI
        progressDiv.style.display = 'block';
        filenameSpan.textContent = file.name;
        totalSpan.textContent = formatFileSize(file.size);

        xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const percent = Math.round((e.loaded / e.total) * 100);
                progressBar.style.width = percent + '%';
                percentSpan.textContent = percent + '%';
                loadedSpan.textContent = formatFileSize(e.loaded);

                // Calculate speed
                const now = Date.now();
                const timeDiff = (now - lastTime) / 1000;
                if (timeDiff > 0.5) {  // Update speed every 0.5 seconds
                    const loadedDiff = e.loaded - lastLoaded;
                    const speed = loadedDiff / timeDiff;
                    speedSpan.textContent = '• ' + formatFileSize(speed) + '/s';
                    lastLoaded = e.loaded;
                    lastTime = now;
                }
            }
        });

        xhr.addEventListener('load', () => {
            progressDiv.style.display = 'none';
            progressBar.style.width = '0%';

            if (xhr.status >= 200 && xhr.status < 300) {
                resolve(JSON.parse(xhr.responseText));
            } else {
                try {
                    const error = JSON.parse(xhr.responseText);
                    reject(new Error(error.detail || i18n.t('toast.error.upload')));
                } catch {
                    reject(new Error(i18n.t('toast.error.upload')));
                }
            }
        });

        xhr.addEventListener('error', () => {
            progressDiv.style.display = 'none';
            reject(new Error(i18n.t('toast.error.network')));
        });

        xhr.open('POST', '/api/jobs');
        xhr.withCredentials = true;
        xhr.send(formData);
    });
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' ' + i18n.t('size.b');
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' ' + i18n.t('size.kb');
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' ' + i18n.t('size.mb');
    return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' ' + i18n.t('size.gb');
}

// ============================================================================
// File Selection for Torrents
// ============================================================================
async function showFileSelectionForMagnet(magnet) {
    showToast(i18n.t('toast.info.loading_files'), 'info');

    try {
        const formData = new FormData();
        formData.append('source', magnet);

        const result = await api.getTorrentFiles(formData);

        if (result.files && result.files.length > 0) {
            state.torrentFiles = result.files;
            state.pendingTorrentData = { type: 'magnet', source: magnet };
            showFileSelectionModal();
        } else {
            showToast(i18n.t('toast.error.no_video_files'), 'warning');
        }
    } catch (err) {
        showToast(i18n.t('toast.error.load_files') + ': ' + err.message, 'error');
    }
}

async function showFileSelectionForTorrent(file) {
    showToast(i18n.t('toast.info.loading_files'), 'info');

    try {
        const formData = new FormData();
        formData.append('torrent_file', file);

        const result = await api.getTorrentFiles(formData);

        if (result.files && result.files.length > 0) {
            state.torrentFiles = result.files;
            state.pendingTorrentData = { type: 'torrent', file: file };
            showFileSelectionModal();
        } else {
            showToast(i18n.t('toast.error.no_video_files'), 'warning');
        }
    } catch (err) {
        showToast(i18n.t('toast.error.load_files') + ': ' + err.message, 'error');
    }
}

function showFileSelectionModal() {
    // Select all files by default
    state.selectedFileIndices = state.torrentFiles.map(f => f.index);

    // Render file list (without sizes - they're unreliable from torrent metadata)
    const fileList = $('#file-list');
    fileList.innerHTML = state.torrentFiles.map(file => `
        <label class="file-item" data-index="${file.index}">
            <input type="checkbox" value="${file.index}" checked>
            <div class="file-item-info">
                <div class="file-item-name" title="${file.path}">${file.path}</div>
            </div>
        </label>
    `).join('');

    updateFileSelectionCount();
    showModal('file-select-modal');
}

function updateFileSelectionCount() {
    const checkboxes = $$('#file-list input[type="checkbox"]');
    const checked = Array.from(checkboxes).filter(cb => cb.checked);

    state.selectedFileIndices = checked.map(cb => parseInt(cb.value));

    $('#selected-count').textContent = i18n.t('files.selected_count', { selected: checked.length, total: checkboxes.length });
    $('#total-size').textContent = '';  // Hide total size - unreliable from torrent metadata

    $('#confirm-files').disabled = checked.length === 0;
}

async function confirmFileSelection() {
    if (state.selectedFileIndices.length === 0) {
        showToast(i18n.t('toast.error.select_at_least_one'), 'warning');
        return;
    }

    hideModal('file-select-modal');

    const formData = new FormData();
    formData.append('embed_subtitles', true);  // Always embed subtitles
    formData.append('language', state.settings?.language || 'auto');

    if (state.pendingTorrentData.type === 'magnet') {
        formData.append('job_type', 'magnet');
        formData.append('source', state.pendingTorrentData.source);
    } else {
        formData.append('job_type', 'torrent');
        formData.append('torrent_file', state.pendingTorrentData.file);
    }

    formData.append('selected_indices', JSON.stringify(state.selectedFileIndices));

    await createJobWithFormData(formData);
}

// ============================================================================
// File Handling
// ============================================================================
function setupDropZone(dropZoneId, inputId, fileType = 'file') {
    const dropZone = $(`#${dropZoneId}`);
    const fileInput = $(`#${inputId}`);

    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');

        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFileSelect(files[0], fileType);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileSelect(e.target.files[0], fileType);
        }
    });
}

function handleFileSelect(file, type) {
    if (type === 'file') {
        state.selectedFile = file;
        $('#selected-file').textContent = `📁 ${file.name} (${formatFileSize(file.size)})`;
    } else if (type === 'torrent') {
        state.selectedTorrent = file;
        $('#selected-torrent').textContent = `📦 ${file.name}`;
    }
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// ============================================================================
// Tab Handling
// ============================================================================
function setupTabs() {
    $$('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;

            $$('.tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            $$('.tab-content').forEach(c => c.classList.remove('active'));
            $(`#tab-${tab}`).classList.add('active');

            state.currentTab = tab;
        });
    });
}

// ============================================================================
// Polling
// ============================================================================
function startPolling() {
    if (state.pollInterval) return;
    state.pollInterval = setInterval(loadJobs, 3000);
}

function stopPolling() {
    if (state.pollInterval) {
        clearInterval(state.pollInterval);
        state.pollInterval = null;
    }
}

// ============================================================================
// Internationalization
// ============================================================================
function applyTranslations() {
    // Update all elements with data-i18n attribute
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        const translated = i18n.t(key);
        if (translated !== key) {
            el.textContent = translated;
        }
    });

    // Update all elements with data-i18n-placeholder attribute
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        const translated = i18n.t(key);
        if (translated !== key) {
            el.placeholder = translated;
        }
    });

    // Update all elements with data-i18n-title attribute
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        const key = el.getAttribute('data-i18n-title');
        const translated = i18n.t(key);
        if (translated !== key) {
            el.title = translated;
        }
    });

    // Update model description with current locale
    if (typeof updateModelDescription === 'function' && state.settings) {
        updateModelDescription();
    }

    console.log(`[i18n] Applied translations for: ${i18n.currentLocale}`);
}

// ============================================================================
// Initialization
// ============================================================================
async function init() {
    // Initialize i18n system
    await i18n.init();
    applyTranslations();

    // Set interface language selector to current locale
    const langSelect = $('#setting-interface-language');
    if (langSelect) {
        langSelect.value = i18n.currentLocale;
        langSelect.addEventListener('change', async (e) => {
            await i18n.setLocale(e.target.value);
            applyTranslations();
        });
    }

    // Listen for locale changes
    window.addEventListener('localeChanged', () => applyTranslations());

    // Login form
    $('#login-form').addEventListener('submit', handleLogin);

    // Logout
    $('#btn-logout').addEventListener('click', handleLogout);

    // Settings
    $('#btn-settings').addEventListener('click', () => showModal('settings-modal'));
    $('#save-settings').addEventListener('click', handleSaveSettings);
    $('#password-form').addEventListener('submit', handleChangePassword);
    $('#setting-model').addEventListener('change', updateModelDescription);
    $('#setting-threads').addEventListener('input', (e) => {
        $('#threads-value').textContent = e.target.value === '0' ? i18n.t('settings.threads.auto') : e.target.value;
    });

    // Modal close buttons
    $$('.modal-close, .modal-backdrop').forEach(el => {
        el.addEventListener('click', (e) => {
            if (e.target === el) {
                el.closest('.modal').classList.add('hidden');
            }
        });
    });

    // Job form
    $('#job-form').addEventListener('submit', handleCreateJob);

    // Refresh button
    $('#btn-refresh').addEventListener('click', loadJobs);

    // Track selection
    $('#confirm-track').addEventListener('click', handleTrackConfirm);

    // Tab selection for track items
    document.addEventListener('click', (e) => {
        if (e.target.closest('.track-item')) {
            $$('.track-item').forEach(t => t.classList.remove('selected'));
            e.target.closest('.track-item').classList.add('selected');
        }
    });

    // Setup tabs
    setupTabs();

    // Setup drop zones
    setupDropZone('drop-zone', 'file-input', 'file');
    setupDropZone('torrent-drop-zone', 'torrent-input', 'torrent');

    // File selection modal
    $('#select-all-files').addEventListener('click', () => {
        $$('#file-list input[type="checkbox"]').forEach(cb => cb.checked = true);
        updateFileSelectionCount();
    });

    $('#deselect-all-files').addEventListener('click', () => {
        $$('#file-list input[type="checkbox"]').forEach(cb => cb.checked = false);
        updateFileSelectionCount();
    });

    $('#confirm-files').addEventListener('click', confirmFileSelection);

    // Update count when checkboxes change
    document.addEventListener('change', (e) => {
        if (e.target.closest('#file-list')) {
            updateFileSelectionCount();
        }
    });

    // License modal
    $('#show-licenses').addEventListener('click', () => {
        showModal('license-modal');
    });

    // Check authentication
    checkAuth();
}

// ============================================================================
// Streaming Video Playback
// ============================================================================

async function prepareAndPlayStreaming(jobId, fileId = null) {
    // Build URLs for video and subtitles
    const videoUrl = fileId
        ? `/api/jobs/${jobId}/stream?file_id=${fileId}`
        : `/api/jobs/${jobId}/stream`;

    const subtitlesUrl = fileId
        ? `/api/jobs/${jobId}/subtitles.vtt?file_id=${fileId}`
        : `/api/jobs/${jobId}/subtitles.vtt`;

    // Get video element and set sources
    const video = $('#video-player');
    const subtitleTrack = $('#video-subtitles');

    // Reset video
    video.pause();
    video.currentTime = 0;

    // Set video source
    video.src = videoUrl;

    // Set subtitle track
    subtitleTrack.src = subtitlesUrl;

    // Show modal
    showModal('video-modal');

    // Start playing
    try {
        await video.play();
    } catch (err) {
        console.log('Autoplay prevented, user can click play manually');
    }
}

// Close video modal and stop playback
function closeVideoModal() {
    const video = $('#video-player');
    video.pause();
    video.src = '';  // Clear source to stop buffering
    hideModal('video-modal');
}

// Initialize video modal close button
document.addEventListener('DOMContentLoaded', () => {
    const closeBtn = $('#close-video-modal');
    if (closeBtn) {
        closeBtn.addEventListener('click', closeVideoModal);
    }

    // Also close on backdrop click
    const videoModal = $('#video-modal');
    if (videoModal) {
        videoModal.querySelector('.modal-backdrop').addEventListener('click', closeVideoModal);
    }
});


// Start the app
document.addEventListener('DOMContentLoaded', init);

