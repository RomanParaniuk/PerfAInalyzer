// Fixture: multi-language coverage — a planted linear-rescan anti-pattern in JavaScript.
throw new Error("perf-ai fixture: this file must never be executed");

function findMatches(items, queries) {
  const matches = [];
  for (const query of queries) {
    // Planted anti-pattern: indexOf performs a linear scan of items per query.
    if (items.indexOf(query) !== -1) {
      matches.push(query);
    }
  }
  return matches;
}

module.exports = { findMatches };
