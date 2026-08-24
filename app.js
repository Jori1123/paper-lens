const state = {
  papers: [],
  filtered: [],
  query: "",
  fields: new Set(),
  yearFrom: new Date().getFullYear() - 9,
  yearTo: new Date().getFullYear(),
  openAccessOnly: false,
  sortBy: "relevance",
  visible: 6,
};

const $ = (selector) => document.querySelector(selector);
const els = {
  searchForm: $("#searchForm"),
  searchInput: $("#searchInput"),
  yearFrom: $("#yearFrom"),
  yearTo: $("#yearTo"),
  fieldFilters: $("#fieldFilters"),
  openAccessOnly: $("#openAccessOnly"),
  sortBy: $("#sortBy"),
  paperList: $("#paperList"),
  resultCount: $("#resultCount"),
  loadMore: $("#loadMore"),
  activeFilters: $("#activeFilters"),
  updatedAt: $("#updatedAt"),
  reader: $("#reader"),
};

const normalize = (value = "") => value.toLocaleLowerCase("zh-CN").normalize("NFKC");

function searchableText(paper) {
  return normalize([
    paper.title, paper.title_zh, paper.abstract, paper.abstract_zh,
    paper.authors?.join(" "), paper.topics?.join(" "), paper.doi, paper.field,
  ].join(" "));
}

function scoreRelevance(paper, terms) {
  if (!terms.length) return paper.popularity || 0;
  const title = normalize(`${paper.title} ${paper.title_zh}`);
  const topics = normalize(paper.topics?.join(" "));
  const all = searchableText(paper);
  return terms.reduce((score, term) => {
    if (title.includes(term)) score += 8;
    if (topics.includes(term)) score += 4;
    if (all.includes(term)) score += 1;
    return score;
  }, 0);
}

function filterAndSort() {
  const terms = normalize(state.query).split(/\s+/).filter(Boolean);
  state.filtered = state.papers.filter((paper) => {
    const matchesQuery = terms.every((term) => searchableText(paper).includes(term));
    const matchesField = !state.fields.size || state.fields.has(paper.field);
    const matchesYear = paper.year >= state.yearFrom && paper.year <= state.yearTo;
    const matchesAccess = !state.openAccessOnly || paper.open_access;
    return matchesQuery && matchesField && matchesYear && matchesAccess;
  });

  const sorters = {
    relevance: (a, b) => scoreRelevance(b, terms) - scoreRelevance(a, terms) || b.year - a.year,
    newest: (a, b) => b.year - a.year || (b.citations || 0) - (a.citations || 0),
    oldest: (a, b) => a.year - b.year || (b.citations || 0) - (a.citations || 0),
    popular: (a, b) => (b.popularity || 0) - (a.popularity || 0),
    cited: (a, b) => (b.citations || 0) - (a.citations || 0),
  };
  state.filtered.sort(sorters[state.sortBy]);
  render();
}

function createBadge(text, type = "") {
  const span = document.createElement("span");
  span.className = `badge ${type}`;
  span.textContent = text;
  return span;
}

function safeHttpUrl(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

function getPdfUrl(paper) {
  const direct = safeHttpUrl(paper.pdf_url);
  if (direct) return direct;
  const arxivUrl = safeHttpUrl(paper.url);
  if (arxivUrl && /arxiv\.org\/abs\//i.test(arxivUrl)) {
    return arxivUrl.replace(/\/abs\//i, "/pdf/").replace(/\/$/, "") + ".pdf";
  }
  const arxivDoi = String(paper.doi || "").match(/10\.48550\/arxiv\.([^/?#]+)/i);
  return arxivDoi ? `https://arxiv.org/pdf/${arxivDoi[1]}.pdf` : "";
}

function renderPaper(paper) {
  const card = $("#paperTemplate").content.firstElementChild.cloneNode(true);
  card.dataset.id = paper.id;
  const badges = card.querySelector(".paper-badges");
  badges.append(createBadge(paper.field));
  badges.append(createBadge(String(paper.year), "year"));
  if (paper.open_access) badges.append(createBadge("OPEN ACCESS", "oa"));
  card.querySelector("h3").textContent = paper.title;
  card.querySelector(".title-zh").textContent = paper.title_zh || "中文标题待生成";
  card.querySelector(".authors").textContent = `${paper.authors?.join(" · ") || "作者未知"} · ${paper.venue || "预印本"}`;
  card.querySelector(".abstract").textContent = paper.abstract_zh || paper.abstract || "暂无摘要";
  const topics = card.querySelector(".topics");
  (paper.topics || []).slice(0, 4).forEach((topic) => {
    const span = document.createElement("span");
    span.textContent = topic;
    topics.append(span);
  });
  card.querySelector(".citation").textContent = `${Number(paper.citations || 0).toLocaleString()} 次引用`;
  card.querySelector(".popularity").textContent = `知名度 ${paper.popularity || 0}`;
  const pdfUrl = getPdfUrl(paper);
  const pdfButton = card.querySelector(".pdf-button");
  if (paper.open_access && pdfUrl) {
    pdfButton.hidden = false;
    pdfButton.addEventListener("click", () => openPdfReader(paper, pdfUrl));
  }
  card.querySelector(".read-button").addEventListener("click", () => openReader(paper));
  card.querySelector("h3").addEventListener("click", () => openReader(paper));
  const save = card.querySelector(".save-button");
  const saved = JSON.parse(localStorage.getItem("paper-lens-saved") || "[]");
  if (saved.includes(paper.id)) {
    save.classList.add("saved");
    save.textContent = "★";
  }
  save.addEventListener("click", () => toggleSaved(paper.id, save));
  return card;
}

function toggleSaved(id, button) {
  const saved = new Set(JSON.parse(localStorage.getItem("paper-lens-saved") || "[]"));
  saved.has(id) ? saved.delete(id) : saved.add(id);
  localStorage.setItem("paper-lens-saved", JSON.stringify([...saved]));
  button.classList.toggle("saved", saved.has(id));
  button.textContent = saved.has(id) ? "★" : "☆";
}

function renderActiveFilters() {
  els.activeFilters.replaceChildren();
  if (state.query) addFilterChip(`搜索：${state.query}`, () => {
    state.query = "";
    els.searchInput.value = "";
  });
  state.fields.forEach((field) => addFilterChip(field, () => {
    state.fields.delete(field);
    const checkbox = [...els.fieldFilters.querySelectorAll("input")].find((input) => input.value === field);
    if (checkbox) checkbox.checked = false;
  }));
  if (state.openAccessOnly) addFilterChip("开放获取", () => {
    state.openAccessOnly = false;
    els.openAccessOnly.checked = false;
  });
}

function addFilterChip(label, remove) {
  const button = document.createElement("button");
  button.textContent = `${label} ×`;
  button.addEventListener("click", () => {
    remove();
    state.visible = 6;
    filterAndSort();
  });
  els.activeFilters.append(button);
}

function render() {
  els.resultCount.textContent = state.filtered.length.toLocaleString();
  els.paperList.replaceChildren();
  const shown = state.filtered.slice(0, state.visible);
  if (!shown.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.innerHTML = "<strong>没有找到匹配论文</strong>尝试缩短关键词，或放宽年份与领域筛选。";
    els.paperList.append(empty);
  } else {
    shown.forEach((paper) => els.paperList.append(renderPaper(paper)));
  }
  els.loadMore.hidden = shown.length >= state.filtered.length;
  renderActiveFilters();
}

function openReader(paper) {
  $("#readerYear").textContent = paper.year;
  $("#readerField").textContent = paper.field;
  $("#readerCitations").textContent = `${Number(paper.citations || 0).toLocaleString()} 次引用`;
  $("#readerTitle").textContent = paper.title;
  $("#readerAuthors").textContent = `${paper.authors?.join(" · ") || "作者未知"} · ${paper.venue || "预印本"}`;
  $("#readerOriginal").textContent = paper.abstract || "The original abstract is not available.";
  $("#readerTranslation").textContent = paper.abstract_zh || "该论文的中文摘要仍在翻译队列中。";
  $("#readerLink").href = safeHttpUrl(paper.url) || (paper.doi ? `https://doi.org/${paper.doi}` : "#");
  const pdfUrl = getPdfUrl(paper);
  const pdfButton = $("#readerPdf");
  pdfButton.hidden = !(paper.open_access && pdfUrl);
  pdfButton.onclick = paper.open_access && pdfUrl
    ? () => {
        els.reader.close();
        openPdfReader(paper, pdfUrl);
      }
    : null;
  const topics = $("#readerTopics");
  topics.replaceChildren();
  (paper.topics || []).forEach((topic) => {
    const span = document.createElement("span");
    span.textContent = topic;
    topics.append(span);
  });
  setReaderView("split");
  els.reader.showModal();
}

function openPdfReader(paper, pdfUrl = getPdfUrl(paper)) {
  if (!pdfUrl) return;
  $("#pdfTitle").textContent = paper.title_zh || paper.title;
  $("#pdfExternal").href = pdfUrl;
  $("#pdfFrame").src = pdfUrl;
  $("#pdfReader").showModal();
}

function closePdfReader() {
  $("#pdfReader").close();
  $("#pdfFrame").src = "about:blank";
}

function setReaderView(view) {
  $("#readerColumns").className = `reader-columns ${view}`;
  document.querySelectorAll(".reader-tabs button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
}

function setupFilters() {
  const currentYear = new Date().getFullYear();
  for (let year = currentYear - 9; year <= currentYear; year += 1) {
    els.yearFrom.add(new Option(year, year));
    els.yearTo.add(new Option(year, year));
  }
  els.yearFrom.value = state.yearFrom;
  els.yearTo.value = state.yearTo;

  const fieldCounts = new Map();
  state.papers.forEach((paper) => fieldCounts.set(paper.field, (fieldCounts.get(paper.field) || 0) + 1));
  els.fieldFilters.replaceChildren();
  [...fieldCounts.entries()].sort((a, b) => b[1] - a[1]).forEach(([field, count]) => {
    const label = document.createElement("label");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = field;
    input.addEventListener("change", () => {
      input.checked ? state.fields.add(field) : state.fields.delete(field);
      state.visible = 6;
      filterAndSort();
    });
    const text = document.createElement("span");
    text.textContent = field;
    const small = document.createElement("small");
    small.textContent = count;
    label.append(input, text, small);
    els.fieldFilters.append(label);
  });
}

function bindEvents() {
  els.searchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    state.query = els.searchInput.value.trim();
    state.visible = 6;
    filterAndSort();
    document.querySelector(".workspace").scrollIntoView({ behavior: "smooth" });
  });
  document.querySelectorAll(".trending button").forEach((button) => {
    button.addEventListener("click", () => {
      els.searchInput.value = button.dataset.query;
      state.query = button.dataset.query;
      state.visible = 6;
      filterAndSort();
    });
  });
  els.yearFrom.addEventListener("change", () => {
    state.yearFrom = Number(els.yearFrom.value);
    if (state.yearFrom > state.yearTo) {
      state.yearTo = state.yearFrom;
      els.yearTo.value = state.yearTo;
    }
    state.visible = 6;
    filterAndSort();
  });
  els.yearTo.addEventListener("change", () => {
    state.yearTo = Number(els.yearTo.value);
    if (state.yearTo < state.yearFrom) {
      state.yearFrom = state.yearTo;
      els.yearFrom.value = state.yearFrom;
    }
    state.visible = 6;
    filterAndSort();
  });
  els.openAccessOnly.addEventListener("change", () => {
    state.openAccessOnly = els.openAccessOnly.checked;
    state.visible = 6;
    filterAndSort();
  });
  els.sortBy.addEventListener("change", () => {
    state.sortBy = els.sortBy.value;
    filterAndSort();
  });
  els.loadMore.addEventListener("click", () => {
    state.visible += 6;
    render();
  });
  $("#resetFilters").addEventListener("click", () => {
    state.query = "";
    state.fields.clear();
    state.yearFrom = new Date().getFullYear() - 9;
    state.yearTo = new Date().getFullYear();
    state.openAccessOnly = false;
    state.sortBy = "relevance";
    state.visible = 6;
    els.searchInput.value = "";
    els.yearFrom.value = state.yearFrom;
    els.yearTo.value = state.yearTo;
    els.openAccessOnly.checked = false;
    els.sortBy.value = "relevance";
    els.fieldFilters.querySelectorAll("input").forEach((input) => { input.checked = false; });
    filterAndSort();
  });
  $("#readerClose").addEventListener("click", () => els.reader.close());
  els.reader.addEventListener("click", (event) => {
    if (event.target === els.reader) els.reader.close();
  });
  $("#pdfClose").addEventListener("click", closePdfReader);
  $("#pdfReader").addEventListener("click", (event) => {
    if (event.target === $("#pdfReader")) closePdfReader();
  });
  $("#pdfReader").addEventListener("close", () => {
    $("#pdfFrame").src = "about:blank";
  });
  document.querySelectorAll(".reader-tabs button").forEach((button) => {
    button.addEventListener("click", () => setReaderView(button.dataset.view));
  });
  $("#themeButton").addEventListener("click", () => {
    document.body.classList.toggle("dark");
    localStorage.setItem("paper-lens-theme", document.body.classList.contains("dark") ? "dark" : "light");
  });
}

async function loadPapers() {
  try {
    const response = await fetch("data/papers.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.papers = payload.papers || payload;
    const date = payload.meta?.updated_at ? new Date(payload.meta.updated_at) : null;
    els.updatedAt.textContent = date && !Number.isNaN(date.valueOf())
      ? `上次同步：${date.toLocaleString("zh-CN", { dateStyle: "medium", timeStyle: "short" })}`
      : "本地数据集";
    setupFilters();
    filterAndSort();
  } catch (error) {
    console.error("论文数据载入失败", error);
    els.paperList.innerHTML = '<div class="empty"><strong>数据载入失败</strong>请通过本项目的 server.py 启动网站，避免直接双击 HTML。</div>';
    els.updatedAt.textContent = "数据连接异常";
    els.loadMore.hidden = true;
  }
}

if (localStorage.getItem("paper-lens-theme") === "dark") document.body.classList.add("dark");
bindEvents();
loadPapers();
