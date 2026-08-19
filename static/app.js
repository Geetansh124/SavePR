/**
 * SavePR — Frontend Client Logic
 * Real-time SSE progress streaming, tabbed format selectors, and multi-threaded downloads.
 */

(function () {
    "use strict";

    // -----------------------------------------------------------------------
    // DOM Elements
    // -----------------------------------------------------------------------
    const urlForm               = document.getElementById("url-form");
    const urlInput              = document.getElementById("url-input");
    const clearBtn              = document.getElementById("clear-btn");
    const pasteBtn              = document.getElementById("paste-btn");
    const fetchBtn              = document.getElementById("fetch-btn");

    const errorBanner           = document.getElementById("error-banner");
    const errorTitle            = document.getElementById("error-title");
    const errorMessage          = document.getElementById("error-message");
    const errorDismissBtn       = document.getElementById("error-dismiss-btn");

    const mediaResultCard       = document.getElementById("media-result-card");
    const mediaThumb            = document.getElementById("media-thumb");
    const mediaDuration         = document.getElementById("media-duration");
    const mediaTitle            = document.getElementById("media-title");
    const mediaUploader         = document.getElementById("media-uploader");
    const mediaViews            = document.getElementById("media-views");
    const quickDownloadBtn      = document.getElementById("quick-download-btn");

    const videoFormatsGrid      = document.getElementById("video-formats-grid");
    const audioFormatsGrid      = document.getElementById("audio-formats-grid");
    const startDownloadBtn      = document.getElementById("start-download-btn");
    const startDownloadBtnText  = document.getElementById("start-download-btn-text");

    const progressCard          = document.getElementById("progress-card");
    const progressHeaderTitle   = document.getElementById("progress-header-title");
    const cancelDownloadBtn     = document.getElementById("cancel-download-btn");
    const progressFill          = document.getElementById("progress-fill");
    const progressPercent       = document.getElementById("progress-percent");
    const progressPhase         = document.getElementById("progress-phase");
    const metaSpeed             = document.getElementById("meta-speed");
    const metaDownloaded        = document.getElementById("meta-downloaded");
    const metaEta               = document.getElementById("meta-eta");

    const downloadReadyBox      = document.getElementById("download-ready-box");
    const readyFilename         = document.getElementById("ready-filename");
    const directFileDownloadBtn = document.getElementById("direct-file-download-btn");

    const historyToggleBtn      = document.getElementById("history-toggle-btn");
    const historyCountBadge     = document.getElementById("history-count-badge");
    const historyModal          = document.getElementById("history-modal");
    const closeHistoryBtn       = document.getElementById("close-history-btn");
    const clearHistoryBtn       = document.getElementById("clear-history-btn");
    const historyList           = document.getElementById("history-list");

    const tabButtons            = document.querySelectorAll(".tab-btn");
    const tabContents           = document.querySelectorAll(".tab-content");

    // -----------------------------------------------------------------------
    // State
    // -----------------------------------------------------------------------
    let currentUrl = "";
    let currentVideoData = null;
    let selectedFormatId = "best_original";
    let activeEventSource = null;
    let activeJobId = null;

    // -----------------------------------------------------------------------
    // Storage & History Management
    // -----------------------------------------------------------------------
    const HISTORY_KEY = "savepr_download_history_v1";

    function getHistory() {
        try {
            return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
        } catch {
            return [];
        }
    }

    function saveHistory(item) {
        const history = getHistory();
        history.unshift(item);
        if (history.length > 30) history.pop();
        try {
            localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
        } catch {}
        updateHistoryBadge();
    }

    function updateHistoryBadge() {
        const history = getHistory();
        if (history.length > 0) {
            historyCountBadge.textContent = history.length;
            historyCountBadge.hidden = false;
        } else {
            historyCountBadge.hidden = true;
        }
    }

    function renderHistoryList() {
        const history = getHistory();
        historyList.textContent = "";

        if (history.length === 0) {
            const emptyEl = document.createElement("div");
            emptyEl.className = "history-empty";
            emptyEl.textContent = "No recent downloads yet.";
            historyList.appendChild(emptyEl);
            return;
        }

        history.forEach((item) => {
            const row = document.createElement("div");
            row.className = "history-item";

            const left = document.createElement("div");
            left.className = "history-item__left";

            const title = document.createElement("div");
            title.className = "history-item__title";
            title.textContent = item.title || "Video";

            const meta = document.createElement("div");
            meta.className = "history-item__meta";
            meta.textContent = `${item.badge || item.format || "MP4"} • ${item.size || ""}`;

            left.appendChild(title);
            left.appendChild(meta);

            const reFetchBtn = document.createElement("button");
            reFetchBtn.className = "icon-btn";
            reFetchBtn.textContent = "Reload";
            reFetchBtn.onclick = () => {
                urlInput.value = item.url;
                historyModal.hidden = true;
                handleFetchFormats();
            };

            row.appendChild(left);
            row.appendChild(reFetchBtn);
            historyList.appendChild(row);
        });
    }

    // -----------------------------------------------------------------------
    // UI Helpers
    // -----------------------------------------------------------------------
    function showError(title, msg) {
        errorTitle.textContent = title || "Error";
        errorMessage.textContent = msg || "An unexpected error occurred.";
        errorBanner.hidden = false;
        errorBanner.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    function hideError() {
        errorBanner.hidden = true;
    }

    function formatNumber(num) {
        if (!num) return "";
        if (num >= 1000000) return (num / 1000000).toFixed(1) + "M views";
        if (num >= 1000) return (num / 1000).toFixed(1) + "K views";
        return num + " views";
    }

    function formatBytes(bytes) {
        if (!bytes || bytes <= 0) return "";
        const units = ["B", "KB", "MB", "GB", "TB"];
        let i = 0;
        let val = bytes;
        while (val >= 1024 && i < units.length - 1) {
            val /= 1024;
            i++;
        }
        return `${val.toFixed(1)} ${units[i]}`;
    }

    // -----------------------------------------------------------------------
    // Format Cards Generation (XSS Safe)
    // -----------------------------------------------------------------------
    function createFormatCard(item, isDefault) {
        const card = document.createElement("div");
        card.className = "format-card" + (isDefault ? " selected" : "");
        card.dataset.id = item.id;
        card.setAttribute("role", "button");
        card.setAttribute("tabindex", "0");

        // Top row
        const top = document.createElement("div");
        top.className = "format-card__top";

        const badge = document.createElement("span");
        badge.className = "format-card__badge" + (item.is_best ? " format-card__badge--best" : "");
        badge.textContent = item.badge || item.ext.toUpperCase();

        const ext = document.createElement("span");
        ext.className = "format-card__ext";
        ext.textContent = item.ext.toUpperCase();

        top.appendChild(badge);
        top.appendChild(ext);

        // Title & Description
        const title = document.createElement("div");
        title.className = "format-card__title";
        title.textContent = item.title;

        const desc = document.createElement("div");
        desc.className = "format-card__desc";
        desc.textContent = item.desc;

        // Bottom row
        const bottom = document.createElement("div");
        bottom.className = "format-card__bottom";

        const size = document.createElement("span");
        size.className = "format-card__size";
        size.textContent = item.filesize ? formatBytes(item.filesize) : "Original Size";

        const radio = document.createElement("span");
        radio.className = "format-radio-check";

        bottom.appendChild(size);
        bottom.appendChild(radio);

        card.appendChild(top);
        card.appendChild(title);
        card.appendChild(desc);
        card.appendChild(bottom);

        card.addEventListener("click", () => {
            document.querySelectorAll(".format-card").forEach((c) => c.classList.remove("selected"));
            card.classList.add("selected");
            selectedFormatId = item.id;
            startDownloadBtnText.textContent = `Download ${item.badge || item.title}`;
        });

        return card;
    }

    function renderFormats(data) {
        videoFormatsGrid.textContent = "";
        audioFormatsGrid.textContent = "";

        // Render Video options
        if (data.video_options && data.video_options.length > 0) {
            data.video_options.forEach((opt, idx) => {
                const card = createFormatCard(opt, idx === 0);
                videoFormatsGrid.appendChild(card);
            });
            selectedFormatId = data.video_options[0].id;
            startDownloadBtnText.textContent = `Download ${data.video_options[0].badge || "Selected Format"}`;
        }

        // Render Audio options
        if (data.audio_options && data.audio_options.length > 0) {
            data.audio_options.forEach((opt) => {
                const card = createFormatCard(opt, false);
                audioFormatsGrid.appendChild(card);
            });
        }
    }

    // -----------------------------------------------------------------------
    // Fetch & Analyze Action
    // -----------------------------------------------------------------------
    async function handleFetchFormats() {
        const url = urlInput.value.trim();
        if (!url) {
            showError("Input Required", "Please enter a valid video link.");
            return;
        }

        hideError();
        fetchBtn.disabled = true;
        fetchBtn.querySelector(".btn-text").textContent = "Analyzing…";
        mediaResultCard.hidden = true;
        progressCard.hidden = true;

        try {
            const resp = await fetch("/api/formats", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url: url }),
            });

            const data = await resp.json();
            if (!resp.ok) {
                showError("Analysis Error", data.error || "Failed to inspect video stream.");
                return;
            }

            currentUrl = url;
            currentVideoData = data;

            // Populate Overview
            mediaTitle.textContent = data.title || "Video";
            mediaThumb.src = data.thumbnail || "";
            mediaDuration.textContent = data.duration_str || "";
            mediaUploader.textContent = data.uploader || "Original Stream";

            if (data.view_count) {
                mediaViews.textContent = formatNumber(data.view_count);
                mediaViews.hidden = false;
            } else {
                mediaViews.hidden = true;
            }

            renderFormats(data);
            mediaResultCard.hidden = false;
            mediaResultCard.scrollIntoView({ behavior: "smooth", block: "nearest" });

        } catch (err) {
            showError("Connection Error", "Could not connect to backend server.");
        } finally {
            fetchBtn.disabled = false;
            fetchBtn.querySelector(".btn-text").textContent = "Analyze Link";
        }
    }

    // -----------------------------------------------------------------------
    // Live Download Execution & SSE Progress
    // -----------------------------------------------------------------------
    async function initiateDownload(formatId) {
        if (!currentUrl) return;

        hideError();
        if (activeEventSource) {
            activeEventSource.close();
            activeEventSource = null;
        }

        // Reset progress UI
        progressCard.hidden = false;
        downloadReadyBox.hidden = true;
        progressFill.style.width = "0%";
        progressPercent.textContent = "0%";
        progressPhase.textContent = "Connecting to server...";
        metaSpeed.textContent = "-- MB/s";
        metaDownloaded.textContent = "0 MB / 0 MB";
        metaEta.textContent = "--:--";
        progressHeaderTitle.textContent = "Downloading Stream...";
        startDownloadBtn.disabled = true;
        quickDownloadBtn.disabled = true;

        progressCard.scrollIntoView({ behavior: "smooth", block: "nearest" });

        try {
            const resp = await fetch("/api/start_download", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    url: currentUrl,
                    format_id: formatId || selectedFormatId,
                }),
            });

            const data = await resp.json();
            if (!resp.ok) {
                showError("Download Error", data.error || "Could not start download.");
                progressCard.hidden = true;
                startDownloadBtn.disabled = false;
                quickDownloadBtn.disabled = false;
                return;
            }

            activeJobId = data.job_id;
            listenToProgress(activeJobId);

        } catch (err) {
            showError("Network Error", "Failed to initiate download job.");
            progressCard.hidden = true;
            startDownloadBtn.disabled = false;
            quickDownloadBtn.disabled = false;
        }
    }

    function listenToProgress(jobId) {
        activeEventSource = new EventSource(`/api/progress/${jobId}`);

        activeEventSource.onmessage = (event) => {
            try {
                const job = JSON.parse(event.data);
                handleProgressUpdate(job);
            } catch (e) {
                console.error("Error parsing progress event", e);
            }
        };

        activeEventSource.onerror = () => {
            if (activeEventSource) {
                activeEventSource.close();
                activeEventSource = null;
            }
            pollProgress(jobId);
        };
    }

    async function pollProgress(jobId) {
        if (!activeJobId || activeJobId !== jobId) return;
        try {
            const resp = await fetch(`/api/status/${jobId}`);
            if (!resp.ok) return;
            const job = await resp.json();
            handleProgressUpdate(job);

            if (job.status !== "completed" && job.status !== "error" && job.status !== "cancelled") {
                setTimeout(() => pollProgress(jobId), 400);
            }
        } catch {}
    }

    function handleProgressUpdate(job) {
        if (job.error) {
            showError("Download Failed", job.error);
            progressCard.hidden = true;
            startDownloadBtn.disabled = false;
            quickDownloadBtn.disabled = false;
            if (activeEventSource) activeEventSource.close();
            return;
        }

        const pct = Math.max(0, Math.min(100, job.percent || 0));
        progressFill.style.width = `${pct}%`;
        progressPercent.textContent = `${pct.toFixed(0)}%`;
        progressPhase.textContent = job.phase || "Processing...";

        metaSpeed.textContent = job.speed_str || "-- MB/s";
        metaDownloaded.textContent = job.info_msg || `${formatBytes(job.downloaded_bytes)} / ${formatBytes(job.total_bytes)}`;
        metaEta.textContent = job.eta_str || "--:--";

        if (job.status === "completed") {
            if (activeEventSource) activeEventSource.close();
            startDownloadBtn.disabled = false;
            quickDownloadBtn.disabled = false;
            progressHeaderTitle.textContent = "Download Finished!";
            progressFill.style.width = "100%";
            progressPercent.textContent = "100%";

            const safeName = encodeURIComponent(job.filename || "video.mp4");
            const downloadUrl = `/api/get_file/${job.job_id}/${safeName}`;
            readyFilename.textContent = job.filename || "video.mp4";
            directFileDownloadBtn.href = downloadUrl;
            directFileDownloadBtn.setAttribute("download", job.filename || "video.mp4");
            downloadReadyBox.hidden = false;

            // Direct download trigger
            const autoLink = document.createElement("a");
            autoLink.href = downloadUrl;
            autoLink.setAttribute("download", job.filename || "video.mp4");
            document.body.appendChild(autoLink);
            autoLink.click();
            autoLink.remove();

            saveHistory({
                url: currentUrl,
                title: job.title || currentVideoData?.title || "Video",
                format: job.ext?.toUpperCase() || "MP4",
                size: job.file_size_str || formatBytes(job.file_size),
                timestamp: Date.now(),
            });
        }
    }

    // -----------------------------------------------------------------------
    // Event Listeners
    // -----------------------------------------------------------------------

    urlForm.addEventListener("submit", (e) => {
        e.preventDefault();
        handleFetchFormats();
    });

    urlInput.addEventListener("input", () => {
        clearBtn.hidden = urlInput.value.length === 0;
    });

    clearBtn.addEventListener("click", () => {
        urlInput.value = "";
        clearBtn.hidden = true;
        urlInput.focus();
    });

    pasteBtn.addEventListener("click", async () => {
        try {
            const text = await navigator.clipboard.readText();
            if (text) {
                urlInput.value = text.trim();
                clearBtn.hidden = false;
                handleFetchFormats();
            }
        } catch {
            urlInput.focus();
        }
    });

    errorDismissBtn.addEventListener("click", hideError);

    quickDownloadBtn.addEventListener("click", () => {
        initiateDownload("best_original");
    });

    startDownloadBtn.addEventListener("click", () => {
        initiateDownload(selectedFormatId);
    });

    cancelDownloadBtn.addEventListener("click", async () => {
        if (!activeJobId) return;
        try {
            await fetch(`/api/cancel/${activeJobId}`, { method: "POST" });
        } catch {}
        if (activeEventSource) activeEventSource.close();
        progressCard.hidden = true;
        startDownloadBtn.disabled = false;
        quickDownloadBtn.disabled = false;
    });

    tabButtons.forEach((btn) => {
        btn.addEventListener("click", () => {
            const target = btn.dataset.tab;
            tabButtons.forEach((b) => {
                b.classList.remove("active");
                b.setAttribute("aria-selected", "false");
            });
            tabContents.forEach((c) => c.classList.remove("active"));

            btn.classList.add("active");
            btn.setAttribute("aria-selected", "true");
            const targetEl = document.getElementById(target);
            if (targetEl) targetEl.classList.add("active");
        });
    });

    historyToggleBtn.addEventListener("click", () => {
        renderHistoryList();
        historyModal.hidden = false;
    });

    closeHistoryBtn.addEventListener("click", () => {
        historyModal.hidden = true;
    });

    historyModal.addEventListener("click", (e) => {
        if (e.target === historyModal) historyModal.hidden = true;
    });

    clearHistoryBtn.addEventListener("click", () => {
        localStorage.removeItem(HISTORY_KEY);
        renderHistoryList();
        updateHistoryBadge();
    });

    updateHistoryBadge();

})();
