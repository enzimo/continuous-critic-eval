"""An in-memory queue assigning tasks to workers."""


class JobQueue:
    def __init__(self):
        self.jobs = {}

    def enqueue(self, job_id, payload):
        self.jobs[job_id] = {"payload": payload, "state": "pending", "owner": None}

    def claim(self, job_id, owner):
        job = self.jobs[job_id]
        if job["state"] != "pending":
            return False
        job["state"] = "running"
        job["owner"] = owner
        return True

    def complete(self, job_id, owner):
        self.jobs[job_id]["state"] = "completed"

    def snapshot(self):
        return self.jobs
