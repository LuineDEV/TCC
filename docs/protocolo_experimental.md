# Protocolo experimental do Mail Desk

## Pergunta

Como acrescentar exemplos com categorias confirmadas altera o desempenho do classificador em mensagens que ficaram fora do ajuste? O estudo piloto simula o lote revisado. A mesma estratégia pode ser repetida com revisão humana efetivamente registrada.

## Rotulação

Leia assunto e corpo antes de atribuir uma única categoria. Decida pela finalidade principal da mensagem. Use somente a informação disponível ao destinatário.

| Categoria | Critério | Exemplo e limite |
| --- | --- | --- |
| Urgente | Exige ação em prazo imediato ou muito curto para evitar dano, interrupção, perda de direito ou consequência concreta. | Confirmação de compra suspeita, prazo administrativo crítico. Promoção que termina hoje é Pessoal se ignorá-la não acarreta perda além do desconto. |
| Trabalho | Assunto profissional, acadêmico ou institucional sem urgência nos termos anteriores. | Processo seletivo, orientação, contrato ou comunicado de incidente já resolvido. Um projeto de lazer é Pessoal. |
| Pessoal | Assunto privado, lazer, consumo ou publicidade sem urgência nos termos anteriores. | Convite familiar, encomenda entregue, oferta opcional. Uma emergência familiar é Urgente. |

**Precedência:** primeiro Urgente, inclusive para mensagens profissionais ou pessoais. Sem urgência, use Trabalho para finalidade profissional, acadêmica ou institucional. Use Pessoal para os demais casos do recorte. Marque casos ambíguos no registro de rotulação, justifique a escolha e resolva divergências antes de congelar os rótulos. Uma pasta, um remetente ou a palavra “urgente” por si só não determinam o rótulo de referência.

## Base e separação

O piloto em `data/avaliacao_piloto.csv` tem 48 mensagens sintéticas novas, com remetentes fictícios e nenhuma mensagem de caixa real. São 18 de treino inicial, seis de validação, nove de revisão simulada e 15 de teste. Cada partição tem o mesmo número de exemplos de cada classe. Os rótulos foram definidos na elaboração dos cenários. O conjunto `data/sample_emails.csv` é destinado à demonstração e ao modelo inicial do aplicativo, separado do experimento.

O CSV experimental contém `id,grupo,particao,sender,subject,body,category`. Preserve juntos na mesma partição registros do mesmo encadeamento, campanha ou molde, com o mesmo `grupo`. Verifique também paráfrases e assinaturas repetidas. O avaliador recusa ID repetido, grupo compartilhado entre partições, texto normalizado duplicado e partição sem uma das classes. Esses controles não detectam automaticamente todos os exemplos quase duplicados. Os IDs e o hash SHA-256 documentam quais exemplos foram usados. Em registros reais, use IDs pseudônimos.

Ajuste inicial de vocabulário, IDF e modelo apenas em `treino`. No segundo estágio, ajuste um novo pipeline em `treino + revisao`. A validação diagnóstica usa `validacao` sem ajustá-la ou selecionar hiperparâmetros no piloto. Todas as condições finais usam os mesmos IDs de `teste`. O lote de revisão é um acréscimo, portanto o efeito observado inclui tamanho e composição da base. Uma comparação com outro lote de igual tamanho e política de rotulação controlada ajudaria a isolar a contribuição da revisão.

As regras são fixas dentro de cada comparação. O teste do piloto já foi inspecionado durante o desenvolvimento. Para uma avaliação confirmatória, congele a implementação e o protocolo antes de receber os IDs e rótulos de um novo conjunto de teste. Não use esse conjunto para editar regras, vocabulário ou hiperparâmetros. Registre a origem, o responsável pela rotulação, as divergências e os rótulos alterados do lote de revisão sem inserir o conteúdo dos e-mails em logs.

## Execução

```powershell
python -m email_classifier_app.evaluation data/avaliacao_piloto.csv --output output/monografia/avaliacao_piloto.json
python -m pytest -q
```

O avaliador usa o pré-processamento e o TF-IDF do produto, Regressão Logística com pesos balanceados e Naive Bayes multinomial com suavização padrão. No modo híbrido, a primeira regra válida substitui a saída da Regressão Logística. O relatório traz acurácia, F1 macro, precisão, revocação, F1 e suporte por classe, matriz de confusão (linhas reais e colunas previstas na ordem Urgente, Trabalho e Pessoal), cobertura das regras, origem e comparação por ID. Registra também a versão do Scikit-Learn e o hash da lista de stopwords. Na preparação da avaliação confirmatória, fixe essas dependências e mantenha a mesma lista de termos entre execuções.

## Rodada confirmatória

1. Antes de receber o teste, registre a assinatura do código e do ambiente com o comando abaixo. Arquive a assinatura e este protocolo com data, independentemente dos resultados.
2. Prepare os lotes por grupos. Deixe a seleção e a rotulação do teste sob guarda separada até fixar as configurações. Use exemplos de origem autorizada ou um corpus sintético criado independentemente. Documente a origem de cada lote, quem fez a rotulação e como divergências foram decididas.
3. Para cada exemplo de **revisão**, registre em CSV o ID, o identificador pseudônimo da pessoa revisora, a categoria antes, a categoria confirmada e uma justificativa sem conteúdo privado. Confirme inclusive os exemplos cuja categoria permaneceu igual. O registro deve conter somente os IDs da partição de revisão.
4. Execute uma vez na base inédita com a assinatura e o registro. Compare as mesmas mensagens entre condições, registre ganhos e perdas por classe e examine erros após calcular as métricas. Se houver ajuste posterior, use uma nova partição independente para confirmar o efeito.

Cabeçalho do registro de revisão: `id,reviewer,category_before,category_confirmed,justification`. Mantenha o CSV experimental e o registro em uma pasta local ignorada pelo Git, como `cache/avaliacao/`.

```powershell
python -m email_classifier_app.evaluation --freeze --output output/monografia/assinatura_confirmatoria.json
python -m email_classifier_app.evaluation cache/avaliacao/base.csv --lock output/monografia/assinatura_confirmatoria.json --review-log cache/avaliacao/revisao.csv --output output/monografia/avaliacao_confirmatoria.json
```

A execução verifica o código, o protocolo, as versões do ambiente e a consistência do registro com a partição de revisão. O JSON contém os hashes e os totais de revisões, sem nomes, justificativas ou conteúdo. Os controles técnicos verificam a consistência dos arquivos. A origem dos dados, a participação de quem revisou e a independência da partição precisam ser registradas no procedimento de pesquisa.

## Demonstração funcional

Execute com um armazenamento isolado ou com o pacote portátil. Use **Ações → Carregar exemplos** para criar a base rotulada. Importe `demonstracao_sem_rotulo.csv` por **Ações → Importar CSV**. Abra “Projeto pessoal de pintura”, observe a previsão e selecione Pessoal com **Salvar categoria**. Use **Treinar com rótulos revisados**, execute **Classificar previsões** e confirme a conservação da categoria. Feche e reabra o aplicativo para conferir a persistência. Teste também CSV inválido e reimportação de duplicados em base de demonstração. O teste automatizado utiliza um repositório JSON e modelo temporários, mensagens sintéticas e os manipuladores da interface com chamadas visuais simuladas.

Use a base sintética na defesa. Se houver dados autorizados para pesquisa, retire identificadores do material exibido, restrinja o acesso e defina retenção e descarte antes da coleta. Mantenha o `.env`, a base privada e o modelo privado fora do repositório.

## Evidências de integração

- IMAP real: conexão TLS, pasta somente leitura e coleta de uma mensagem. A flag de leitura foi comparada antes e depois de BODY.PEEK. O conteúdo foi descartado em memória e ficou fora do experimento.
- MySQL 8.0.42: instância local descartável, banco de teste e dados sintéticos. Foram verificados migração de coluna em registro preexistente, importação CSV, deduplicação, busca no corpo, explicação persistida, revisão, reclassificação, reabertura e reutilização do modelo.
- JSON: o fluxo de revisão e reutilização foi testado em armazenamento temporário. Um teste simula escrita interrompida e verifica a preservação do modelo salvo anteriormente.

O painel mostra o padrão acionado pelas regras ou até três termos que favoreceram a previsão estatística em relação à alternativa mais provável. Essa indicação é calculada a partir de pesos TF-IDF e coeficientes do modelo, e armazenada junto da decisão para preservar seu contexto após novos treinamentos.

Na defesa, use somente exemplos sintéticos e revise as capturas antes de compartilhá-las. Restrinja o acesso aos diretórios locais que contêm mensagens, credenciais e modelos, inclusive cópias de segurança. Use uma conta MySQL própria do aplicativo quando possível e configure a proteção do disco conforme o ambiente. TLS protege a comunicação IMAP. Credenciais e dados locais não são criptografados em repouso pelo Mail Desk.
