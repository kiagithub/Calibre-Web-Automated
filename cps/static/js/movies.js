(function () {
  "use strict";

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
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
    var csrf = document.querySelector("input[name='csrf_token']");

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var button = form.querySelector("button[type='submit']");
      var query = form.elements.query.value.trim();
      if (!query) {
        form.elements.query.focus();
        return;
      }
      button.disabled = true;
      results.replaceChildren(element("p", "movie-search-status", "Searching TMDB…"));
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
        results.replaceChildren();
        if (!movies.length) {
          results.appendChild(element("p", "movie-search-status", "No matches found. Try another title or add the release year."));
          return;
        }
        movies.forEach(function (movie) {
          var card = element("article", "movie-metadata-result");
          var copy = element("div", "movie-metadata-result-copy");
          copy.appendChild(element("h3", "", movie.title + (movie.year ? " (" + movie.year + ")" : "")));
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
          results.appendChild(card);
        });
      }).catch(function (error) {
        results.replaceChildren(element("p", "movie-search-status movie-search-error", error.message));
      }).finally(function () {
        button.disabled = false;
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
