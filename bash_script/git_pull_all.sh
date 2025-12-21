#!/bin/bash

# Loop through all directories in the current folder
for dir in */; do
    # Check if it's a git repository
    if [ -d "$dir/.git" ]; then
        echo "----------------------------------------"
        echo "Updating repository: $dir"
        cd "$dir" || continue

        # Pull latest changes
        git pull

        # Go back to parent directory
        cd ..
    else
        echo "Skipping (not a git repo): $dir"
    fi
done

echo "All repositories processed."

