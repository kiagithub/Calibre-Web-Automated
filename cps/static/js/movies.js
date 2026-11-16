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

  function requestMovie(context, movie, button) {
    var url = context.panel.dataset.requestUrl;
    if (!url) return;
    button.disabled = true;
    fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": context.csrf ? context.csrf.value : ""
      },
      body: JSON.stringify({
        content_type: "movie",
        title: movie.title,
        metadata_provider: "tmdb",
        metadata_id: movie.tmdb_id ? String(movie.tmdb_id) : "",
        metadata_url: movie.tmdb_id ? "https://www.themoviedb.org/movie/" + movie.tmdb_id : "",
        cover_url: movie.poster_url || "",
        tmdb_id: movie.tmdb_id || "",
        release_date: movie.release_date || ""
      })
    }).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok) throw new Error(data && data.error ? data.error : "Could not add the request.");
        return data;
      });
    }).then(function (data) {
      context.status.textContent = data.created ? "Added to wishlist." : "That request is already on the wishlist.";
    }).catch(function (error) {
      context.status.textContent = error && error.message ? error.message : "Could not add the request.";
    }).finally(function () {
      button.disabled = false;
    });
  }

  function renderResult(movie, context) {
    var card = element("article", "movie-metadata-result");
    card.dataset.owned = movie.owned ? "true" : "false";
    var hideOwned = context.panel.querySelector("#movie-hide-owned");
    card.hidden = !!(hideOwned && hideOwned.checked && movie.owned);
    var copy = element("div", "movie-metadata-result-copy");
    copy.appendChild(element(
      "h4",
      "movie-metadata-result-title",
      movie.title + (movie.year ? " (" + movie.year + ")" : "")
    ));
    if (movie.owned) {
      copy.appendChild(element(
        "span",
        "movie-metadata-result-badge",
        "In library" + (movie.owned_as ? " · " + movie.owned_as : "")
      ));
    }

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
    var actions = element("div", "movie-metadata-result-actions");
    actions.appendChild(applyForm);
    var request = element("button", "btn btn-default", "Request");
    request.type = "button";
    request.addEventListener("click", function () {
      requestMovie(context, movie, request);
    });
    actions.appendChild(request);
    card.appendChild(actions);
    return card;
  }

  function initMetadataSearch() {
    if (!metadataSearch) return;
    var panel = document.getElementById("metadata-search");
    var hideOwned = panel && panel.querySelector("#movie-hide-owned");
    var resultList = panel && panel.querySelector(".movie-metadata-result-list");
    if (hideOwned && resultList) {
      hideOwned.addEventListener("change", function () {
        resultList.querySelectorAll("[data-owned='true']").forEach(function (card) {
          card.hidden = hideOwned.checked;
        });
      });
    }
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
          body: JSON.stringify({query: query, year: form.elements.year.value, check_owned: true})
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
