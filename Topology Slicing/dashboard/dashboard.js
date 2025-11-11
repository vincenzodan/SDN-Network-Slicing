let ws = new WebSocket("ws://localhost:8765/");
let barChart, latencyChart;
let latencyHistory = {};
let timeLabels = [];
const MAX_POINTS = 20;

// filtri
const filterDPID = document.getElementById("filter-dpid");
const filterPort = document.getElementById("filter-port");

ws.onmessage = function(event) {
    let data = JSON.parse(event.data);
    if (data.type !== "bandwidth_stats") return;

    let labels = [], values = [], tableHTML = `<tr>
        <th>DPID</th><th>Port</th><th>RX Mbps</th><th>TX Mbps</th><th>Total Mbps</th><th>Latenza (ms)</th>
    </tr>`;

    let timestamp = new Date().toLocaleTimeString();
    if (timeLabels.length >= MAX_POINTS) timeLabels.shift();
    timeLabels.push(timestamp);

    // aggiorno filtri
    let dpids = new Set(), ports = new Set();

    data.stats.forEach(s => {
        dpids.add(s.dpid);
        ports.add(s.port_no);
    });

    updateFilterOptions(filterDPID, dpids);
    updateFilterOptions(filterPort, ports);

    data.stats.forEach(s => {
        if ((filterDPID.value !== "all" && s.dpid != filterDPID.value) ||
            (filterPort.value !== "all" && s.port_no != filterPort.value)) return;

        labels.push(`dp${s.dpid}-p${s.port_no}`);
        let rx = s.rx_mbps?.toFixed(2) || 0;
        let tx = s.tx_mbps?.toFixed(2) || 0;
        let total = (parseFloat(rx) + parseFloat(tx)).toFixed(2);
        values.push(total);

        let latency = s.latency_ms?.toFixed(2) || "-";
        tableHTML += `<tr>
            <td>${s.dpid}</td><td>${s.port_no}</td><td>${rx}</td><td>${tx}</td><td>${total}</td><td>${latency}</td>
        </tr>`;

        if (s.latency_ms != null) {
            if (!latencyHistory[s.dpid]) latencyHistory[s.dpid] = [];
            if (latencyHistory[s.dpid].length >= MAX_POINTS) latencyHistory[s.dpid].shift();
            latencyHistory[s.dpid].push(s.latency_ms);
        }
    });

    document.getElementById("port-stats").innerHTML = tableHTML;
    updateBarChart(labels, values);
    updateLatencyChart();
};

function updateFilterOptions(select, valuesSet) {
    let existing = Array.from(select.options).map(o => o.value);
    valuesSet.forEach(val => {
        if (!existing.includes(val.toString())) {
            let option = document.createElement("option");
            option.value = val;
            option.text = val;
            select.add(option);
        }
    });
}

// BAR CHART
function updateBarChart(labels, values) {
    if (!barChart) {
        let ctx = document.getElementById("bandwidth-bar").getContext("2d");
        barChart = new Chart(ctx, {
            type: 'bar',
            data: { labels, datasets: [{ label: 'Banda totale (Mbps)', data: values, backgroundColor: 'rgba(52, 152, 219, 0.7)', borderColor: 'rgba(41, 128, 185,1)', borderWidth:1 }]},
            options: { responsive:true, scales: { y:{beginAtZero:true,title:{display:true,text:'Mbps'}}, x:{title:{display:true,text:'Switch-Port'}} } }
        });
    } else {
        barChart.data.labels = labels;
        barChart.data.datasets[0].data = values;
        barChart.update();
    }
}

// LATENCY CHART
function updateLatencyChart() {
    let latencyDatasets = Object.keys(latencyHistory).map(dpid => ({
        label: `Switch ${dpid}`,
        data: latencyHistory[dpid],
        fill: false,
        borderColor: getColor(dpid),
        tension: 0.1
    }));
    if (!latencyChart) {
        let ctx2 = document.getElementById("latency-line").getContext("2d");
        latencyChart = new Chart(ctx2, { type:'line', data:{labels: timeLabels, datasets: latencyDatasets},
            options:{ responsive:true, scales:{y:{beginAtZero:true,title:{display:true,text:'ms'}},x:{title:{display:true,text:'Tempo'}}}, plugins:{legend:{position:'top'},title:{display:true,text:'Latenza per switch (ms)'}}}});
    } else {
        latencyChart.data.labels = [...timeLabels];
        latencyChart.data.datasets = latencyDatasets;
        latencyChart.update();
    }
}

function getColor(key) {
    const colors = ['rgba(231,76,60,1)','rgba(46,204,113,1)','rgba(52,152,219,1)','rgba(241,196,15,1)','rgba(155,89,182,1)'];
    return colors[key % colors.length];
}
