from __future__ import annotations
import re
from .capabilities import CapabilityRegistry
from .models import AgentSpec, Complexity, ProjectMap


ROLE_NAMES = {
    "software_engineering": "Software Engineering Specialist",
    "backend": "Backend Engineer",
    "frontend": "Frontend Engineer",
    "database": "Database Engineer",
    "security": "Security Engineer",
    "devops": "DevOps Engineer",
    "machine_learning": "Machine Learning Engineer",
    "robotics": "Robotics Systems Engineer",
    "control": "Controls Engineer",
    "research": "Research Specialist",
    "testing": "QA/Test Engineer",
    "statistics": "Statistics Reviewer",
    "mechanical": "Mechanical Engineer",
    "electronics": "Electronics Engineer",
    "networking": "Networking Engineer",
    "cloud": "Cloud Engineer",
    "ux": "UX Engineer",
    "documentation": "Documentation Engineer",
    "benchmarking": "Benchmark Engineer",
    "optimization": "Optimization Engineer",
    "mathematics": "Applied Mathematics Specialist",
    "simulation": "Simulation Engineer",
}


class AgentFactory:
    DEFAULT_FORBIDDEN = [
        "modify acceptance gates", "hide failed tests", "disable safety checks",
        "perform irreversible external action without approval",
    ]

    def __init__(self, registry: CapabilityRegistry):
        self.registry = registry

    def staff(self, project: ProjectMap) -> list[AgentSpec]:
        agents: list[AgentSpec] = []
        domains = [d for d in project.required_domains if self.registry.has(d)]
        for domain in domains:
            cap = self.registry.get(domain)
            agents.append(AgentSpec(
                name=ROLE_NAMES.get(domain, f"{domain.replace('_',' ').title()} Specialist"),
                mission=f"Own {domain.replace('_',' ')} work for project {project.project_id}; use evidence, minimal changes, and reproducible tests.",
                capabilities=[domain], allowed_tools=list(cap.tools), read_scopes=["."],
                write_scopes=list(cap.write_scopes), forbidden_actions=list(self.DEFAULT_FORBIDDEN),
                model_tier=Complexity.MEDIUM,
            ))
        # Permanent quality perspective is always represented, but it remains read/test oriented.
        if not any(a.name == "QA/Test Engineer" for a in agents):
            cap = self.registry.get("testing")
            agents.append(AgentSpec(
                name="QA/Test Engineer", mission="Execute reproducible tests and capture evidence without masking failures.",
                capabilities=["testing"], allowed_tools=cap.tools, read_scopes=["."], write_scopes=cap.write_scopes,
                forbidden_actions=self.DEFAULT_FORBIDDEN + ["modify candidate implementation merely to make tests pass"],
                model_tier=Complexity.LOW,
            ))
        return agents

    def create_specialist(self, expertise: str, reason: str, write_scopes: list[str], tools: list[str]) -> AgentSpec:
        lower = expertise.lower()
        capabilities = ["software_engineering"]
        if any(k in lower for k in ["postgres", "sql", "database", "sqlite"]): capabilities = ["database"]
        elif any(k in lower for k in ["robot", "ros", "gazebo", "nav2", "moveit"]): capabilities = ["robotics"]
        elif any(k in lower for k in ["control", "pid", "mpc"]): capabilities = ["control"] if self.registry.has("control") else ["software_engineering"]
        elif any(k in lower for k in ["security", "auth", "crypto"]): capabilities = ["security"]
        elif any(k in lower for k in ["mechanical", "cad", "solidworks", "freecad"]): capabilities = ["mechanical"]
        elif any(k in lower for k in ["electronics", "pcb", "kicad", "embedded", "firmware"]): capabilities = ["electronics"]
        elif any(k in lower for k in ["network", "tcp", "udp"]): capabilities = ["networking"]
        elif any(k in lower for k in ["cloud", "aws", "azure", "gcp"]): capabilities = ["cloud"]
        elif any(k in lower for k in ["ux", "accessibility", "design system"]): capabilities = ["ux"]
        elif any(k in lower for k in ["benchmark", "performance", "profil"]): capabilities = ["benchmarking"]
        elif any(k in lower for k in ["statistics", "statistical"]): capabilities = ["statistics"]
        elif any(k in lower for k in ["research", "literature"]): capabilities = ["research"]
        clean = re.sub(r"[^A-Za-z0-9 +#.-]", "", expertise).strip() or "Domain"
        cap = self.registry.get(capabilities[0]) if self.registry.has(capabilities[0]) else None
        effective_tools = tools or (list(cap.tools) if cap else ["filesystem.read", "filesystem.search"] )
        effective_write_scopes = write_scopes if write_scopes else (list(cap.write_scopes) if cap else [])
        return AgentSpec(
            name=f"{clean} Specialist",
            mission=f"Investigate {expertise} because {reason}. Stay within assigned scope and produce evidence-backed conclusions.",
            capabilities=capabilities, allowed_tools=effective_tools, read_scopes=["."], write_scopes=effective_write_scopes,
            forbidden_actions=list(self.DEFAULT_FORBIDDEN), model_tier=Complexity.HIGH,
        )
