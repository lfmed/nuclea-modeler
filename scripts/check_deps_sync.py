"""Valida que pyproject.toml e requirements.txt estão sincronizados.

Hoje o app usa requirements.txt em produção (Databricks Apps install) e
pyproject.toml para dev (uv pip install -e .[dev]). Os dois precisam ter
o mesmo set de runtime deps com versões compatíveis.

Esse script roda no pre-commit + CI para detectar:
- Pkg em requirements.txt mas não em pyproject.toml (ou vice-versa)
- Versões muito divergentes (>=X.Y em um, >=X.Z em outro)

Saída:
- 0 = sync ok
- 2 = mismatch (printa diff)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _parse_requirements(path: Path) -> dict[str, str]:
    """Retorna {pkg_lowered: full_spec} de um requirements.txt."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Strip extras: pkg[extra]>=1.0  →  pkg
        m = re.match(r"^([A-Za-z0-9_.-]+)(\[[^\]]+\])?\s*(.*)$", line)
        if not m:
            continue
        pkg, _extras, spec = m.groups()
        out[pkg.lower()] = (spec or "").strip() or "*"
    return out


def _parse_pyproject_deps(path: Path) -> dict[str, str]:
    """Extrai project.dependencies (runtime) do pyproject.toml.

    Usa parser muito simples — assume cada dep numa linha entre
    `dependencies = [` e o `]` correspondente.
    """
    out: dict[str, str] = {}
    if not path.exists():
        return out
    text = path.read_text(encoding="utf-8")
    # Pega o bloco [project] dependencies. Não usar non-greedy porque
    # `[binary]` dentro de um pkg name (ex: psycopg[binary]) tem `]`
    # que confundiria o regex. Estratégia: começa após `dependencies = [`
    # e procura o `]` no INÍCIO de uma linha (heurística do estilo
    # pyproject hand-formatted).
    m = re.search(r"^\s*dependencies\s*=\s*\[\s*\n", text, re.MULTILINE)
    if not m:
        return out
    start = m.end()
    # Acha a linha que começa com `]` (fechamento da lista)
    close = re.search(r"^\s*\]", text[start:], re.MULTILINE)
    if not close:
        return out
    block = text[start:start + close.start()]
    for raw in block.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Strip trailing inline comment + comma
        if "#" in line:
            line = line.split("#", 1)[0].rstrip()
        line = line.rstrip(",").strip()
        # Strip quotes
        line = line.strip("'\"")
        m2 = re.match(r"^([A-Za-z0-9_.-]+)(\[[^\]]+\])?\s*(.*)$", line)
        if not m2:
            continue
        pkg, _extras, spec = m2.groups()
        out[pkg.lower()] = (spec or "").strip() or "*"
    return out


def main() -> int:
    pyproject = _parse_pyproject_deps(ROOT / "pyproject.toml")
    reqs = _parse_requirements(ROOT / "requirements.txt")

    only_pyproject = set(pyproject) - set(reqs)
    only_reqs = set(reqs) - set(pyproject)

    problems: list[str] = []

    if only_pyproject:
        for p in sorted(only_pyproject):
            problems.append(
                f"  • {p} está em pyproject.toml ({pyproject[p]}) mas FALTA em requirements.txt"
            )
    if only_reqs:
        for p in sorted(only_reqs):
            problems.append(
                f"  • {p} está em requirements.txt ({reqs[p]}) mas FALTA em pyproject.toml"
            )

    # Compare specs for pkgs in both
    for pkg in sorted(set(pyproject) & set(reqs)):
        spec_py = pyproject[pkg]
        spec_req = reqs[pkg]
        # Normaliza spaces para comparar
        if spec_py.replace(" ", "") != spec_req.replace(" ", ""):
            problems.append(
                f"  • {pkg} tem specs diferentes: pyproject='{spec_py}' vs requirements='{spec_req}'"
            )

    if problems:
        print("::error::pyproject.toml e requirements.txt estão dessincronizados:")
        for p in problems:
            print(p)
        print(
            "\nFix: alinhe os 2 arquivos com mesma lista de pkgs e versões. "
            "Em geral, pyproject é a fonte de verdade — sincronize requirements.txt."
        )
        return 2

    print(f"OK — {len(pyproject)} runtime deps em sync entre pyproject.toml e requirements.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
