library(shiny)
library(jsonlite)
library(yaml)
library(grendelshiny)
library(shinyseo)

csv_file <- "barnefilmer_kino.csv"
omtaler_file <- "film_omtaler.json"

app_meta <- yaml::read_yaml("meta.yml")
app_meta$url   <- Sys.getenv("KINO_BARN_URL",   app_meta$url)
app_meta$image <- Sys.getenv("KINO_BARN_IMAGE", app_meta$image)
app_title <- app_meta$title

read_showings <- function() {
  if (!file.exists(csv_file)) {
    return(data.frame())
  }

  rows <- read.csv(
    csv_file,
    fileEncoding = "UTF-8",
    stringsAsFactors = FALSE,
    check.names = FALSE
  )

  if (nrow(rows) == 0) {
    return(rows)
  }

  rows$dato_date <- as.Date(rows$dato)
  rows
}

read_omtaler <- function() {
  if (!file.exists(omtaler_file)) {
    return(list())
  }

  data <- fromJSON(omtaler_file, simplifyVector = FALSE)
  data$movies %||% list()
}

`%||%` <- function(x, y) {
  if (is.null(x)) y else x
}

format_date_no <- function(x) {
  ifelse(is.na(x), "", format(x, "%d.%m.%Y"))
}

has_date <- function(x) {
  !is.null(x) && length(x) == 1 && !is.na(x) && nzchar(x)
}

ui <- fluidPage(
  tags$head(
    tags$title(app_title),
    shinyseo::social_meta(app_meta),
    tags$link(rel = "manifest", href = "manifest.json"),
    tags$link(rel = "apple-touch-icon", href = "apple-touch-icon.png"),
    tags$meta(name = "theme-color", content = app_meta$theme_color),
    tags$meta(name = "mobile-web-app-capable", content = "yes"),
    tags$meta(name = "apple-mobile-web-app-capable", content = "yes"),
    tags$meta(name = "apple-mobile-web-app-status-bar-style", content = "black-translucent"),
    tags$meta(name = "apple-mobile-web-app-title", content = app_meta$title),
    grendelshiny::grendelshiny_css(),
    grendelshiny::grendelshiny_js(),
    tags$script(HTML("
      Shiny.addCustomMessageHandler('clearDateFilters', function(_) {
        ['from_date', 'to_date'].forEach(function(id) {
          var field = document.getElementById(id);
          if (!field) {
            return;
          }
          field.value = '';
          field.dispatchEvent(new Event('input', { bubbles: true }));
          field.dispatchEvent(new Event('change', { bubbles: true }));
        });
      });

      (function () {
        var STORAGE_KEY = 'kinoBarnSeenFilms';

        $(document).on('shiny:value', function (event) {
          if (event.target.id !== 'film_list') {
            return;
          }

          setTimeout(function () {
            var items = document.querySelectorAll('#film_list [data-film]');
            if (!items.length) {
              return;
            }

            var stored = null;
            try {
              stored = JSON.parse(localStorage.getItem(STORAGE_KEY));
            } catch (e) {
              stored = null;
            }

            var seen = Array.isArray(stored) ? stored : null;
            var current = [];

            items.forEach(function (item) {
              var film = item.getAttribute('data-film');
              current.push(film);

              if (seen !== null && seen.indexOf(film) === -1 && !item.querySelector('.film-badge-new')) {
                var badge = document.createElement('span');
                badge.className = 'film-badge-new';
                badge.textContent = 'Ny!';
                item.appendChild(badge);
              }
            });

            try {
              localStorage.setItem(STORAGE_KEY, JSON.stringify(current));
            } catch (e) {
              /* localStorage utilgjengelig - hopper over lagring */
            }
          }, 0);
        });
      })();
    ")),
    tags$style(HTML("
      .kino-grid {
        display: grid;
        grid-template-columns: minmax(260px, 0.35fr) minmax(0, 1fr);
        gap: 24px;
        margin: 0 auto 44px;
        max-width: 1240px;
        padding: 0 24px;
      }

      .toolbar-actions {
        display: grid;
        grid-template-columns: 1fr;
        gap: 10px;
        margin-top: 8px;
      }

      .summary-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 12px;
        margin-bottom: 16px;
      }

      .summary-card {
        padding: 14px 16px;
        border: 1px solid var(--border);
        border-radius: 20px;
        background: rgba(255, 255, 255, 0.04);
      }

      .summary-card span {
        display: block;
        color: var(--text);
        font-size: 28px;
        font-weight: 800;
      }

      .summary-card strong {
        color: var(--muted);
        font-size: 13px;
      }

      .table-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
        margin-bottom: 16px;
      }

      .table-header h2,
      .table-header p {
        margin: 0;
      }

      .table-header p {
        color: var(--muted);
      }

      .table-wrap {
        overflow-x: auto;
      }

      table.kino-table {
        width: 100%;
        min-width: 920px;
        border-collapse: collapse;
      }

      .kino-table th,
      .kino-table td {
        padding: 12px 14px;
        border-bottom: 1px solid rgba(153, 247, 235, 0.12);
        text-align: left;
        vertical-align: top;
      }

      .kino-table th {
        background: rgba(118, 233, 217, 0.10);
        color: var(--muted);
        font-size: 12px;
        text-transform: uppercase;
      }

      .kino-table tr:hover td {
        background: rgba(118, 233, 217, 0.06);
      }

      .date-cell,
      .time-cell,
      .movie-title {
        font-weight: 800;
      }

      .movie-cell {
        min-width: 320px;
      }

      .movie-description,
      .movie-meta {
        margin: 6px 0 0;
        max-width: 560px;
        font-size: 14px;
        line-height: 1.45;
      }

      .movie-meta {
        color: var(--muted);
      }

      .empty-state {
        padding: 28px 16px;
        color: var(--muted);
        text-align: center;
      }

      .film-list {
        list-style: none;
        margin: 0;
        padding: 0;
        display: flex;
        flex-direction: column;
        gap: 8px;
      }

      .film-list li {
        padding: 10px 14px;
        border: 1px solid var(--border);
        border-radius: 14px;
        background: rgba(255, 255, 255, 0.04);
        font-weight: 700;
        display: flex;
        align-items: center;
        gap: 8px;
      }

      .sidebar-card {
        align-self: start;
      }

      .hero-header {
        align-items: center;
      }

      .hero-mark {
        display: flex;
        align-items: center;
      }

      .hero-mark img {
        display: block;
        height: 48px;
        width: auto;
      }

      .hero-badges a.hero-badge {
        cursor: pointer;
        text-decoration: none;
        transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
      }

      .hero-badge-active {
        background: #176b5f !important;
        border-color: #176b5f !important;
        color: #ffffff !important;
      }

      .film-badge-new {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 999px;
        background: #176b5f;
        color: #ffffff;
        font-size: 11px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.04em;
      }

      @media (max-width: 760px) {
        .kino-grid {
          grid-template-columns: 1fr;
          padding: 0 14px;
        }

        .summary-grid {
          grid-template-columns: 1fr;
        }

        .table-header {
          display: block;
        }
      }
    "))
  ),
  div(
    class = "hero",
    div(
      class = "hero-copy",
      div(
        class = "hero-header",
        div(class = "hero-mark", tags$img(src = "grendel-mark.png", alt = "Grendel")),
        div(
          class = "hero-heading",
          p(class = "eyebrow", "Kinoprogram"),
          h1(app_title)
        )
      ),
      p(
        class = "hero-text",
        "Datoer, klokkeslett og korte omtaler for filmer som kan passe barn og ungdom."
      ),
      uiOutput("cinema_badges")
    ),
    div(
      class = "hero-panel",
      h2("Aktuelle filmer"),
      uiOutput("film_list")
    )
  ),
  div(
    class = "kino-grid",
    div(
      class = "sidebar-card",
      h2("Filtre"),
      textInput("search", "Søk", placeholder = "Film, sal, språk eller omtale"),
      uiOutput("cinema_filter"),
      div(
        class = "form-group shiny-input-container",
        tags$label(class = "control-label", `for` = "from_date", "Fra dato"),
        tags$input(id = "from_date", type = "date", class = "form-control")
      ),
      div(
        class = "form-group shiny-input-container",
        tags$label(class = "control-label", `for` = "to_date", "Til dato"),
        tags$input(id = "to_date", type = "date", class = "form-control")
      ),
      div(
        class = "toolbar-actions",
        actionButton("clear_filters", "Nullstill"),
        actionButton("reload_files", "Les filer på nytt")
      )
    ),
    div(
      class = "main-card",
      div(
        class = "summary-grid",
        div(class = "summary-card", span(textOutput("showing_count", inline = TRUE)), strong("visninger")),
        div(class = "summary-card", span(textOutput("movie_count", inline = TRUE)), strong("filmer")),
        div(class = "summary-card", span(textOutput("date_range", inline = TRUE)), strong("periode"))
      ),
      div(
        class = "table-header",
        h2("Visninger"),
        p(textOutput("status_text", inline = TRUE))
      ),
      uiOutput("showings_table")
    )
  )
)

server <- function(input, output, session) {
  data_version <- reactiveVal(0)

  observeEvent(input$reload_files, {
    data_version(data_version() + 1)
  })

  observeEvent(input$clear_filters, {
    updateTextInput(session, "search", value = "")
    updateSelectInput(session, "cinema", selected = "")
    session$sendCustomMessage("clearDateFilters", list())
  })

  toggle_cinema <- function(name) {
    current <- input$cinema %||% ""
    new_value <- if (identical(current, name)) "" else name
    updateSelectInput(session, "cinema", selected = new_value)
  }

  observeEvent(input$badge_verdal, toggle_cinema("Verdal"))
  observeEvent(input$badge_steinkjer, toggle_cinema("Steinkjer"))
  observeEvent(input$badge_begge, updateSelectInput(session, "cinema", selected = ""))

  output$cinema_badges <- renderUI({
    selected <- input$cinema %||% ""

    badge <- function(id, label, value) {
      cls <- if (identical(selected, value)) "hero-badge hero-badge-active" else "hero-badge"
      actionLink(id, label, class = cls)
    }

    div(
      class = "hero-badges",
      badge("badge_begge", "Begge kinoene", ""),
      badge("badge_verdal", "Verdal", "Verdal"),
      badge("badge_steinkjer", "Steinkjer", "Steinkjer")
    )
  })

  showings <- reactive({
    data_version()
    read_showings()
  })

  omtaler <- reactive({
    data_version()
    read_omtaler()
  })

  output$cinema_filter <- renderUI({
    rows <- showings()
    cinemas <- sort(unique(rows$kino %||% character()))
    selectInput(
      "cinema",
      "Kino",
      choices = c("Begge kinoene" = "", cinemas),
      selected = input$cinema %||% ""
    )
  })

  output$film_list <- renderUI({
    rows <- showings()
    films <- sort(unique(rows$film %||% character()))

    if (length(films) == 0) {
      return(p(class = "hero-text", "Ingen filmer i programmet for øyeblikket."))
    }

    tags$ul(
      class = "film-list",
      lapply(films, function(film) {
        tags$li(`data-film` = film, film)
      })
    )
  })

  filtered_showings <- reactive({
    rows <- showings()
    if (nrow(rows) == 0) {
      return(rows)
    }

    query <- trimws(tolower(input$search %||% ""))
    if (nzchar(query)) {
      movie_texts <- vapply(rows$film, function(title) {
        omtale <- omtaler()[[title]]
        if (is.null(omtale)) {
          return("")
        }
        paste(
          omtale$kort_omtale %||% "",
          omtale$passer_for %||% "",
          omtale$foreldre_merknad %||% ""
        )
      }, character(1))

      haystack <- tolower(paste(
        rows$film,
        rows$kino,
        rows$sal,
        rows$aldersgrense,
        rows$kategori,
        rows$sprak_og_tekst,
        movie_texts
      ))
      rows <- rows[grepl(query, haystack, fixed = TRUE), , drop = FALSE]
    }

    if (nzchar(input$cinema %||% "")) {
      rows <- rows[rows$kino == input$cinema, , drop = FALSE]
    }

    if (has_date(input$from_date)) {
      rows <- rows[rows$dato_date >= as.Date(input$from_date), , drop = FALSE]
    }

    if (has_date(input$to_date)) {
      rows <- rows[rows$dato_date <= as.Date(input$to_date), , drop = FALSE]
    }

    rows
  })

  output$showing_count <- renderText({
    nrow(filtered_showings())
  })

  output$movie_count <- renderText({
    rows <- filtered_showings()
    length(unique(rows$film %||% character()))
  })

  output$date_range <- renderText({
    rows <- filtered_showings()
    if (nrow(rows) == 0) {
      return("-")
    }
    dates <- range(rows$dato_date, na.rm = TRUE)
    paste(format_date_no(dates[1]), "-", format_date_no(dates[2]))
  })

  output$status_text <- renderText({
    csv_time <- if (file.exists(csv_file)) {
      format(file.info(csv_file)$mtime, "%H:%M")
    } else {
      "mangler CSV"
    }
    paste("Sist lest", csv_time)
  })

  output$showings_table <- renderUI({
    rows <- filtered_showings()
    current_omtaler <- omtaler()

    if (nrow(rows) == 0) {
      return(div(class = "empty-state", "Ingen visninger passer filtrene."))
    }

    table_rows <- lapply(seq_len(nrow(rows)), function(index) {
      row <- rows[index, , drop = FALSE]
      omtale <- current_omtaler[[row$film]]
      meta <- if (is.null(omtale)) {
        ""
      } else {
        paste(
          omtale$passer_for %||% "",
          omtale$foreldre_merknad %||% ""
        )
      }

      tags$tr(
        tags$td(class = "date-cell", paste(row$ukedag, format_date_no(row$dato_date))),
        tags$td(class = "time-cell", row$klokkeslett),
        tags$td(row$kino),
        tags$td(
          class = "movie-cell",
          div(class = "movie-title", row$film),
          if (!is.null(omtale)) p(class = "movie-description", omtale$kort_omtale),
          if (nzchar(trimws(meta))) p(class = "movie-meta", meta)
        ),
        tags$td(row$sal),
        tags$td(row$aldersgrense),
        tags$td(row$sprak_og_tekst)
      )
    })

    div(
      class = "table-wrap",
      tags$table(
        class = "kino-table",
        tags$thead(
          tags$tr(
            tags$th("Dato"),
            tags$th("Tid"),
            tags$th("Kino"),
            tags$th("Film"),
            tags$th("Sal"),
            tags$th("Alder"),
            tags$th("Språk og tekst")
          )
        ),
        tags$tbody(table_rows)
      )
    )
  })
}

shinyApp(ui, server)


# Local Variables:
# mode: ess-r
# ess-indent-offset: 2
# End:
