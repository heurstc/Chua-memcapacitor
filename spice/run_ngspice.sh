#!/usr/bin/env bash
# Run ngspice simulation then plot results.
# Writes: ac_bode.dat  tran_1k.dat  tran_8k.dat  tran_step.dat
# Usage: ./run_ngspice.sh

set -e
cd "$(dirname "$0")"

if ! command -v ngspice &>/dev/null; then
    echo "ngspice not found — install with:"
    echo "  sudo apt install ngspice"
    echo ""
    echo "Running pure-scipy plot instead..."
    python3 plot_response.py
    exit 0
fi

echo "=== Running ngspice ==="
ngspice -b signal_cond.spice

echo ""
echo "=== Simulation complete ==="
echo "Output files:"
ls -lh ac_bode.dat tran_1k.dat tran_8k.dat tran_step.dat 2>/dev/null || true

echo ""
echo "=== Plotting ==="
python3 plot_response.py --ngspice
