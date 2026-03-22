#!/usr/bin/env node
"use strict";

/**
 * Default pattern set for telemetry signal detection.
 * Patterns are case-insensitive and intentionally avoid /g to keep .test()
 * deterministic across repeated calls.
 */
const DEFAULT_PATTERNS = {
  phone: /\b(?:phone|cell|gsm|lte|ims)\b/i,
  trap: /\b(?:trap|snare|hook|redirect)\b/i,
  ai: /\b(?:ai|ml|model|agent)\b/i,
  telegraphy: /\b(?:telegraph|morse|signal|carrier)\b/i,
  browser_hook: /\b(?:browser|chrome|chromium|electron|webview|openexternal|launch\s+browser|force(?:d)?\s+browser|user[-\s]?agent)\b/i,
};

/**
 * Scan text and return normalized telemetry flags.
 *
 * @param {string} text
 * @param {{ patterns?: Record<string, RegExp>, log?: (msg: string) => void }} [options]
 * @returns {string[]}
 */
function scanTelemetry(text, options = {}) {
  if (typeof text !== "string" || !text.trim()) return [];

  const patterns = options.patterns || DEFAULT_PATTERNS;
  const log = options.log || ((msg) => console.log(msg));
  const flags = [];

  for (const [key, pattern] of Object.entries(patterns)) {
    if (pattern.test(text)) flags.push(key.toUpperCase());
  }

  if (flags.length) {
    log(`AUTO-TELEMETRY FLAGS: ${flags.join(", ")}`);
  }

  return flags;
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { scanTelemetry, DEFAULT_PATTERNS };
}

if (typeof require !== "undefined" && require.main === module) {
  const input = process.argv.slice(2).join(" ");
  if (!input) {
    console.error('Usage: node scripts/scanTelemetry.js "<text to scan>"');
    process.exit(1);
  }
  scanTelemetry(input);
}
