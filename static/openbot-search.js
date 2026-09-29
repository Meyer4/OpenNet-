/* Client-side document retrieval for OpenBot.
 *
 * This mirrors search_documents() in app.py so a static host (GitHub Pages)
 * answers the same way the Flask server does. searchDocs() is pure and is
 * tested against the Python implementation by tests/js/test_parity.mjs.
 */
(function (root) {
  'use strict';

  var CHUNK_SIZE = 700;
  var OVERLAP = 120;
  var TITLE_THRESHOLD = 0.55;

  // Must stay identical to STOPWORDS in app.py; tests/js/parity_check.mjs
  // fails if the two implementations rank anything differently.
  var STOPWORDS = new Set([
    "a", "about", "above", "after", "again", "all", "also", "am",
    "an", "and", "any", "are", "as", "at", "be", "because",
    "been", "before", "being", "below", "between", "both", "but", "by",
    "can", "could", "did", "do", "does", "doing", "down", "during",
    "each", "few", "for", "from", "further", "had", "has", "have",
    "having", "he", "her", "here", "hers", "him", "his", "how",
    "i", "if", "in", "into", "is", "it", "its", "itself",
    "just", "me", "more", "most", "my", "no", "nor", "not",
    "of", "off", "on", "once", "only", "or", "other", "our",
    "ours", "out", "over", "own", "same", "she", "should", "so",
    "some", "such", "than", "that", "the", "their", "theirs", "them",
    "then", "there", "these", "they", "this", "those", "through", "to",
    "too", "under", "until", "up", "very", "was", "we", "were",
    "what", "when", "where", "which", "while", "who", "whom", "why",
    "will", "with", "you", "your", "yours"
  ]);

  function tokens(text) {
    var words = String(text).toLowerCase().match(/[a-z0-9']+/g) || [];
    var out = new Set();
    for (var i = 0; i < words.length; i++) {
      if (!STOPWORDS.has(words[i])) { out.add(words[i]); }
    }
    return out;
  }

  function chunks(text) {
    var cleaned = String(text)
      .replace(/[ \t]+/g, ' ')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
    if (!cleaned) { return []; }
    var step = Math.max(CHUNK_SIZE - OVERLAP, 1);
    var out = [];
    for (var i = 0; i < cleaned.length; i += step) {
      var piece = cleaned.slice(i, i + CHUNK_SIZE).trim();
      if (piece) { out.push(piece); }
    }
    return out;
  }

  function scoreChunk(chunkTokens, queryTokens) {
    if (queryTokens.size === 0) { return 0; }
    var hits = 0;
    queryTokens.forEach(function (token) {
      if (chunkTokens.has(token)) { hits += 1; }
    });
    return hits === 0 ? 0 : hits / queryTokens.size;
  }

  // Length of the longest common subsequence, used for the title similarity.
  function lcsLength(a, b) {
    var prev = new Array(b.length + 1).fill(0);
    var curr = new Array(b.length + 1).fill(0);
    for (var i = 1; i <= a.length; i++) {
      for (var j = 1; j <= b.length; j++) {
        curr[j] = a[i - 1] === b[j - 1]
          ? prev[j - 1] + 1
          : Math.max(prev[j], curr[j - 1]);
      }
      var swap = prev; prev = curr; curr = swap;
      curr.fill(0);
    }
    return prev[b.length];
  }

  function ratio(a, b) {
    a = String(a).toLowerCase();
    b = String(b).toLowerCase();
    if (!a.length && !b.length) { return 1; }
    if (!a.length || !b.length) { return 0; }
    return (2 * lcsLength(a, b)) / (a.length + b.length);
  }

  function trimSnippet(text, limit) {
    if (text.length <= limit) { return text; }
    var cut = text.slice(0, limit);
    var lastSpace = cut.lastIndexOf(' ');
    return (lastSpace > 0 ? cut.slice(0, lastSpace) : cut) + '...';
  }

  /**
   * Rank documents against a question. Pure: pass [{name, text}].
   * Returns [{name, score, snippet, kind}] best first.
   */
  function searchDocs(question, docs, topK) {
    var queryTokens = tokens(question);
    if (queryTokens.size === 0) { return []; }
    var limit = topK || 3;
    var results = [];

    docs.forEach(function (doc) {
      var nameRatio = ratio(doc.name, question);
      if (nameRatio > TITLE_THRESHOLD) {
        results.push({
          name: doc.name,
          score: Math.round(nameRatio * 1000) / 1000,
          snippet: 'The document title matches your question.',
          kind: 'title'
        });
      }

      var bestScore = 0;
      var bestChunk = '';
      chunks(doc.text || '').forEach(function (chunk) {
        var s = scoreChunk(tokens(chunk), queryTokens);
        if (s > bestScore) { bestScore = s; bestChunk = chunk; }
      });

      if (bestScore > 0) {
        results.push({
          name: doc.name,
          score: Math.round(bestScore * 1000) / 1000,
          snippet: trimSnippet(bestChunk, 340),
          kind: 'content'
        });
      }
    });

    results.sort(function (a, b) { return b.score - a.score; });

    // A document can match by title and by content; keep only its best entry.
    var bestByName = {};
    var deduped = [];
    results.forEach(function (item) {
      if (!bestByName[item.name]) {
        bestByName[item.name] = true;
        deduped.push(item);
      }
    });

    return deduped.slice(0, limit);
  }

  /** Fetch the bundled documents, then rank them. Used on static hosts. */
  async function search(question, docsUrl, topK) {
    var base = docsUrl || 'docs/';
    var response = await fetch(base + 'index.json', { cache: 'force-cache' });
    if (!response.ok) {
      throw new Error('Could not load the document index (' + response.status + ')');
    }
    var manifest = await response.json();

    var docs = await Promise.all((manifest.documents || []).map(async function (entry) {
      if (!entry.searchable) { return { name: entry.name, text: '' }; }
      var res = await fetch(base + entry.file, { cache: 'force-cache' });
      return { name: entry.name, text: res.ok ? await res.text() : '' };
    }));

    return searchDocs(question, docs, topK);
  }

  root.OpenBotSearch = {
    search: search,
    searchDocs: searchDocs,
    tokens: tokens,
    chunks: chunks,
    ratio: ratio
  };
})(typeof window !== 'undefined' ? window : globalThis);
