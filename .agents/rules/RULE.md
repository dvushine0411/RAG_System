---
trigger: always_on
---

# SYSTEM & AGENT RULES (MANDATORY)

## 1. CORE WORKFLOW & ARCHITECTURE
- **Single Source of Truth:** Always read `ARCHITECTURE.md` before making any structural decisions.
- **Preview Before Execution:** Always report the intended folder structure and file changes for user approval BEFORE generating or modifying any code.
- **Version Check:** Always verify the installed versions of core frameworks (Node.js, Python, FastAPI, React) before writing syntax-specific code.

## 2. CODE STRUCTURE & MODULARITY
- **Microservices Isolation:** Any component defined in `ARCHITECTURE.md` must be initialized as an independent folder with its own isolated environment (e.g., `Dockerfile`, `.env`).
- **Single Responsibility:** Each specific function must reside in its own separate file. 
  *Example:* Text chunking logic belongs in `chunking.py`; vector database operations belong in `vector_db.py`.

## 3. STRICT DEPENDENCY MANAGEMENT
- **Initialization:** If `package.json` or `requirements.txt` do not exist during setup, you MUST automatically create and populate them. Do NOT ask the user to manually create these files.
- **Zero Unauthorized Installations:** Never execute install commands (`npm install`, `pip install`) in the terminal without explicit user permission.
- **Manifest Synchronization:** If a dependency is approved, you MUST immediately save it to `package.json` (Node.js) or `requirements.txt` (Python) with pinned versions.
- **Post-Generation Dependency Audit:** Whenever you generate or modify code files, you MUST perform this 3-step audit:
  1. *Scan Imports:* Extract all `import`/`require()` statements from the new code.
  2. *Cross-Reference:* Check if non-built-in modules exist in the corresponding manifest files.
  3. *Action:* If missing dependencies are found, explicitly update the manifest files. Do NOT auto-install. Stop and alert the user: *"Missing dependencies added to manifests. Run `docker-compose build <service>` to resync."*

## 4. DOCUMENTATION, TRACKING & STATE UPDATES
Every time you create/modify files, complete a Task, or finish a Project Phase, BEFORE stopping your execution flow, you MUST perform the following actions:
- **Code-Level Documentation:** The absolute first lines of any new or modified code file (Docstring/Comment block) MUST contain a concise explanation of its exact system role, inputs, and outputs.
- **Architecture-Level Updates:** You MUST proactively update `ARCHITECTURE.md` across the following four sections:
  1. **Directory Dictionary:** When creating new folders/files, add a single-sentence definition of their exact purpose to the dictionary.
  2. **System Flow:** You MUST map out how the new files/modules interact using a Data Flow representation. Use strict arrow notation (`A -> B -> C`) or short functional chains (e.g., `routes/ingest.py -> factory.py (check KEY) -> openai_provider.py (batching) -> vector_ops.py (upsert)`). **STRICTLY NO verbose explanations.**
  3. **Update Roadmap:** Find the corresponding task in the `7. Implementation Progress & Roadmap Checklist` section and mark it as completed `[x]`.
  4. **Write Changelog:** Add a new bullet point under the `8. CHANGELOG` section. The entry MUST include:
     - Date (`YYYY-MM-DD`).
     - Brief summary of completed work.
     - Important technical decisions (e.g., port numbers, environment variables, new dependencies).
     - Any complex errors encountered and the specific solution applied.

## 5. CENTRALIZED CONFIGURATION & ZERO HARDCODING
1. No hardcore values: Never hardcode environment variables (e.g., Database URLs, API Keys, Ports) or algorithmic hyperparameters (e.g., HNSW M, ef_construct, chunk_size) directly into business logic files.
2. Import Principle: All other modules (routes, services, factories) must import the configuration instance exclusively from their respective service's central config file. Direct access to os.environ or process.env outside the central config file is strictly prohibited.