/* ═══════════════════════════════════════════════════════
   ML Drift Dashboard — Single Page Application
   ═══════════════════════════════════════════════════════ */

// ── State ──
let ws;
let token = localStorage.getItem("token");
let reconnectTimer = null;
let reconnectAttempts = 0;
let currentUser = null;
let currentPage = "dashboard";
let alertsPage = 0;
const alertsPerPage = 20;

const featuresData = {};
const recentAlerts = [];
let unresolvedAlertCount = 0;

// Chart instances
let psiChart, klChart, psiTimeChart, klTimeChart;

// ═══════════════ INITIALIZATION ═══════════════

document.addEventListener("DOMContentLoaded", () => {
    if (token) {
        verifyTokenAndInit();
    }

    // Login form
    document.getElementById("login-form").addEventListener("submit", handleLogin);

    // Logout
    document.getElementById("logout-btn").addEventListener("click", handleLogout);

    // Profile dropdown toggle
    document.getElementById("user-profile").addEventListener("click", (e) => {
        e.stopPropagation();
        document.getElementById("profile-dropdown").classList.toggle("open");
    });
    document.addEventListener("click", () => {
        document.getElementById("profile-dropdown")?.classList.remove("open");
    });

    // Sidebar navigation
    document.querySelectorAll(".nav-item").forEach(item => {
        item.addEventListener("click", (e) => {
            e.preventDefault();
            const page = item.dataset.page;
            navigateTo(page);
        });
    });

    // Alert page controls
    document.getElementById("alerts-refresh-btn")?.addEventListener("click", () => loadAlertsPage());
    document.getElementById("alerts-prev")?.addEventListener("click", () => { alertsPage = Math.max(0, alertsPage - 1); loadAlertsPage(); });
    document.getElementById("alerts-next")?.addEventListener("click", () => { alertsPage++; loadAlertsPage(); });
    document.getElementById("alert-severity-filter")?.addEventListener("change", () => { alertsPage = 0; loadAlertsPage(); });

    // Notification bell -> go to alerts
    document.getElementById("notification-bell")?.addEventListener("click", () => navigateTo("alerts"));

    // Keyboard shortcuts
    document.addEventListener("keydown", (e) => {
        if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT" || e.target.tagName === "TEXTAREA") return;
        const pages = ["dashboard", "models", "monitoring", "alerts", "settings", "help"];
        const idx = parseInt(e.key) - 1;
        if (idx >= 0 && idx < pages.length) navigateTo(pages[idx]);
    });

    // Hash-based routing
    window.addEventListener("hashchange", () => {
        const hash = location.hash.replace("#", "") || "dashboard";
        if (hash !== currentPage) navigateTo(hash, false);
    });
});

// ═══════════════ AUTH ═══════════════

async function handleLogin(e) {
    e.preventDefault();
    const username = document.getElementById("username").value;
    const password = document.getElementById("password").value;
    const btn = document.getElementById("login-btn");
    const errorEl = document.getElementById("login-error");

    btn.querySelector(".btn-text").style.display = "none";
    btn.querySelector(".btn-loader").style.display = "inline-block";
    errorEl.style.display = "none";

    try {
        const res = await fetch("/auth/token", {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: new URLSearchParams({ username, password })
        });

        if (res.ok) {
            const data = await res.json();
            token = data.access_token;
            localStorage.setItem("token", token);
            showApp();
            await initDashboard();
        } else {
            errorEl.style.display = "block";
        }
    } catch (err) {
        errorEl.style.display = "block";
    } finally {
        btn.querySelector(".btn-text").style.display = "inline";
        btn.querySelector(".btn-loader").style.display = "none";
    }
}

function handleLogout() {
    localStorage.removeItem("token");
    token = null;
    currentUser = null;
    if (ws) ws.close();
    location.reload();
}

async function verifyTokenAndInit() {
    try {
        const res = await apiFetch("/auth/me");
        if (res.ok) {
            showApp();
            await initDashboard();
        } else {
            localStorage.removeItem("token");
            token = null;
        }
    } catch {
        localStorage.removeItem("token");
        token = null;
    }
}

function showApp() {
    document.getElementById("login-container").style.display = "none";
    document.getElementById("app-container").style.display = "flex";
}

// ═══════════════ NAVIGATION ═══════════════

function navigateTo(page, pushHash = true) {
    currentPage = page;

    // Update sidebar
    document.querySelectorAll(".nav-item").forEach(item => {
        item.classList.toggle("active", item.dataset.page === page);
    });

    // Update pages
    document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
    const pageEl = document.getElementById(`page-${page}`);
    if (pageEl) pageEl.classList.add("active");

    // Update title
    const titles = {
        dashboard: "Dashboard", models: "Models", monitoring: "Monitoring",
        alerts: "Alerts", settings: "Settings", help: "Help & Documentation"
    };
    document.getElementById("page-title").textContent = titles[page] || "Dashboard";

    if (pushHash) location.hash = page;

    // Load page data
    switch (page) {
        case "dashboard": loadDashboardData(); break;
        case "models": loadModelsPage(); break;
        case "monitoring": loadMonitoringPage(); break;
        case "alerts": loadAlertsPage(); break;
        case "settings": loadSettingsPage(); break;
    }
}

// ═══════════════ DASHBOARD INIT ═══════════════

async function initDashboard() {
    await loadUserProfile();
    initCharts();
    connectWebSocket();
    setInterval(updateClock, 1000);
    updateClock();

    // Route to hash or default
    const hash = location.hash.replace("#", "") || "dashboard";
    navigateTo(hash, false);
}

async function loadUserProfile() {
    try {
        const res = await apiFetch("/auth/me");
        if (res.ok) {
            currentUser = await res.json();
            document.getElementById("user-name").textContent = currentUser.username;
            document.getElementById("user-role").textContent = currentUser.role;
            document.getElementById("user-avatar").textContent = currentUser.username.charAt(0).toUpperCase();
        }
    } catch (e) {
        console.error("Failed to load user profile", e);
    }
}

// ═══════════════ API HELPERS ═══════════════

function apiFetch(url, options = {}) {
    const headers = { "Authorization": "Bearer " + token, ...(options.headers || {}) };
    return fetch(url, { ...options, headers });
}

// ═══════════════ DASHBOARD PAGE ═══════════════

async function loadDashboardData() {
    try {
        // Load summary
        const summaryRes = await apiFetch("/api/v1/drift/summary");
        if (summaryRes.ok) {
            const s = await summaryRes.json();
            const maxPsi = s.max_psi_score;
            const maxKl = s.max_kl_score;
            const latestMmd = s.latest_mmd_score;
            document.getElementById("max-psi").textContent = maxPsi != null ? maxPsi.toFixed(4) : "—";
            document.getElementById("mmd-pvalue").textContent = latestMmd != null ? latestMmd.toFixed(4) : "—";
            document.getElementById("features-monitored").textContent = s.feature_count ?? "—";

            if (s.latest_timestamp) {
                const d = new Date(s.latest_timestamp);
                document.getElementById("last-update").textContent = d.toISOString().replace("T", " ").substring(0, 19) + " UTC";
            }

            // Color code PSI
            const psiEl = document.getElementById("max-psi");
            if (maxPsi > 0.20) psiEl.style.color = "var(--red)";
            else if (maxPsi > 0.10) psiEl.style.color = "var(--orange)";
            else psiEl.style.color = "var(--green)";

            unresolvedAlertCount = s.unresolved_alerts || 0;
            updateNotificationBadge();
        }

        // Load scores for charts
        const scoresRes = await apiFetch("/api/v1/drift/scores?limit=200");
        if (scoresRes.ok) {
            const scores = await scoresRes.json();
            // Reset features data
            Object.keys(featuresData).forEach(k => delete featuresData[k]);
            scores.forEach(score => handleScoreData(score));
            updateBarCharts();
        }

        // Load recent alerts
        const alertsRes = await apiFetch("/api/v1/drift/alerts?limit=15");
        if (alertsRes.ok) {
            const alerts = await alertsRes.json();
            recentAlerts.length = 0;
            alerts.forEach(a => recentAlerts.push(a));
            renderAlertFeed();
        }
    } catch (e) {
        console.error("Failed to load dashboard data", e);
    }
}

function handleScoreData(data) {
    const fname = data.feature_name;
    if (fname === "multivariate") return;
    if (!featuresData[fname]) featuresData[fname] = { psi: 0, kl: 0 };
    if (data.detector_type === "psi") featuresData[fname].psi = Math.max(featuresData[fname].psi, data.score);
    if (data.detector_type === "kl") featuresData[fname].kl = Math.max(featuresData[fname].kl, data.score);
}

function renderAlertFeed() {
    const list = document.getElementById("alert-list");
    const emptyState = document.getElementById("alerts-empty");

    if (recentAlerts.length === 0) {
        list.innerHTML = "";
        if (emptyState) emptyState.style.display = "block";
        return;
    }

    if (emptyState) emptyState.style.display = "none";
    list.innerHTML = "";

    recentAlerts.forEach(a => {
        const li = document.createElement("li");
        const ts = a.fired_at ? new Date(a.fired_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—";
        const severity = a.severity || "info";
        const sevLabel = severity === "critical" ? "DRIFT" : severity === "warning" ? "WARNING" : "ALERT";
        const score = typeof a.score === "number" ? a.score.toFixed(4) : "—";

        li.innerHTML = `
            <div>
                <span class="alert-badge ${severity}">${sevLabel}</span>
                <span class="alert-time">[${ts}]</span>
                <span class="alert-detail"><b>${a.feature_name}</b> — ${(a.detector_type || "").toUpperCase()}: ${score}</span>
            </div>`;
        list.appendChild(li);
    });
}

function updateNotificationBadge() {
    const badge = document.getElementById("notif-count");
    const sidebarBadge = document.getElementById("alerts-badge");
    if (unresolvedAlertCount > 0) {
        badge.textContent = unresolvedAlertCount;
        badge.style.display = "block";
        if (sidebarBadge) {
            sidebarBadge.textContent = unresolvedAlertCount;
            sidebarBadge.style.display = "block";
        }
    } else {
        badge.style.display = "none";
        if (sidebarBadge) sidebarBadge.style.display = "none";
    }
}

// ═══════════════ MODELS PAGE ═══════════════

async function loadModelsPage() {
    try {
        const res = await apiFetch("/api/v1/drift/models");
        if (!res.ok) return;
        const models = await res.json();
        const tbody = document.getElementById("models-tbody");
        const emptyState = document.getElementById("models-empty");

        if (models.length === 0) {
            tbody.innerHTML = "";
            if (emptyState) emptyState.style.display = "block";
            return;
        }
        if (emptyState) emptyState.style.display = "none";

        tbody.innerHTML = models.map(m => `
            <tr>
                <td><strong>${m.model_version}</strong></td>
                <td>${m.baseline_count}</td>
                <td>${m.latest_event_at ? new Date(m.latest_event_at).toLocaleString() : "—"}</td>
                <td><span class="status-badge ${m.has_drift_in_last_window ? "status-drifted" : "status-stable"}">${m.has_drift_in_last_window ? "Drifted" : "Stable"}</span></td>
            </tr>`).join("");
    } catch (e) {
        console.error("Failed to load models", e);
    }
}

// ═══════════════ MONITORING PAGE ═══════════════

async function loadMonitoringPage() {
    try {
        const res = await apiFetch("/api/v1/drift/monitoring");
        if (!res.ok) return;
        const data = await res.json();

        updateTimeSeriesChart(psiTimeChart, data.psi, "PSI", "rgba(248, 113, 113, 0.8)");
        updateTimeSeriesChart(klTimeChart, data.kl, "KL Divergence", "rgba(251, 146, 60, 0.8)");
    } catch (e) {
        console.error("Failed to load monitoring data", e);
    }
}

function updateTimeSeriesChart(chart, dataPoints, label, color) {
    if (!chart || !dataPoints) return;

    // Group by feature
    const byFeature = {};
    dataPoints.forEach(p => {
        if (!byFeature[p.feature]) byFeature[p.feature] = [];
        byFeature[p.feature].push(p);
    });

    const colors = [
        "rgba(248,113,113,0.8)", "rgba(251,146,60,0.8)",
        "rgba(74,222,128,0.8)", "rgba(96,165,250,0.8)",
        "rgba(139,92,246,0.8)", "rgba(244,114,182,0.8)"
    ];

    const datasets = Object.keys(byFeature).map((feat, i) => ({
        label: feat,
        data: byFeature[feat].map(p => ({ x: new Date(p.time), y: p.score })),
        borderColor: colors[i % colors.length],
        backgroundColor: "transparent",
        borderWidth: 2,
        pointRadius: 2,
        tension: 0.3
    }));

    chart.data.datasets = datasets;
    chart.update();
}

// ═══════════════ ALERTS PAGE ═══════════════

async function loadAlertsPage() {
    try {
        const severity = document.getElementById("alert-severity-filter")?.value || "";
        const offset = alertsPage * alertsPerPage;
        let url = `/api/v1/drift/alerts?limit=${alertsPerPage}&offset=${offset}`;
        if (severity) url += `&severity=${severity}`;

        const res = await apiFetch(url);
        if (!res.ok) return;
        const alerts = await res.json();

        const tbody = document.getElementById("alerts-tbody");
        const emptyState = document.getElementById("alerts-table-empty");

        if (alerts.length === 0 && alertsPage === 0) {
            tbody.innerHTML = "";
            if (emptyState) emptyState.style.display = "block";
        } else {
            if (emptyState) emptyState.style.display = "none";
            tbody.innerHTML = alerts.map(a => {
                const time = a.fired_at ? new Date(a.fired_at).toLocaleString() : "—";
                const status = a.resolved_at ? "Resolved" : "Open";
                const statusClass = a.resolved_at ? "status-resolved" : "status-open";
                const score = typeof a.score === "number" ? a.score.toFixed(4) : "—";
                const threshold = typeof a.threshold === "number" ? a.threshold.toFixed(4) : "—";
                return `<tr>
                    <td>${time}</td>
                    <td><strong>${a.feature_name}</strong></td>
                    <td>${(a.detector_type || "").toUpperCase()}</td>
                    <td>${score}</td>
                    <td>${threshold}</td>
                    <td><span class="status-badge status-${a.severity || "info"}">${(a.severity || "").toUpperCase()}</span></td>
                    <td><span class="status-badge ${statusClass}">${status}</span></td>
                </tr>`;
            }).join("");
        }

        // Pagination
        document.getElementById("alerts-prev").disabled = alertsPage === 0;
        document.getElementById("alerts-next").disabled = alerts.length < alertsPerPage;
        document.getElementById("alerts-page-info").textContent = `Page ${alertsPage + 1}`;
    } catch (e) {
        console.error("Failed to load alerts page", e);
    }
}

// ═══════════════ SETTINGS PAGE ═══════════════

async function loadSettingsPage() {
    // Load alert rules
    try {
        const res = await apiFetch("/api/v1/drift/alerts/rules");
        if (res.ok) {
            const rules = await res.json();
            const tbody = document.getElementById("rules-tbody");
            const emptyState = document.getElementById("rules-empty");

            if (rules.length === 0) {
                tbody.innerHTML = "";
                if (emptyState) emptyState.style.display = "block";
            } else {
                if (emptyState) emptyState.style.display = "none";
                tbody.innerHTML = rules.map(r => `
                    <tr data-rule-id="${r.id}">
                        <td>${r.feature_name || "All"}</td>
                        <td>${(r.detector_type || "").toUpperCase()}</td>
                        <td><input type="number" class="rule-input" value="${r.threshold}" step="0.01" data-field="threshold"></td>
                        <td>
                            <select class="rule-select" data-field="severity">
                                <option value="critical" ${r.severity === "critical" ? "selected" : ""}>Critical</option>
                                <option value="warning" ${r.severity === "warning" ? "selected" : ""}>Warning</option>
                                <option value="info" ${r.severity === "info" ? "selected" : ""}>Info</option>
                            </select>
                        </td>
                        <td><span class="status-badge ${r.is_active ? "status-active" : "status-inactive"}">${r.is_active ? "Active" : "Inactive"}</span></td>
                        <td><button class="btn-save" onclick="saveRule('${r.id}', this)">Save</button></td>
                    </tr>`).join("");
            }
        }
    } catch (e) {
        console.error("Failed to load rules", e);
    }

    // Load system health
    try {
        const healthRes = await fetch("/api/v1/health");
        if (healthRes.ok) {
            const h = await healthRes.json();
            document.getElementById("sys-db-status").textContent = h.database === "up" ? "✅ Connected" : "❌ Down";
            document.getElementById("sys-redis-status").textContent = h.redis === "up" ? "✅ Connected" : "❌ Down";
        }
    } catch { }

    document.getElementById("sys-model-version").textContent = currentUser?.model_version || "v1.0.0";
    document.getElementById("sys-environment").textContent = "Production";
}

async function saveRule(ruleId, btn) {
    const row = btn.closest("tr");
    const threshold = parseFloat(row.querySelector("[data-field='threshold']").value);
    const severity = row.querySelector("[data-field='severity']").value;

    try {
        const res = await apiFetch(`/api/v1/drift/alerts/rules/${ruleId}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ threshold, severity })
        });

        if (res.ok) {
            btn.textContent = "✓ Saved";
            btn.style.background = "var(--green)";
            setTimeout(() => { btn.textContent = "Save"; btn.style.background = ""; }, 2000);
        } else {
            btn.textContent = "Error";
            btn.style.background = "var(--red)";
            setTimeout(() => { btn.textContent = "Save"; btn.style.background = ""; }, 2000);
        }
    } catch {
        btn.textContent = "Error";
        setTimeout(() => { btn.textContent = "Save"; btn.style.background = ""; }, 2000);
    }
}

// ═══════════════ CHARTS ═══════════════

function initCharts() {
    Chart.defaults.color = "#94a3b8";
    Chart.defaults.borderColor = "rgba(42, 45, 62, 0.5)";
    Chart.defaults.font.family = "'Inter', sans-serif";

    const barOptions = {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
            x: { grid: { display: false }, ticks: { font: { size: 11 } } },
            y: { beginAtZero: true, grid: { color: "rgba(42, 45, 62, 0.5)" }, ticks: { font: { size: 11 } } }
        },
        plugins: {
            legend: {
                display: true,
                labels: {
                    boxWidth: 12,
                    usePointStyle: true,
                    generateLabels: () => [
                        { text: "Stable", fillStyle: "#4ade80", strokeStyle: "#4ade80", lineWidth: 0 },
                        { text: "Warning", fillStyle: "#fb923c", strokeStyle: "#fb923c", lineWidth: 0 },
                        { text: "Critical", fillStyle: "#f87171", strokeStyle: "#f87171", lineWidth: 0 }
                    ]
                }
            }
        }
    };

    psiChart = new Chart(document.getElementById("psiChart"), {
        type: "bar",
        data: { labels: [], datasets: [{ data: [], backgroundColor: [], borderRadius: 4 }] },
        options: barOptions
    });

    klChart = new Chart(document.getElementById("klChart"), {
        type: "bar",
        data: { labels: [], datasets: [{ data: [], backgroundColor: [], borderRadius: 4 }] },
        options: barOptions
    });

    const timeOptions = {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
            x: {
                type: "linear",
                display: true,
                grid: { color: "rgba(42, 45, 62, 0.5)" },
                ticks: {
                    font: { size: 10 },
                    callback: function(val) {
                        const d = new Date(val);
                        return d.getHours().toString().padStart(2, "0") + ":" + d.getMinutes().toString().padStart(2, "0");
                    }
                }
            },
            y: { beginAtZero: true, grid: { color: "rgba(42, 45, 62, 0.5)" }, ticks: { font: { size: 11 } } }
        },
        plugins: { legend: { labels: { boxWidth: 12, usePointStyle: true } } }
    };

    psiTimeChart = new Chart(document.getElementById("psiTimeChart"), {
        type: "line",
        data: { datasets: [] },
        options: timeOptions
    });

    klTimeChart = new Chart(document.getElementById("klTimeChart"), {
        type: "line",
        data: { datasets: [] },
        options: timeOptions
    });
}

function updateBarCharts() {
    const fnames = Object.keys(featuresData);

    const psiData = fnames.map(f => featuresData[f].psi);
    const psiColors = psiData.map(v => v > 0.2 ? "#f87171" : (v > 0.1 ? "#fb923c" : "#4ade80"));

    psiChart.data.labels = fnames;
    psiChart.data.datasets[0].data = psiData;
    psiChart.data.datasets[0].backgroundColor = psiColors;
    psiChart.update();

    const klData = fnames.map(f => featuresData[f].kl);
    const klColors = klData.map(v => v > 0.15 ? "#f87171" : (v > 0.08 ? "#fb923c" : "#4ade80"));

    klChart.data.labels = fnames;
    klChart.data.datasets[0].data = klData;
    klChart.data.datasets[0].backgroundColor = klColors;
    klChart.update();
}

// ═══════════════ WEBSOCKET ═══════════════

function connectWebSocket() {
    const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${wsProto}//${window.location.host}/ws/live?token=${token}`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        document.getElementById("live-dot").classList.add("connected");
        document.getElementById("connection-text").textContent = "Connected";
        reconnectAttempts = 0;
        if (reconnectTimer) clearTimeout(reconnectTimer);
    };

    ws.onclose = () => {
        document.getElementById("live-dot").classList.remove("connected");
        document.getElementById("connection-text").textContent = "Disconnected";
        const backoff = Math.min(Math.pow(2, reconnectAttempts) * 1000, 30000);
        reconnectAttempts++;
        reconnectTimer = setTimeout(connectWebSocket, backoff);
    };

    ws.onerror = () => {
        document.getElementById("connection-text").textContent = "Error";
    };

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === "ping") {
            ws.send(JSON.stringify({ type: "pong" }));
            return;
        }

        if (msg.type === "score") {
            handleScoreData(msg.data);
            if (currentPage === "dashboard") updateBarCharts();
            blinkStage("stage-faust");
        } else if (msg.type === "alert") {
            recentAlerts.unshift(msg.data);
            if (recentAlerts.length > 20) recentAlerts.pop();
            unresolvedAlertCount++;
            updateNotificationBadge();

            if (currentPage === "dashboard") renderAlertFeed();
            blinkStage("stage-alert");

            if (msg.data.severity === "critical") {
                document.getElementById("stage-airflow")?.classList.add("firing");
                const banner = document.getElementById("retrain-banner");
                if (banner) banner.style.display = "flex";
                setTimeout(() => {
                    document.getElementById("stage-airflow")?.classList.remove("firing");
                    if (banner) banner.style.display = "none";
                    blinkStage("stage-mlflow");
                }, 5000);
            }
        }
    };
}

function blinkStage(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.add("active");
    setTimeout(() => el.classList.remove("active"), 1500);
}

// ═══════════════ UTILITIES ═══════════════

function updateClock() {
    const now = new Date();
    document.getElementById("utc-time").textContent = now.toISOString().substring(11, 19) + " UTC";
}
