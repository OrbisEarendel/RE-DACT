# RE-DACT

Privacy-controlled document sanitisation. RE-DACT finds personal information in documents, spreadsheets and images, then removes or transforms it at a privacy level the user chooses. Everything runs locally and offline.

Built by team StrangerStrings for CONVERGE '26.

> **Status:** this repository currently holds the **frontend UI** (`re-dact.html`). The redaction engine is a separate backend that the UI talks to through a small local API (see [Backend API](#backend-api)). Without that backend connected, the UI cannot process or save files, and it says so instead of faking results.

## What it does

- **Upload:** drag and drop or browse, multiple files, add or remove files at any time.
- **Choose what to redact:** names, emails, phone numbers, addresses, government IDs, financial information, other personal details, and custom words or phrases.
- **Choose a privacy level:**
  1. **Mask:** replace details with labels such as `[PERSON]`.
  2. **Pseudonyms:** consistent stand-ins (Person A stays Person A across files).
  3. **Anonymise:** generalise details so they cannot point to an individual.
  4. **Synthetic:** realistic fictional data that keeps structure and relationships.
- **Review, process, results:** summary before starting, per-file progress, results with optional before/after preview, and save to the Desktop.
- **Light, Dark and Auto themes:** the choice is remembered between sessions.

Supported inputs: text files (`txt`, `md`, `log`, `json`), spreadsheets (`csv`, `tsv`, `xlsx`, `xls`), `docx`, `pdf`, and images (`png`, `jpg`, `jpeg`, `tiff`, `bmp`). Video (`mp4`, `mov`, `mkv`) is only offered when the backend reports `video: true`.

## How it works

```
input -> classifier -> (image) OCR -> NLP model + Regex/checksums -> user picks what to redact -> redaction
```

- Detection combines rules, checksums, spaCy NER or GLiNER, dictionaries and context cues. Detected spans are cached, so changing the privacy level does not repeat detection.
- Images: OCR with bounding boxes, then the exact regions are removed.
- PDFs: true redaction (underlying text and pixels removed, metadata stripped). Scanned pages are treated as images.
- Each output is re-extracted to check that nothing sensitive remains.

## Architecture

```
Browser (local)  <-->  Docker container (local web server + engine)  -->  ~/Desktop/RE-DACT
   re-dact.html            --network none, no cloud, no third-party APIs
```

- The UI is one self-contained HTML file with no build step and no external dependencies apart from an optional Google Fonts stylesheet (it falls back to system fonts offline). For a fully offline setup, bundle the font locally.
- The engine runs in a hardened Docker container started with `--network none`.
- No file contents leave the machine. The UI only talks to its own origin (`/api/...`).

## Running

Placeholders below, adjust to your image and server setup.

1. Serve `re-dact.html` as the index page from the container's web server, next to the `/api` routes.
2. Start the container with no network and the Desktop output folder mounted:

   ```bash
   docker run --rm --network none \
     -p 127.0.0.1:8080:8080 \
     -v "$HOME/Desktop/RE-DACT:/output" \
     redact:latest
   ```

   `--network none` blocks outside traffic from the container. Check that your Docker setup still publishes the port to localhost, or use a unix socket or a local reverse proxy if it does not.
3. Open `http://127.0.0.1:8080` in a browser.

To preview the UI alone, open `re-dact.html` directly. The engine shows as not connected and **Start redaction** is blocked. A link on the Review screen opens the processing and results layouts as a labelled, layout-only preview.

## Backend API

The UI expects these endpoints (defined in the `API` object at the top of the script).

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Returns `{ "ok": true, "video": false }`. |
| `POST` | `/api/jobs` | Multipart form: `files` (repeated) and `options` (JSON). Returns `{ "id": "..." }`. |
| `GET` | `/api/jobs/:id` | Returns job status (see below). |
| `POST` | `/api/jobs/:id/save` | Writes output to the mounted Desktop folder. Returns `{ "folder": "..." }`. |
| `POST` | `/api/jobs/:id/open` | Opens the output folder on the host, if supported. |

`options` JSON:

```json
{ "categories": ["names", "email", "phone"], "custom": ["Project Atlas"], "level": "mask" }
```

`categories` values: `names`, `email`, `phone`, `address`, `govid`, `fin`, `other`.
`level` values: `mask`, `pseudonyms`, `anonymise`, `synthetic`.

Job status response:

```json
{
  "status": "running",
  "progress": 0.5,
  "files": [
    {
      "name": "report.pdf",
      "status": "done",
      "verified": true,
      "preview": { "before": "text", "after": "text" }
    },
    { "name": "scan.png", "status": "failed", "error": "OCR failed" }
  ]
}
```

- `status` is `running`, `done` or `failed`. Per-file `status` is `waiting`, `running`, `done` or `failed`.
- `verified` and `preview` are optional. The UI reports the re-extraction check as passed only when every file has `verified: true`, and otherwise says the engine did not report it.

## Saving output

Browsers cannot write to the Desktop on their own, so the backend does it. Mount `~/Desktop/RE-DACT` into the container and write there. Recommended behaviour:

- Never modify or overwrite the original files.
- Put a multi-file job in one new folder, for example `RE-DACT_2026-11-17_1430/`.
- Name outputs so they cannot collide with originals, for example `report.redacted.pdf`.

If you later package this as a desktop app (Tauri or Electron), replace the save and open calls with the native file-system dialog.

## Theming

Colours are CSS variables on `:root`, with dark values under `prefers-color-scheme` and `[data-theme="dark"]`. The preference is stored in `localStorage` under `redact-theme` (`system`, `light` or `dark`). To add a theme, add a new variable block.

## Extending

- **New detection category:** add an entry to the `CATS` array, then handle its key in the backend.
- **New privacy level:** add to `LEVELS` and to the `SAMPLE` strings used for the live example.
- **New file type:** add its extension to `TYPES` (the letter picks the icon).

## Known limits

- Implicit identifiers, pronouns and messy OCR scans can be missed. Review sensitive output before sharing.
- The UI does not claim a file is permanently redacted. It only reports what the backend returns.

## References

- Tesseract OCR: https://github.com/tesseract-ocr/tesseract
- GLiNER: https://github.com/urchade/GLiNER
