#!/bin/bash
# Build every web simulator listed in logs/ids.txt, 3 at a time (each with 6 compile jobs), log per build.
#   bash run_all.sh [ids...]   -> logs/<id>-build.log, summary in logs/run_all.log
cd "$(dirname "$0")"
PY=../tools/emsdk/python/3.13.3_64bit/python.exe
IDS="${*:-$(cat logs/ids.txt)}"
printf '%s\n' $IDS | xargs -P 3 -I{} sh -c "RSIM_JOBS=6 $PY -I build.py build {} > logs/{}-build.log 2>&1; tail -1 logs/{}-build.log" > logs/run_all.log
