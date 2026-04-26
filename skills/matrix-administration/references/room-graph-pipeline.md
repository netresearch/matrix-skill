# Room graph pipeline

`synapse-graph.py` produces a Graphviz `.dot` file (and optionally an `.svg` via the system `dot` binary) showing every non-replaced room and its parent-space relationships. Edges go from a child room to its parent space; node colours and the gradient on space nodes encode the rating.

## Local one-shot

```bash
python3 skills/matrix-administration/scripts/synapse-fetch-rooms.py
python3 skills/matrix-administration/scripts/synapse-graph.py --space '!home:server'
xdg-open rooms.svg
```

`dot` must be installed (`apt install graphviz`, `brew install graphviz`, …). Pass `--no-svg` to emit only the `.dot` source.

## Periodic dashboard (Docker)

A common deployment is a static-file container that re-runs the snapshot+render at build time and serves the resulting SVG behind a reverse proxy. The Dockerfile below is a generic version of the upstream pipeline — drop in your own homeserver URL and reverse-proxy labels.

```dockerfile
# Builder: produce rooms.{en,de}.svg from a live snapshot
FROM python:3.13-slim AS builder
WORKDIR /app
RUN apt-get update \
 && apt-get install -y --no-install-recommends graphviz \
 && rm -rf /var/lib/apt/lists/*

COPY skills/matrix-administration/scripts ./scripts

# admin token mounted as a build secret
RUN --mount=type=secret,id=matrix_token \
    mkdir -p /root/.config/matrix && \
    cat <<EOF > /root/.config/matrix/config.json
{
  "homeserver": "${MATRIX_HOMESERVER:-https://matrix.example.com}",
  "admin_token": "$(cat /run/secrets/matrix_token)"
}
EOF

RUN python3 scripts/synapse-fetch-rooms.py
RUN LANGUAGE=en python3 scripts/synapse-graph.py && mv rooms.svg rooms.en.svg
RUN LANGUAGE=de python3 scripts/synapse-graph.py && mv rooms.svg rooms.de.svg

# Runtime: any tiny static-file server
FROM ghcr.io/thedevminertv/gostatic:1.5.2
CMD ["-cache","4h","-log-requests","-compress-level=2","-spa","-index","rooms.en.svg"]
COPY --from=builder /app/rooms.*.svg /static/
```

Build with:

```bash
echo -n "syt_admin_…" > /tmp/token
DOCKER_BUILDKIT=1 docker build --secret id=matrix_token,src=/tmp/token -t matrix-graph .
```

Schedule a rebuild however your platform prefers (cron + `docker compose build --no-cache && up -d`, a CI pipeline on a timer, a Kubernetes CronJob …).

## Reading the output

- **Green** node — all checks SUCCESS.
- **Orange** node — at least one WARNING, no FAIL.
- **Red** node — at least one FAIL.
- **Spaces** get a green→blue gradient when healthy, otherwise a flat orange/red.
- **Edges** are labelled `space child` and point from a room to the space that contains it.
- **Node tooltip** (visible in browsers / vector editors that honour SVG `title` attributes) lists every individual rating message.
- **Replaced** rooms (those that were upgraded and tombstoned) are dropped from the graph entirely.
