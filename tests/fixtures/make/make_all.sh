#!/bin/sh
# Regenerate every oracle-derived fixture. Each script runs with the
# interpreter of the earlier repository it reads, which it never writes to.
set -e
here=$(cd "$(dirname "$0")" && pwd)
codebase=$(cd "$here/../../../.." && pwd)
"$codebase/open_alex_adt_gate/.venv/bin/python" -B "$here/make_oa.py"
"$codebase/wos_paper_sample/.venv/bin/python" -B "$here/make_ws.py"
"$codebase/divergence-validation/.venv/bin/python" -B "$here/make_dv.py"
