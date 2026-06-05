let ws;
let token = localStorage.getItem("token");
let reconnectTimer = null;
let reconnectAttempts = 0;

const featuresData = {}; // Stores latest score by feature
const timeSeriesData = { labels: [], datasets: [] }; // for PSI over time
const alerts = [];

// Charts instances
let psiChart, klChart, psiTimeChart, distChart;

document.getElementById("login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = document.getElementById("username").value;
    const password = document.getElementById("password").value;
    
    try {
        const res = await fetch("/auth/token", {
            method: "POST",
            headers: {"Content-Type": "application/x-www-form-urlencoded"},
            body: new URLSearchParams({username, password})
        });
        
        if (res.ok) {
            const data = await res.json();
            token = data.access_token;
            localStorage.setItem("token", token);
            document.getElementById("login-container").style.display = "none";
            document.getElementById("dashboard-container").style.display = "block";
            initDashboard();
        } else {
            document.getElementById("login-error").style.display = "block";
        }
    } catch (err) {
        document.getElementById("login-error").style.display = "block";
    }
});

document.getElementById("logout-btn").addEventListener("click", () => {
    localStorage.removeItem("token");
    if(ws) ws.close();
    location.reload();
});

if (token) {
    document.getElementById("login-container").style.display = "none";
    document.getElementById("dashboard-container").style.display = "block";
    initDashboard();
}

function initDashboard() {
    initCharts();
    fetchHistoricalData();
    connectWebSocket();
    setInterval(updateClock, 1000);
}

async function fetchHistoricalData() {
    try {
        const scoreRes = await fetch("/api/v1/drift/scores?limit=50", {
            headers: {"Authorization": "Bearer " + token}
        });
        if (scoreRes.ok) {
            const scores = await scoreRes.json();
            // Process from oldest to newest to replay
            scores.reverse().forEach(score => handleScore(score));
        }

        const alertRes = await fetch("/api/v1/drift/alerts?limit=20", {
            headers: {"Authorization": "Bearer " + token}
        });
        if (alertRes.ok) {
            const histAlerts = await alertRes.json();
            histAlerts.reverse().forEach(a => handleAlert(a));
        }
    } catch (e) {
        console.error("Failed to load historical data", e);
    }
}

function connectWebSocket() {
    const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${wsProto}//${window.location.host}/ws/live?token=${token}`;
    
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        document.getElementById("live-dot").classList.add("connected");
        reconnectAttempts = 0;
        if(reconnectTimer) clearTimeout(reconnectTimer);
    };
    
    ws.onclose = () => {
        document.getElementById("live-dot").classList.remove("connected");
        // Reconnect with exponential backoff, max 30s
        const backoff = Math.min(Math.pow(2, reconnectAttempts) * 1000, 30000);
        reconnectAttempts++;
        reconnectTimer = setTimeout(connectWebSocket, backoff);
    };
    
    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === "ping") {
            ws.send(JSON.stringify({type: "pong"}));
            return;
        }
        
        if (msg.type === "score") {
            handleScore(msg.data);
            blinkStage("stage-faust");
        } else if (msg.type === "alert") {
            handleAlert(msg.data);
            blinkStage("stage-alert");
            if (msg.data.severity === "critical") {
                document.getElementById("stage-airflow").classList.add("firing");
                document.getElementById("retrain-banner").style.display = "block";
                setTimeout(() => {
                    document.getElementById("stage-airflow").classList.remove("firing");
                    document.getElementById("retrain-banner").style.display = "none";
                    blinkStage("stage-mlflow");
                }, 5000);
            }
        }
    };
}

function blinkStage(id) {
    const el = document.getElementById(id);
    el.classList.add("active");
    setTimeout(() => el.classList.remove("active"), 1000);
}

function handleScore(data) {
    const fname = data.feature_name;
    if (!featuresData[fname]) featuresData[fname] = { psi: 0, kl: 0 };
    
    if (data.detector_type === "psi") featuresData[fname].psi = data.score;
    if (data.detector_type === "kl") featuresData[fname].kl = data.score;
    if (data.detector_type === "mmd") {
        const pval = data.metadata ? data.metadata.p_value : data.score;
        document.getElementById("mmd-pvalue").innerText = pval ? pval.toFixed(4) : "N/A";
    }
    
    updateCards();
    updateBarCharts();
}

function handleAlert(data) {
    alerts.unshift(data);
    if (alerts.length > 20) alerts.pop();
    
    const list = document.getElementById("alert-list");
    list.innerHTML = "";
    alerts.forEach(a => {
        const li = document.createElement("li");
        const ts = new Date().toLocaleTimeString();
        li.innerHTML = `<span>[${ts}] <b>${a.feature_name}</b> - ${a.detector_type.toUpperCase()}: ${a.score.toFixed(4)}</span>
                        <span class="badge ${a.severity}">${a.severity.toUpperCase()}</span>`;
        list.appendChild(li);
    });
}

function updateCards() {
    const fnames = Object.keys(featuresData).filter(f => f !== 'multivariate');
    document.getElementById("features-monitored").innerText = fnames.length;
    
    let maxPsi = 0;
    let maxKl = 0;
    fnames.forEach(f => {
        if (featuresData[f].psi > maxPsi) maxPsi = featuresData[f].psi;
        if (featuresData[f].kl > maxKl) maxKl = featuresData[f].kl;
    });
    
    document.getElementById("max-psi").innerText = maxPsi.toFixed(4);
    document.getElementById("max-kl").innerText = maxKl.toFixed(4);
}

function updateClock() {
    document.getElementById("utc-time").innerText = new Date().toISOString().substr(11, 8) + " UTC";
}

function initCharts() {
    Chart.defaults.color = "#ccc";
    
    const barOptions = {
        responsive: true,
        maintainAspectRatio: false,
        scales: { y: { beginAtZero: true } },
        plugins: { legend: { display: false } }
    };

    psiChart = new Chart(document.getElementById("psiChart"), {
        type: 'bar',
        data: { labels: [], datasets: [{ data: [], backgroundColor: [] }] },
        options: { ...barOptions, plugins: { title: { display: true, text: 'PSI by Feature' } } }
    });

    klChart = new Chart(document.getElementById("klChart"), {
        type: 'bar',
        data: { labels: [], datasets: [{ data: [], backgroundColor: [] }] },
        options: { ...barOptions, plugins: { title: { display: true, text: 'KL Divergence by Feature' } } }
    });
}

function updateBarCharts() {
    const fnames = Object.keys(featuresData).filter(f => f !== 'multivariate');
    
    const psiData = fnames.map(f => featuresData[f].psi);
    const psiColors = psiData.map(v => v > 0.2 ? '#f44336' : (v > 0.1 ? '#ff9800' : '#4caf50'));
    
    psiChart.data.labels = fnames;
    psiChart.data.datasets[0].data = psiData;
    psiChart.data.datasets[0].backgroundColor = psiColors;
    psiChart.update();
    
    const klData = fnames.map(f => featuresData[f].kl);
    const klColors = klData.map(v => v > 0.15 ? '#f44336' : '#4caf50');
    
    klChart.data.labels = fnames;
    klChart.data.datasets[0].data = klData;
    klChart.data.datasets[0].backgroundColor = klColors;
    klChart.update();
}
