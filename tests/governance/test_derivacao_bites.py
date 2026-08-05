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
        "test_roots": ["tests/unit"],
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
                "code_roots": ["src"], "test_roots": ["tests/unit"], "languages": ["python"]}))
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


ANCORA = ("papel do repositório", "lock_source", "target.lock", "code_roots")

# CP-021: um derivado bem formado ancora DUAS coisas — o alvo que governa (target_sha) e a versão
# do molde de que nasceu (mold_release). O caso legítimo passa a incluir a segunda âncora; sem
# isso, este teste positivo estaria afirmando que "bem formado" é o estado que o schema recusa.
MOLD_RELEASE_VALIDO = {
    "repository": "danzeroum/project",
    "tag": "v1.0.0",
    "commit_sha": "1" * 40,
    "manifest_path": "harness/releases/v1.0.0.manifest.json",
    "manifest_sha": "2" * 64,
}


def test_derivado_bem_formado_nao_gera_achado_de_ancora(repo_copy, run_metadata):
    """A trava tem que deixar passar o caso legítimo — senão ela não é trava, é obstáculo.

    Escopo deliberadamente estreito: este arquivo prova a ÂNCORA (papel, lock, raízes declaradas),
    não a cobertura de metadado. Uma cópia do molde marcada como derivada segue com os metadados
    do molde apontando para src/ e tests/, o que depois do ADR-009 é divergência real — e é
    exatamente o que test_inventario_bites cobre, com um alvo materializado de verdade. Afirmar
    exit 0 aqui obrigaria a montar um derivado inteiro só para testar duas chaves de YAML, e
    afirmar exit 1 esconderia a regressão que importa atrás de erros de outro fiscal.
    """
    _edit_yaml(repo_copy, "project.yaml", _vira_derivado)
    _edit_yaml(repo_copy, "target.lock",
               lambda d: d.update(kind="derived", target_sha=SHA_FICTICIO,
                                  mold_release=MOLD_RELEASE_VALIDO))
    _, errors = run_metadata(repo_copy)
    ancora = [e for e in errors if any(t in e for t in ANCORA)]
    assert not ancora, ancora


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


def test_molde_virando_derivado_reprova(repo_copy, run_auditor):
    """ADR-008-A6: a trava que vale para ESTE repositório, não para qualquer cópia dele.

    Todas as demais travas valem para qualquer molde; esta vale para a origem. Sem ela, rodar
    /adotar dentro do molde em vez de derivar dele produz um kind:derived perfeitamente válido —
    cada trava individual continua satisfeita, e o repositório genérico simplesmente deixa de
    existir, sem alarme. O derivado herda a asserção e a remove no CP-000, junto com o superseded
    do ADR-005: ele não é este repositório e não carrega as travas que dizem respeito só a ele.
    """
    _edit_yaml(repo_copy, "project.yaml", _vira_derivado)
    _edit_yaml(repo_copy, "target.lock", lambda d: d.update(kind="derived", target_sha=SHA_FICTICIO))
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-008-A6" in ids_of(findings), ids_of(findings)


# --------------------------------------------------------------------------------------
# CP-018: a proposta é registro histórico; o metadado vivo continua cobrado
# --------------------------------------------------------------------------------------

ID_FANTASMA = "CAP-FANTASMA"
CMP_FANTASMA = "CMP-FANTASMA"


def _gravar_cp(root, nome: str, **campos) -> None:
    doc = yaml.safe_load((root / "harness/change-proposals/EXAMPLE-CP-001.yaml")
                         .read_text(encoding="utf-8"))
    doc["proposal"].update(id="CP-900", title="proposta sintética do teste", **campos)
    (root / f"harness/change-proposals/{nome}").write_text(
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_proposta_citando_id_removido_nao_reprova(repo_copy, run_metadata):
    """O achado que originou o CP-018, na forma mínima.

    Uma proposta fala do dia em que foi escrita. Executá-la é justamente o que apaga os IDs que
    ela cita — então resolver esses IDs contra o presente faz a proposta reprovar por ter
    funcionado. Medido num derivado real: dezoito achados desta espécie, incluindo o da proposta
    que se invalidava ao ser cumprida.
    """
    _gravar_cp(repo_copy, "CP-900-sintetica.yaml",
               capabilities_affected=[ID_FANTASMA], components_affected=[CMP_FANTASMA])
    code, errors = run_metadata(repo_copy)
    assert not [e for e in errors if "[CP]" in e], errors
    assert code == 0, errors


def test_a_isencao_nao_vaza_para_o_adr(repo_copy, run_metadata):
    """O limite do CP-018, e a razão de este teste existir junto com o de cima.

    O risco da proposta não é a checagem que ela remove — é uma isenção escrita larga demais, que
    apagasse a resolução de ID de todo o metadado. ADR descreve o que É, não o que foi decidido:
    referência pendurada nele segue sendo achado.
    """
    p = repo_copy / "architecture/adr/index.yaml"
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    doc["adrs"][0].setdefault("related_capabilities", []).append(ID_FANTASMA)
    p.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("[ADR]" in e and ID_FANTASMA in e for e in errors), errors
