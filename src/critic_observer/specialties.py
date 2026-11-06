"""Specialty labels are separate from coordinator/reviewer/challenger duties."""

LEGACY_SPECIALTIES = {
    "bug hunter": "Bug hunting",
    "security": "Security",
    "dependency and security reviewer": "Security",
    "requirements": "Requirements",
    "intent checker": "Requirements",
    "evidence": "Evidence and testing",
    "evidence auditor": "Evidence and testing",
    "test auditor": "Evidence and testing",
    "failure sequences": "Failure handling",
    "failure-handling auditor": "Failure handling",
    "outside assumptions": "Boundaries and integration",
    "impact tracer": "Boundaries and integration",
    "diverse hypotheses": "Counterexamples",
}


def specialty_of(config):
    """Do not infer a historical specialty from a prompt or a task's subject."""
    if config.get("specialty"):
        return " ".join(config["specialty"].split())
    role = " ".join(config["role"].split()).casefold()
    return LEGACY_SPECIALTIES.get(role, "General review")
