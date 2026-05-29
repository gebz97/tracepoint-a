#!/usr/bin/env bash


DIR="$(dirname "$0")/v1"
cat "$DIR"/*.sql | psql