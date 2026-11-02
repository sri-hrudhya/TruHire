#!/usr/bin/env bash
set -euo pipefail

target="${DGX_SSH_TARGET:-truviq_domain@100.122.195.84}"
local_port="${DGX_LOCAL_PORT:-65432}"
remote_port="${DGX_REMOTE_PORT:-65432}"

echo "Forwarding localhost:${local_port} to ${target}:localhost:${remote_port}"
ssh -f -N -T -o ExitOnForwardFailure=yes \
  -L "${local_port}:127.0.0.1:${remote_port}" "$target"
echo "DGX tunnel established in the background."
