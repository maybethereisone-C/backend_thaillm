#!/usr/bin/env bash
# Ensure the model server (:8002) and the app1 gateway (:18000) are up.
# Idempotent: starts a service only when it is not already answering, and never
# touches a healthy one. Safe to run repeatedly (used by watchdog.sh).
set +e

APP1=/root/data/workspace/app1
THAILLM_ENV=/root/data/miniforge3/envs/thaillm
FAHMAI_ENV=/root/data/miniforge3/envs/fahmai
MODEL=/root/data/model/typhoon-s-thaillm-8b-instruct-research-preview
LOG="$APP1/logs/autostart.log"
mkdir -p "$APP1/logs"
log() { echo "$(date -u +%FT%TZ) $*" >> "$LOG"; }

# 1) Model server on :8002 (only start if no process is already serving/loading it)
if ! curl -s -m 4 http://127.0.0.1:8002/v1/models >/dev/null 2>&1; then
  if ! pgrep -f "vllm serve .*--port 8002" >/dev/null 2>&1; then
    log "vLLM :8002 down -> launching"
    CC=$(ls "$THAILLM_ENV"/bin/*-linux-gnu-gcc 2>/dev/null | head -1)
    cd /root/data/API-Ready || exit 0
    CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    HF_HOME=/root/data/hf-cache XDG_CACHE_HOME=/root/data/.cache \
    CC="$CC" PATH="$THAILLM_ENV/bin:$PATH" \
    setsid "$THAILLM_ENV/bin/vllm" serve "$MODEL" \
      --served-model-name typhoon-local --host 127.0.0.1 --port 8002 \
      --max-model-len 32768 --gpu-memory-utilization 0.30 --max-num-seqs 4 \
      --attention-backend FLASH_ATTN --trust-remote-code --enforce-eager \
      >> "$APP1/logs/typhoon_vllm.log" 2>&1 </dev/null &
    log "vLLM launched pid $!"
  else
    log "vLLM :8002 not answering yet but process exists (loading)"
  fi
fi

# 2) app1 gateway on :18000
if ! curl -s -m 4 http://127.0.0.1:18000/health >/dev/null 2>&1; then
  if ! pgrep -f "uvicorn app.main:app" >/dev/null 2>&1; then
    log "app1 :18000 down -> launching"
    cd "$APP1" || exit 0
    setsid "$FAHMAI_ENV/bin/python" -m uvicorn app.main:app \
      --host 0.0.0.0 --port 18000 \
      >> "$APP1/logs/uvicorn.log" 2>&1 </dev/null &
    log "app1 launched pid $!"
  fi
fi
