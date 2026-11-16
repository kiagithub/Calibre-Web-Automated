(function (global) {
  "use strict";

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function init(options) {
    var panel = document.getElementById("metadata-search");
    if (!panel) return;
    var form = panel.querySelector(options.formSelector);
    if (!form) return;
    var results = options.resultsSelector ? panel.querySelector(options.resultsSelector) : null;
    var resultList = panel.querySelector(options.resultListSelector);
    var resultsHeading = panel.querySelector(options.headingSelector);
    var status = panel.querySelector(options.statusSelector);
    var csrf = document.querySelector("input[name='csrf_token']");
    if (!resultList || !resultsHeading || !status) return;

    var messages = options.messages || {};
    var partialMessage = messages.partial || panel.dataset.partialMessage || "";

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var button = form.querySelector("button[type='submit']");
      var query = form.elements.query.value.trim();
      if (!query) {
        status.textContent = messages.emptyQuery;
        form.elements.query.focus();
        return;
      }

      button.disabled = true;
      if (results) results.setAttribute("aria-busy", "true");
      if (options.onStart) options.onStart(status);
      status.textContent = messages.searching;
      resultList.replaceChildren();

      var request = options.buildRequest(query, form, csrf);
      fetch(panel.dataset.searchUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: request.headers,
        body: request.body
      }).then(function (response) {
        return response.json().then(function (data) {
          if (!response.ok) {
            var message = options.errorMessage
              ? options.errorMessage(data, response)
              : "Metadata search failed.";
            throw new Error(message);
          }
          return {
            items: options.parseResponse(data, response) || [],
            partial: response.headers.get("X-Metadata-Partial") === "true"
          };
        });
      }).then(function (result) {
        var items = result.items;
        if (!items.length) {
          status.textContent = messages.empty;
          if (result.partial && partialMessage) status.textContent += " " + partialMessage;
        } else {
          items.forEach(function (item, index) {
            resultList.appendChild(options.renderResult(item, {
              panel: panel,
              status: status,
              csrf: csrf,
              index: index
            }));
          });
          var message = items.length === 1
            ? messages.one
            : messages.many.replace("%d", items.length);
          if (result.partial && partialMessage) message += " " + partialMessage;
          status.textContent = message;
        }
        resultsHeading.focus();
      }).catch(function (error) {
        resultList.replaceChildren();
        if (options.onError) options.onError(status);
        status.textContent = error && error.message ? error.message : messages.failed;
        resultsHeading.focus();
      }).finally(function () {
        button.disabled = false;
        if (results) results.setAttribute("aria-busy", "false");
      });
    });
  }

  global.CWA = global.CWA || {};
  global.CWA.metadataSearch = {element: element, init: init};
}(window));
