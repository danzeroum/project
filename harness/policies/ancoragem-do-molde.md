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

**Release nasce só de commit validado.** `.github/workflows/release.yml` roda `ci/validate_all.py`
e a suíte de fiscais *antes* de aceitar a tag, e o schema do manifesto trava o comando de validação
como `const`: afrouxar o significado de "validado" na hora de publicar não passa despercebido.

**Ancorar não migra.** Apontar para uma versão nova do molde não traz os fiscais dela. Adotar o que
a versão nova acrescenta é trabalho declarado em change-proposal de risco `high` — e o vermelho no
intervalo é o mapa da migração, não defeito.

**Só `/atualizar-carcaca` move a âncora, e ele move só ela.** Não reingere, não avança `target_sha`,
não toca `derived_from` nem `workspace/`. A âncora do molde e a do alvo são perguntas diferentes;
avançar as duas juntas tornaria impossível saber qual causou o vermelho seguinte.

## Onde a verificação é indeterminada

Os elos que dependem de resolver a tag no repositório do molde não rodam dentro de
`validate_all.py`. Sem rede, o estado é **indeterminado** — nem conforme, nem violação. Colapsar os
dois faria "estou offline" e "a tag foi movida" produzirem a mesma cor, e a cor mais barata venceria
por hábito. Por isso `verify_chain` é função pura, alimentada por quem tem a rede.

Fiscalizado por: `ci/validate_metadata.py::check_mold_release`, `ci/validate_metadata.py::check_release_manifests`, `ci/mold_release.py::verify_chain`, `.github/workflows/release.yml`
