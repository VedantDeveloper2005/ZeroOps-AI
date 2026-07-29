import {
  cpSync,
  existsSync,
  mkdirSync,
  rmSync,
} from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const standaloneRoot = resolve(repositoryRoot, ".next", "standalone");
const serverPath = resolve(standaloneRoot, "server.js");

if (!existsSync(serverPath)) {
  throw new Error("Standalone output is missing. Run `npm run build` before `npm start`.");
}

const assets = [
  {
    source: resolve(repositoryRoot, "public"),
    destination: resolve(standaloneRoot, "public"),
  },
  {
    source: resolve(repositoryRoot, ".next", "static"),
    destination: resolve(standaloneRoot, ".next", "static"),
  },
];

for (const { source, destination } of assets) {
  if (!existsSync(source)) continue;
  rmSync(destination, { force: true, recursive: true });
  mkdirSync(dirname(destination), { recursive: true });
  cpSync(source, destination, { recursive: true });
}

await import(pathToFileURL(serverPath).href);
