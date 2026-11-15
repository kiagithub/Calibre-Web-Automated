(function () {
  "use strict";

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
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

  function renderResult(book, status, panel) {
    var card = element("article", "external-books-metadata-result");
    var copy = element("div", "external-books-metadata-result-copy");
    var source = book.source || {};

    var cover = element("img", "external-books-metadata-result-cover");
    cover.src = coverSource(panel, book);
    cover.alt = "";
    cover.loading = "lazy";
    cover.decoding = "async";
    cover.width = 60;
    cover.height = 90;
    cover.addEventListener("error", function () {
      var fallback = panel.dataset.genericCover || "";
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
      status.textContent = "Metadata applied. Review the fields and save your changes.";
    });
    card.appendChild(apply);
    return card;
  }

  function initMetadataSearch() {
    var panel = document.getElementById("metadata-search");
    if (!panel) return;
    var form = panel.querySelector(".external-books-metadata-search-form");
    if (!form) return;
    var resultList = panel.querySelector(".external-books-metadata-result-list");
    var resultsHeading = panel.querySelector(".external-books-metadata-results-heading");
    var status = panel.querySelector(".external-books-metadata-status");
    var csrf = document.querySelector("input[name='csrf_token']");

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var button = form.querySelector("button[type='submit']");
      var query = form.elements.query.value.trim();
      if (!query) {
        status.textContent = "Enter a title, author, or identifier to search.";
        form.elements.query.focus();
        return;
      }

      button.disabled = true;
      status.textContent = "Searching for book metadata…";
      resultList.replaceChildren();
      fetch(panel.dataset.searchUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {"X-CSRFToken": csrf ? csrf.value : ""},
        body: new URLSearchParams({query: query})
      }).then(function (response) {
        return response.json().then(function (data) {
          if (!response.ok) {
            throw new Error(data && data.error ? data.error : "Metadata search failed.");
          }
          if (!Array.isArray(data)) throw new Error("Metadata search returned an invalid response.");
          return {books: data, partial: response.headers.get("X-Metadata-Partial") === "true"};
        });
      }).then(function (result) {
        var books = result.books;
        var partialMessage = panel.dataset.partialMessage || "Some sources are still responding; results may be incomplete.";
        if (!books.length) {
          status.textContent = "No matches found. Try another title, author, or identifier.";
          if (result.partial) status.textContent += " " + partialMessage;
        } else {
          books.forEach(function (book) {
            resultList.appendChild(renderResult(book, status, panel));
          });
          var message = books.length === 1 ? "1 metadata result found." : books.length + " metadata results found.";
          if (result.partial) message += " " + partialMessage;
          status.textContent = message;
        }
        resultsHeading.focus();
      }).catch(function (error) {
        resultList.replaceChildren();
        status.textContent = error && error.message ? error.message : "Metadata search failed.";
        resultsHeading.focus();
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
