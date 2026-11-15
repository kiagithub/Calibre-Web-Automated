(function () {
  "use strict";

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function hiddenInput(name, value) {
    var input = element("input");
    input.type = "hidden";
    input.name = name;
    input.value = value;
    return input;
  }

  function initMetadataSearch() {
    var panel = document.getElementById("metadata-search");
    if (!panel) return;
    var form = panel.querySelector(".movie-metadata-search-form");
    if (!form) return;
    var results = panel.querySelector(".movie-metadata-results");
    var resultList = panel.querySelector(".movie-metadata-result-list");
    var resultsHeading = panel.querySelector(".movie-metadata-results-heading");
    var status = panel.querySelector(".movie-metadata-status");
    var csrf = document.querySelector("input[name='csrf_token']");
    if (!results || !resultList || !resultsHeading || !status) return;

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var button = form.querySelector("button[type='submit']");
      var query = form.elements.query.value.trim();
      if (!query) {
        status.textContent = "Enter a movie title to search.";
        form.elements.query.focus();
        return;
      }
      button.disabled = true;
      results.setAttribute("aria-busy", "true");
      status.classList.remove("movie-search-error");
      status.textContent = "Searching TMDB…";
      resultList.replaceChildren();
      fetch(panel.dataset.searchUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrf ? csrf.value : ""
        },
        body: JSON.stringify({query: query, year: form.elements.year.value})
      }).then(function (response) {
        return response.json().then(function (data) {
          if (!response.ok) throw new Error(data.error || "Metadata search failed.");
          return data.results || [];
        });
      }).then(function (movies) {
        if (!movies.length) {
          status.textContent = "No matches found. Try another title or add the release year.";
        } else {
          movies.forEach(function (movie) {
            var card = element("article", "movie-metadata-result");
            var copy = element("div", "movie-metadata-result-copy");
            copy.appendChild(element("h4", "movie-metadata-result-title", movie.title + (movie.year ? " (" + movie.year + ")" : "")));
            var facts = [];
            if (movie.tmdb_rating !== null) facts.push("TMDB " + movie.tmdb_rating + "/10");
            if (movie.original_title && movie.original_title !== movie.title) facts.push(movie.original_title);
            if (facts.length) copy.appendChild(element("p", "movie-result-facts", facts.join(" · ")));
            if (movie.overview) copy.appendChild(element("p", "movie-result-overview", movie.overview));
            card.appendChild(copy);

            var applyForm = element("form", "movie-metadata-apply");
            applyForm.method = "post";
            applyForm.action = panel.dataset.applyUrl;
            applyForm.appendChild(hiddenInput("csrf_token", csrf ? csrf.value : ""));
            applyForm.appendChild(hiddenInput("tmdb_id", movie.tmdb_id));
            if (panel.dataset.import === "true") {
              applyForm.appendChild(hiddenInput("media_format", document.getElementById("import-format").value));
              applyForm.appendChild(hiddenInput("location", document.getElementById("import-location").value));
            }
            var apply = element("button", "btn btn-primary", panel.dataset.import === "true" ? "Add to library" : "Use this metadata");
            apply.type = "submit";
            applyForm.appendChild(apply);
            card.appendChild(applyForm);
            resultList.appendChild(card);
          });
          status.textContent = movies.length === 1 ? "1 metadata result found." : movies.length + " metadata results found.";
        }
        resultsHeading.focus();
      }).catch(function (error) {
        resultList.replaceChildren();
        status.classList.add("movie-search-error");
        status.textContent = error && error.message ? error.message : "Metadata search failed.";
        resultsHeading.focus();
      }).finally(function () {
        button.disabled = false;
        results.setAttribute("aria-busy", "false");
      });
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
