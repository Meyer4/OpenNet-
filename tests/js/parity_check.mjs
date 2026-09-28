/* Compares the browser retrieval against results produced by app.py.
 *
 * Invoked by tests/test_app.py with a JSON file of expected results:
 *   node tests/js/parity_check.mjs /tmp/expected.json <docsDir>
 * Exits non-zero on the first mismatch.
 */
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const [, , expectedPath, docsDir] = process.argv;
if (!expectedPath || !docsDir) {
  console.error('usage: parity_check.mjs <expected.json> <docsDir>');
  process.exit(2);
}

// Load the browser module. It attaches to globalThis when there is no window.
const src = readFileSync(new URL('../../static/openbot-search.js', import.meta.url), 'utf8');
(0, eval)(src);
const { searchDocs } = globalThis.OpenBotSearch;

const docs = readdirSync(docsDir)
  .filter((name) => /\.(txt|md|markdown|rst|csv|json)$/i.test(name))
  .sort()
  .map((name) => ({ name, text: readFileSync(join(docsDir, name), 'utf8') }));

const expected = JSON.parse(readFileSync(expectedPath, 'utf8'));

let failures = 0;
for (const { question, expected_names, expected_top_score } of expected) {
  const actual = searchDocs(question, docs, 3);
  const actualNames = actual.map((m) => m.name);

  if (JSON.stringify(actualNames) !== JSON.stringify(expected_names)) {
    console.error(`MISMATCH for ${JSON.stringify(question)}`);
    console.error(`  python: ${JSON.stringify(expected_names)}`);
    console.error(`  js:     ${JSON.stringify(actualNames)}`);
    failures += 1;
    continue;
  }

  if (actual.length && Math.abs(actual[0].score - expected_top_score) > 0.01) {
    console.error(`SCORE MISMATCH for ${JSON.stringify(question)}`);
    console.error(`  python: ${expected_top_score}  js: ${actual[0].score}`);
    failures += 1;
    continue;
  }

  console.log(`ok  ${JSON.stringify(question)} -> ${JSON.stringify(actualNames)}`);
}

if (failures) {
  console.error(`\n${failures} of ${expected.length} queries disagreed with app.py`);
  process.exit(1);
}
console.log(`\nall ${expected.length} queries agree with app.py`);
