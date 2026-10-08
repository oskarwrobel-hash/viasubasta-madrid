const state = { auctions: [] };

const $ = id => document.getElementById(id);

function money(value) {
  if (value === null || value === undefined || value === "") return "—";
  return new Intl.NumberFormat("en-GB", {
    style: "currency", currency: "EUR", maximumFractionDigits: 2
  }).format(Number(value));
}

function normaliseStatus(s) {
  const x = String(s || "").toLowerCase();
  if (x.includes("active") || x.includes("activa") || x.includes("activo")) return "active";
  if (x.includes("upcoming") || x.includes("proxim") ) return "upcoming";
  if (x.includes("not_seen")) return "not_seen";
  return x || "unknown";
}

function imageUrl(path) {
  if (!path) return "";
  // JSON is served from /data and image paths are relative to /data.
  return "../data/" + path.replace(/^data\//, "");
}

function card(a) {
  const img = a.image ? imageUrl(a.image) : "";
  const status = normaliseStatus(a.status);
  return `
    <article class="card">
      <div class="photo">
        ${img ? `<img src="${img}" loading="lazy" alt="">` : `<div class="no-photo">NO PHOTO</div>`}
      </div>
      <div class="card-body">
        <div class="ref">REF. ${escapeHtml(a.reference || a.id || "")}</div>
        <div class="title">${escapeHtml(a.title || "Untitled auction")}</div>
        <div class="row">
          <div class="price">${money(a.current_bid)}</div>
          <div class="status">${escapeHtml(status)}</div>
        </div>
        ${a.url ? `<a class="link" href="${escapeAttr(a.url)}" target="_blank" rel="noopener">VIEW ORIGINAL AUCTION ↗</a>` : ""}
      </div>
    </article>
  `;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
  }[c]));
}

function escapeAttr(value) {
  return escapeHtml(value);
}

function render() {
  const q = $("search").value.trim().toLowerCase();
  const status = $("status").value;
  const min = Number($("minPrice").value || 0);
  const maxRaw = $("maxPrice").value;
  const max = maxRaw === "" ? Infinity : Number(maxRaw);
  const sort = $("sort").value;

  let list = state.auctions.filter(a => {
    const text = `${a.title || ""} ${a.reference || ""} ${a.id || ""}`.toLowerCase();
    const price = Number(a.current_bid);
    return (!q || text.includes(q))
      && (!status || normaliseStatus(a.status) === status)
      && (Number.isNaN(price) || price >= min)
      && (Number.isNaN(price) || price <= max);
  });

  if (sort === "price-low") list.sort((a,b)=>(Number(a.current_bid)||Infinity)-(Number(b.current_bid)||Infinity));
  if (sort === "price-high") list.sort((a,b)=>(Number(b.current_bid)||0)-(Number(a.current_bid)||0));
  if (sort === "reference") list.sort((a,b)=>String(a.reference).localeCompare(String(b.reference), undefined, {numeric:true}));
  if (sort === "newest") list.sort((a,b)=>String(b.last_seen).localeCompare(String(a.last_seen)));

  $("count").textContent = list.length.toLocaleString();
  $("grid").innerHTML = list.length
    ? list.map(card).join("")
    : `<div style="grid-column:1/-1;padding:60px;text-align:center;color:#777">No auctions found.</div>`;
}

async function load() {
  try {
    const response = await fetch("../data/auctions.json", {cache:"no-store"});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    state.auctions = Array.isArray(data) ? data : Object.values(data);

    const latest = state.auctions
      .map(a => a.last_seen)
      .filter(Boolean)
      .sort()
      .pop();

    $("updated").textContent = latest ? `Last data update: ${new Date(latest).toLocaleString()}` : "Catalogue ready";
    $("footerUpdated").textContent = latest ? ` Last update: ${new Date(latest).toLocaleString()}.` : "";
    render();
  } catch (err) {
    $("error").classList.remove("hidden");
    $("error").textContent = "Could not load auction data. Run the scraper and make sure data/auctions.json exists.";
    console.error(err);
  }
}

["search","status","minPrice","maxPrice","sort"].forEach(id => {
  $(id).addEventListener("input", render);
  $(id).addEventListener("change", render);
});

load();
