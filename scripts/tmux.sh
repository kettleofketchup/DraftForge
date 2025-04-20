#!/bin/bash -x

SESSION="dtx"
FRONTEND_DIR="frontend"  # <-- replace with your actual frontend path
BACKEND_DIR="backend"    # <-- replace with your actual backend path
nginx="$PWD"    # <-- replace with your actual backend path

# Kill the session if it exists
tmux has-session -t $SESSION 2>/dev/null
if [ $? -eq 0 ]; then
  tmux kill-session -t $SESSION
fi

# Start new tmux session
tmux new-session -d -s $SESSION -n dev
tmux send-keys -t $SESSION "cd $nginx" C-m
tmux send-keys -t $SESSION "docker compose -f docker-compose.debug.yaml run nginx" C-m

# Split below: big bottom area
tmux split-window -v -t $SESSION

# Setup backend pane (left)
tmux send-keys -t $SESSION "cd $BACKEND_DIR" C-m
tmux send-keys -t $SESSION "python manage.py runserver 0.0.0.0:8000" C-m

# Split window horizontally for frontend (right)
tmux split-window -v -t $SESSION
tmux send-keys -t $SESSION "cd $FRONTEND_DIR" C-m
tmux send-keys -t $SESSION "npm run dev" C-m
tmux split-window -v -t $SESSION
tmux send-keys -t $SESSION "" C-m
tmux send-keys -t $SESSION "npm run dev" C-m

# Attach to the session

funcion
tmux set-hook -g client-attached 'run-shell "tmux resize-pane -t 0.0 -y 8; tmux resize-pane -t 0.1 -y 24" '

tmux attach-session -t $SESSION
