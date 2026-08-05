#!/usr/bin/env python3
"""Cold start idempotente: leva um clone cru a um estado conhecido.

STDLIB PURO até a etapa 2. É a restrição de desenho central deste arquivo, e não é preciosismo:
pyyaml e jsonschema vivem no extra [dev] do pyproject.toml, então um clone fresco não os tem — e
um script que instala dependências não pode depender das dependências que instala. Só depois da
etapa 2 este módulo importa yaml, e o faz dentro das funções, nunca no topo.

Etapas, nesta ordem (cada uma pressupõe a anterior):

  1. ambiente    — python e git presentes; o repositório é um repositório
  2. dependências— pip install -e ".[dev]"
  3. papel       — lê project.yaml e target.lock: molde não materializa nada
  4. workspace   — clone raso do alvo e checkout no SHA de target.lock (re-execução: fetch)
  5. validação   — ci/validate_all.py
  6. laudo       — harness/state/bootstrap.json

Idempotente: rodar de novo com o workspace já no SHA certo custa um fetch e nada mais. É o que
permite chamá-lo em toda sessão nova sem pensar duas vezes.

Uso:  python ci/bootstrap.py [--check-drift] [--skip-deps] [--quiet]
Sai:  0 pronto · 1 divergência (validate_all reprovou) · 2 não conseguiu levantar o ambiente.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(os.environ.get("HARNESS_REPO_ROOT") or Path(__file__).resolve().parent.parent).resolve()
WORKSPACE = REPO / "workspace" / "target"
LAUDO = "harness/state/bootstrap.json"

# Host fixo e único: o alvo é declarado por owner/repo, e a URL é montada aqui. Deixar o host no
# metadado seria uma decisão de infraestrutura escondida num arquivo de identidade de projeto.
HOST = "https://github.com"


class BootstrapError(Exception):
    """Não deu para levantar o ambiente. Vira exit 2 — nunca exit 0."""


def _run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise BootstrapError(f"{' '.join(cmd[:3])}… falhou: {(proc.stderr or proc.stdout).strip()}")
    return proc


# --------------------------------------------------------------------------------------
# 1. Ambiente
# --------------------------------------------------------------------------------------

def check_environment() -> dict:
    if sys.version_info < (3, 11):
        raise BootstrapError(f"python 3.11+ requerido; encontrado {sys.version.split()[0]}")
    if not shutil.which("git"):
        raise BootstrapError("git não encontrado no PATH")
    if not (REPO / "pyproject.toml").exists():
        raise BootstrapError(f"{REPO} não parece ser este repositório (falta pyproject.toml)")
    return {"python": sys.version.split()[0], "git": _run(["git", "--version"]).stdout.strip()}


# --------------------------------------------------------------------------------------
# 2. Dependências
# --------------------------------------------------------------------------------------

def ensure_dependencies(skip: bool = False) -> dict:
    """Instala só se faltar. Reinstalar a cada sessão é o que faz o bootstrap parecer caro."""
    try:
        import jsonschema  # noqa: F401
        import yaml  # noqa: F401
        return {"instalado_agora": False}
    except ImportError:
        pass
    if skip:
        raise BootstrapError("dependências ausentes e --skip-deps pedido: nada a fazer")
    _run([sys.executable, "-m", "pip", "install", "-e", ".[dev]", "-q"], cwd=REPO)
    return {"instalado_agora": True}


# --------------------------------------------------------------------------------------
# 3. Papel do repositório
# --------------------------------------------------------------------------------------

def read_role() -> tuple[str | None, dict, str | None]:
    """(kind, target, target_sha). Importa yaml aqui dentro: antes da etapa 2 ele não existe."""
    import yaml

    def ler(rel: str) -> dict:
        path = REPO / rel
        if not path.exists():
            raise BootstrapError(f"{rel} ausente — o papel do repositório não está declarado")
        try:
            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise BootstrapError(f"{rel}: YAML ilegível ({exc})") from exc

    projeto, lock = ler("project.yaml"), ler("target.lock")
    kind = (projeto.get("project") or {}).get("kind")
    if kind != lock.get("kind"):
        raise BootstrapError(
            f"project.yaml diz kind={kind!r} e target.lock diz kind={lock.get('kind')!r} — "
            f"o papel do repositório não pode depender de qual arquivo se lê primeiro"
        )
    return kind, projeto.get("target") or {}, lock.get("target_sha")


# --------------------------------------------------------------------------------------
# 4. Workspace
# --------------------------------------------------------------------------------------

def materialize(target: dict, sha: str) -> dict:
    """Clone raso do alvo no SHA exato do lock. Nada de branch: o lock é a fonte da versão.

    O alvo é LIDO, nunca escrito: nenhum remote de escrita é configurado e nenhum commit é criado.
    """
    url = f"{HOST}/{target['repo']}.git"
    WORKSPACE.parent.mkdir(parents=True, exist_ok=True)

    if (WORKSPACE / ".git").exists():
        atual = _run(["git", "rev-parse", "HEAD"], cwd=WORKSPACE).stdout.strip()
        if atual == sha:
            return {"acao": "ja-no-sha", "sha": sha}
        _run(["git", "fetch", "--depth", "1", "origin", sha], cwd=WORKSPACE)
        _run(["git", "checkout", "--detach", sha], cwd=WORKSPACE)
        return {"acao": "avancado", "de": atual, "sha": sha}

    if WORKSPACE.exists():
        shutil.rmtree(WORKSPACE)
    _run(["git", "init", "--quiet", str(WORKSPACE)])
    _run(["git", "remote", "add", "origin", url], cwd=WORKSPACE)
    _run(["git", "fetch", "--depth", "1", "origin", sha], cwd=WORKSPACE)
    _run(["git", "checkout", "--detach", sha], cwd=WORKSPACE)
    return {"acao": "materializado", "sha": sha}


def check_drift(target: dict, sha: str) -> dict:
    """O alvo continua evoluindo; o lock não. Reporta a distância, não a corrige.

    Avançar o lock é decisão declarada (change-proposal), nunca efeito colateral de um bootstrap:
    o metadado descreve o alvo NAQUELE commit, e movê-lo sem revisar o metadado troca um drift
    visível por um metadado errado — que é estritamente pior.
    """
    ref = target["ref"]
    proc = _run(["git", "ls-remote", f"{HOST}/{target['repo']}.git", ref], check=False)
    if proc.returncode != 0 or not proc.stdout.strip():
        return {"estado": "indisponivel", "motivo": (proc.stderr or "ref não encontrada").strip()}
    remoto = proc.stdout.split()[0]
    if remoto == sha:
        return {"estado": "em-dia", "sha": sha}
    return {"estado": "atrasado", "lock": sha, "remoto": remoto, "ref": ref}


# --------------------------------------------------------------------------------------
# 5 e 6. Validação e laudo
# --------------------------------------------------------------------------------------

def validate() -> int:
    proc = subprocess.run([sys.executable, "ci/validate_all.py", "--quiet"], cwd=REPO)
    return proc.returncode


def emit(estado: dict, quiet: bool = False) -> None:
    """Laudo em harness/state/ (gitignored): é evidência de execução, não fonte de verdade."""
    import jsonschema

    schema = json.loads((REPO / "harness/schemas/bootstrap-report.schema.json")
                        .read_text(encoding="utf-8"))
    try:
        jsonschema.Draft202012Validator(schema).validate(estado)
    except jsonschema.ValidationError as exc:
        raise BootstrapError(f"laudo de bootstrap fora do próprio schema: {exc.message}") from exc
    out = REPO / LAUDO
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(estado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not quiet:
        print(f"• laudo: {LAUDO}")


# --------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cold start idempotente do repositório.")
    parser.add_argument("--check-drift", action="store_true",
                        help="só compara target.lock com o remoto; não materializa nem valida")
    parser.add_argument("--skip-deps", action="store_true", help="não instala dependências")
    parser.add_argument("--only-workspace", action="store_true",
                        help="materializa o alvo e PARA — não roda os fiscais (CP-016)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    estado: dict = {"schema_version": "1.0", "etapas": {}}
    try:
        estado["etapas"]["ambiente"] = check_environment()
        estado["etapas"]["dependencias"] = ensure_dependencies(args.skip_deps)
        kind, target, sha = read_role()
        estado["kind"] = kind

        if kind == "mold":
            estado["etapas"]["workspace"] = {"acao": "nao-aplicavel"}
            estado["proximo_passo"] = "/adotar <url-do-alvo>"
            if not args.quiet:
                print("• Molde: não governa alvo algum — nada a materializar.")
        else:
            if not sha:
                raise BootstrapError("derivado sem target_sha em target.lock: nada a ancorar")
            drift = check_drift(target, sha)
            estado["etapas"]["drift"] = drift
            if args.check_drift:
                estado["resultado"] = "ok"
                estado["proximo_passo"] = (
                    "/sincronizar" if drift["estado"] == "atrasado" else "nada a fazer")
                emit(estado, args.quiet)
                if not args.quiet:
                    print(f"• drift: {drift}")
                return 0
            estado["etapas"]["workspace"] = materialize(target, sha)
            estado["proximo_passo"] = "python ci/validate_all.py"

    except BootstrapError as exc:
        estado["resultado"] = "erro"
        estado["erro"] = str(exc)
        print(f"✗ bootstrap: {exc}", file=sys.stderr)
        try:
            emit(estado, args.quiet)
        except Exception:  # noqa: BLE001 - sem dependências não há laudo, e tudo bem
            pass
        return 2

    if args.check_drift:  # molde: nada a comparar
        estado["resultado"] = "ok"
        emit(estado, args.quiet)
        return 0

    if args.only_workspace:
        # CP-016: no CI, materializar e validar são passos SEPARADOS, e é o ponto da separação.
        # Um clone que falha por rede, credencial ausente ou SHA sumido por force-push é estado do
        # MUNDO; uma divergência de metadado é estado do REPOSITÓRIO. Colapsar os dois num único
        # vermelho ensina a ler "governança falhou" como "provavelmente foi a rede" — e a partir
        # daí o gate está desligado por hábito, sem ninguém ter decidido desligá-lo. Aqui saímos
        # antes de validate(), e quem reprova divergência é o passo seguinte do workflow.
        estado["resultado"] = "ok"
        estado["proximo_passo"] = "python ci/validate_all.py"
        emit(estado, args.quiet)
        return 0

    code = validate()
    estado["resultado"] = {0: "ok", 1: "divergencias"}.get(code, "fiscal-nao-fiscalizou")
    emit(estado, args.quiet)
    if not args.quiet:
        print(f"• próximo passo: {estado['proximo_passo']}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
