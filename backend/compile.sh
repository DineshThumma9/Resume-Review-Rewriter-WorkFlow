#!/bin/sh
# compile.sh — LaTeX compilation wrapper for the latex-compiler container.
# Reads LaTeX source from stdin, compiles it with pdflatex, writes PDF to stdout.
# Used by: docker/podman run -i --rm latex-compiler

set -e

WORKDIR=$(mktemp -d)
trap "rm -rf $WORKDIR" EXIT

TEX_FILE="$WORKDIR/resume.tex"
PDF_FILE="$WORKDIR/resume.pdf"

# Read LaTeX source from stdin
cat > "$TEX_FILE"

# Run pdflatex twice (second pass resolves references/TOC)
pdflatex -interaction=nonstopmode -halt-on-error -output-directory "$WORKDIR" "$TEX_FILE" > /dev/null 2>&1 || \
pdflatex -interaction=nonstopmode -output-directory "$WORKDIR" "$TEX_FILE" > /dev/null 2>&1 || true

if [ ! -f "$PDF_FILE" ]; then
    # Re-run and capture stderr for the error message
    pdflatex -interaction=nonstopmode -output-directory "$WORKDIR" "$TEX_FILE" 1>&2
    echo "ERROR: PDF not generated" >&2
    exit 1
fi

# Write PDF bytes to stdout
cat "$PDF_FILE"
