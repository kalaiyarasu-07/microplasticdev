const API = "http://127.0.0.1:5000";
let activeDataset = "aquapulse_sample_dataset";
let currentPlot = null;
let datasets = [];
let gpsMap = null;

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 2600);
}

async function api(path, options = {}) {
  const res = await fetch(API + path, options);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
}

function plotConfig() {
  return {responsive:true,displaylogo:false,modeBarButtonsToRemove:["lasso2d","select2d"]};
}

function darkLayout(extra={}) {
  return Object.assign({
    paper_bgcolor:"#17131F",plot_bgcolor:"#17131F",font:{family:"Inter",color:"#FFFFFF",size:10},
    margin:{l:42,r:18,t:18,b:38},showlegend:false,
    xaxis:{gridcolor:"#30263D",linecolor:"#30263D",tickcolor:"#30263D"},
    yaxis:{gridcolor:"#30263D",linecolor:"#30263D",tickcolor:"#30263D"}
  },extra);
}

$$(".nav-item").forEach(btn => btn.addEventListener("click", () => {
  $$(".nav-item").forEach(n => n.classList.remove("active"));
  btn.classList.add("active");
  $$(".page").forEach(p => p.classList.remove("active"));
  const page = btn.dataset.page;
  $("#" + page)?.classList.add("active");
  $("#pageTitle").textContent = btn.querySelector("span:last-child").textContent;
  $("#sidebar").classList.remove("open");
  if (page === "gps") setTimeout(initMap,100);
  if (page === "monitoring") initMonitoring();
}));

$("#menuToggle").addEventListener("click", () => $("#sidebar").classList.toggle("open"));

async function loadDashboard() {
  const data = await api("/api/dashboard/summary?dataset=" + activeDataset);
  const kpis = [
    ["Observations","observations","◷",true],["Active devices","devices","⌘",true],
    ["Avg. piezoelectric","average_piezo","⌁",false],["Avg. ultrasonic","average_ultrasonic","≋",false],
    ["Particle-like responses","particle_responses","◉",true],["Normal observations","normal_observations","✓",true],
    ["Further analysis","further_analysis","⚠",true],["Latest timestamp","latest_timestamp","◷",false]
  ];
  $("#kpiGrid").innerHTML = kpis.map(([label,key,icon,number]) => {
    let value = data[key];
    if (key === "latest_timestamp" && value) value = new Date(value).toLocaleString([], {month:"short",day:"2-digit",hour:"2-digit",minute:"2-digit"});
    if (typeof value === "number" && number) value = value.toLocaleString();
    return `<div class="kpi-card"><div class="kpi-icon">${icon}</div><p>${label}</p><h2>${value ?? "—"}</h2><small><i>●</i> Live dataset</small></div>`;
  }).join("");

  const readings = data.readings;
  Plotly.newPlot("telemetryChart",[{
    x:readings.map(r=>r.timestamp),y:readings.map(r=>r.piezo),name:"Piezoelectric",mode:"lines",line:{color:"#8B5CF6",width:2},
  },{
    x:readings.map(r=>r.timestamp),y:readings.map(r=>r.ultrasonic),name:"Ultrasonic",mode:"lines",line:{color:"#C4B5FD",width:2,yaxis:"y2"}
  }],darkLayout({showlegend:true,legend:{orientation:"h",x:0,y:1.12,font:{size:9}},yaxis:{title:"Piezo",gridcolor:"#30263D"},yaxis2:{title:"Ultrasonic",overlaying:"y",side:"right",gridcolor:"transparent"}}),plotConfig());

  const cls = data.classification;
  Plotly.newPlot("classificationChart",[{
    labels:Object.keys(cls),values:Object.values(cls),type:"pie",hole:.68,
    marker:{colors:["#7C3AED","#A78BFA","#30263D"]},textinfo:"percent",textfont:{color:"#fff",size:9},
    hoverinfo:"label+value"
  }],darkLayout({showlegend:true,legend:{orientation:"h",y:-.08,font:{size:8}}}),plotConfig());

  const devices = Object.entries(data.devices_counts);
  const energyValues = readings.map(r => Math.abs(r.piezo)).slice(0,60);
  while (energyValues.length < 60) energyValues.push(0);
  Plotly.newPlot("energyChart",[{
    x:Array.from({length:60},(_,i)=>i),y:energyValues,
    type:"bar",marker:{color:"#8B5CF6",opacity:.75}
  }],darkLayout({bargap:.18}),plotConfig());

  const daily = Object.entries(data.daily);
  Plotly.newPlot("dailyChart",[{
    x:daily.map(d=>d[0]),y:daily.map(d=>d[1]),type:"scatter",mode:"lines+markers",
    fill:"tozeroy",line:{color:"#8B5CF6",width:2},fillcolor:"rgba(124,58,237,.18)",
    marker:{color:"#C4B5FD",size:5}
  }],darkLayout({}),plotConfig());
}

async function loadDatasets() {
  datasets = await api("/api/datasets");
  const names = ["dashboardDevice","gpsDevice"];
  names.forEach(id => {
    const el = $("#" + id);
    if (!el) return;
    const all = el.options[0].outerHTML;
    el.innerHTML = all;
  });
  const devices = await api("/api/dashboard/summary?dataset=" + activeDataset);
  Object.keys(devices.devices_counts).forEach(d => {
    if ($("#dashboardDevice")) $("#dashboardDevice").add(new Option(d,d));
    if ($("#gpsDevice")) $("#gpsDevice").add(new Option(d,d));
  });
  const gpsClasses = ["Normal Water Observation","Particle-Like Response","Requires Further Analysis"];
  gpsClasses.forEach(c => { if ($("#gpsClass")) $("#gpsClass").add(new Option(c,c)); });
  $("#datasetList").innerHTML = datasets.map(ds => `
    <button class="dataset-card ${ds.id===activeDataset?"active":""}" data-id="${ds.id}">
      <strong>${ds.name}</strong><small>${ds.rows.toLocaleString()} rows · ${ds.columns} columns</small>
    </button>`).join("");
  $$(".dataset-card").forEach(card => card.onclick = () => selectDataset(card.dataset.id));
  await refreshDatasetPreview();
  await loadVizDatasets();
}

async function refreshDatasetPreview() {
  const ds = datasets.find(d=>d.id===activeDataset);
  if (!ds) return;
  $("#datasetName").textContent = ds.name;
  $("#datasetMeta").textContent = `${ds.rows.toLocaleString()} rows · ${ds.columns} columns`;
  const preview = await api(`/api/datasets/${activeDataset}/preview?limit=12`);
  $("#previewHead").innerHTML = "<tr>"+preview.columns.map(c=>`<th>${c}</th>`).join("")+"</tr>";
  $("#previewBody").innerHTML = preview.rows.map(row=>"<tr>"+preview.columns.map(c=>`<td>${row[c] ?? ""}</td>`).join("")+"</tr>").join("");
}

async function selectDataset(id) {
  activeDataset = id;
  $$(".dataset-card").forEach(c => c.classList.toggle("active",c.dataset.id===id));
  await refreshDatasetPreview();
  await loadDashboard();
  await loadVizColumns();
  toast("Active dataset changed");
}

async function loadVizDatasets() {
  $("#vizDataset").innerHTML = datasets.map(d=>`<option value="${d.id}" ${d.id===activeDataset?"selected":""}>${d.name}</option>`).join("");
  await loadVizColumns();
}

async function loadVizColumns() {
  const id = $("#vizDataset").value || activeDataset;
  const cols = await api(`/api/datasets/${id}/columns`);
  const fill = (el,includeOption) => {
    const options = cols.map(c=>`<option value="${c.name}">${c.name}</option>`).join("");
    el.innerHTML = includeOption ? `<option value="">None</option>${options}` : options;
  };
  fill($("#vizX"),true); fill($("#vizY"),true); fill($("#vizColor"),true); fill($("#analyticsField"),false);
  const timestamp = cols.find(c=>c.name==="Timestamp"); if(timestamp) $("#vizX").value="Timestamp";
  const numeric = cols.find(c=>c.type==="numeric"); if(numeric) $("#vizY").value=numeric.name;
  if ($("#analyticsField").querySelector('[value="Piezoelectric_Reading"]')) $("#analyticsField").value="Piezoelectric_Reading";
}

async function generateChart() {
  $("#chartStatus").textContent="Processing data...";
  try {
    const body = {
      dataset:$("#vizDataset").value,
      chartType:$("#vizType").value,
      x:$("#vizX").value,
      y:$("#vizY").value,
      color:$("#vizColor").value,
      title:$("#vizTitle").value
    };
    const res = await api("/api/visualization/generate", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    currentPlot=res.plotly;
    Plotly.react("mainChart",res.plotly.data,res.plotly.layout,Object.assign(plotConfig(),{responsive:true}));
    $("#chartStatus").textContent="Chart generated";
  } catch(e) { $("#chartStatus").textContent=e.message; toast(e.message); }
}

async function loadSaved() {
  const items=await api("/api/visualization/saved");
  $("#savedCount").textContent=`${items.length} saved`;
  $("#savedCharts").innerHTML=items.length?items.map(v=>`<div class="saved-card"><h4>${v.title||"Visualization"}</h4><p>${v.chartType||"Chart"} · ${v.dataset||"Dataset"}</p><button class="secondary-button" onclick="deleteSaved('${v.id}')">Delete</button></div>`).join(""):`<div class="saved-card"><p>No saved visualizations yet.</p></div>`;
}

window.deleteSaved=async id=>{await api("/api/visualization/saved/"+id,{method:"DELETE"});loadSaved();toast("Visualization deleted");};

$("#generateChart").addEventListener("click",generateChart);
$("#saveChart").addEventListener("click",async()=>{
  const body={dataset:$("#vizDataset").value,chartType:$("#vizType").value,title:$("#vizTitle").value,x:$("#vizX").value,y:$("#vizY").value};
  await api("/api/visualization/save",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  loadSaved();toast("Visualization saved");
});
$("#resetChart").addEventListener("click",()=>{ $("#vizType").value="Line Chart";$("#vizTitle").value="Sensor performance analysis";$("#vizX").value="Timestamp";$("#vizY").value="Piezoelectric_Reading";Plotly.purge("mainChart");$("#chartStatus").textContent="Ready to visualize"; });
$("#downloadPNG").addEventListener("click",()=>Plotly.downloadImage("mainChart",{format:"png",filename:"aquapulse-chart"}));
$("#downloadCSV").addEventListener("click",()=>{
  if(!currentPlot) return toast("Generate a chart first");
  const traces=currentPlot.data||[];let csv="series,x,y\n";
  traces.forEach(t=>{const xs=t.x||[],ys=t.y||[];ys.forEach((y,i)=>csv+=`"${t.name||"series"}","${xs[i]??i}","${y}"\n`);});
  const blob=new Blob([csv],{type:"text/csv"});const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="aquapulse-chart.csv";a.click();
});

async function runAnalytics() {
  const field=$("#analyticsField").value;
  try {
    const stats=await api("/api/analytics/statistics",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({dataset:activeDataset,field})});
    $("#analyticsKpis").innerHTML=[["Mean",stats.mean],["Median",stats.median],["Std. deviation",stats.std],["Maximum",stats.max]].map(v=>`<div class="kpi-card"><p>${v[0]}</p><h2>${Number(v[1]).toFixed(3)}</h2><small><i>●</i> Calculated</small></div>`).join("");
    const out=await api("/api/analytics/outlier-detection",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({dataset:activeDataset,field,method:$("#analyticsMethod").value})});
    Plotly.newPlot("analyticsChart",[{
      x:out.indices.map((_,i)=>i),y:out.values,type:"scatter",mode:"markers",marker:{color:"#8B5CF6",size:7},
      name:"Outliers"
    }],darkLayout({title:{text:`${out.count} detected outliers`,font:{size:11,color:"#C4B5FD"}}}),plotConfig());
  } catch(e){toast(e.message);}
}
$("#runAnalytics").addEventListener("click",runAnalytics);

function initMonitoring() {
  const traceX=Array.from({length:120},(_,i)=>i);
  const vals=traceX.map(i=>.8+Math.sin(i/8)*.18+Math.sin(i/3)*.08);
  Plotly.newPlot("liveSignal",[{
    x:traceX,y:vals,type:"scatter",mode:"lines",line:{color:"#8B5CF6",width:2},
    fill:"tozeroy",fillcolor:"rgba(124,58,237,.12)"
  }],darkLayout({}),plotConfig());
  $("#deviceStatus").innerHTML=["AP-01","AP-02","AP-03","AP-04"].map((d,i)=>`<div class="status-row"><span><i></i>${d}</span><strong>${i===3?"Standby":"Streaming"}</strong></div>`).join("");
}

async function initMap() {
  if (!$("#gpsMap")) return;
  if (!gpsMap) gpsMap=L.map("gpsMap",{attributionControl:true}).setView([12.9716,77.5946],10);
  else gpsMap.eachLayer(layer=>{if(!!layer.toGeoJSON)gpsMap.removeLayer(layer)});
  L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",{subdomains:"abcd",maxZoom:20,attribution:"&copy; OpenStreetMap"}).addTo(gpsMap);
  let path="/api/gps/observations?dataset="+activeDataset;
  if($("#gpsDevice").value)path+="&device="+encodeURIComponent($("#gpsDevice").value);
  if($("#gpsClass").value)path+="&classification="+encodeURIComponent($("#gpsClass").value);
  try {
    const points=await api(path);
    points.slice(0,500).forEach(p=>{
      L.circleMarker([p.Latitude,p.Longitude],{radius:5,color:"#C4B5FD",fillColor:"#7C3AED",fillOpacity:.85,weight:1}).bindPopup(`<b>${p.Observation_ID}</b><br>${p.Device_ID}<br>${p.Classification}<br>${p.Timestamp}`).addTo(gpsMap);
    });
  } catch(e){toast(e.message);}
}
$("#gpsDevice").addEventListener("change",initMap);
$("#gpsClass").addEventListener("change",initMap);

$("#csvUpload").addEventListener("change",async e=>{
  if(!e.target.files[0])return;
  const form=new FormData();form.append("file",e.target.files[0]);
  try {const res=await api("/api/datasets/upload",{method:"POST",body:form});activeDataset=res.id;await loadDatasets();await loadDashboard();toast("CSV uploaded successfully");}
  catch(err){toast(err.message);}
});

async function generateReport() {
  try {const report=await api("/api/reports/generate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({dataset:activeDataset})});window.open(API+report.url,"_blank");toast("Report generated");}
  catch(e){toast(e.message);}
}
$("#generateReport").addEventListener("click",generateReport);
$$(".report-action").forEach(b=>b.addEventListener("click",generateReport));
$("#refreshDashboard").addEventListener("click",()=>{loadDashboard();toast("Dashboard refreshed");});
$("#dashboardDevice").addEventListener("change",()=>{api("/api/dashboard/summary?dataset="+activeDataset+"&device="+encodeURIComponent($("#dashboardDevice").value)).then(data=>toast(data.observations+" observations displayed"));});

async function init() {
  await loadDatasets();
  await loadDashboard();
  const types=["Line Chart","Bar Chart","Horizontal Bar Chart","Scatter Plot","Area Chart","Pie Chart","Donut Chart","Histogram","Box Plot","Violin Plot","Heatmap","Correlation Matrix","Bubble Chart","3D Scatter Plot","Time Series Line Chart","Moving Average Chart","Distribution Plot","Outlier Visualization"];
  $("#vizType").innerHTML=types.map(t=>`<option>${t}</option>`).join("");
  await loadSaved();
  initMonitoring();
}
init().catch(e=>toast("Backend unavailable: "+e.message));
