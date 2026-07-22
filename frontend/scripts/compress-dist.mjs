import { readdir, readFile, stat, writeFile } from "node:fs/promises";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { brotliCompress, gzip } from "node:zlib";
import { promisify } from "node:util";

const gzipAsync = promisify(gzip);
const brotliAsync = promisify(brotliCompress);
const root = fileURLToPath(new URL("../dist/", import.meta.url));
const compressible = new Set([".css", ".html", ".js", ".json", ".svg"]);

async function filesBelow(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(entries.map(async entry => {
    const path = join(directory, entry.name);
    return entry.isDirectory() ? filesBelow(path) : [path];
  }));
  return nested.flat();
}

let generated = 0;
for (const path of await filesBelow(root)) {
  if (!compressible.has(extname(path)) || (await stat(path)).size < 1024) continue;
  const source = await readFile(path);
  const [gzipped, brotlied] = await Promise.all([
    gzipAsync(source, { level: 9 }),
    brotliAsync(source, { params: { 1: 11 } }),
  ]);
  await Promise.all([
    writeFile(`${path}.gz`, gzipped),
    writeFile(`${path}.br`, brotlied),
  ]);
  generated += 2;
}

console.log(`Prekompresja dist: utworzono ${generated} plików .gz/.br`);
