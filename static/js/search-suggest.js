/* Live search-bar autocomplete.
 *
 * As the user types, fetch movie suggestions (title + year) from the backend
 * (which proxies IMDb's suggestion API). Picking a suggestion sends the user
 * to the import endpoint, which scrapes the full record, saves it to the DB,
 * and redirects to that movie's detail page.
 */
(function () {
  "use strict";

  const form = document.querySelector(".header-search");
  const input = document.getElementById("search-input");
  const list = document.getElementById("search-suggestions");
  if (!form || !input || !list) return;

  const suggestUrl = form.dataset.suggestUrl || "/api/suggest/";
  const importUrl = form.dataset.importUrl || "/movies/import/";
  const overlay = document.getElementById("import-overlay");

  let items = [];
  let activeIndex = -1;
  let lastQuery = "";
  let debounceTimer = null;
  let controller = null;

  function buildImportHref(item) {
    const params = new URLSearchParams({ title: item.title });
    if (item.year) params.set("year", item.year);
    if (item.imdb_url) params.set("imdb_url", item.imdb_url);
    return importUrl + "?" + params.toString();
  }

  function closeList() {
    list.hidden = true;
    list.innerHTML = "";
    input.setAttribute("aria-expanded", "false");
    items = [];
    activeIndex = -1;
  }

  function setActive(index) {
    const options = list.querySelectorAll(".suggestion");
    options.forEach((el) => el.classList.remove("is-active"));
    if (index >= 0 && index < options.length) {
      options[index].classList.add("is-active");
      options[index].scrollIntoView({ block: "nearest" });
      activeIndex = index;
    } else {
      activeIndex = -1;
    }
  }

  function renderSuggestions(suggestions) {
    items = suggestions;
    activeIndex = -1;
    if (!suggestions.length) {
      closeList();
      return;
    }

    const fallback = "/static/img/MovieCinema.jpg";
    list.innerHTML = suggestions
      .map(function (item, i) {
        const img = item.image || fallback;
        const year = item.year
          ? '<span class="suggestion-year">' + item.year + "</span>"
          : "";
        return (
          '<li class="suggestion" role="option" id="suggestion-' + i + '" data-index="' + i + '">' +
            '<img class="suggestion-img" src="' + img + '" alt="" loading="lazy" ' +
              "onerror=\"this.src='" + fallback + "'\">" +
            '<span class="suggestion-text">' +
              '<span class="suggestion-title">' + escapeHtml(item.title) + "</span>" +
              year +
            "</span>" +
          "</li>"
        );
      })
      .join("");

    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fetchSuggestions(query) {
    if (controller) controller.abort();
    controller = new AbortController();

    fetch(suggestUrl + "?q=" + encodeURIComponent(query), {
      signal: controller.signal,
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (resp) { return resp.ok ? resp.json() : { suggestions: [] }; })
      .then(function (data) {
        // Ignore stale responses if the input changed while in flight.
        if (input.value.trim() !== query) return;
        renderSuggestions((data && data.suggestions) || []);
      })
      .catch(function () { /* aborted or network error — keep current list */ });
  }

  function chooseItem(item) {
    if (!item) return;
    if (overlay) overlay.hidden = false;
    window.location.href = buildImportHref(item);
  }

  input.addEventListener("input", function () {
    const query = input.value.trim();
    if (query === lastQuery) return;
    lastQuery = query;

    clearTimeout(debounceTimer);
    if (query.length < 2) {
      closeList();
      return;
    }
    debounceTimer = setTimeout(function () { fetchSuggestions(query); }, 250);
  });

  input.addEventListener("keydown", function (event) {
    if (list.hidden || !items.length) return;

    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((activeIndex + 1) % items.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((activeIndex - 1 + items.length) % items.length);
    } else if (event.key === "Enter") {
      if (activeIndex >= 0) {
        event.preventDefault();
        chooseItem(items[activeIndex]);
      }
    } else if (event.key === "Escape") {
      closeList();
    }
  });

  list.addEventListener("mousedown", function (event) {
    // mousedown (not click) so it fires before the input's blur closes the list.
    const li = event.target.closest(".suggestion");
    if (!li) return;
    event.preventDefault();
    const index = parseInt(li.dataset.index, 10);
    chooseItem(items[index]);
  });

  document.addEventListener("click", function (event) {
    if (!form.contains(event.target)) closeList();
  });

  // "Top Matches" cards import on click — show the loading overlay while the
  // backend scrapes + saves the movie before redirecting to its detail page.
  document.querySelectorAll(".import-link").forEach(function (link) {
    link.addEventListener("click", function () {
      if (overlay) overlay.hidden = false;
    });
  });
})();
