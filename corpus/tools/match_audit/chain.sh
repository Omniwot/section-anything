#!/bin/zsh
# Track M (F063) chain: the miss audit on the base code (rc/0.1.7 2066ab2) and on fix/match-failures, keys v1, v2
# and v2.1 at once. Each step is resumable; re-run after a guard stop (never with a higher limit).
# usage: chain.sh dev|test
cd /Users/harshal/Desktop/omni/hustles/.tmp
PY=/Users/harshal/Desktop/omni/hustles/.tmp/sa-017/.venv/bin/python
SPLIT=$1
step() {  # name, log, src, command...
  local name=$1 log=$2 src=$3; shift 3
  for k in 1 2 3 4 5 6 7 8; do
    PYTHONPATH=$src structure-eval/g.sh guarded "$@" 2>&1 | grep -v "recursion depth" > $log
    echo "$(date +%T) $name pass $k: $(tail -1 $log | cut -c1-90)"
    grep -q "GUARD STOP\|not starting" $log || return 0
    sleep 60
  done
  return 1
}
TAG=base SPLIT=$SPLIT step base-$SPLIT match-fail/run-base-$SPLIT.log sa-017-rc/packages/section-anything/src \
  $PY match-fail/tools/match_audit.py run || exit 1
TAG=fix SPLIT=$SPLIT step fix-$SPLIT match-fail/run-fix-$SPLIT.log sa-match/packages/section-anything/src \
  $PY match-fail/tools/match_audit.py run || exit 1
echo "chain done $SPLIT"
