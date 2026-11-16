(function () {
  "use strict";

  var metadataSearch = window.CWA && window.CWA.metadataSearch;

  function element(tag, className, text) {
    return metadataSearch.element(tag, className, text);
  }

  function hiddenInput(name, value) {
    var input = element("input");
    input.type = "hidden";
    input.name = name;
    input.value = value;
    return input;
  }

  function renderResult(movie, context) {
    var card = element("article", "movie-metadata-result");
    var copy = element("div", "movie-metadata-result-copy");
    copy.appendChild(element(
      "h4",
      "movie-metadata-result-title",
      movie.title + (movie.year ? " (" + movie.year + ")" : "")
    ));

    var facts = [];
    if (movie.tmdb_rating !== null) facts.push("TMDB " + movie.tmdb_rating + "/10");
    if (movie.original_title && movie.original_title !== movie.title) facts.push(movie.original_title);
    if (facts.length) copy.appendChild(element("p", "movie-result-facts", facts.join(" · ")));
    if (movie.overview) copy.appendChild(element("p", "movie-result-overview", movie.overview));
    card.appendChild(copy);

    var applyForm = element("form", "movie-metadata-apply");
    applyForm.method = "post";
    applyForm.action = context.panel.dataset.applyUrl;
    applyForm.appendChild(hiddenInput("csrf_token", context.csrf ? context.csrf.value : ""));
    applyForm.appendChild(hiddenInput("tmdb_id", movie.tmdb_id));
    if (context.panel.dataset.import === "true") {
      applyForm.appendChild(hiddenInput("media_format", document.getElementById("import-format").value));
      applyForm.appendChild(hiddenInput("location", document.getElementById("import-location").value));
    }
    var apply = element(
      "button",
      "btn btn-primary",
      context.panel.dataset.import === "true" ? "Add to library" : "Use this metadata"
    );
    apply.type = "submit";
    applyForm.appendChild(apply);
    card.appendChild(applyForm);
    return card;
  }

  function initMetadataSearch() {
    if (!metadataSearch) return;
    metadataSearch.init({
      formSelector: ".movie-metadata-search-form",
      resultsSelector: ".movie-metadata-results",
      resultListSelector: ".movie-metadata-result-list",
      headingSelector: ".movie-metadata-results-heading",
      statusSelector: ".movie-metadata-status",
      messages: {
        emptyQuery: "Enter a movie title to search.",
        searching: "Searching TMDB…",
        empty: "No matches found. Try another title or add the release year.",
        one: "1 metadata result found.",
        many: "%d metadata results found.",
        failed: "Metadata search failed."
      },
      buildRequest: function (query, form, csrf) {
        return {
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrf ? csrf.value : ""
          },
          body: JSON.stringify({query: query, year: form.elements.year.value})
        };
      },
      parseResponse: function (data) {
        return data.results || [];
      },
      errorMessage: function (data) {
        return data.error || "Metadata search failed.";
      },
      onStart: function (status) {
        status.classList.remove("movie-search-error");
      },
      onError: function (status) {
        status.classList.add("movie-search-error");
      },
      renderResult: renderResult
    });
  }

  function initDeleteConfirmation() {
    document.querySelectorAll("form[data-confirm]").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        if (!window.confirm(form.dataset.confirm)) event.preventDefault();
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initMetadataSearch();
    initDeleteConfirmation();
  });
}());
