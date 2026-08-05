"""Mordidas da trava externa em duas camadas (CP-024 / ADR-020).

A pergunta que estes testes protegem é a frase que abre o CLAUDE.md: *uma trava que o vigiado pode
desligar em silêncio não é uma trava.* Ela era parcialmente falsa aqui, e continua parcialmente
falsa — a diferença é que agora a parte falsa está declarada, datada e barulhenta.

`verify_protection` recebe a resposta da API como argumento. O motivo é o de sempre nesta casa:
"a proteção está desligada" e "não consegui perguntar" pedem reações opostas, e um verificador que
faz a chamada dentro de si mesmo não consegue manter os dois separados.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from conftest import REPO

sys.path.insert(0, str(REPO / "ci"))

import verify_protection as vp  # noqa: E402

PROTEGIDOS = ["ci/", "harness/", ".github/"]
CODEOWNERS_OK = ["/ci/ @dono", "/harness/ @dono", "/.github/ @dono"]

PROTECAO_OK = {
    "required_pull_request_reviews": {"require_code_owner_reviews": True},
    "allow_force_pushes": {"enabled": False},
}


def test_protecao_ligada_e_caminhos_com_dono_passa():
    """O par positivo. Sem ele, um verificador que reprovasse tudo passaria em todos os negativos."""
    assert vp.verify_protection(protection=PROTECAO_OK, codeowners=CODEOWNERS_OK,
                                protected_paths=PROTEGIDOS) == []


def test_protecao_ausente_reprova():
    v = vp.verify_protection(protection={}, codeowners=CODEOWNERS_OK, protected_paths=PROTEGIDOS)
    assert any("não tem proteção alguma" in m for m in v), v


def test_review_sem_code_owner_reprova():
    """É o elo que faz protected_paths significar alguma coisa.

    Sem ele, qualquer aprovador serve para mudar um fiscal — e "o fiscal só muda com revisão de
    quem é dono dele" vira "o fiscal muda com revisão de qualquer um".
    """
    protecao = {**PROTECAO_OK,
                "required_pull_request_reviews": {"require_code_owner_reviews": False}}
    v = vp.verify_protection(protection=protecao, codeowners=CODEOWNERS_OK,
                             protected_paths=PROTEGIDOS)
    assert any("review de CODE OWNER" in m for m in v), v


def test_force_push_permitido_reprova():
    """Histórico reescrevível torna TODA âncora por commit uma afirmação sobre conteúdo mutável.

    target.lock, mold_release.commit_sha, executed_in.merge_commit_sha — as três dependem de o
    commit citado continuar sendo o que era.
    """
    protecao = {**PROTECAO_OK, "allow_force_pushes": {"enabled": True}}
    v = vp.verify_protection(protection=protecao, codeowners=CODEOWNERS_OK,
                             protected_paths=PROTEGIDOS)
    assert any("force push" in m for m in v), v


def test_caminho_protegido_sem_dono_reprova():
    v = vp.verify_protection(protection=PROTECAO_OK, codeowners=["/ci/ @dono"],
                             protected_paths=PROTEGIDOS)
    assert any("harness/" in m for m in v), v


def test_indeterminacao_nao_vira_violacao():
    """Princípio (h), e aqui ele tem um motivo bem concreto.

    A API responde 404 tanto para "sem proteção" quanto para "sem permissão de ver". Os dois são
    indistinguíveis de fora — escolher a conclusão mais grave produziria alarme de fraude toda vez
    que o token não tivesse escopo, e alarme que dispara sem fraude é alarme que se desliga.
    """
    assert vp.verify_protection(protection=None, codeowners=[], protected_paths=PROTEGIDOS) == []


# --------------------------------------------------------------------------------------
# O estado declarado da camada externa
# --------------------------------------------------------------------------------------

def _desligar(root: Path) -> None:
    """Monta, numa cópia, o cenário DESLIGADO por inteiro — não só a flag.

    Simétrico a `_ligar`, e pela mesma razão, que já custou duas correções. Os três testes abaixo
    cobrem o caminho desligado, que continua sendo um estado legítimo do fiscal e continua
    precisando de teste. Eles herdavam esse estado do repositório; quando a CP-036 ligou a
    autoridade, caíram todos.

    "Por inteiro" tem conteúdo aqui. Desligada, a camada exige um risco aceito que EXISTA e TENHA
    DATA — e a CP-036 moveu o `RISK-EXT-001` para `mitigated`, sem `due`, porque risco mitigado não
    tem prazo a vencer. Uma fixture que virasse só a flag produziria `EXT-AUDIT-RISCO-SEM-DATA` e
    nunca chegaria ao achado que o teste quer ver. Montar o cenário é construir a premissa, não
    afrouxar o fiscal: quem desligasse a camada de verdade teria de reabrir o risco com data nova.
    """
    caminho = root / "harness/harness.yaml"
    doc = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    doc["external_audit"]["enabled"] = False
    doc["external_audit"].pop("authorized_issuer", None)   # o schema o exige só quando ligada
    caminho.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (root / "harness/state/protection-attestation.json").unlink(missing_ok=True)

    registro = root / "governance/risk-register.yaml"
    riscos = yaml.safe_load(registro.read_text(encoding="utf-8"))
    for risco in riscos["risks"]:
        if risco["id"] == doc["external_audit"]["accepted_risk"]:
            risco["status"] = "open"
            risco["treatment"] = "accept"
            risco["due"] = "2026-11-03"
    registro.write_text(yaml.safe_dump(riscos, allow_unicode=True, sort_keys=False),
                        encoding="utf-8")


def test_auditoria_externa_desligada_aparece_no_laudo(repo_copy: Path, run_auditor):
    """O desligado é DECLARADO, não omitido: a lacuna aparece a cada execução, com severidade
    `info` — bloquear inverteria a decisão da CP-024, e vermelho permanente é como um fiscal se
    aprende a ignorar."""
    _desligar(repo_copy)
    _, findings = run_auditor("audit_governance", repo_copy)
    desligada = _achados(findings, "EXT-AUDIT-DESLIGADA")
    assert desligada, [f["id"] for f in findings]
    assert desligada[0]["severity"] == "info", desligada


def test_desligar_HOJE_contradiz_um_ADR_ACEITO_e_reprova(repo_copy: Path, run_auditor):
    """O que mudou com a CP-036, dito como teste.

    Antes desta CP, desligar a camada externa era um estado conforme: a decisão vigente dizia que
    ela estava desligada, e o achado `info` era todo o barulho que cabia. Agora existe um ADR
    ACEITO afirmando o contrário, e é ele quem morde — `enabled: false` deixou de ser configuração
    e passou a ser contradição com uma decisão registrada.

    Os dois achados convivem, e é a mesma doutrina de sempre (princípio (h)): o `info` continua
    descrevendo o estado, e o bloqueante diz que esse estado precisa de uma decisão nova, não de
    uma edição de linha.
    """
    _desligar(repo_copy)
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert _achados(findings, "ADR-028-A2"), [f["id"] for f in findings]
    assert _achados(findings, "EXT-AUDIT-DESLIGADA"), [f["id"] for f in findings]


def test_desligada_sem_risco_declarado_reprova(repo_copy: Path, run_auditor):
    """Desligar a camada externa tem que CUSTAR um risco datado a alguém."""
    _desligar(repo_copy)
    caminho = repo_copy / "harness/harness.yaml"
    doc = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    doc["external_audit"]["accepted_risk"] = "RISK-QUE-NAO-EXISTE"
    caminho.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f["id"].endswith("RISCO-AUSENTE") for f in findings), [f["id"] for f in findings]


def test_risco_aceito_sem_data_reprova(repo_copy: Path, run_auditor):
    """Princípio (g): risco aceito sem data é risco esquecido."""
    _desligar(repo_copy)
    caminho = repo_copy / "governance/risk-register.yaml"
    doc = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    for risco in doc["risks"]:
        if risco["id"] == "RISK-EXT-001":
            risco.pop("due", None)
    caminho.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f["id"].endswith("RISCO-SEM-DATA") for f in findings), [f["id"] for f in findings]


def test_workflow_sem_auditoria_externa_reprova(repo_copy: Path, run_auditor):
    """Remover o passo de verificação é o gesto exato de quem quer desligar a trava."""
    wf = repo_copy / ".github/workflows/governance.yml"
    wf.write_text(wf.read_text(encoding="utf-8").replace(
        "python ci/verify_protection.py", "true # removido"), encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f.get("assertion") == "ADR-020-A2" for f in findings), [f["id"] for f in findings]


# --------------------------------------------------------------------------------------
# Camada externa LIGADA: o que passa a ser exigido
# --------------------------------------------------------------------------------------

def _ligar(root: Path) -> None:
    """Liga a camada externa e parte de um estado CONHECIDO: sem atestado.

    A remoção não é zelo excessivo — ela é a correção de um teste que passava por acidente. Até
    hoje o repositório não tinha atestado nenhum, então `test_ligada_sem_atestado_reprova` testava
    a ausência sem precisar produzi-la. Quando a autoridade externa entregou o primeiro atestado
    real, a premissa do teste evaporou e ele passou a falhar — corretamente, porque a cópia já não
    representava o cenário que o nome dele promete.

    Quem quer atestado chama `_atestado`. Fixture que depende do acaso do repositório testa o que o
    repositório é hoje, não o que a regra diz.
    """
    caminho = root / "harness/harness.yaml"
    doc = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    doc["external_audit"]["enabled"] = True
    caminho.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (root / "harness/state/protection-attestation.json").unlink(missing_ok=True)


def _atestado(root: Path, *, expires: str, identity: str = "harness-authority",
              kind: str = "github_app") -> None:
    import json

    destino = root / "harness/state"
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "protection-attestation.json").write_text(json.dumps({
        "schema_version": "1.0", "metadata_version": "1.0",
        "source_of_truth": True, "generated_from": None,
        "attestation": {
            "repository": "danzeroum/project", "branch": "main",
            "checked_at": "2026-08-05T00:00:00+00:00", "expires_at": expires,
            "ruleset_ref": "org/rulesets/42",
            "issuer": {"identity": identity, "kind": kind},
            "verifier_version": "1.0", "config_digest": "sha256:" + "a" * 64,
        },
    }, indent=2), encoding="utf-8")


def test_ligada_sem_atestado_reprova(repo_copy: Path, run_auditor):
    _ligar(repo_copy)
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f["id"].endswith("SEM-ATESTADO") for f in findings), [f["id"] for f in findings]


def test_atestado_externo_expirado_reprova(repo_copy: Path, run_auditor):
    """Expirado bloqueia do mesmo modo que ausente — senão o atestado vira carimbo eterno."""
    _ligar(repo_copy)
    ontem = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
    _atestado(repo_copy, expires=ontem)
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f["id"].endswith("ATESTADO-EXPIRADO") for f in findings), [f["id"] for f in findings]


def test_atestado_valido_passa(repo_copy: Path, run_auditor):
    """O par positivo da camada ligada: com atestado válido, nada de externo bloqueia."""
    _ligar(repo_copy)
    amanha = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(timespec="seconds")
    _atestado(repo_copy, expires=amanha)
    code, findings = run_auditor("audit_governance", repo_copy)
    bloqueantes = [f for f in findings
                   if f["origin"] == "external_audit" and f["severity"] != "info"]
    assert not bloqueantes, bloqueantes


def test_atestado_emitido_por_identidade_nao_autorizada_reprova(repo_copy: Path, run_auditor):
    """Atestado anônimo é indistinguível de atestado forjado — e quem mais teria motivo para
    forjá-lo é o próprio repositório fiscalizado."""
    import json

    _ligar(repo_copy)
    amanha = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(timespec="seconds")
    _atestado(repo_copy, expires=amanha)
    caminho = repo_copy / "harness/state/protection-attestation.json"
    doc = json.loads(caminho.read_text(encoding="utf-8"))
    del doc["attestation"]["issuer"]
    caminho.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f["id"].endswith("ATESTADO-INVALIDO") for f in findings), [f["id"] for f in findings]


def test_cp_024_esta_deferred():
    """A CP não se declara implementada, e isso é uma afirmação verificável.

    A §7 do plano é explícita: sem identidade externa viável, a CP-024 fica `deferred` — não conta
    como implementada. Se alguém a promover a `executed` sem ligar a camada externa, este teste
    falha, e é a única coisa que impede a promoção silenciosa.
    """
    doc = yaml.safe_load(
        (REPO / "harness/change-proposals/CP-024-trava-externa-em-duas-camadas.yaml")
        .read_text(encoding="utf-8"))
    harness = yaml.safe_load((REPO / "harness/harness.yaml").read_text(encoding="utf-8"))
    if not harness["external_audit"]["enabled"]:
        assert doc["proposal"]["status"] == "deferred", \
            "camada externa desligada e CP não está deferred — ela estaria passando por pronta"


# --------------------------------------------------------------------------------------
# O emissor: a emenda que fecha "alguém atestou" vs "quem devia atestou" (CP-036)
# --------------------------------------------------------------------------------------

def _achados(findings, sufixo: str) -> list[dict]:
    return [f for f in findings if f["id"].endswith(sufixo)]


def test_emissor_nao_autorizado_reprova_com_achado_PROPRIO(repo_copy: Path, run_auditor):
    """Atestado de emissor não declarado é indistinguível de atestado escrito à mão por quem tem
    direito de merge — que é exatamente quem teria motivo para escrevê-lo."""
    _ligar(repo_copy)
    amanha = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(timespec="seconds")
    _atestado(repo_copy, expires=amanha, identity="impostor")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert _achados(findings, "EMISSOR-NAO-AUTORIZADO"), [f["id"] for f in findings]
    assert not _achados(findings, "ATESTADO-EXPIRADO")


def test_kind_divergente_tambem_reprova(repo_copy: Path, run_auditor):
    """A identidade certa com o tipo errado seria um emissor diferente com o mesmo nome."""
    _ligar(repo_copy)
    amanha = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(timespec="seconds")
    _atestado(repo_copy, expires=amanha, kind="external_service")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert _achados(findings, "EMISSOR-NAO-AUTORIZADO")


def test_expirado_E_emissor_errado_produzem_DOIS_achados(repo_copy: Path, run_auditor):
    """Princípio (h) levado a sério: são dois problemas, com duas reações. Colapsá-los num
    'EXT-AUDIT-INVALIDO' genérico economizaria código e destruiria a informação que diz para onde
    olhar — 'o verificador parou' e 'alguém escreveu isto à mão' pedem coisas opostas."""
    _ligar(repo_copy)
    ontem = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
    _atestado(repo_copy, expires=ontem, identity="impostor")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert _achados(findings, "EMISSOR-NAO-AUTORIZADO")
    assert _achados(findings, "ATESTADO-EXPIRADO")


def test_os_tres_estados_tem_mensagens_distintas(repo_copy: Path, run_auditor):
    """Ausente, expirado e emissor errado nunca dizem a mesma coisa."""
    _ligar(repo_copy)
    _, ausente = run_auditor("audit_governance", repo_copy)

    ontem = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
    _atestado(repo_copy, expires=ontem)
    _, expirado = run_auditor("audit_governance", repo_copy)

    amanha = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(timespec="seconds")
    _atestado(repo_copy, expires=amanha, identity="impostor")
    _, emissor = run_auditor("audit_governance", repo_copy)

    frases = {
        _achados(ausente, "SEM-ATESTADO")[0]["summary"],
        _achados(expirado, "ATESTADO-EXPIRADO")[0]["summary"],
        _achados(emissor, "EMISSOR-NAO-AUTORIZADO")[0]["summary"],
    }
    assert len(frases) == 3


def test_a_autoridade_esta_LIGADA_e_o_emissor_declarado():
    """O estado que esta CP produziu, afirmado em teste: se alguém reverter `enabled` para false,
    isto cai — e cair é o ponto, porque desligar a autoridade é decisão, não ajuste."""
    doc = yaml.safe_load((REPO / "harness/harness.yaml").read_text(encoding="utf-8"))
    externo = doc["external_audit"]
    assert externo["enabled"] is True
    assert externo["authorized_issuer"] == {"identity": "harness-authority", "kind": "github_app"}


def test_o_atestado_real_na_arvore_e_do_emissor_declarado():
    """A ponta a ponta do dia: o arquivo que a autoridade entregou casa a autoridade declarada."""
    import json

    doc = yaml.safe_load((REPO / "harness/harness.yaml").read_text(encoding="utf-8"))
    caminho = REPO / doc["external_audit"]["attestation_path"]
    atestado = json.loads(caminho.read_text(encoding="utf-8"))["attestation"]
    assert atestado["issuer"] == doc["external_audit"]["authorized_issuer"]


def test_MUTACAO_CANONICA_issuer_trocado_no_atestado_REAL_reprova(repo_copy: Path, run_auditor):
    """A mutação canônica da CP-036, aplicada ao ARTEFATO REAL — não a uma fixture montada aqui.

    A diferença importa e já custou correção nesta suíte: uma fixture prova que o fiscal reage ao
    JSON que o teste escreveu. Isto prova que ele reage ao JSON que a autoridade entregou, com um
    único campo trocado e nada mais — que é exatamente o gesto de quem tem direito de merge e quer
    o carimbo sem a auditoria.

    Nenhuma identidade é restatada aqui: a autorizada é lida de `harness.yaml`, e a impostora é
    derivada dela. Um teste que escrevesse "harness-authority" viraria um terceiro lugar onde a
    identidade mora, e o terceiro lugar é sempre o que fica desatualizado.

    Robusto ao calendário de propósito: quando o atestado real expirar, este teste continua válido
    porque a checagem de emissor não tem `return` — expirado E emissor errado produzem os dois
    achados, e é o de emissor que ele afirma.
    """
    import json

    harness = yaml.safe_load((repo_copy / "harness/harness.yaml").read_text(encoding="utf-8"))
    autorizado = harness["external_audit"]["authorized_issuer"]
    caminho = repo_copy / harness["external_audit"]["attestation_path"]

    doc = json.loads(caminho.read_text(encoding="utf-8"))
    assert doc["attestation"]["issuer"] == autorizado, "premissa: a cópia parte do estado conforme"
    doc["attestation"]["issuer"]["identity"] = autorizado["identity"] + "-impostor"
    caminho.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert _achados(findings, "EMISSOR-NAO-AUTORIZADO"), [f["id"] for f in findings]
