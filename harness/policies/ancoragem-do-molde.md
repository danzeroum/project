# Ancoragem do molde — o derivado declara de qual versão nasceu

Este repositório fixa três versões, e as três pela mesma razão: **o número mora num lugar só, e
esse lugar é verificável.**

| O que é fixado | Onde mora | Fiscal |
|---|---|---|
| versão da régua (WebQA Suite) | `requirements-qa.txt` | `ci/validate_metadata.py::check_version_single_source` |
| SHA do alvo governado | `target.lock:target_sha` | `ci/validate_metadata.py::check_target_lock` |
| versão do molde de origem | `target.lock:mold_release` | `ci/validate_metadata.py::check_mold_release` |

## As regras

**Derivado exige `mold_release`; molde o proíbe.** Trava de schema nos dois sentidos, para que não
exista "derivado quase ancorado" — estado que dura para sempre porque nenhum fiscal o reprova.

**A âncora é o hash do manifesto, não a tag.** Tag é ponteiro móvel: reescrevê-la faria todo
derivado que a cita afirmar procedência sobre um conteúdo que nunca existiu. `manifest_sha` é o que
transforma isso de evento invisível em falha de CI.

**Manifesto fora da árvore Git é ausência de release.** Release asset é editável depois de
publicado, sem rastro no histórico. Só o que está na árvore do commit é endereçado por hash junto
com o resto.

**Release nasce só de commit validado, e a ref nasce do workflow.** O job `publicar` de
`.github/workflows/release.yml` roda `ci/validate_all.py`, a suíte de fiscais e a prova de mutação
*antes* de a tag existir — o schema do manifesto trava o comando de validação como `const`, para
que afrouxar o significado de "validado" na hora de publicar não passe despercebido. Qualquer passo
vermelho e **nenhuma ref nasce**: não existe release parcial.

**O workflow cria a ref e não a move** (ADR-025). `git push` sem `--force` recusa atualizar uma tag
existente, então o que o workflow assina é *"esta versão nasceu de um commit validado"*. A
afirmação seguinte — *"e continua sendo isto"* — exige ruleset administrado fora daqui. Ele existe
desde 05/08/2026 (`tags-imoveis`: `deletion` + `non_fast_forward` + `update`, bypass vazio), é
auditado de fora todo dia pelo `danzeroum/harness-authority`, e o eixo de tags de
`ci/verify_protection.py` passou a **bloquear** em vez de reportar quando `external_audit.enabled`
virou `true` (CP-036, ADR-028). `RISK-EXT-001` está `mitigated`.

**A janela entre validar e publicar é vazia, não vigiada.** Manifesto emitido, commit de release
montado, tag criada e cadeia verificada — tudo em objetos locais. O `git push` da ref é a única
operação remota, e é a última: o que se publica é byte a byte o que se verificou, porque é o mesmo
objeto Git. `preflight_publicacao` é a segunda tranca, e recusa tag preexistente, `HEAD` movido e
manifesto já na árvore.

**Ancorar não migra.** Apontar para uma versão nova do molde não traz os fiscais dela. Adotar o que
a versão nova acrescenta é trabalho declarado em change-proposal de risco `high` — e o vermelho no
intervalo é o mapa da migração, não defeito.

**Só `/atualizar-carcaca` move a âncora, e ele move só ela.** Não reingere, não avança `target_sha`,
não toca `derived_from` nem `workspace/`. A âncora do molde e a do alvo são perguntas diferentes;
avançar as duas juntas tornaria impossível saber qual causou o vermelho seguinte.

## Qual pergunta se faz a qual árvore

| Árvore | Pergunta certa |
|---|---|
| um commit qualquer, a `main` | `python ci/validate_all.py` |
| a árvore **taggeada** | pai verde · `diff pai..tag` só o manifesto · `--verify-tag` |

A árvore taggeada **não** se valida por `validate_all.py` (ADR-026). Não é afrouxamento: o manifesto
descreve a validação do **pai**, e o elo *"nada além do manifesto"* é o que transporta essa validação
para a árvore publicada. Rodar a validação total na tag sempre foi perguntar a pergunta errada
àquela árvore — e enquanto isso não estava dito, o job de auditoria era incapaz de ficar verde.

`validate_all.py` permanece **puro e cego a refs**. A semântica da tag mora no ADR e no job, nunca
no fiscal: um fiscal que soubesse em qual ref está teria duas respostas para a mesma árvore.

## Onde a verificação é indeterminada

Os elos que dependem de resolver a tag no repositório do molde não rodam dentro de
`validate_all.py`. Sem rede, o estado é **indeterminado** — nem conforme, nem violação. Colapsar os
dois faria "estou offline" e "a tag foi movida" produzirem a mesma cor, e a cor mais barata venceria
por hábito. Por isso `verify_chain` é função pura, alimentada por quem tem a rede.

Fiscalizado por: `ci/validate_metadata.py::check_mold_release`, `ci/validate_metadata.py::check_release_manifests`, `ci/mold_release.py::verify_chain`, `ci/mold_release.py::preflight_publicacao`, `.github/workflows/release.yml`
