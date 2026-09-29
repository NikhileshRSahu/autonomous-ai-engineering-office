from __future__ import annotations
import hashlib
import json
import re
import subprocess
from pathlib import Path
from .models import ProjectMap
from .project_index import ProjectIndex


class ProjectDiscovery:
    TECH_RULES = [
        ("Python", {"pyproject.toml", "requirements.txt", "setup.py", "Pipfile"}),
        ("Node.js", {"package.json"}),
        ("Rust", {"Cargo.toml"}),
        ("Go", {"go.mod"}),
        ("Java", {"pom.xml", "build.gradle", "settings.gradle"}),
        (".NET", {"global.json"}),
        ("ROS 2", {"package.xml", "colcon.meta"}),
        ("Docker", {"Dockerfile", "docker-compose.yml", "compose.yml"}),
        ("Terraform", {"main.tf", "terraform.tfvars"}),
        ("Kubernetes", {"Chart.yaml", "kustomization.yaml"}),
    ]

    def inspect(self, root: str | Path, objective: str) -> ProjectMap:
        root = Path(root).resolve()
        if not root.is_dir():
            raise ValueError(f"project root is not a directory: {root}")
        files = [p for p in root.rglob("*") if p.is_file()]
        names = {p.name for p in files if len(p.relative_to(root).parts) <= 4}
        suffixes = {p.suffix.lower() for p in files}
        text = self._sample_text(root)
        technologies: list[str] = []
        for tech, markers in self.TECH_RULES:
            if markers & names:
                technologies.append(tech)
        lower = text.lower()
        keyword_tech = {
            "FastAPI": ["fastapi"], "Django": ["django"], "Flask": ["flask"],
            "React": ["react"], "Next.js": ["next"], "Express": ["express"],
            "PostgreSQL": ["postgres", "psycopg", "pg"], "SQLite": ["sqlite"],
            "PyTorch": ["torch", "pytorch"], "TensorFlow": ["tensorflow"],
            "Gazebo": ["gazebo", "gz sim"], "Nav2": ["nav2"], "MoveIt": ["moveit"],
            "KiCad": ["kicad"], "CAD": ["solidworks", "freecad", "step", "iges"],
            "Embedded": ["arduino", "stm32", "esp32", "zephyr", "freertos"],
        }
        for tech, keys in keyword_tech.items():
            if any(k in lower for k in keys) and tech not in technologies:
                technologies.append(tech)
        if suffixes & {".step", ".stp", ".iges", ".igs", ".fcstd", ".sldprt", ".sldasm"}:
            technologies.append("CAD")
        if suffixes & {".kicad_sch", ".kicad_pcb", ".sch", ".brd"}:
            technologies.append("KiCad")
        domains = self._domains(technologies, lower, suffixes)
        tests = (root / "tests").is_dir() or (root / "test").is_dir() or any(part.lower() in {"test", "tests"} for p in files for part in p.parts[-3:])
        ci = (root / ".github" / "workflows").exists() or (root / ".gitlab-ci.yml").exists()
        docs = (root / "docs").is_dir() or any(n.lower().startswith("readme") for n in names)
        project_type = self._project_type(domains)
        digest = hashlib.sha1(str(root).encode()).hexdigest()[:10]
        git = self._git_metadata(root)
        unknowns: list[str] = []
        if not (root / "acceptance.json").exists():
            unknowns.append("acceptance criteria are not explicitly configured")
        if not tests:
            unknowns.append("automated test coverage is unknown or absent")
        return ProjectMap(
            project_id=f"P-{digest}", root=str(root), objective=objective,
            project_type=project_type, technologies=sorted(set(technologies)),
            working_components=[x for x in ["tests" if tests else "", "ci" if ci else "", "documentation" if docs else ""] if x],
            broken_components=[], constraints=[], risk_areas=self._risks(domains),
            required_domains=domains, unknowns=unknowns,
            metadata={"has_tests": tests, "has_ci": ci, "has_docs": docs, "file_count": len(files), "git": git, "index": ProjectIndex(root).status() if (root / ".office" / "index" / "index.db").exists() else None},
        )

    def _sample_text(self, root: Path) -> str:
        chunks: list[str] = []
        candidates = [
            root / "README.md", root / "README", root / "requirements.md", root / "pyproject.toml",
            root / "requirements.txt", root / "package.json", root / "package.xml", root / "Cargo.toml",
            root / "go.mod", root / "pom.xml", root / "CMakeLists.txt", root / ".gitlab-ci.yml",
        ]
        docs = root / "docs"
        if docs.is_dir():
            candidates.extend(sorted(docs.glob("*.md"))[:20])
        for p in candidates:
            if p.exists() and p.is_file():
                try:
                    chunks.append(p.read_text(errors="ignore")[:100_000])
                except OSError:
                    pass
        return "\n".join(chunks)

    def _domains(self, technologies: list[str], text: str, suffixes: set[str]) -> list[str]:
        result: set[str] = set()
        software_signals = any(t in technologies for t in ["Python", "Node.js", "Rust", "Go", "Java", ".NET", "ROS 2"])
        if software_signals or suffixes & {".py", ".js", ".ts", ".rs", ".go", ".java", ".cs", ".cpp", ".c", ".h"}:
            result.add("software_engineering")
        if any(t in technologies for t in ["FastAPI", "Django", "Flask", "Express"]): result.add("backend")
        if any(t in technologies for t in ["React", "Next.js"]): result.add("frontend")
        if any(t in technologies for t in ["PostgreSQL", "SQLite"]): result.add("database")
        if any(t in technologies for t in ["PyTorch", "TensorFlow"]): result.add("machine_learning")
        if any(t in technologies for t in ["ROS 2", "Gazebo", "Nav2", "MoveIt"]): result.add("robotics")
        if any(t in technologies for t in ["Docker", "Terraform", "Kubernetes"]) or "github/workflows" in text: result.add("devops")
        if any(k in text for k in ["oauth", "jwt", "auth", "password", "cryptography"]): result.add("security")
        if "CAD" in technologies: result.add("mechanical")
        if "KiCad" in technologies or "Embedded" in technologies: result.add("electronics")
        if any(k in text for k in ["statistics", "hypothesis test", "confidence interval"]): result.add("statistics")
        if any(k in text for k in ["benchmark", "latency", "throughput", "profiling"]): result.add("benchmarking")
        if any(k in text for k in ["ux", "accessibility", "design system", "figma"]): result.add("ux")
        if any(k in text for k in ["aws", "azure", "gcp", "cloudflare"]): result.add("cloud")
        if any(k in text for k in ["socket", "tcp", "udp", "networking"]): result.add("networking")
        if not result:
            # Unknown engineering/research work still needs a general analyst rather than pretending a domain was detected.
            result.add("research")
        return sorted(result)

    def _project_type(self, domains: list[str]) -> str:
        if "robotics" in domains: return "robotics"
        if "mechanical" in domains or "electronics" in domains: return "engineering"
        if "machine_learning" in domains: return "machine_learning"
        if "frontend" in domains and "backend" in domains: return "full_stack"
        if "backend" in domains: return "backend_service"
        if "frontend" in domains: return "frontend"
        if "software_engineering" in domains: return "software"
        return "research_or_engineering"

    def _risks(self, domains: list[str]) -> list[str]:
        risks = ["regression"] if "software_engineering" in domains else []
        if "database" in domains: risks.append("data_integrity")
        if "security" in domains: risks.append("security")
        if "robotics" in domains: risks.extend(["physical_safety", "simulation_reality_gap"])
        if "mechanical" in domains: risks.extend(["mechanical_safety", "manufacturability"])
        if "electronics" in domains: risks.extend(["electrical_safety", "hardware_damage"])
        return risks or ["requirements_ambiguity"]

    def _git_metadata(self, root: Path) -> dict:
        git_dir = root / ".git"
        if not git_dir.exists():
            return {"is_repository": False}
        result = {"is_repository": True, "branch": None, "head": None, "dirty": None}
        try:
            branch = subprocess.run(["git", "branch", "--show-current"], cwd=root, text=True, capture_output=True, timeout=5)
            head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, text=True, capture_output=True, timeout=5)
            status = subprocess.run(["git", "status", "--porcelain"], cwd=root, text=True, capture_output=True, timeout=5)
            result.update({
                "branch": branch.stdout.strip() or None,
                "head": head.stdout.strip() if head.returncode == 0 else None,
                "dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
            })
        except (OSError, subprocess.SubprocessError):
            pass
        return result
