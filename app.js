const csvPath = "barnefilmer_kino.csv";
const omtalerPath = "film_omtaler.json";
const state = {
  omtaler: {},
  rows: [],
  filteredRows: [],
};

const elements = {
  body: document.querySelector("#showingsBody"),
  cinemaFilter: document.querySelector("#cinemaFilter"),
  clearFiltersButton: document.querySelector("#clearFiltersButton"),
  dateRange: document.querySelector("#dateRange"),
  emptyState: document.querySelector("#emptyState"),
  fromDate: document.querySelector("#fromDate"),
  movieCount: document.querySelector("#movieCount"),
  refreshButton: document.querySelector("#refreshButton"),
  searchInput: document.querySelector("#searchInput"),
  showingCount: document.querySelector("#showingCount"),
  statusText: document.querySelector("#statusText"),
  toDate: document.querySelector("#toDate"),
};

async function loadCsv() {
  setStatus("Laster data ...");
  const [csvResponse, omtaler] = await Promise.all([
    fetch(`${csvPath}?t=${Date.now()}`),
    loadOmtaler(),
  ]);
  if (!csvResponse.ok) {
    throw new Error(`Kunne ikke lese ${csvPath}: ${csvResponse.status}`);
  }
  const text = await csvResponse.text();
  state.omtaler = omtaler;
  state.rows = parseCsv(text);
  updateCinemaFilter(state.rows);
  applyFilters();
  setStatus(`Sist lest ${new Date().toLocaleTimeString("no-NO", {
    hour: "2-digit",
    minute: "2-digit",
  })}`);
}

async function loadOmtaler() {
  const response = await fetch(`${omtalerPath}?t=${Date.now()}`);
  if (!response.ok) {
    return {};
  }
  const data = await response.json();
  return data.movies || {};
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let quoted = false;

  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    const next = text[index + 1];

    if (quoted && character === "\"" && next === "\"") {
      cell += "\"";
      index += 1;
    } else if (character === "\"") {
      quoted = !quoted;
    } else if (!quoted && character === ",") {
      row.push(cell);
      cell = "";
    } else if (!quoted && (character === "\n" || character === "\r")) {
      if (character === "\r" && next === "\n") {
        index += 1;
      }
      row.push(cell);
      if (row.some((value) => value.length > 0)) {
        rows.push(row);
      }
      row = [];
      cell = "";
    } else {
      cell += character;
    }
  }

  if (cell.length || row.length) {
    row.push(cell);
    rows.push(row);
  }

  const [headers, ...dataRows] = rows;
  if (!headers) {
    return [];
  }

  return dataRows.map((dataRow) => Object.fromEntries(
    headers.map((header, index) => [header, dataRow[index] || ""])
  ));
}

function updateCinemaFilter(rows) {
  const current = elements.cinemaFilter.value;
  const cinemas = [...new Set(rows.map((row) => row.kino).filter(Boolean))].sort();

  elements.cinemaFilter.replaceChildren(
    optionElement("", "Alle kinoer"),
    ...cinemas.map((cinema) => optionElement(cinema, cinema))
  );
  elements.cinemaFilter.value = cinemas.includes(current) ? current : "";
}

function optionElement(value, text) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = text;
  return option;
}

function applyFilters() {
  const query = elements.searchInput.value.trim().toLocaleLowerCase("no-NO");
  const cinema = elements.cinemaFilter.value;
  const from = elements.fromDate.value;
  const to = elements.toDate.value;

  state.filteredRows = state.rows.filter((row) => {
    const haystack = [
      row.film,
      row.kino,
      row.sal,
      row.aldersgrense,
      row.kategori,
      row.sprak_og_tekst,
      movieText(row.film),
    ].join(" ").toLocaleLowerCase("no-NO");

    return (!query || haystack.includes(query))
      && (!cinema || row.kino === cinema)
      && (!from || row.dato >= from)
      && (!to || row.dato <= to);
  });

  renderRows(state.filteredRows);
  renderSummary(state.filteredRows);
}

function renderRows(rows) {
  elements.body.replaceChildren(...rows.map((row) => {
    const tr = document.createElement("tr");
    appendCell(tr, `${row.ukedag} ${formatDate(row.dato)}`, "date-cell");
    appendCell(tr, row.klokkeslett, "time-cell");
    appendCell(tr, row.kino);
    appendMovieCell(tr, row.film);
    appendCell(tr, row.sal);
    appendCell(tr, row.aldersgrense);
    appendCell(tr, row.sprak_og_tekst);
    return tr;
  }));

  elements.emptyState.hidden = rows.length > 0;
}

function appendCell(tr, text, className = "") {
  const td = document.createElement("td");
  td.textContent = text || "-";
  if (className) {
    td.className = className;
  }
  tr.append(td);
}

function appendMovieCell(tr, title) {
  const td = document.createElement("td");
  td.className = "movie-cell";

  const titleElement = document.createElement("div");
  titleElement.className = "movie-title";
  titleElement.textContent = title || "-";
  td.append(titleElement);

  const omtale = state.omtaler[title];
  if (omtale) {
    const description = document.createElement("p");
    description.className = "movie-description";
    description.textContent = omtale.kort_omtale || "";
    td.append(description);

    const meta = [omtale.passer_for, omtale.foreldre_merknad].filter(Boolean);
    if (meta.length) {
      const metaElement = document.createElement("p");
      metaElement.className = "movie-meta";
      metaElement.textContent = meta.join(" ");
      td.append(metaElement);
    }
  }

  tr.append(td);
}

function movieText(title) {
  const omtale = state.omtaler[title];
  if (!omtale) {
    return "";
  }
  return [
    omtale.kort_omtale,
    omtale.passer_for,
    omtale.foreldre_merknad,
  ].join(" ");
}

function renderSummary(rows) {
  const movies = new Set(rows.map((row) => row.film));
  const dates = rows.map((row) => row.dato).filter(Boolean).sort();

  elements.showingCount.textContent = rows.length.toString();
  elements.movieCount.textContent = movies.size.toString();
  elements.dateRange.textContent = dates.length
    ? `${formatDate(dates[0])} - ${formatDate(dates[dates.length - 1])}`
    : "-";
}

function formatDate(value) {
  if (!value) {
    return "-";
  }
  const [year, month, day] = value.split("-");
  return `${day}.${month}.${year}`;
}

function setStatus(message) {
  elements.statusText.textContent = message;
}

function showError(error) {
  elements.body.replaceChildren();
  elements.emptyState.hidden = false;
  elements.emptyState.textContent = error.message;
  setStatus("Kunne ikke laste CSV");
}

[
  elements.cinemaFilter,
  elements.fromDate,
  elements.searchInput,
  elements.toDate,
].forEach((element) => {
  element.addEventListener("input", applyFilters);
});

elements.refreshButton.addEventListener("click", () => {
  loadCsv().catch(showError);
});

elements.clearFiltersButton.addEventListener("click", () => {
  elements.searchInput.value = "";
  elements.cinemaFilter.value = "";
  elements.fromDate.value = "";
  elements.toDate.value = "";
  applyFilters();
});

loadCsv().catch(showError);


/* Local Variables:
 * mode: javascript
 * js-indent-level: 2
 * End:
 */
