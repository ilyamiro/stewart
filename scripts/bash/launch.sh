#!/usr/bin/bash

DIR=$1

launch_in_terminal() {
    CMD="cd '$DIR' && source venv/bin/activate && python3.11 main.py; exec bash"

    declare -A terminals=(
        [gnome-terminal]="-- bash -c \"$CMD\""
        [gnome-console]="-- bash -c \"$CMD\""          # Alternative name for kgx
        [kgx]="-- bash -c \"$CMD\""                    # GNOME Console
        [konsole]="--noclose -e bash -c \"$CMD\""
        [xfce4-terminal]="--command=\"bash -c '$CMD'\""
        [tilix]="-e bash -c \"$CMD\""
        [kitty]="bash -c \"$CMD\""
        [alacritty]="-e bash -c \"$CMD\""
        [wezterm]="start -- bash -c \"$CMD\""
        [lxterminal]="-e bash -c \"$CMD\""
        [terminator]="-x bash -c \"$CMD\""
        [mate-terminal]="-- bash -c \"$CMD\""
        [urxvt]="-e bash -c \"$CMD\""
        [st]="-e bash -c \"$CMD\""
        [xterm]="-hold -e bash -c \"$CMD\""
        [x-terminal-emulator]="-e bash -c \"$CMD\""
    )

    for term in "${!terminals[@]}"; do
        if command -v "$term" &> /dev/null; then
            eval "$term ${terminals[$term]}" &
            return
        fi
    done

    echo "No supported terminal emulator found. Running in current shell."
    cd "$DIR"
    source venv/bin/activate
    python3.11 main.py
}

launch_in_terminal
