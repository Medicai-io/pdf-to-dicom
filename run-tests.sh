#!/bin/bash
# dicom-pdf — local build / run / test helper (wraps docker-compose.yml).
# Usage: ./run-tests.sh <command>        Override the port with:  PORT=8010 ./run-tests.sh up
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

export PORT="${PORT:-8000}"
URL="http://localhost:${PORT}"

up()    { docker compose up -d --build --wait; echo "running at $URL"; }
down()  { docker compose down; }
logs()  { docker compose logs -f --tail 100 dicom-pdf; }
dev()   { uvicorn src.dicom_pdf.main:app --reload --port "$PORT"; }

# Health + a real conversion both ways: PDF -> DICOM (verified with pydicom inside
# the container), then DICOM -> PDF and byte-compare against the source PDF.
smoke() {
    curl -sf "$URL/health"; echo

    local dcm pdf
    dcm="$(mktemp)"
    pdf="$(mktemp)"
    trap 'rm -f "$dcm" "$pdf"' RETURN

    curl -sf -X POST "$URL/pdf-to-dicom" \
        -F "pdf_file=@fixtures/radiology_report.pdf" \
        -F 'metadata={"patient_name":"Doe^John","patient_id":"12345"}' \
        -o "$dcm"
    docker compose exec -T dicom-pdf python -c \
        "import sys,io,pydicom; ds=pydicom.dcmread(io.BytesIO(sys.stdin.buffer.read())); \
assert ds.SOPClassUID=='1.2.840.10008.5.1.4.1.1.104.1' and ds.Modality=='DOC'; \
print('DICOM OK:', ds.PatientName, ds.Modality, len(ds.EncapsulatedDocument), 'bytes')" < "$dcm"

    curl -sf -X POST "$URL/dicom-to-pdf" -F "dicom_file=@$dcm" -o "$pdf"
    cmp -s "$pdf" fixtures/radiology_report.pdf \
        && echo "PDF OK: extracted PDF is byte-identical to the source" \
        || { echo "PDF FAIL: extracted PDF differs from the source"; exit 1; }
}

# Host test suite + linters (needs: pip install -e ".[dev]").
suite() { pytest; black --check .; isort --check-only .; flake8 src tests; mypy src; bandit -q -r src; }

case "${1:-help}" in
    up|start)  up ;;
    down|stop) down ;;
    smoke)     smoke ;;
    all)       up; smoke; down ;;
    suite|test) suite ;;
    dev)       dev ;;
    logs)      logs ;;
    *) printf 'Usage: [PORT=8010] ./run-tests.sh <command>\nCommands: up | down | smoke | all | suite | dev | logs\n' ;;
esac
