# dicom-pdf — Code Conventions

Conventions for writing Python in this repo. They describe the patterns already in
the code — where the code is inconsistent, follow what's documented here and align
the outlier when you touch it. Don't invent conventions that conflict with this.

For components and runtime flows, see `CLAUDE.md`. This file is only about how to
write code.

## 1. Guiding principles

This is a small, single-purpose service: PDF in, Encapsulated-PDF DICOM out — and the
reverse, DICOM in, embedded PDF out. Keep it that way.

- Solve what's asked, nothing more. Inline over abstract until there's real
  duplication (3+ call sites) or real complexity worth naming. More code is more bugs.
- No helper/wrapper for its own sake. If a stdlib call, pydicom, or FastAPI does the
  job, use it directly.
- Working code encodes edge cases (the PDF validation order, the double size check);
  don't rewrite it just to restyle it.

## 2. Module structure

```
src/dicom_pdf/
  main.py        # FastAPI app, CORS, GET / — wiring only
  api.py         # APIRouter: request shaping, HTTP status mapping, no business logic
  converter.py   # pure logic: convert_pdf_to_dicom + extract_pdf_from_dicom
                 # + _validate_pdf + _validate_dicom + _create_dicom_dataset
  models.py      # Pydantic request/response models + field validators
```

- `converter.py` stays framework-free (no FastAPI imports) so it's usable as a
  library (`from dicom_pdf import convert_pdf_to_dicom, extract_pdf_from_dicom`).
  Keep it that way.
- `api.py` is HTTP-only: validate the upload, call the converter, map exceptions to
  status codes, return the response. No DICOM/PDF logic there.
- Private module-level helpers are prefixed `_` (`_validate_pdf`, `_validate_dicom`,
  `_create_dicom_dataset`).

## 3. Naming & style

- `snake_case` functions/modules, `PascalCase` classes. Exceptions end in `Error`
  (`InvalidPDFError`, `DICOMCreationError`).
- `black` (line length 88) + `isort` (black profile) are authoritative for
  formatting; `flake8` max line 120. Run them before committing (`./run-tests.sh suite`).
- Full type hints and a short docstring on every `src` function — `mypy` runs strict
  (`disallow_untyped_defs`) on `src`. Tests are exempt.
- Keep comments short (2–3 lines max) and about *why*, not *what*.

## 4. Models & validation

- Request/response shapes are Pydantic v2 models in `models.py`. Add new input
  fields there with a `Field(..., description=..., examples=[...])` — the description
  feeds the OpenAPI docs.
- Cheap, structural validation (non-empty, UID format, date/time formats) goes in a
  `@field_validator` on the model. Semantic validation that needs the file bytes
  (magic bytes, page count, SOP class, size) goes in `converter._validate_pdf` /
  `converter._validate_dicom`.
- If you add a metadata field that maps to a DICOM tag, wire it through both
  `ConversionMetadata` **and** `_create_dicom_dataset`, and update the README table.

## 5. Error handling & HTTP mapping

- The converter raises domain exceptions only: `InvalidPDFError` / `InvalidDICOMError`
  (bad input) and `DICOMCreationError` / `PDFExtractionError` (unexpected failure).
  It never raises `HTTPException`.
- `api.py` owns the HTTP mapping: `400` bad file/PDF/DICOM/JSON · `413` too large
  (100MB PDF, 101MB DICOM) · `422` metadata validation · `500` creation/extraction/
  unexpected. Keep that mapping in one place.
- Small, specific exception classes per concern; catch them explicitly. The bad-input
  exceptions (`InvalidPDFError`, `InvalidDICOMError`) are re-raised as-is inside the
  converter — don't let them get wrapped into the 500-class exceptions.
- The `/dicom-to-pdf` route deliberately has **no file-extension check** — DICOM files
  legitimately ship without extensions and the content check (`dcmread`) is stronger.
  Don't "align" it with the `.pdf` check on the encode route.

## 6. DICOM conventions

- Output is **Encapsulated PDF Storage** (SOP Class `1.2.840.10008.5.1.4.1.1.104.1`,
  Modality `DOC`), Explicit VR Little Endian. Don't change the SOP class without a
  reason — downstream PACS depend on it.
- Generate UIDs with `pydicom.uid.generate_uid()`; never hand-roll UID strings.
- Set tags by DICOM module (Patient / Study / Series / Equipment / Encapsulated Doc),
  mirroring the grouping already in `_create_dicom_dataset`. The full tag table lives
  in `CLAUDE.md`.
- No PHI in logs or error messages — reference `patient_id`, not `patient_name`. The
  same applies to response headers: `X-Patient-ID` is fine (same exposure as the
  `Content-Disposition` filename), `PatientName` never is. Intermediaries/access logs
  must not log `X-Patient-ID`.
- On extraction, recover the exact payload: honor `EncapsulatedDocumentLength` when a
  writer set it, otherwise strip exactly **one** trailing null (the OB even-length
  pad) — never `rstrip`, which could eat payload bytes.

## 7. Testing

- `pytest`, split into `tests/unit/` (converter internals) and `tests/integration/`
  (endpoints via FastAPI `TestClient`). Group related cases in a `Test*` class.
- Reuse the real fixtures in `fixtures/` (`radiology_report.pdf`, `corrupted.pdf`,
  `encapsulated_report.dcm`); only synthesize bytes inline when testing malformed
  input. The `.dcm` fixture keeps decoder tests independent of encoder bugs; the
  regeneration command is in `fixtures/README.md`.
- Coverage gate is **90%**, set once in `pyproject.toml` (`[tool.coverage.report]
  fail_under`), so local `pytest` and CI enforce the same threshold. A change that
  drops below it fails. Add tests with the change, not after.
- After any change run `./run-tests.sh suite` (pytest + all linters) and read the
  whole output, not just the exit code.

## 8. Dependencies & versioning

- Two dependency sources, keep them in sync: `pyproject.toml` (ranges, used by local
  dev / CI via `.[dev]`) and `requirements.txt` (pins, used by the Docker build).
  Changing a runtime dep means editing both.
- The version string lives in several places — bump them together: `__init__.py`
  (`__version__`), `pyproject.toml`, the health/`SoftwareVersions` strings in
  `api.py`/`converter.py`, and `ImplementationVersionName` in `converter.py`.
