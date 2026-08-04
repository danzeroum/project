# ADR-009 — Código sem metadado não existe, e ignorância de linguagem é declarada

- **Status:** accepted
- **Data:** 2026-08-04
- **Riscos relacionados:** RISK-INGEST-001, RISK-DERIV-002

## Contexto

Até aqui todos os fiscais verificavam uma direção só. `check_capabilities` pergunta se o
`source_path` declarado aponta para arquivo real. `check_components` pergunta se o `tested_by`
existe. As asserções do ADR-005 perguntam se o import proibido apareceu. Nenhuma pergunta a
inversa: **esse arquivo de código é reivindicado por algum metadado?**

Com uma direção só, um arquivo novo entra e passa. Sem erro, sem aviso, e o repositório segue
verde afirmando a rastreabilidade capacidade → componente → código → teste que aquele arquivo
nunca teve. É o modo de falha do ADR-002 — o que ninguém verifica dura para sempre — do lado de
fora do metadado, e ele piora exatamente onde deveria melhorar: num derivado que governa um alvo
grande e em evolução, onde arquivos aparecem mais rápido do que alguém os declara.

O segundo problema é de alcance. Um molde que só sabe ler Python fiscaliza alvos em Python e
**passa verde** nos demais — não porque estejam conformes, mas porque o fiscal percorreu um
conjunto vazio. Verde por vacuidade é indistinguível de verde por cobertura, que é a definição do
`assertion_unresolvable` do ADR-006 aplicada ao inventário.

## Decisão

**1. Todo arquivo sob as raízes de código tem exatamente um dono.** Pertence a `source_paths` de
um `CMP-*`, ou a uma isenção justificada em `architecture/components.yaml:exemptions`. Isenção que
não casa arquivo algum é achado, como em `stages.yaml:ungoverned`. **Dois donos também reprovam**:
quando o arquivo mudar, cada time achará que o outro revisou.

**2. Três invariantes irmãs.** Teste fora de `tested_by`/`test_paths`/`validated_by` é órfão;
import entre componentes fora de `depends_on` é acoplamento não registrado; `exposes` que o código
não define é promessa vazia.

**3. Import não declarado acusa; `depends_on` sobrando avisa.** A assimetria é deliberada.
`depends_on` sem import pode ser dependência legítima que o adapter não enxerga — reprovar aí
criaria pressão para apagar declarações verdadeiras só para o CI passar.

**4. As raízes são declaradas, nunca convencionadas.** O prefixo `src/` deixa de ser literal
dentro do fiscal e passa a vir de `project.yaml`. Não é afrouxamento: convenção cravada no fiscal
é a forma mais discreta de tornar o molde específico de um alvo, e sem essa mudança o metadado de
um derivado — que aponta para `workspace/target/` — não valida no CI que deveria protegê-lo.

**5. Adapters são plugins, e ignorância é declarada.** Acrescentar linguagem escreve um módulo em
`ci/adapters/`, não um `elif`. O adapter genérico casa qualquer extensão e resolve **pertencimento**
— que é o que a invariante precisa e que não depende de entender a linguagem. O que ele não leu
entra no laudo em `nao_lido`. O silêncio é que está proibido, não a ignorância.

**5b. Todo especificador cai em exatamente um balde, e a conta é verificada.** Resolvido,
externo ou `unresolved` — e `ci/inventory_code.py` recusa o inventário quando
`resolvidos + externos + unresolved ≠ total`, com exit 2. Medido num alvo real: o adapter de TS
cumpria "nunca inventar aresta" e quebrava "declarar o que não leu" — 84 arestas entre pacotes de
um monorepo sumiam sem entrar em lugar nenhum, e `check_declared_dependencies` validava
`depends_on` contra conjunto vazio. Verde por vacuidade, no formato de repositório mais provável
de alvo real. A aritmética é a trava porque o modo de falha não é resolver errado: é engolir, e
nenhum teste de caso específico pega o próximo caminho de código que engolir.

**5c. Alias de workspace resolve pelos `package.json`, não por `tsconfig:paths`.** O alvo medido
não declara `paths` algum — a resolução vem do link do gerenciador de pacotes, e o registro de
verdade é o `name` de cada `package.json`. Quando o entrypoint declarado aponta para build
inexistente (`./dist/index.js` num clone fresco), o adapter mapeia o nome de volta para a fonte
antes de desistir; desistir ali faria toda aresta entre pacotes virar `unresolved` — tecnicamente
honesto e praticamente inútil.

**6. Raiz declarada ausente é exit 2, não achado.** "O fiscal não conseguiu fiscalizar" é uma
resposta diferente de "está tudo certo", e confundi-las é o que produz verde por vacuidade.

## Consequências

- Coisas que ontem passavam reprovam hoje. Neste próprio repositório,
  `src/project/__init__.py` passa a exigir isenção declarada com justificativa em vez de silêncio.
  É o custo pretendido: a pendência sai do implícito.
- Um alvo em linguagem sem leitor semântico é governável desde o primeiro dia quanto a
  pertencimento, e o laudo diz o que ficou por fazer em vez de omitir.
- O adapter de TypeScript é parser próprio de imports, não `dependency-cruiser`: este molde é
  Python puro, e adotá-lo faria a fiscalização de **qualquer** alvo passar a exigir toolchain de
  Node. A troca é uma decisão futura legítima — tomá-la em silêncio, não.
- Custo assumido: o inventário percorre o alvo inteiro a cada validação. Memoizado por processo,
  e o `parse_module` de `harness_lib` já é cacheado por mtime — mas num alvo muito grande isto
  deixa de ser barato, e a resposta certa será cache por SHA do lock, não afrouxar o fiscal.

## Fiscal

`ci/inventory_code.py` (inventário multi-linguagem; raiz ausente ⇒ exit 2);
`ci/adapters/` (registro de plugins);
`ci/validate_metadata.py::check_orphan_code`, `::check_orphan_tests`,
`::check_declared_dependencies`, `::check_exposes`;
`harness/schemas/components.schema.json` (`exemptions` com `justification` obrigatória);
`harness/policies/code-metadata.md`; `.github/workflows/governance.yml`.
