# Cartola Scout (MVP)
Um projeto em **Python + Streamlit** para:
- Coletar dados do **Cartola FC** (mercado, partidas e parciais quando disponíveis)
- Manter histórico em **SQLite**
- Estimar tendência de **valorização** (heurística) e sugerir um **time** por formação e orçamento

> ⚠️ Observação: a API do Cartola não é oficialmente documentada e pode mudar. Este projeto foi feito para ser **tolerante** a pequenas mudanças (campos ausentes, payloads alternativos).

---

## 1) Rodar localmente

### Requisitos
- Python 3.11+ (recomendado)
- Windows / Linux / macOS

### Instalação
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
# source .venv/bin/activate

pip install -r requirements.txt
```

### Rodar o app
```bash
streamlit run app/app.py
```

---

## 2) Como funciona

### Coleta de dados
O app consulta:
- `/mercado/status`  -> rodada e se mercado está aberto
- `/atletas/mercado` -> atletas, preço, status, scouts, média etc.
- `/partidas`        -> jogos da rodada (mando)
- `/atletas/pontuados` -> parciais (quando disponível)

E salva snapshots por rodada em SQLite em `data/cartola.db`.

### Sugestão de time
- Filtra atletas por **status** (por padrão: apenas prováveis `status_id=7`)
- Calcula um **score** simples (pontos esperados + bônus de valorização)
- Monta um time respeitando:
  - orçamento
  - formação (ex.: 4-3-3)
  - posições (GOL, ZAG, LAT, MEI, ATA, TEC)

> Para ficar mais “inteligente”, você pode melhorar o `analytics.py` (ex.: usar histórico real para treinar um modelo).

---

## 3) Deploy (colocar “no ar”)

### Opção A: Streamlit Community Cloud (grátis para repo público)
1. Suba esse projeto para um repositório no GitHub.
2. No Streamlit Community Cloud, selecione o repositório.
3. Escolha o arquivo **entrypoint**: `app/app.py`
4. Confirme que o `requirements.txt` está na raiz.

Docs:
- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy

### Opção B: Railway (template Streamlit)
- Railway tem template pronto para Streamlit.

---

## 4) Estrutura de pastas
```
cartola-scout/
  app/
    app.py
  cartola/
    client.py
    storage.py
    analytics.py
    team_builder.py
    utils.py
  data/               # criado em runtime
  requirements.txt
```

---

## 5) Próximos upgrades (recomendado)
- Implementar **otimização** (ILP) para maximizar score sob restrições
- Armazenar histórico por atleta e aprender a prever `delta_preco`
- Criar webhook/Telegram para enviar time sugerido quando mercado abre
