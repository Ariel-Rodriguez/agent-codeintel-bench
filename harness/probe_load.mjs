#!/usr/bin/env node
// Load an extension entry with a mock Pi API, to prove it imports cleanly and
// to record what it registers. Runs under a no-network, read-only container.
//
// Usage: node --experimental-strip-types probe_load.mjs <entry-file>
//
// Exit codes: 0 loaded, 3 load/registration threw.
import { pathToFileURL } from "node:url";

const entry = process.argv[2];
if (!entry) {
  console.error("usage: probe_load.mjs <entry-file>");
  process.exit(2);
}

const registered = { tools: [], commands: [], events: [], flags: [] };
const record = (list) => (definition) => {
  const name = definition && (definition.name || definition.id);
  if (name) list.push(String(name));
};
const pi = new Proxy(
  {},
  {
    get(_target, prop) {
      switch (prop) {
        case "registerTool":
          return (definition) => {
            const name = definition && definition.name;
            if (name) registered.tools.push(String(name));
          };
        case "registerCommand":
          return record(registered.commands);
        case "registerFlag":
          return record(registered.flags);
        case "on":
          return (event) => registered.events.push(String(event));
        default:
          return () => undefined;
      }
    },
  },
);

try {
  const module = await import(pathToFileURL(entry).href);
  const factory = module.default ?? module;
  if (typeof factory !== "function") {
    console.error("PROBE LOAD FAILED: entry has no default export function");
    process.exit(3);
  }
  await factory(pi);
  console.log("PROBE LOAD OK " + JSON.stringify(registered));
} catch (error) {
  console.error("PROBE LOAD FAILED: " + (error && error.stack ? error.stack : String(error)));
  process.exit(3);
}
