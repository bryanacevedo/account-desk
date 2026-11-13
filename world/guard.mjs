// The truth-visibility check for a TypeScript desk: the twin of guard.py, copied into every slice.
// Usage: node guard.mjs REPO "src/server/sim-*.ts" ...   exits 1 and lists the files when any are found.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, extname, sep } from "node:path";

const SOURCE = new Set([".py", ".ts", ".tsx", ".js", ".mjs", ".sql"]);
const SKIP = new Set(["node_modules", ".venv", ".git", "dist", "build", "__pycache__", "tests", "samples", "world"]);
const MENTION = /truth\/|["']truth["']/;
const glob = (g) => new RegExp("^" + g.split("*").map((s) => s.replace(/[.+?^${}()|[\]\\]/g, "\\$&")).join("[^/]*") + "$");

export function violations(repo, allowed) {
  const pats = allowed.map(glob);
  const bad = [];
  const walk = (dir) => {
    for (const name of readdirSync(dir).sort()) {
      const p = join(dir, name);
      if (statSync(p).isDirectory()) { if (!SKIP.has(name) && !name.startsWith(".")) walk(p); continue; }  // hidden: worktrees, tools
      if (!SOURCE.has(extname(name))) continue;
      const rel = relative(repo, p).split(sep).join("/");
      if (!MENTION.test(readFileSync(p, "utf8"))) continue;
      if (!pats.some((r) => r.test(rel))) bad.push(rel);
    }
  };
  walk(repo);
  return bad;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const found = violations(process.argv[2], process.argv.slice(3));
  console.log(found.join("\n") || "No module outside the allowed list reads the truth.");
  process.exit(found.length ? 1 : 0);
}
