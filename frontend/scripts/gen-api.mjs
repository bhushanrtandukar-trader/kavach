// Regenerates src/lib/schema.d.ts from the Python API's OpenAPI schema, so the frontend's types
// can never drift from the backend.  Uses the project's own virtualenv.
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..", "..");
const python = [join(root, ".venv", "Scripts", "python.exe"), join(root, ".venv", "bin", "python")].find(existsSync);
if (!python) {
  console.error("Create the virtualenv first (see the README): python -m venv .venv");
  process.exit(1);
}
const spec = join(here, "..", "openapi.json");
execFileSync(python, [join(root, "scripts", "export_openapi.py"), spec], { stdio: "inherit" });
const bin = join(here, "..", "node_modules", "openapi-typescript", "bin", "cli.js");
execFileSync(process.execPath, [bin, spec, "-o", join(here, "..", "src", "lib", "schema.d.ts")], { stdio: "inherit" });
