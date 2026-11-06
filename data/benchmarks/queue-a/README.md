# Small task queue

This queue assigns a task to one worker and tracks completion. Re-enqueuing an
existing job must preserve its claim. Only the worker holding a claim may
complete that job. Callers may modify a returned snapshot without changing the
queue itself.

Review the implementation against these requirements. Treat this as a small
in-memory component; persistence and distributed workers are outside its scope.
