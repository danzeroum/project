"""Prova que as travas do ADR-008 mordem — o papel do repositório e a âncora do alvo.

Os dois testes que mais importam são test_kind_derived_sem_target_reprova e
test_sha_em_project_yaml_reprova. O primeiro fecha o "derivado quase pronto": um estado
intermediário que nenhum fiscal reprova é um estado permanente, porque ninguém volta para
terminá-lo. O segundo fecha a segunda cópia do SHA, que é a falha do ADR-003 com outro objeto —
duas cópias de uma versão derivam, e a comparação entre o metadado e o alvo passa a mentir sem
erro nem aviso.
"""

from __future__ import annotations

import yaml

from conftest import ids_of

ALVO_FICTICIO = "exemplo-owner/exemplo-repo"
SHA_FICTICIO = "0123456789abcdef0123456789abcdef01234567"


def _edit_yaml(root, rel: str, mutate):
    p = root / rel
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    mutate(doc)
    p.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _vira_derivado(doc: dict) -> None:
    """O bloco target completo, como o /adotar o escreveria."""
    doc["project"]["kind"] = "derived"
    doc["target"] = {
        "repo": ALVO_FICTICIO,
        "ref": "principal",
        "lock_source": "target.lock",
        "code_roots": ["src"],
        "languages": ["python"],
    }


def test_baseline_esta_conforme(repo_copy, run_metadata):
    code, errors = run_metadata(repo_copy)
    assert code == 0, f"o baseline deveria estar verde, mas: {errors}"


def test_kind_derived_sem_target_reprova(repo_copy, run_metadata):
    """Derivado que não diz o que governa é um molde fingindo ter alvo."""
    _edit_yaml(repo_copy, "project.yaml", lambda d: d["project"].update(kind="derived"))
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("target" in e for e in errors), errors


def test_kind_mold_com_target_reprova(repo_copy, run_metadata):
    """Molde ancorado num alvo específico deixou de ser genérico — e genérico é o produto."""
    _edit_yaml(repo_copy, "project.yaml", lambda d: d.update(
        target={"repo": ALVO_FICTICIO, "ref": "principal", "lock_source": "target.lock",
                "code_roots": ["src"], "languages": ["python"]}))
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("target" in e for e in errors), errors


def test_papeis_divergentes_entre_project_e_lock_reprovam(repo_copy, run_metadata):
    """Dois arquivos que discordam sobre o papel do repositório são pior que um só:
    cada fiscal pode acreditar em um deles, e ambos passam."""
    _edit_yaml(repo_copy, "project.yaml", _vira_derivado)
    # target.lock segue dizendo mold — é a divergência que se quer flagrar.
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("papel do repositório" in e for e in errors), errors


def test_lock_source_apontando_para_outro_lugar_reprova(repo_copy, run_metadata):
    def mutate(doc):
        _vira_derivado(doc)
        doc["target"]["lock_source"] = "project.yaml"
    _edit_yaml(repo_copy, "project.yaml", mutate)
    _edit_yaml(repo_copy, "target.lock", lambda d: d.update(kind="derived", target_sha=SHA_FICTICIO))
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("lock_source" in e or "estrutural" in e for e in errors), errors


def test_derivado_sem_sha_no_lock_reprova(repo_copy, run_metadata):
    """Não existe derivado a meio caminho: quem declara derived ancora um commit."""
    _edit_yaml(repo_copy, "project.yaml", _vira_derivado)
    _edit_yaml(repo_copy, "target.lock", lambda d: d.update(kind="derived"))  # target_sha segue null
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("target.lock" in e for e in errors), errors


def test_molde_com_sha_no_lock_reprova(repo_copy, run_metadata):
    _edit_yaml(repo_copy, "target.lock", lambda d: d.update(target_sha=SHA_FICTICIO))
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("target.lock" in e for e in errors), errors


def test_derivado_bem_formado_passa(repo_copy, run_metadata):
    """A trava tem que deixar passar o caso legítimo — senão ela não é trava, é obstáculo.

    code_roots aponta para 'src', que existe no molde; sem workspace/target materializado,
    check_target_roots fica em silêncio de propósito (cobrar aí transformaria 'ainda não rodou o
    bootstrap' em divergência de metadado).
    """
    _edit_yaml(repo_copy, "project.yaml", _vira_derivado)
    _edit_yaml(repo_copy, "target.lock", lambda d: d.update(kind="derived", target_sha=SHA_FICTICIO))
    code, errors = run_metadata(repo_copy)
    assert code == 0, errors


def test_code_root_inexistente_reprova_com_workspace(repo_copy, run_metadata):
    """Raiz chutada torna a invariante do código órfão verdadeira por vacuidade —
    um fiscal que percorre conjunto vazio reporta verde."""
    def mutate(doc):
        _vira_derivado(doc)
        doc["target"]["code_roots"] = ["pacotes-que-nao-existem"]
    _edit_yaml(repo_copy, "project.yaml", mutate)
    _edit_yaml(repo_copy, "target.lock", lambda d: d.update(kind="derived", target_sha=SHA_FICTICIO))
    (repo_copy / "workspace/target").mkdir(parents=True, exist_ok=True)
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("code_roots" in e for e in errors), errors


def test_sha_em_project_yaml_reprova(repo_copy, run_auditor):
    """ADR-008-A4: o SHA mora num lugar só. A segunda cópia é a que mente."""
    p = repo_copy / "project.yaml"
    p.write_text(p.read_text(encoding="utf-8") + f"\n# ingerido em {SHA_FICTICIO}\n",
                 encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-008-A4" in ids_of(findings)


def test_alvo_cravado_no_fiscal_reprova(repo_copy, run_auditor):
    """ADR-008-A5, a invariante da genericidade: um molde que ganhou um caminho especial para o
    alvo difícil de ontem funciona para aquele alvo e falha calado nos outros — falha parecendo
    que funcionou, porque o caminho geral nunca é exercitado."""
    p = repo_copy / "ci/validate_metadata.py"
    p.write_text(
        p.read_text(encoding="utf-8")
        + "\n# caso especial do alvo: https://github.com/exemplo-owner/exemplo-repo\n",
        encoding="utf-8",
    )
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-008-A5" in ids_of(findings)
