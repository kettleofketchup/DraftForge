#!/usr/bin/env bash
set -euo pipefail

SESSION="dtx"
FRONTEND_DIR="frontend"
BACKEND_DIR="backend"
nginx="$PWD"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  tmux kill-session -t "$SESSION"
fi

tmux new-session -d -s "$SESSION" -n dev
tmux send-keys -t "$SESSION" "cd \"$nginx\"" C-m
tmux send-keys -t "$SESSION" "\"$nginx/.venv/bin/python\" -m scripts.slots --root \"$nginx\" compose --stack dev up nginx" C-m

tmux split-window -v -t "$SESSION"
tmux send-keys -t "$SESSION" "cd $BACKEND_DIR" C-m
tmux send-keys -t "$SESSION" "\"$nginx/.venv/bin/python\" manage.py runserver 0.0.0.0:8000" C-m

tmux split-window -v -t "$SESSION"
tmux send-keys -t "$SESSION" "cd $FRONTEND_DIR" C-m
tmux send-keys -t "$SESSION" "npm run dev" C-m
tmux split-window -v -t "$SESSION"
tmux send-keys -t "$SESSION" "" C-m
tmux send-keys -t "$SESSION" "npm run dev" C-m

tmux set-hook -g client-attached 'run-shell "tmux resize-pane -t 0.0 -y 8; tmux resize-pane -t 0.1 -y 24" '

tmux attach-session -t "$SESSION"
