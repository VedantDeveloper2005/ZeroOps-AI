import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function readProjectFile(relativePath) {
  return readFileSync(new URL(relativePath, new URL("../", import.meta.url)), "utf8");
}

const homepageSource = readProjectFile(
  "src/components/landing/MarketingHome.tsx",
);
const previewSource = readProjectFile(
  "src/components/landing/HomeHeroMotion.tsx",
);
const layoutSource = readProjectFile("src/app/layout.tsx");

function findMatchingSquareBracket(source, openingIndex) {
  let depth = 0;
  let quote = null;
  let escaped = false;
  let lineComment = false;
  let blockComment = false;

  for (let index = openingIndex; index < source.length; index += 1) {
    const character = source[index];
    const nextCharacter = source[index + 1];

    if (lineComment) {
      if (character === "\n") lineComment = false;
      continue;
    }

    if (blockComment) {
      if (character === "*" && nextCharacter === "/") {
        blockComment = false;
        index += 1;
      }
      continue;
    }

    if (quote) {
      if (escaped) {
        escaped = false;
      } else if (character === "\\") {
        escaped = true;
      } else if (character === quote) {
        quote = null;
      }
      continue;
    }

    if (character === "/" && nextCharacter === "/") {
      lineComment = true;
      index += 1;
      continue;
    }

    if (character === "/" && nextCharacter === "*") {
      blockComment = true;
      index += 1;
      continue;
    }

    if (character === '"' || character === "'" || character === "`") {
      quote = character;
      continue;
    }

    if (character === "[") depth += 1;
    if (character === "]") {
      depth -= 1;
      if (depth === 0) return index;
    }
  }

  throw new Error("Capability array is missing its closing bracket.");
}

function splitTopLevelArrayItems(arrayBody) {
  const items = [];
  let itemStart = 0;
  let braceDepth = 0;
  let bracketDepth = 0;
  let parenthesisDepth = 0;
  let quote = null;
  let escaped = false;
  let lineComment = false;
  let blockComment = false;

  for (let index = 0; index < arrayBody.length; index += 1) {
    const character = arrayBody[index];
    const nextCharacter = arrayBody[index + 1];

    if (lineComment) {
      if (character === "\n") lineComment = false;
      continue;
    }

    if (blockComment) {
      if (character === "*" && nextCharacter === "/") {
        blockComment = false;
        index += 1;
      }
      continue;
    }

    if (quote) {
      if (escaped) {
        escaped = false;
      } else if (character === "\\") {
        escaped = true;
      } else if (character === quote) {
        quote = null;
      }
      continue;
    }

    if (character === "/" && nextCharacter === "/") {
      lineComment = true;
      index += 1;
      continue;
    }

    if (character === "/" && nextCharacter === "*") {
      blockComment = true;
      index += 1;
      continue;
    }

    if (character === '"' || character === "'" || character === "`") {
      quote = character;
      continue;
    }

    if (character === "{") braceDepth += 1;
    if (character === "}") braceDepth -= 1;
    if (character === "[") bracketDepth += 1;
    if (character === "]") bracketDepth -= 1;
    if (character === "(") parenthesisDepth += 1;
    if (character === ")") parenthesisDepth -= 1;

    if (
      character === "," &&
      braceDepth === 0 &&
      bracketDepth === 0 &&
      parenthesisDepth === 0
    ) {
      const item = arrayBody.slice(itemStart, index).trim();
      if (item) items.push(item);
      itemStart = index + 1;
    }
  }

  const finalItem = arrayBody.slice(itemStart).trim();
  if (finalItem) items.push(finalItem);

  return items;
}

function extractCapabilities(source) {
  const declaration =
    /(?:export\s+)?const\s+([A-Za-z_$][\w$]*capabilities)\s*(?::[^=]+)?=\s*\[/gi;
  const matches = [...source.matchAll(declaration)];

  assert.ok(
    matches.length > 0,
    "Declare a capabilities array so the public MVP scope remains testable.",
  );

  const match =
    matches.find((candidate) => /(?:current|mvp)/i.test(candidate[1])) ??
    matches[0];
  const openingIndex = match.index + match[0].lastIndexOf("[");
  const closingIndex = findMatchingSquareBracket(source, openingIndex);
  const body = source.slice(openingIndex + 1, closingIndex);

  return {
    name: match[1],
    body,
    items: splitTopLevelArrayItems(body),
  };
}

test("homepage keeps one accessible primary content structure", () => {
  assert.equal(
    (homepageSource.match(/<h1\b/g) ?? []).length,
    1,
    "The homepage must have exactly one h1.",
  );
  assert.match(homepageSource, /<main\b[^>]*\bid=["']main-content["']/);
  assert.match(layoutSource, /href=["']#main-content["']/);
  assert.match(
    homepageSource,
    /<section\b(?=[^>]*\bid=["']capabilities["'])[^>]*>/,
  );
  assert.match(
    homepageSource,
    /<section\b(?=[^>]*\bid=["']workflow["'])[^>]*>[\s\S]*?<ol\b/,
  );
});

test("homepage presents exactly three truthful MVP capabilities", () => {
  const capabilities = extractCapabilities(homepageSource);

  assert.equal(
    capabilities.items.length,
    3,
    `${capabilities.name} must contain exactly three focused MVP capabilities.`,
  );
  const statuses = [
    ...capabilities.body.matchAll(
      /\bstatus\s*:\s*["'`](available|setup_required)["'`]/g,
    ),
  ].map((match) => match[1]);
  assert.equal(
    statuses.length,
    capabilities.items.length,
    "Every capability must use an available or setup_required status.",
  );
  assert.ok(statuses.includes("available"));
  assert.ok(statuses.includes("setup_required"));
  assert.match(homepageSource, /\bMVP\b/i);
  assert.match(
    homepageSource,
    /\b(?:setup required|requires?\s+(?:operator\s+)?setup|unavailable)\b/i,
    "Setup-dependent or unavailable behavior must remain visible.",
  );
  assert.doesNotMatch(
    capabilities.body,
    /\b(?:fully autonomous|production[- ]ready|zero[- ]touch|one[- ]click|self[- ]healing|guaranteed)\b/i,
    "Positive capability copy must not promise unsupported automation or readiness.",
  );
});

test("homepage retains a real signup action", () => {
  assert.equal(
    (homepageSource.match(/href=["']\/signup["']/g) ?? []).length,
    2,
    "The hero and closing primary actions must both lead to signup.",
  );
});

test("hero preview is illustrative, reduced-motion aware, and not fake runtime progress", () => {
  const combinedSource = `${homepageSource}\n${previewSource}`;

  assert.match(previewSource, /\buseReducedMotion\b/);
  assert.match(
    combinedSource,
    /(?:illustration only|illustrative preview|example only|not (?:a )?live (?:pipeline|status)|MVP preview)/i,
    "The product preview must be labeled as illustrative rather than live state.",
  );
  assert.doesNotMatch(
    previewSource,
    /\b(?:setInterval|setTimeout|requestAnimationFrame|Date\.now|Math\.random)\b/,
    "The homepage preview must not synthesize runtime progress.",
  );
  assert.doesNotMatch(
    previewSource,
    /\bstate\s*:\s*["'`](?:running|passed|success|succeeded|complete|completed)["'`]/i,
    "Illustrative steps must not masquerade as successful runtime states.",
  );
});
