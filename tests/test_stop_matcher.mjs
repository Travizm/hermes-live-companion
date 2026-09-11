// Mirrors the matcher in the patched bundle (dashboard/dist/index.js).
// A prefix regex false-fired on "goodbye was what he said in the movie", and commas broke
// "Hey Chaddy, that's all" — hence whole-clause matching after normalisation.
const STOP_PHRASES = ["stop listening", "stop voice", "that's all", "thats all", "disconnect",
  "end session", "end the session", "go to sleep", "sleep now", "goodbye", "bye",
  "we're done", "were done", "i'm done", "im done", "shut down", "hang up"];
const WAKE_PREFIXES = ["hey chaddy", "chaddy", "okay", "ok", "hi", "hey", "please", "alright", "thanks"];
const TRAILERS = ["please", "now", "thanks", "thank you", "folks", "mate", "then", "chaddy", "hermes", "okay", "ok"];

function normalizeUtterance(text) {
  return String(text || "").toLowerCase().replace(/[^a-z0-9' ]+/g, " ").replace(/\s+/g, " ").trim();
}
function clauseTriggersStop(clause) {
  let words = clause.split(" ").filter(Boolean);
  let changed = true;
  while (changed && words.length) {
    changed = false;
    for (const prefix of WAKE_PREFIXES) {
      const prefixWords = prefix.split(" ");
      if (words.slice(0, prefixWords.length).join(" ") === prefix) {
        words = words.slice(prefixWords.length); changed = true;
      }
    }
  }
  const rest = words.join(" ");
  if (!rest) return false;
  for (const phrase of STOP_PHRASES) {
    if (rest === phrase) return true;
    if (rest.startsWith(phrase + " ") && TRAILERS.includes(rest.slice(phrase.length + 1))) return true;
  }
  return false;
}
export function shouldDisconnect(text) {
  return normalizeUtterance(text).split(/\s+and\s+|[,;.!?]+/)
    .some(function (clause) { return clauseTriggersStop(clause.trim()); });
}

const cases = [
  ["stop listening", true], ["Stop listening.", true], ["Hey Chaddy, that's all", true],
  ["hey chaddy stop listening", true], ["okay, goodbye", true], ["go to sleep", true],
  ["disconnect", true], ["end session", true], ["that's all folks", true],
  ["Hey Chaddy, we're done thanks", true], ["thanks Chaddy, hang up", true],
  ["don't stop the server", false], ["stop the server", false],
  ["we should disconnect the battery", false], ["goodbye was what he said in the movie", false],
  ["can you restart the gateway", false], ["the disconnect happened yesterday", false], ["", false],
];
let pass = 0, fail = 0;
for (const [text, expected] of cases) {
  const got = shouldDisconnect(text);
  got === expected ? pass++ : fail++;
  console.log(`${got === expected ? "PASS" : "FAIL"}  expected=${String(expected).padEnd(5)} got=${String(got).padEnd(5)} ${JSON.stringify(text)}`);
}
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
