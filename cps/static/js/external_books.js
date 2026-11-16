(function () {
  "use strict";

  var metadataSearch = window.CWA && window.CWA.metadataSearch;

  function element(tag, className, text) {
    return metadataSearch.element(tag, className, text);
  }

  function stringValue(value) {
    return value === undefined || value === null ? "" : String(value);
  }

  function listValue(value) {
    return Array.isArray(value) ? value : [];
  }

  function plainText(value) {
    if (value === undefined || value === null || value === "") return "";
    var documentFragment = new DOMParser().parseFromString(String(value), "text/html");
    documentFragment.querySelectorAll("script, style").forEach(function (node) {
      node.remove();
    });
    return (documentFragment.body.textContent || "").trim();
  }

  function setField(name, value) {
    var field = document.getElementById(name);
    if (field) field.value = stringValue(value);
  }

  function identifier(identifiers, names) {
    var normalized = {};
    Object.keys(identifiers || {}).forEach(function (key) {
      normalized[key.toLowerCase()] = identifiers[key];
    });
    for (var index = 0; index < names.length; index += 1) {
      if (normalized[names[index]] !== undefined && normalized[names[index]] !== null) {
        return normalized[names[index]];
      }
    }
    return "";
  }

  function remoteCover(value) {
    var url = stringValue(value);
    return /^https?:\/\//i.test(url) ? url : "";
  }

  function coverSource(panel, book) {
    var cover = remoteCover(book.cover);
    if (!cover || !panel.dataset.coverUrl) return panel.dataset.genericCover || "";
    return panel.dataset.coverUrl + "?url=" + encodeURIComponent(cover);
  }

  function populateForm(book) {
    var identifiers = book.identifiers || {};
    setField("title", book.title);
    setField("authors", listValue(book.authors).join(" & "));
    setField("description", plainText(book.description));
    setField("publisher", book.publisher);
    setField("published_date", book.publishedDate);
    setField("series", book.series);
    setField("series_index", book.series_index);
    setField("languages", listValue(book.languages).join(", "));
    setField("isbn_13", identifier(identifiers, ["isbn", "isbn13", "isbn_13"]));
    setField("isbn_10", identifier(identifiers, ["isbn10", "isbn_10"]));
    setField("asin", identifier(identifiers, ["amazon", "mobi-asin"]));

    var source = book.source || {};
    setField("metadata_provider", source.id);
    setField("metadata_id", book.id);
    setField("metadata_url", book.url);
    setField("cover_url", remoteCover(book.cover));
    setField("metadata_selected", "1");
  }

  function renderResult(book, context) {
    var card = element("article", "external-books-metadata-result");
    card.dataset.owned = book.owned ? "true" : "false";
    var copy = element("div", "external-books-metadata-result-copy");
    var source = book.source || {};
    var hideOwned = context.panel.querySelector("#metadata-hide-owned");
    card.hidden = !!(hideOwned && hideOwned.checked && book.owned);

    var cover = element("img", "external-books-metadata-result-cover");
    cover.src = coverSource(context.panel, book);
    cover.alt = "";
    cover.loading = "lazy";
    cover.decoding = "async";
    cover.width = 60;
    cover.height = 90;
    cover.addEventListener("error", function () {
      var fallback = context.panel.dataset.genericCover || "";
      if (fallback && cover.getAttribute("src") !== fallback && cover.dataset.fallback !== "true") {
        cover.dataset.fallback = "true";
        cover.src = fallback;
      }
    });
    card.appendChild(cover);

    copy.appendChild(element("h4", "external-books-metadata-result-title", book.title || "Untitled metadata result"));
    if (listValue(book.authors).length) {
      copy.appendChild(element("p", "external-books-metadata-result-authors", listValue(book.authors).join(", ")));
    }
    if (source.description || source.id) {
      copy.appendChild(element("p", "external-books-metadata-result-source", source.description || source.id));
    }
    if (book.owned) {
      copy.appendChild(element(
        "span",
        "external-books-metadata-result-badge",
        "In library" + (book.owned_as ? " · " + book.owned_as : "")
      ));
    }

    var facts = [];
    if (book.publisher) facts.push(stringValue(book.publisher));
    if (book.publishedDate) facts.push(stringValue(book.publishedDate));
    if (book.series) {
      var series = stringValue(book.series);
      if (book.series_index !== undefined && book.series_index !== null && book.series_index !== "") {
        series += " #" + stringValue(book.series_index);
      }
      facts.push(series);
    }
    if (listValue(book.tags).length) facts.push(listValue(book.tags).join(", "));
    if (facts.length) copy.appendChild(element("p", "external-books-metadata-result-facts", facts.join(" · ")));

    var description = plainText(book.description);
    if (description) copy.appendChild(element("p", "external-books-metadata-result-description", description));
    card.appendChild(copy);

    var apply = element("button", "btn btn-primary", "Use this metadata");
    apply.type = "button";
    apply.addEventListener("click", function () {
      populateForm(book);
      context.status.textContent = "Metadata applied. Review the fields and save your changes.";
    });
    card.appendChild(apply);
    return card;
  }

  function initMetadataSearch() {
    if (!metadataSearch) return;
    var panel = document.getElementById("metadata-search");
    var hideOwned = panel && panel.querySelector("#metadata-hide-owned");
    var resultList = panel && panel.querySelector(".external-books-metadata-result-list");
    if (hideOwned && resultList) {
      hideOwned.addEventListener("change", function () {
        resultList.querySelectorAll("[data-owned='true']").forEach(function (card) {
          card.hidden = hideOwned.checked;
        });
      });
    }
    metadataSearch.init({
      formSelector: ".external-books-metadata-search-form",
      resultListSelector: ".external-books-metadata-result-list",
      headingSelector: ".external-books-metadata-results-heading",
      statusSelector: ".external-books-metadata-status",
      messages: {
        emptyQuery: "Enter a title, author, or identifier to search.",
        searching: "Searching for book metadata…",
        empty: "No matches found. Try another title, author, or identifier.",
        one: "1 metadata result found.",
        many: "%d metadata results found.",
        failed: "Metadata search failed."
      },
      buildRequest: function (query, form, csrf) {
        return {
          headers: {"X-CSRFToken": csrf ? csrf.value : ""},
          body: new URLSearchParams({query: query, check_owned: "1"})
        };
      },
      parseResponse: function (data) {
        if (!Array.isArray(data)) throw new Error("Metadata search returned an invalid response.");
        return data;
      },
      errorMessage: function (data) {
        return data && data.error ? data.error : "Metadata search failed.";
      },
      onStart: function (status) {
        delete status.dataset.error;
      },
      onError: function (status) {
        status.dataset.error = "true";
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
