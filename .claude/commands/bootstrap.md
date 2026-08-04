---
description: Leva este repositório de um clone cru a um estado conhecido, e diz o próximo passo.
---

# /bootstrap

```bash
python ci/bootstrap.py
```

Idempotente. Rodar de novo com o workspace já no SHA certo custa um fetch e nada mais — é o que
permite chamá-lo em toda sessão nova sem pensar duas vezes.

## O que ele faz, nesta ordem

1. **ambiente** — python 3.11+, git, e que este diretório é mesmo o repositório;
2. **dependências** — instala `.[dev]` só se faltar;
3. **papel** — lê `project.yaml` e `target.lock`. Se discordarem sobre `kind`, para: o papel do
   repositório não pode depender de qual arquivo se lê primeiro;
4. **workspace** — só no derivado: clone raso do alvo e checkout no SHA de `target.lock`;
5. **validação** — `ci/validate_all.py`;
6. **laudo** — `harness/state/bootstrap.json`, validado contra o próprio schema antes de gravado.

Saída: `0` pronto · `1` os fiscais acharam divergência · `2` não deu para levantar o ambiente.

## Drift

```bash
python ci/bootstrap.py --check-drift
```

Compara `target.lock` com o remoto de `target.ref` e **reporta**, sem corrigir. Avançar o lock é
decisão declarada em change-proposal, nunca efeito colateral de um bootstrap: o metadado descreve
o alvo *naquele* commit, e movê-lo sem revisar o metadado troca um drift visível por um metadado
errado — que é estritamente pior.

## Se ele falhar

Leia a mensagem antes de agir. As três causas comuns:

- **`kind` divergente** entre `project.yaml` e `target.lock` → alguém editou um e esqueceu o outro;
- **derivado sem `target_sha`** → o `/adotar` não terminou de ancorar;
- **fetch do SHA recusado** → o alvo saiu do escopo da sessão (`add_repo`) ou o commit sumiu do
  remoto por force-push.

Nenhuma delas se resolve editando um fiscal.
