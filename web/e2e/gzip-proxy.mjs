// A compressing reverse proxy for the side-by-side measurement: `streamlit run` serves its 5 MB of JavaScript
// uncompressed, while a host (and the web app's API) gzips. Measuring Streamlit through this proxy keeps the
// comparison about the frameworks, not about one server's missing gzip.
//   node e2e/gzip-proxy.mjs http://localhost:8577 8578      → MEASURE_ST_URL=http://localhost:8578
// HTTP bodies of text types are gzipped (level 6) when the browser accepts gzip; WebSocket upgrades pass through.
import http from "node:http";
import net from "node:net";
import zlib from "node:zlib";

const [target = "http://localhost:8577", port = "8578"] = process.argv.slice(2);
const t = new URL(target);

const server = http.createServer((req, res) => {
  const headers = { ...req.headers, host: t.host, "accept-encoding": "identity" };
  const up = http.request({ host: t.hostname, port: t.port, path: req.url, method: req.method, headers }, (r) => {
    const type = String(r.headers["content-type"] ?? "");
    const gz = /gzip/.test(String(req.headers["accept-encoding"] ?? "")) && /(javascript|css|html|json|svg|text)/.test(type) && !r.headers["content-encoding"];
    const out = { ...r.headers };
    if (gz) {
      delete out["content-length"];
      out["content-encoding"] = "gzip";
      out.vary = "Accept-Encoding";
    }
    res.writeHead(r.statusCode ?? 502, out);
    (gz ? r.pipe(zlib.createGzip({ level: 6 })) : r).pipe(res);
  });
  up.on("error", () => {
    res.writeHead(502);
    res.end();
  });
  req.pipe(up);
});

server.on("upgrade", (req, socket, head) => {
  const up = net.connect(Number(t.port), t.hostname, () => {
    const lines = [`${req.method} ${req.url} HTTP/1.1`];
    for (let i = 0; i < req.rawHeaders.length; i += 2) {
      const k = req.rawHeaders[i];
      lines.push(`${k}: ${k.toLowerCase() === "host" ? t.host : req.rawHeaders[i + 1]}`);
    }
    up.write(lines.join("\r\n") + "\r\n\r\n");
    if (head?.length) up.write(head);
    socket.pipe(up).pipe(socket);
  });
  up.on("error", () => socket.destroy());
  socket.on("error", () => up.destroy());
});

server.listen(Number(port), () => console.log(`gzip proxy :${port} → ${target}`));
