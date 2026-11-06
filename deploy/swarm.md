# Host Critic observer on an internal Docker Swarm

The stack contains one application service. The image includes the web UI, HTTP
collector, MCP server, and SQLite support. No separate database or model service
is required.

## Build and push

On a machine with a Docker engine and access to your internal registry:

```bash
export OBSERVER_IMAGE=registry.example.com/critic-observer:0.1.0
docker build -t "$OBSERVER_IMAGE" .
docker push "$OBSERVER_IMAGE"
```

Use your real registry. Prefer an immutable tag or digest for deployment. The
Swarm nodes must be able to pull that image. Run registry login separately when
required; credentials do not belong in this stack file.

### Build locally without a registry

For a single pinned storage node, build from this repository on that node:

```bash
docker build --pull --tag critic-observer:0.1.0 .
export OBSERVER_IMAGE=critic-observer:0.1.0
```

After setting the remaining variables and creating secrets as described below,
deploy from a Swarm manager with registry resolution disabled:

```bash
docker stack deploy --resolve-image never -c deploy/stack.yml critic-observer
```

The selected storage node must already have that image. Swarm does not distribute
locally built images. If the build machine is different, use `docker save` and
`docker load` to transfer it to the storage node, or use the registry workflow.
Use a new image tag for each release and match the storage node's architecture.

## Create credentials

Generate two different credentials of at least 8 characters using your
secret manager, or use `critic-observer init --directory .local/secrets`.
On a Swarm manager, create these secrets from the resulting private files:

```bash
docker secret create observer_admin_token .local/secrets/admin_token
docker secret create observer_ingest_token .local/secrets/ingest_token
```

Keep secure copies so you can sign in and configure clients. Docker does not
offer a command to retrieve secret contents after creation. The stack mounts
both secrets read-only for UID 10001. Do not place token values in environment
variables inside the stack, image layers, Git, or tool transcripts.

## Choose the storage node and URL

Inspect `docker node ls` on the manager. Choose the exact hostname of the node
that will own the database volume:

```bash
export OBSERVER_STORAGE_NODE=YOUR_STORAGE_NODE
export OBSERVER_PORT=8000
export OBSERVER_PUBLIC_URL=http://observer.example.com:8000
docker stack config -c deploy/stack.yml
docker stack deploy --with-registry-auth -c deploy/stack.yml critic-observer
```

Export the variables in the same shell that runs the command. `docker stack
deploy` does not automatically load a Compose `.env` file. The configuration
command should show the intended image, node constraint, public URL, and port
before deployment.

The host-mode port is published on the chosen node. Use that node's reachable
address, or route your existing internal reverse proxy to it. The service is not
automatically restricted to an internal network by its name; apply your normal
network access rules. For credentials crossing the network, use your internal
HTTPS proxy or trusted encrypted network. With a proxy, set `OBSERVER_PUBLIC_URL`
to the exact HTTPS origin and preserve the original Host header. Do not add a
URL path prefix. The UI and MCP live at `/` and `/mcp` on that origin.

Check the service:

```bash
docker service ps critic-observer_observer
docker service logs --tail 100 critic-observer_observer
```

The public `/healthz` route reports process/database availability without
exposing review records. Log in through the configured URL with the operator
credential, then configure clients with the ingestion credential.

## Persistence and updates

The named `critic-observer_observer_data` volume contains the database and its
WAL files on the pinned node. The process runs as UID/GID 10001. New local Docker
volumes inherit `/data` ownership from the image. If you restore into an existing
volume, set its ownership accordingly before starting the service.

If you replace the named volume with a host bind mount, prepare that directory
on the actual storage node. The image's `/data` ownership does not change the
ownership of a directory mounted over it. SQLite must be able to write both the
database and its containing directory, where it creates WAL and shared-memory
files. For a dedicated application directory on local disk:

```bash
sudo install -d -m 0700 -o 10001 -g 10001 /srv/critic-observer/data
```

For an existing dedicated data directory, make its database files writable by
UID/GID 10001 as well. An `unable to open database file` startup error can mean
the host directory or existing database file is inaccessible to this user.
Check the filesystem type and mount write permissions before changing ownership.
Keep network filesystems out of this storage path. A read-only container root
filesystem can still use a separately mounted read-write data directory.

Keep exactly one replica. The application also locks the database to reject a
second process. Stop-first updates avoid concurrent tasks holding the same
storage. Use the same stack name to preserve volume identity during updates.
Changing the stack name creates another local volume unless you deliberately
configure an existing one.

If the storage node fails, the service remains unavailable on that node. A
different node's local volume is a different database, even with the same volume
name. Do not remove the placement constraint to simulate failover. Restore a
verified backup on the new node and intentionally change placement. SQLite WAL
requires local storage; do not substitute NFS, and do not scale this stack to
several writers. This design is persistent and recoverable, not highly available.

## Backup and restoration

Use an operator client, outside the server container:

```bash
critic-observer --server "$OBSERVER_PUBLIC_URL" \
  --token-file /private/admin_token backup --output observer-backup.sqlite3
```

The service uses SQLite's online backup API and checks integrity. Copy backups
off the storage node and apply your normal retention policy. A volume alone is
not a backup. Do not copy only the live main database file while ignoring WAL.
The database volume needs space for a temporary second copy during backup.
After a crash, inspect abandoned `observer-backup-*` directories while the service
is stopped; normal completed requests remove their temporary files.

For restoration, stop the service and restore to a new path in a staging
directory or replacement volume:

```bash
docker service scale critic-observer_observer=0
critic-observer restore --backup observer-backup.sqlite3 \
  --database /staging/observer.sqlite3
```

The CLI rejects an existing destination and unsupported or invalid backups.
Place the restored database into the intended volume while the service is
stopped, set UID/GID 10001 ownership, and keep old database/WAL files together
in a separate recovery directory rather than mixing them with the restored
database. Then start one replica, verify history and metric counts, and take
another backup. Test this recovery procedure on a non-production volume first.

## Rotate credentials

Swarm secrets are immutable. Create newly named secrets, update the stack's
secret sources while preserving their container target names, then redeploy.
Update client credentials after the service changes. Rotating the operator
credential invalidates existing browser sessions. Existing queued observations
do not contain credentials and can be delivered with the new ingestion token.

## Current deployment verification

The repository includes automated application and deployment-contract checks.
Building the image and running a real Swarm task also requires a Docker engine,
registry access, and a manager context. Complete those checks on your hosting
network; application tests alone do not establish that the Swarm deployment works.
