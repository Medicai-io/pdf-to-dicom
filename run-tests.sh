#!/bin/bash
# pdf-to-dicom — local build / run / test helper (wraps docker-compose.yml).
# Usage: ./run-tests.sh <command>        Override the port with:  PORT=8010 ./run-tests.sh up
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

export PORT="${PORT:-8000}"
URL="http://localhost:${PORT}"

up()    { docker compose up -d --build --wait; echo "running at $URL"; }
down()  { docker compose down; }
logs()  { docker compose logs -f --tail 100 pdf-to-dicom; }
dev()   { uvicorn src.pdf_to_dicom.main:app --reload --port "$PORT"; }

# Health + a real conversion, verified with pydicom inside the container.
smoke() {
    curl -sf "$URL/health"; echo
    curl -sf -X POST "$URL/convert" \
        -F "pdf_file=@fixtures/radiology_report.pdf" \
        -F 'metadata={"patient_name":"Doe^John","patient_id":"12345"}' \
    | docker compose exec -T pdf-to-dicom python -c \
        "import sys,io,pydicom; ds=pydicom.dcmread(io.BytesIO(sys.stdin.buffer.read())); \
assert ds.SOPClassUID=='1.2.840.10008.5.1.4.1.1.104.1' and ds.Modality=='DOC'; \
print('DICOM OK:', ds.PatientName, ds.Modality, len(ds.EncapsulatedDocument), 'bytes')"
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
