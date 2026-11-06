# Artifact storage

Keep source code separate from runtime credentials, databases, transcripts,
generated reports and dependency environments.

| Data | Storage requirement |
| --- | --- |
| Source, documentation and synthetic fixtures | Project directory |
| SQLite database, WAL and shared-memory files | One local persistent directory |
| Reporting outbox and its lock | Private local persistent directory |
| Credentials and reporting profiles | Private storage outside Git |
| Model traces, review outputs, caches and environments | Private artifact directory |

The default client outbox is under `~/.local/state/critic-observer/outbox`.
Set `--queue-dir` when using another private local directory. Configure
`OBSERVER_DATABASE` for the application database.
Check the filesystem hosting each resolved path; a directory under a home or
checkout is not necessarily on local disk.

SQLite needs its containing directory writable as well as the database file.
Keep WAL and shared-memory files with the database. Do not substitute network
storage or run several application writers. See [deployment](../deploy/swarm.md).

Use SQLite's online backup command rather than copying a live main database
without its WAL. Restore to a new path while the service is stopped, then verify
integrity and record counts. Keep database backups and raw model traces in
private storage.

Do not move an outbox while a reporter holds its file lock. Preserve stable event
IDs when repairing pending submissions. A persisted but rejected batch still
needs its underlying delivery problem corrected.
