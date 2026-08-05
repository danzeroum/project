"""Mordidas do caminho de release executável (CP-031 / ADR-025).

Três níveis, e a divisão não é decorativa — cada um só consegue provar o que o anterior não
alcança:

  UNIDADE     as funções puras (`preflight_publicacao`, `verify_tag_protection`) decidem certo
              sobre entradas construídas à mão. É onde os modos de falha raros são baratos.
  INTEGRAÇÃO  o workflow DECLARA a ordem que a decisão exige. Uma função pura correta dentro de um
              workflow que a chama depois do push não protege nada.
  SISTEMA     a cadeia inteira sobre um repositório git de verdade, com commits e tag reais.

O limite de maior risco é a janela entre validar e criar a ref, e ele aparece nos três: como `!=`
na unidade, como ordem dos passos na integração, e como "o objeto publicado é o objeto verificado"
no sistema.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from conftest import REPO

sys.path.insert(0, str(REPO / "ci"))

import harness_lib as hl  # noqa: E402
import mold_release as mr  # noqa: E402
import verify_protection as vp  # noqa: E402

WORKFLOW = REPO / ".github/workflows/release.yml"
SHA_A = "a" * 40
SHA_B = "b" * 40


# --------------------------------------------------------------------------------------
# UNIDADE — preflight: a janela, num `!=`
# --------------------------------------------------------------------------------------

def _preflight(**kw) -> list[str]:
    base = dict(tag="v1.0.0", tags_remotas=[], head_sha=SHA_A, validado_sha=SHA_A,
                manifesto_na_arvore=False)
    base.update(kw)
    return mr.preflight_publicacao(**base)


def test_publicacao_legitima_passa():
    """O par obrigatório da mordida: um fiscal que só reprova é desligado por quem trabalha."""
    assert _preflight() == []


def test_head_movido_entre_validar_e_publicar_reprova():
    """A JANELA. Se o HEAD andou, a tag certificaria uma árvore que nenhuma validação olhou —
    com o carimbo de uma que olhou outra. É o modo de falha que esta CP existe para fechar."""
    v = _preflight(head_sha=SHA_B)
    assert v and "mudou entre a validação" in v[0]


def test_tag_preexistente_reprova():
    """Publicar por cima é mover a âncora. O `git push` sem --force também recusa; esta é a
    recusa que chega em segundos, antes de um minuto e meio de prova de mutação."""
    assert any("já existe no remoto" in m for m in _preflight(tags_remotas=["v1.0.0"]))


def test_manifesto_ja_na_arvore_reprova():
    """Sem isto, o elo 'o commit de release não muda nada além do manifesto' passaria por
    VACUIDADE — não haveria mudança alguma para inspecionar."""
    assert any("já está na árvore" in m for m in _preflight(manifesto_na_arvore=True))


@pytest.mark.parametrize("tag", ["1.0.0", "v1.0", "release-1", "v1.0.0-rc1", ""])
def test_tag_de_forma_livre_reprova(tag):
    """O caminho do manifesto é DERIVADO da tag: forma livre produz caminho que nenhum fiscal
    prevê."""
    assert any("forma vX.Y.Z" in m for m in _preflight(tag=tag))


def test_preflight_acumula_em_vez_de_parar_no_primeiro():
    """Quem está consertando precisa ver os quatro problemas de uma vez."""
    assert len(_preflight(tag="1.0", tags_remotas=["1.0"], head_sha=SHA_B,
                          manifesto_na_arvore=True)) == 4


def test_preflight_e_puro():
    """Se ele tocasse git ou rede, 'não pode publicar' e 'não consegui olhar' virariam a mesma
    cor — e a mais barata venceria por hábito (princípio (h))."""
    fonte = (REPO / "ci/mold_release.py").read_text(encoding="utf-8")
    corpo = fonte.split("def preflight_publicacao(")[1].split("\ndef ")[0]
    for proibido in ("subprocess.", "urlopen", "requests.", "open("):
        assert proibido not in corpo, proibido


# --------------------------------------------------------------------------------------
# UNIDADE — eixo de tags da trava externa
# --------------------------------------------------------------------------------------

def _ruleset(**kw) -> dict:
    base = {
        "id": 1, "name": "tags imóveis", "target": "tag", "enforcement": "active",
        "conditions": {"ref_name": {"include": ["refs/tags/v*"]}},
        "rules": [{"type": t} for t in ("deletion", "non_fast_forward", "update")],
        "bypass_actors": [],
    }
    base.update(kw)
    return base


def test_ruleset_completo_protege():
    assert vp.verify_tag_protection(rulesets=[_ruleset()]) == []


def test_creation_nao_e_exigida():
    """Deliberado: exigir `creation` trancaria o único caminho legítimo de publicação, e uma
    trava que impede o trabalho legítimo é desligada por quem tem trabalho a fazer."""
    sem_creation = [r["type"] for r in _ruleset()["rules"]]
    assert "creation" not in sem_creation
    assert vp.verify_tag_protection(rulesets=[_ruleset()]) == []


def test_sem_ruleset_de_tag_acusa():
    """O `git push` sem --force é recusa do CLIENTE. Quem tem token e vontade empurra com
    --force; o que transforma a recusa em trava é o ruleset."""
    v = vp.verify_tag_protection(rulesets=[])
    assert v and "nenhum ruleset de tag ATIVO" in v[0]


@pytest.mark.parametrize("faltando", ["deletion", "non_fast_forward", "update"])
def test_regra_ausente_acusa(faltando):
    regras = [{"type": t} for t in ("deletion", "non_fast_forward", "update") if t != faltando]
    v = vp.verify_tag_protection(rulesets=[_ruleset(rules=regras)])
    assert v and faltando in v[0]


def test_bypass_list_nao_vazia_acusa():
    """Quem pode bypassar pode mover a tag — e a trava passa a valer só para quem não precisaria
    dela."""
    v = vp.verify_tag_protection(rulesets=[_ruleset(bypass_actors=[{"actor_id": 5}])])
    assert any("bypass list" in m for m in v)


def test_ruleset_desativado_nao_conta_como_protecao():
    assert vp.verify_tag_protection(rulesets=[_ruleset(enforcement="disabled")])


def test_ruleset_que_nao_cobre_a_familia_de_tags_nao_conta():
    inclui = {"ref_name": {"include": ["refs/tags/beta-*"]}}
    assert vp.verify_tag_protection(rulesets=[_ruleset(conditions=inclui)])


def test_indeterminacao_nao_vira_violacao():
    """A API responde 403/404 tanto para 'não há ruleset' quanto para 'você não pode ver'.
    Escolher a conclusão mais grave produziria alarme de fraude toda vez que o token não tivesse
    escopo — quem trata a indeterminação é o chamador."""
    assert vp.verify_tag_protection(rulesets=None) == []


# --------------------------------------------------------------------------------------
# INTEGRAÇÃO — o workflow declara a ordem que a decisão exige
# --------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def wf_texto() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def wf() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_dispatch_recebe_a_versao_como_entrada(wf):
    # `on` vira True no YAML 1.1 (a chave `on` é booleana); por isso o lookup tolera as duas formas.
    gatilhos = wf.get("on") or wf.get(True)
    assert gatilhos["workflow_dispatch"]["inputs"]["tag"]["required"] is True


def test_so_o_job_de_publicar_escreve_conteudo(wf):
    """Permissão de escrita é o que separa 'audita' de 'publica'. O default do arquivo continua
    read: um job novo não nasce podendo criar refs."""
    assert wf["permissions"]["contents"] == "read"
    assert wf["jobs"]["publicar"]["permissions"]["contents"] == "write"
    assert "permissions" not in wf["jobs"]["auditar"]


def test_os_dois_caminhos_sao_mutuamente_exclusivos(wf):
    assert wf["jobs"]["publicar"]["if"] == "github.event_name == 'workflow_dispatch'"
    assert wf["jobs"]["auditar"]["if"] == "github.event_name == 'push'"


def _passos(wf: dict, job: str) -> list[str]:
    return [json.dumps(p, ensure_ascii=False) for p in wf["jobs"][job]["steps"]]


def _indice(passos: list[str], agulha: str) -> int:
    for i, p in enumerate(passos):
        if agulha in p:
            return i
    raise AssertionError(f"passo com {agulha!r} não existe no job")


@pytest.mark.parametrize("antes,depois", [
    ("ci/validate_all.py", "git push origin"),
    ("pytest tests/governance", "git push origin"),
    ("ci/audit_mutations.py", "git push origin"),
    ("--preflight", "git push origin"),
    ("--verify-tag", "git push origin"),
    ("git push origin", "audit_ledger.py --append release"),
])
def test_ordem_dos_passos_do_job_de_publicar(wf, antes, depois):
    """A ORDEM é a decisão inteira. Uma função pura correta chamada depois do push não protege
    coisa alguma — e o registro no ledger vem DEPOIS porque ele referencia o commit taggeado."""
    passos = _passos(wf, "publicar")
    assert _indice(passos, antes) < _indice(passos, depois)


def test_o_registro_nasce_do_validado_e_cita_o_taggeado(wf):
    """Dentro DO PASSO do ledger — e a distinção é a razão de este teste existir separado.

    A busca "existe um detach antes do append?" acha o detach do passo que monta o commit de
    release, que vem antes de tudo isto, e passaria mesmo com o do ledger removido. É o mesmo
    alçapão que a asserção ADR-025-A14 evita ancorando no nome do passo — e o teste ingênuo caiu
    nele antes de virar este.
    """
    passo = next(p for p in wf["jobs"]["publicar"]["steps"]
                 if p.get("name") == "Registrar a release no ledger")
    script = passo["run"]
    assert script.index('git switch --detach "${VALIDADO}"') < script.index("--append release")
    assert '--commit-sha "${RELEASE_COMMIT}"' in script


def test_o_registro_vem_depois_da_ref(wf):
    """Registrar antes de publicar seria registrar o que ainda pode não acontecer."""
    passos = _passos(wf, "publicar")
    assert _indice(passos, "Publicar a ref") < _indice(passos, "Registrar a release no ledger")


def test_nenhum_push_com_force(wf_texto):
    """Criar e mover são operações distintas, e a assimetria entre elas é toda a resposta à
    objeção do auto-atestado do CP-021."""
    assert not re.search(r"^[^#\n]*git push[^\n]*--force", wf_texto, re.MULTILINE)


def test_a_ref_publicada_e_a_tag_de_entrada_e_nada_mais(wf_texto):
    """Um push de branch junto com o da tag seria o workflow escrevendo onde o ruleset da main
    recusa — por fora do portão que esta casa exige."""
    empurrados = re.findall(r"git push origin \"([^\"]+)\"", wf_texto)
    assert empurrados == ['refs/tags/${TAG}', 'HEAD:refs/heads/release/ledger-${TAG}']


def test_a_release_e_registrada_referenciando_o_commit_taggeado(wf_texto):
    assert "--commit-sha \"${RELEASE_COMMIT}\"" in wf_texto
    assert "--artifact-ref \"harness/releases/${TAG}.manifest.json\"" in wf_texto


def test_o_commit_validado_e_fixado_antes_de_validar(wf, wf_texto):
    """Sem o SHA fixado, 'o que foi validado' seria 'o que o git tiver quando cada passo
    perguntar' — que é exatamente a ambiguidade que a janela explora."""
    passos = _passos(wf, "publicar")
    assert _indice(passos, "VALIDADO=") < _indice(passos, "ci/validate_all.py")
    assert 'git switch --detach "${VALIDADO}"' in wf_texto


def test_o_job_de_auditoria_tambem_prova_mutacao(wf):
    """Uma tag que chegue por outro caminho é auditada com a mesma régua, não com uma mais fraca."""
    passos = _passos(wf, "auditar")
    for exigido in ("ci/validate_all.py", "ci/audit_mutations.py", "--verify-tag"):
        _indice(passos, exigido)


# --------------------------------------------------------------------------------------
# INTEGRAÇÃO + SISTEMA — a recusa rápida da entrada (CP-032)
# --------------------------------------------------------------------------------------

PASSO_RECUSA = "Recusar entrada malformada"


def _script_da_recusa(wf: dict) -> str:
    """O `run:` real do passo, extraído do workflow. Testar uma CÓPIA do script seria testar a
    cópia: ela e o original divergem no primeiro dia em que alguém edita um só dos dois."""
    for p in wf["jobs"]["publicar"]["steps"]:
        if p.get("name") == PASSO_RECUSA:
            return p["run"]
    raise AssertionError(f"passo {PASSO_RECUSA!r} não existe")


def test_a_recusa_e_o_primeiro_passo_do_job(wf):
    """Antes até do checkout. A posição É a decisão: a v1.0.0 morreu três minutos depois de um
    erro de digitação porque a checagem mais barata do caminho estava entre as últimas."""
    passos = wf["jobs"]["publicar"]["steps"]
    assert passos[0].get("name") == PASSO_RECUSA
    assert "checkout" not in json.dumps(passos[0])


def test_a_recusa_usa_o_regex_EXATO_do_preflight(wf):
    """Duas checagens da mesma coisa que discordam num caso de borda são um gerador de bugs: a
    rápida libera, a lenta recusa, e o operador descobre a discordância no pior momento."""
    achados = re.findall(r"grep -qE '([^']+)'", _script_da_recusa(wf))
    assert achados == [mr.TAG_RE.pattern]


def test_a_recusa_nao_sabe_nada_do_repositorio(wf):
    """A fronteira dura da CP-032: nenhuma verificação semântica saiu do preflight. É o que
    permite rodar antes do checkout — e é o que impede este passo de virar um segundo preflight
    pior, que decide sobre um repositório que ainda não baixou."""
    script = _script_da_recusa(wf)
    for proibido in ("python", "git ", "curl", "ls-remote", "harness/"):
        assert proibido not in script, proibido


def test_a_entrada_nunca_e_interpolada_no_shell(wf_texto):
    """`${{ inputs.tag }}` só aparece sob `env:`. Interpolar entrada de dispatch dentro de um
    `run:` é injeção de comando com outro nome — e o passo que existe para desconfiar da entrada
    seria o pior lugar para confiar nela."""
    for linha in wf_texto.splitlines():
        if "inputs.tag" in linha:
            assert re.match(r"\s*ENTRADA:\s*\$\{\{\s*inputs\.tag\s*\}\}\s*$", linha), linha


def _rodar_recusa(script: str, entrada: str, tmp_path: Path) -> tuple[int, str]:
    """Roda o script REAL em bash, como o runner roda."""
    genv = tmp_path / "github_env"
    genv.write_text("", encoding="utf-8")
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "ENTRADA": entrada,
                            "GITHUB_ENV": str(genv), "LC_ALL": "C.UTF-8"})
    return r.returncode, genv.read_text(encoding="utf-8").strip()


@pytest.mark.parametrize("entrada", [
    "tag = v1.0.0",   # o erro real que matou o run 31012472062
    "V1.0.0",
    "v1.0",
    "v1.0.0-rc1",
    "v 1.0.0",        # espaço NO MEIO muda o número: normalizar seria reescrever a versão
    "",
    "v1.0.0; rm -rf /",
])
def test_entrada_malformada_e_recusada(wf, entrada, tmp_path):
    codigo, _ = _rodar_recusa(_script_da_recusa(wf), entrada, tmp_path)
    assert codigo == 1
    assert not mr.TAG_RE.match(entrada), "o preflight também recusaria — as duas concordam"


@pytest.mark.parametrize("entrada,esperado", [
    ("v1.0.1", "v1.0.1"),
    ("v10.2.33", "v10.2.33"),
    ("  v1.0.0  ", "v1.0.0"),   # espaço EM VOLTA é engano de cópia: normaliza
])
def test_entrada_valida_passa_e_chega_normalizada(wf, entrada, esperado, tmp_path):
    """O trim é a única diferença deliberada entre a checagem rápida e o TAG_RE — e ele
    NORMALIZA antes de seguir, então o preflight recebe a forma exata."""
    codigo, github_env = _rodar_recusa(_script_da_recusa(wf), entrada, tmp_path)
    assert codigo == 0
    assert github_env == f"TAG={esperado}"
    assert mr.TAG_RE.match(esperado)


def test_a_mensagem_diz_o_formato_esperado(wf, tmp_path):
    script = _script_da_recusa(wf)
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "ENTRADA": "tag = v1.0.0",
                            "GITHUB_ENV": str(tmp_path / "e"), "LC_ALL": "C.UTF-8"})
    assert "vX.Y.Z" in r.stdout


def test_o_valor_normalizado_chega_pelo_ambiente_e_nao_por_env_de_job(wf):
    """`env` de job vence o arquivo de ambiente — se TAG continuasse declarado no nível do job, a
    normalização não teria efeito nenhum nos passos seguintes e o teste acima passaria mentindo."""
    assert "TAG" not in (wf["jobs"]["publicar"].get("env") or {})
    assert 'echo "TAG=$tag" >> "$GITHUB_ENV"' in _script_da_recusa(wf)


def test_o_caminho_feliz_nao_mudou(wf):
    """A validação, no sentido do §: o que publicou a v1.0.0 continua igual. Os passos seguintes
    seguem referenciando ${TAG} — nenhum `run:` posterior foi tocado pela CP-032."""
    corridas = [p.get("run", "") for p in wf["jobs"]["publicar"]["steps"][1:]]
    assert 'python ci/mold_release.py --verify-tag "${TAG}"' in corridas
    assert 'git push origin "refs/tags/${TAG}"' in corridas


# --------------------------------------------------------------------------------------
# SISTEMA — a cadeia sobre um repositório git de verdade
# --------------------------------------------------------------------------------------

def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo_publicado(tmp_path: Path, monkeypatch):
    """Monta P → R(manifesto) → tag, como o workflow monta: tudo local, tag por último."""
    repo = tmp_path / "molde"
    (repo / "harness/releases").mkdir(parents=True)
    _git(repo.parent, "init", "--quiet", str(repo))

    (repo / "conteudo.txt").write_text("o que foi validado\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "P")
    parent = _git(repo, "rev-parse", "HEAD")

    manifest = mr.build_manifest(repository="danzeroum/project", tag="v1.0.0", commit_sha=parent,
                                 run_id="42", artifact_digest="sha256:" + "c" * 64,
                                 released_at="2026-08-05T22:00:00+00:00")
    dados = mr.canonical_bytes(manifest)
    (repo / mr.manifest_path_for("v1.0.0")).write_bytes(dados)
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "release(v1.0.0)")
    _git(repo, "tag", "-a", "v1.0.0", "-m", "release v1.0.0")

    monkeypatch.setattr(hl, "REPO", repo)
    return repo, parent, manifest, dados


def test_cadeia_emendada_verde_de_ponta_a_ponta(repo_publicado, capsys):
    """O aceite arbitrado: `manifest.commit_sha` == PRIMEIRO PAI do commit da tag, e o diff
    pai..tag contém só o manifesto. Não há ADR novo para isto porque não há decisão nova — exigir
    que o manifesto contenha o hash do commit que o contém não é escolha de desenho, é impossível.
    """
    repo, parent, manifest, _ = repo_publicado
    assert mr.main(["--verify-tag", "v1.0.0"]) == 0

    commit = _git(repo, "rev-list", "-n", "1", "v1.0.0")
    assert manifest["release"]["commit_sha"] == parent
    assert _git(repo, "rev-list", "--parents", "-n", "1", commit).split()[1] == parent
    assert _git(repo, "diff", "--name-only", f"{parent}..{commit}").splitlines() == [
        "harness/releases/v1.0.0.manifest.json"]


def test_commit_de_release_com_carona_reprova(tmp_path, monkeypatch, capsys):
    """O elo que torna a declaração-do-pai honesta: sem ele, código não validado entraria na
    versão sob a bandeira de uma validação que rodou no pai."""
    repo = tmp_path / "molde"
    (repo / "harness/releases").mkdir(parents=True)
    _git(repo.parent, "init", "--quiet", str(repo))
    (repo / "conteudo.txt").write_text("validado\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "P")
    parent = _git(repo, "rev-parse", "HEAD")

    manifest = mr.build_manifest(repository="o/r", tag="v1.0.0", commit_sha=parent, run_id="1",
                                 artifact_digest="sha256:" + "c" * 64)
    (repo / mr.manifest_path_for("v1.0.0")).write_bytes(mr.canonical_bytes(manifest))
    (repo / "carona.py").write_text("print('nunca validado')\n", encoding="utf-8")  # a carona
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "release + carona")
    _git(repo, "tag", "-a", "v1.0.0", "-m", "r")

    monkeypatch.setattr(hl, "REPO", repo)
    assert mr.main(["--verify-tag", "v1.0.0"]) == 1
    assert "além do manifesto" in capsys.readouterr().err


def test_tag_apontando_para_commit_sem_manifesto_reprova(repo_publicado, capsys):
    """'Tag que aponta para commit sem manifesto não é release parcial — é ausência de release.'"""
    repo, parent, _, _ = repo_publicado
    _git(repo, "tag", "-f", "-a", "v1.0.0", "-m", "movida", parent)
    _git(repo, "checkout", "--quiet", parent)
    assert mr.main(["--verify-tag", "v1.0.0"]) == 1
    assert "manifesto fora da árvore" in capsys.readouterr().err


def test_um_byte_alterado_depois_da_tag_quebra_a_cadeia_no_derivado(repo_publicado):
    """A BORDA do aceite, e ela mora no consumidor — que é onde a decisão (b) a colocou.

    O derivado guarda `manifest_sha` em `target.lock` como âncora INDEPENDENTE. Um byte alterado
    no manifesto depois de consumido produz outro hash, e o elo 3 acusa.
    """
    _, _, manifest, dados = repo_publicado
    lock = {"mold_release": mr.lock_block(repository="danzeroum/project", tag="v1.0.0",
                                          commit_sha=manifest["release"]["commit_sha"],
                                          manifest_bytes=dados)}

    adulterado = dados.replace(b'"run_id": "42"', b'"run_id": "43"')
    assert adulterado != dados

    v = mr.verify_chain(lock=lock, manifest=json.loads(adulterado), manifest_bytes=adulterado,
                        tag_commit_sha="f" * 40, parent_sha=None, changed_paths=None)
    assert any("manifest_sha não confere" in m for m in v)


def test_no_molde_a_ancora_independente_nao_existe_e_isso_e_deliberado(repo_publicado):
    """A honestidade que a decisão (b) exige que fique escrita em teste, não só em prosa.

    `--verify-tag` DERIVA o lock do próprio manifesto — no molde não há onde registrar um
    `manifest_sha` independente, porque não há a quem se ancorar. Os elos lock×manifesto são
    portanto tautológicos aqui, e chamá-los de verificação seria inventar rigor que não existe. O
    que morde no molde é outra coisa: a tag, o pai e o diff.
    """
    _, _, manifest, dados = repo_publicado
    derivado_do_proprio = mr.lock_block(repository=manifest["release"]["repository"],
                                        tag="v1.0.0",
                                        commit_sha=manifest["release"]["commit_sha"],
                                        manifest_bytes=dados)
    assert derivado_do_proprio["manifest_sha"] == mr.manifest_sha(dados)

    fonte = (REPO / "ci/mold_release.py").read_text(encoding="utf-8")
    assert "lock = {\"mold_release\": lock_block(" in fonte


# --------------------------------------------------------------------------------------
# A semântica da árvore taggeada (CP-034 / ADR-026)
# --------------------------------------------------------------------------------------

def test_o_auditar_verifica_a_cadeia_na_tag_e_valida_no_pai(wf):
    """A ordem do ADR-026: `--verify-tag` lê o manifesto do DISCO, então precisa da tag montada;
    `validate_all` é a pergunta certa para o PAI, e roda depois do switch."""
    passos = _passos(wf, "auditar")
    assert _indice(passos, "--verify-tag") < _indice(passos, "git switch --detach")
    assert _indice(passos, "git switch --detach") < _indice(passos, "python ci/validate_all.py")
    assert _indice(passos, "Recusar tag movida") < _indice(passos, "--verify-tag")


def test_o_auditar_recusa_commit_de_release_sem_pai(wf):
    """Sem pai não há árvore validada para auditar — e concluir 'verde' de uma árvore que não se
    olhou é a forma mais barata de mentir."""
    passo = next(p for p in wf["jobs"]["auditar"]["steps"]
                 if p.get("name", "").startswith("Voltar ao commit validado"))
    assert 'if [ -z "$pai" ]' in passo["run"]


def test_o_manifesto_nasce_sem_url_de_repositorio():
    """Cláusula A: não é 'proibido escrever', é que não existe caminho que produza o campo."""
    m = mr.build_manifest(repository="o/r", tag="v9.9.9", commit_sha="a" * 40, run_id="7",
                          artifact_digest="sha256:" + "c" * 64)
    assert "run_url" not in m["release"]["validation"]
    assert "run_url" not in (REPO / "ci/mold_release.py").read_text(encoding="utf-8")
    with pytest.raises(TypeError):
        mr.build_manifest(repository="o/r", tag="v9.9.9", commit_sha="a" * 40, run_id="7",
                          artifact_digest="sha256:" + "c" * 64, run_url="https://x")


def test_o_schema_ainda_aceita_run_url():
    """E é deliberado: o manifesto da v1.0.0 carrega o campo e é registro histórico. Registro que
    se invalida quando a regra muda deixa de ser registro."""
    schema = json.loads((REPO / "harness/schemas/release-manifest.schema.json")
                        .read_text(encoding="utf-8"))
    validation = schema["properties"]["release"]["properties"]["validation"]
    assert "run_url" in validation["properties"]
    assert "run_url" not in validation["required"]


def test_dir_allowlist_acusa_intruso_e_absolve_o_permitido(tmp_path, monkeypatch):
    """A cláusula B, e o tipo que existe porque `path_absent` com glob era uma armadilha."""
    import audit_governance as ag
    import harness_lib as hl2

    (tmp_path / "harness/releases").mkdir(parents=True)
    (tmp_path / "harness/releases/README.md").write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(hl2, "REPO", tmp_path)
    monkeypatch.setattr(ag.hl, "REPO", tmp_path)

    asser = {"id": "T-A1", "kind": "dir_allowlist", "severity": "critical",
             "description": "d", "dir": "harness/releases", "allow": ["README.md"]}

    f, e = hl2.Findings(), hl2.Errors()
    ag.assert_dir_allowlist("ADR-T", asser, f, e)
    assert not f.blocking()

    (tmp_path / "harness/releases/v1.0.0.manifest.json").write_text("{}\n", encoding="utf-8")
    f2, e2 = hl2.Findings(), hl2.Errors()
    ag.assert_dir_allowlist("ADR-T", asser, f2, e2)
    assert f2.blocking()
    assert "v1.0.0.manifest.json" in json.dumps(f2.items, ensure_ascii=False)


def test_dir_allowlist_sem_diretorio_e_indeterminacao_nao_aprovacao(tmp_path, monkeypatch):
    """'Uma trava que não encontra o que vigiar está quebrada, não satisfeita.'"""
    import audit_governance as ag
    import harness_lib as hl2

    monkeypatch.setattr(hl2, "REPO", tmp_path)
    monkeypatch.setattr(ag.hl, "REPO", tmp_path)
    f, e = hl2.Findings(), hl2.Errors()
    ag.assert_dir_allowlist("ADR-T", {"id": "T-A2", "kind": "dir_allowlist", "severity": "high",
                                      "description": "d", "dir": "nao/existe",
                                      "allow": []}, f, e)
    assert f.blocking()


def test_a_mutacao_de_dir_allowlist_poe_algo_no_diretorio():
    """O inverso canônico honesto — e o contraste com o que NÃO se fez.

    Com `path_absent` + glob, a mutação criaria um arquivo chamado literalmente
    `v*.manifest.json`, `rel_exists` o encontraria, e a prova de mutação certificaria uma trava
    que nunca mordeu um manifesto de verdade. Um fiscal de fiscais enganado produz um selo.
    """
    import audit_mutations as am

    m = am.derivar_mutacao({"kind": "dir_allowlist", "dir": "harness/releases",
                            "allow": ["README.md"]})
    assert m["op"] == "criar_caminho"
    assert m["alvo"].startswith("harness/releases/")
    assert not m["alvo"].endswith("README.md")


def test_manifesto_plantado_reprova_por_DOIS_motivos_distintos(repo_copy: Path):
    """A borda que separa decisão dupla de redundância cega.

    Plantado um manifesto com URL de repositório na árvore validada, DUAS travas acusam — e o que
    importa é que elas dizem coisas diferentes: a allowlist reprova por ele ESTAR ALI; o
    ADR-008-A5, por ele CARREGAR a URL. Cada uma pelo seu motivo, com sua mensagem.
    """
    import importlib

    import audit_governance as ag
    import harness_lib as hl2

    alvo = repo_copy / "harness/releases/v9.9.9.manifest.json"
    alvo.write_bytes(mr.canonical_bytes(mr.build_manifest(
        repository="o/r", tag="v9.9.9", commit_sha="a" * 40, run_id="1",
        artifact_digest="sha256:" + "c" * 64)))
    # A URL entra à mão: o caminho que a produzia deixou de existir (cláusula A).
    alvo.write_text(alvo.read_text(encoding="utf-8").replace(
        '"run_id": "1"', '"run_id": "1", "run_url": "https://github.com/o/r/actions/runs/1"'),
        encoding="utf-8")

    hl2.REPO = repo_copy
    ag = importlib.reload(ag)
    ag.hl.REPO = repo_copy

    findings, errors = ag.hl.Findings(), ag.hl.Errors()
    ag.check_adr_conformance(ag.hl.read_yaml("architecture/adr/index.yaml"), findings, errors)

    por_assercao = {f.get("assertion"): f["summary"] for f in findings.items}
    assert "ADR-026-A5" in por_assercao, sorted(k for k in por_assercao if k)
    assert "ADR-008-A5" in por_assercao

    assert "allowlist" in por_assercao["ADR-026-A5"]
    assert "proíbe" in por_assercao["ADR-008-A5"]
    assert por_assercao["ADR-026-A5"] != por_assercao["ADR-008-A5"]


def test_o_adr_registra_a_nota_da_v1_0_0():
    """A v1.0.0 não é re-emitida e não ganha mecanismo de exceção — a nota mora no ADR, porque
    exceção declarada em lista vira lista que cresce."""
    texto = (REPO / "architecture/adr/ADR-026-a-arvore-taggeada-valida-se-pela-cadeia.md"
             ).read_text(encoding="utf-8")
    assert "não é re-emitida" in texto
    assert "5631106937d7" in texto           # a cadeia dela, citada
    assert "exceção" in texto


def test_a_evidencia_nasce_do_validado_e_mergeia_limpa(tmp_path, monkeypatch):
    """A simulação do fluxo inteiro (CP-033), sobre um repositório git de verdade.

    Reproduz a sequência do job `publicar`: valida em P, monta R com o manifesto, tagueia, volta a
    P e só então grava o registro. O que se prova é o que custou um PR manual na v1.0.0 — a branch
    de evidência precisa ser a main MAIS UM COMMIT que muda um arquivo.
    """
    import audit_ledger as al

    repo = tmp_path / "molde"
    (repo / "harness/releases").mkdir(parents=True)
    (repo / "harness/state").mkdir(parents=True)
    (repo / "harness/state/ledger.jsonl").write_text("", encoding="utf-8")
    _git(repo.parent, "init", "--quiet", str(repo))
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "P")
    validado = _git(repo, "rev-parse", "HEAD")

    manifest = mr.build_manifest(repository="o/r", tag="v1.0.0", commit_sha=validado, run_id="1",
                                 artifact_digest="sha256:" + "c" * 64)
    (repo / mr.manifest_path_for("v1.0.0")).write_bytes(mr.canonical_bytes(manifest))
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "release(v1.0.0): manifesto")
    taggeado = _git(repo, "rev-parse", "HEAD")
    _git(repo, "tag", "-a", "v1.0.0", "-m", "r")

    # O passo da CP-033: volta ao VALIDADO antes do append.
    _git(repo, "switch", "--detach", validado)
    monkeypatch.setattr(hl, "REPO", repo)
    monkeypatch.setattr(al.hl, "REPO", repo)
    al.append("release", commit_sha=taggeado, fiscal="ci/mold_release.py",
              artifact_ref="harness/releases/v1.0.0.manifest.json")
    _git(repo, "add", "harness/state/ledger.jsonl")
    _git(repo, "commit", "--quiet", "-m", "release(v1.0.0): registro no ledger")
    evidencia = _git(repo, "rev-parse", "HEAD")

    # VERIFICAÇÃO — o diff da evidência contra a main contém só o ledger.
    assert _git(repo, "diff", "--name-only", f"{validado}..{evidencia}").splitlines() == [
        "harness/state/ledger.jsonl"]
    assert _git(repo, "rev-list", "--parents", "-n", "1", evidencia).split()[1] == validado

    # ...e o registro cita o commit TAGGEADO, que não é seu pai. Citar e descender são coisas
    # diferentes, e confundi-las foi o defeito.
    linha = json.loads((repo / "harness/state/ledger.jsonl").read_text(encoding="utf-8").strip())
    assert linha["commit_sha"] == taggeado != validado

    # VALIDAÇÃO — o merge na main é direto, e não traz o manifesto junto.
    _git(repo, "switch", "--quiet", "--detach", validado)
    _git(repo, "merge", "--no-edit", "--quiet", evidencia)
    assert not (repo / mr.manifest_path_for("v1.0.0")).exists()
    assert _git(repo, "rev-list", "-n", "1", "v1.0.0") == taggeado  # a tag não se mexeu


def test_ledger_registra_a_release_apontando_para_o_commit_taggeado(tmp_path, monkeypatch):
    """Um commit não pode conter o registro de si mesmo — mesma aritmética que fez o manifesto
    declarar o pai. Por isso `--commit-sha` existe: o default (`commit_corrente()`) registraria o
    commit do PRÓPRIO ledger, que não é o que foi publicado."""
    import audit_ledger as al

    repo = tmp_path / "r"
    (repo / "harness/state").mkdir(parents=True)
    (repo / "harness/state/ledger.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(hl, "REPO", repo)
    monkeypatch.setattr(al.hl, "REPO", repo)

    taggeado = "d" * 40
    assert al.main(["--append", "release", "--commit-sha", taggeado,
                    "--fiscal", "ci/mold_release.py", "--run-id", "42",
                    "--artifact-ref", "harness/releases/v1.0.0.manifest.json"]) == 0

    linha = json.loads((repo / "harness/state/ledger.jsonl").read_text(encoding="utf-8").strip())
    assert linha["event"] == "release"
    assert linha["commit_sha"] == taggeado
    assert linha["artifact_ref"] == "harness/releases/v1.0.0.manifest.json"
    assert linha["fiscal"] == "ci/mold_release.py"


def test_linha_de_ledger_fora_do_schema_e_recusada(tmp_path, monkeypatch):
    """A allowlist estrutural continua valendo para o evento novo: `release` não abre porta para
    campo textual livre."""
    import audit_ledger as al

    repo = tmp_path / "r"
    (repo / "harness/state").mkdir(parents=True)
    monkeypatch.setattr(hl, "REPO", repo)
    monkeypatch.setattr(al.hl, "REPO", repo)

    # artifact_ref fora do prefixo canônico: caminho arbitrário carrega nome de diretório, e nome
    # de diretório carrega o que alguém quis chamar de alguma coisa.
    assert al.main(["--append", "release", "--commit-sha", "d" * 40,
                    "--artifact-ref", "/tmp/qualquer/coisa.json"]) == 1
