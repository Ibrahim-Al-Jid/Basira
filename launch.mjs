import { existsSync } from "node:fs";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = fileURLToPath(new URL(".", import.meta.url));
const venv = path.join(root, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const args = process.argv[2] === "test"
  ? ["-m", "pytest", "-q", "backend"]
  : ["-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", process.env.PORT ?? "8765"];
const child = spawn(existsSync(venv) ? venv : "python", args, { cwd: root, stdio: "inherit" });
child.on("error", error => { console.error(error.message); process.exitCode = 1; });
child.on("exit", code => { process.exitCode = code ?? 1; });
