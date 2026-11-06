"""An in-memory queue assigning tasks to workers."""

from copy import deepcopy


class JobQueue:
    def __init__(self):
        self.jobs = {}

    def enqueue(self, job_id, payload):
        if job_id in self.jobs:
            return False
        self.jobs[job_id] = {"payload": deepcopy(payload), "state": "pending", "owner": None}
        return True

    def claim(self, job_id, owner):
        job = self.jobs[job_id]
        if job["state"] != "pending":
            return False
        job["state"] = "running"
        job["owner"] = owner
        return True

    def complete(self, job_id, owner):
        job = self.jobs[job_id]
        if job["state"] != "running" or job["owner"] != owner:
            return False
        job["state"] = "completed"
        return True

    def snapshot(self):
        return deepcopy(self.jobs)
