# Mapa do projeto TCC — Mail Desk

Análise do código e do relatório de acompanhamento de Luis Felipe Costa Pedro, realizada em 28/10/2026. O relatório foi usado como referência histórica; suas próximas etapas não foram tratadas como autorização para implementar novas funcionalidades.

## Objetivo e fluxo

Aplicativo desktop Python para organizar e-mails localmente em **Urgente**, **Trabalho** e **Pessoal**. Não utiliza IA generativa nem requer API de classificação.

IMAP, CSV ou Gmail aberto no Chrome → registros → captura/OCR quando coletado por RPA → regras de classificação → TF-IDF e Regressão Logística quando nenhuma regra atende → MySQL ou JSON → interface → correção manual → treinamento explícito.

## Funcionalidades e localização

Atualização IMAP (28/10/2026): `imap_importer.py` coleta mensagens via TLS/readonly e MIME; `imap_dialog.py` oferece conexão local, importação e cancelamento. `source_key` identifica a mensagem por conta/pasta/UIDVALIDITY/UID e `category_source` separa rótulos revisados/importados de previsões. Treinar usa apenas manual/imported; Classificar preserva esses rótulos. As observações anteriores sobre sobrescrever categorias e treinar com previsões foram resolvidas para os novos registros. Registros anteriores recebem origem legacy e exigem revisão antes do treino. Gmail por tela permanece como caminho legado.

| Recurso | Implementação | Observações |
| --- | --- | --- |
| Inicialização desktop | `email_classifier_app/main.py`, `app.py` | CustomTkinter; lista central e leitor lateral |
| Importação CSV e exemplos | `importer.py`, `app.py` | `subject` e `body` obrigatórios; remetente, categoria e data opcionais; evita duplicados por remetente, assunto e início do corpo |
| Gmail por RPA | `desktop_rpa.py`, `gmail_rpa.py` | Até dez mensagens da primeira página; Chrome autenticado, maximizado, zoom 100%, tela mínima 1280×720; coleta em thread e atualizações por fila |
| Capturas longas | `visual_capture.py` | Rolagem, comparação entre quadros, composição com sobreposição e limites de segurança |
| OCR local | `ocr.py` | RapidOCR carregado sob demanda; recuperação textual de imagens |
| Preparação textual | `nlp.py`, `model.py` | Limpeza, normalização e composição; remetente duplicado e assunto triplicado |
| Classificação híbrida | `model.py` | Regras precedem o modelo; a confiança das regras é fixa e não representa probabilidade calibrada |
| Treinamento | `model.py`, `app.py` | Mínimo seis registros e duas categorias; validação estratificada quando possível; modelo Joblib reutilizado na próxima execução |
| Revisão manual | `app.py` | Categorias revisadas são elegíveis para treinamento e preservadas ao reclassificar |
| Busca e filtros | `app.py` | Categoria, contadores e busca textual; 40 mensagens por página; a busca considera o corpo completo |
| Leitura | `reader_presenter.py`, `app.py` | Imagem, texto extraído, data, remetente, categoria e confiança |
| Persistência | `database.py`, `config.py` | MySQL configurado por `.env`; fallback JSON quando conexão falha; migrações de colunas de captura |
| Limpeza local | `database.py`, `app.py` | Remove mensagens e capturas autorizadas dentro da pasta de capturas; preserva modelo e logs |

## Dados locais

- `data/sample_emails.csv`: exemplos para demonstração e primeiro treino.
- `models/email_classifier.joblib`: modelo persistido.
- `cache/emails_cache.json`: mensagens e logs no modo demonstração.
- `cache/email_images/`: capturas das mensagens.
- `.env`: configuração privada do MySQL; não versionada.
- `.venv/`: ambiente Python local; não versionado.

## Correções desta análise

- O modelo final agora aprende com todos os registros após medir o desempenho na divisão de validação. Antes, os exemplos de validação ficavam fora do modelo salvo, apesar de serem contados como usados.
- Falha ao ajustar um novo modelo preserva o pipeline anterior na memória.
- Campos vazios do CSV deixam de virar o texto `nan`; espaços externos da categoria são removidos e categorias desconhecidas seguem para classificação automática.
- Cache JSON passa a ser gravado em arquivo temporário e substituído atomicamente, reduzindo o risco de truncamento em caso de interrupção.

## Pendências e limites conhecidos

1. Preservar o estado lido/não lido no Gmail; a coleta atual pode marcar mensagens como lidas.
2. Validar RPA em Gmail real: coordenadas, anúncios, idiomas, resoluções e seleção visual. A versão atual já captura antes de copiar o texto; isso exige confirmação visual.
3. Comparar Regressão Logística, Naive Bayes e estratégia híbrida sobre base rotulada independente; apresentar precisão, recall, F1 e matriz de confusão.
4. Exibir termos que explicam a decisão e distinguir regra de inferência estatística.
5. Avaliar migração para SQLite conforme orientação registrada no PDF.
6. Melhorar recuperação de cache já corrompido e relato de importação parcialmente salva; a gravação atômica previne novas interrupções, mas não repara arquivos danificados anteriormente.

As métricas atuais medem o pipeline estatístico na divisão interna, sem avaliar as regras nem constituir um experimento independente do TCC.

## Verificação histórica em 28/10/2026

- 30 testes automatizados passaram, sem avisos na execução final.
- Teste da interface com armazenamento temporário: importação de 48 exemplos, rejeição de duplicados, abertura do leitor e filtro Trabalho aprovados. Dados desse teste não foram inseridos na base de uso.
- Aplicativo iniciado, janela `Organizador de E-mails` respondendo, modelo inicial gerado e nenhum erro registrado na saída de inicialização.
- `pip check` não encontrou dependências incompatíveis; `git diff --check` passou.
- Gmail real, OCR com imagens reais e MySQL não foram validados nesta sessão. A cobertura automatizada desses módulos usa simulações.
- A primeira importação das bibliotecas científicas foi lenta neste computador; a repetição da suíte completa levou aproximadamente 11 segundos.

## Execução no Windows

```powershell
.\.venv\Scripts\python.exe -m email_classifier_app.main
```

Sem MySQL disponível, o modo demonstração usa armazenamento JSON local. Para verificar as unidades automatizadas:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
