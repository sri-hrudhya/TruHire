#!/usr/bin/env bash
set -euo pipefail

target="${DGX_SSH_TARGET:-truviq_domain@100.122.195.84}"
local_port="${DGX_LOCAL_PORT:-8000}"

echo "Forwarding localhost:${local_port} to ${target}:localhost:8000"
ssh -f -N -T -o ExitOnForwardFailure=yes \
  -L "${local_port}:localhost:8000" "$target"
echo "DGX tunnel established in the background."
