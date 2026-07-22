import { createReadStream } from "node:fs";
import { access, readFile, stat } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const host = process.env.HOST || "0.0.0.0";
const port = Number(process.env.PORT || 5173);
const dist = resolve(fileURLToPath(new URL("./dist/", import.meta.url)));
const indexPath = resolve(dist, "index.html");
const packageJson = JSON.parse(await readFile(new URL("./package.json", import.meta.url), "utf8"));

const mimeTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".ico": "image/x-icon",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".map": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".webp": "image/webp",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
};

function securityHeaders() {
  return {
    "Content-Security-Policy": "default-src 'self'; connect-src 'self' http: https: ws: wss:; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; font-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
  };
}

async function existingFile(path) {
  try {
    await access(path);
    return (await stat(path)).isFile();
  } catch {
    return false;
  }
}

async function sendFile(request, response, sourcePath, requestPath) {
  const accepted = request.headers["accept-encoding"] || "";
  let servedPath = sourcePath;
  let encoding;
  if (accepted.includes("br") && await existingFile(`${sourcePath}.br`)) {
    servedPath = `${sourcePath}.br`;
    encoding = "br";
  } else if (accepted.includes("gzip") && await existingFile(`${sourcePath}.gz`)) {
    servedPath = `${sourcePath}.gz`;
    encoding = "gzip";
  }

  const metadata = await stat(servedPath);
  const immutable = requestPath.startsWith("/assets/");
  response.writeHead(200, {
    ...securityHeaders(),
    "Cache-Control": immutable ? "public, max-age=31536000, immutable" : "no-store",
    "Content-Length": metadata.size,
    "Content-Type": mimeTypes[extname(sourcePath)] || "application/octet-stream",
    ...(encoding ? { "Content-Encoding": encoding, "Vary": "Accept-Encoding" } : {}),
  });
  if (request.method === "HEAD") return response.end();
  createReadStream(servedPath).pipe(response);
}

const server = createServer(async (request, response) => {
  try {
    if (!request.url || !["GET", "HEAD"].includes(request.method || "")) {
      response.writeHead(405, { ...securityHeaders(), "Allow": "GET, HEAD" });
      return response.end();
    }
    const requestPath = decodeURIComponent(new URL(request.url, `http://${request.headers.host || "localhost"}`).pathname);
    if (requestPath === "/healthz") {
      const body = JSON.stringify({ status: "ok", version: packageJson.version });
      response.writeHead(200, {
        ...securityHeaders(),
        "Cache-Control": "no-store",
        "Content-Type": "application/json; charset=utf-8",
        "Content-Length": Buffer.byteLength(body),
      });
      return request.method === "HEAD" ? response.end() : response.end(body);
    }

    const relative = requestPath.replace(/^\/+/, "");
    const candidate = resolve(dist, relative);
    if (candidate !== dist && !candidate.startsWith(`${dist}${sep}`)) {
      response.writeHead(400, securityHeaders());
      return response.end();
    }

    if (relative && await existingFile(candidate)) {
      return sendFile(request, response, candidate, requestPath);
    }
    if (extname(requestPath)) {
      response.writeHead(404, { ...securityHeaders(), "Cache-Control": "no-store" });
      return response.end();
    }
    return sendFile(request, response, indexPath, "/");
  } catch (error) {
    console.error("Błąd serwera statycznego:", error);
    response.writeHead(500, { ...securityHeaders(), "Cache-Control": "no-store" });
    response.end();
  }
});

server.listen(port, host, () => {
  console.log(`MStock frontend v${packageJson.version}: http://${host}:${port}`);
});

function shutdown() {
  server.close(error => process.exit(error ? 1 : 0));
  setTimeout(() => process.exit(1), 5000).unref();
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
