#!/usr/bin/env bash

CONTAINER_NAME="finally-app"

if docker ps -q -f name="^${CONTAINER_NAME}$" | grep -q .; then
    echo "Stopping FinAlly..."
    docker stop "$CONTAINER_NAME"
    docker rm "$CONTAINER_NAME"
    echo "FinAlly stopped. Database data preserved in ./db/"
elif docker ps -aq -f name="^${CONTAINER_NAME}$" | grep -q .; then
    docker rm "$CONTAINER_NAME"
    echo "Removed stopped container."
else
    echo "FinAlly is not running."
fi
