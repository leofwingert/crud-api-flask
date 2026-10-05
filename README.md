# Como Rodar e Testar a API

## 🚀 Como Rodar

```bash
# 1. Ativar o ambiente virtual
source .venv/bin/activate

# 2. Instalar dependências (se necessário)
pip install -r requirements.txt

# 3. Iniciar o servidor
python app.py
```

O servidor estará disponível em: `http://127.0.0.1:5000`

---

## 🧪 Comandos cURL para Testar

### 1. Documentação / Metadados dos Endpoints
```bash
curl -i "http://127.0.0.1:5000/"
```

### 2. Sincronizar com a API Externa (RestCountries)
```bash
curl -i -X POST "http://127.0.0.1:5000/api/countries/sync"
```

---

### 3. CRUD Básico

#### Read All (Listar países locais com paginação ou busca)
```bash
# Listar primeiros 10 países
curl -i "http://127.0.0.1:5000/api/countries?limit=10&page=1"

# Buscar por nome ou capital
curl -i "http://127.0.0.1:5000/api/countries?search=bra"
```

#### Read One (Consultar país por ID)
```bash
# Sucesso (200 OK)
curl -i "http://127.0.0.1:5000/api/countries/1"

# Não encontrado (404 Not Found)
curl -i "http://127.0.0.1:5000/api/countries/99999"
```

#### Create (Cadastrar novo país)
```bash
# Sucesso (201 Created)
curl -i -X POST "http://127.0.0.1:5000/api/countries" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Atlântida",
    "official_name": "Reino de Atlântida",
    "region": "Americas",
    "capital": "Poseidonis",
    "population": 250000,
    "area": 45000.0,
    "alpha2_code": "AT",
    "alpha3_code": "ATL"
  }'

# Erro de validação - falta 'name' (400 Bad Request)
curl -i -X POST "http://127.0.0.1:5000/api/countries" \
  -H "Content-Type: application/json" \
  -d '{"region": "Americas"}'
```

#### Update (Atualizar país existente)
```bash
# Sucesso (200 OK)
curl -i -X PUT "http://127.0.0.1:5000/api/countries/1" \
  -H "Content-Type: application/json" \
  -d '{"capital": "Nova Capital", "population": 300000}'

# Não encontrado (404 Not Found)
curl -i -X PUT "http://127.0.0.1:5000/api/countries/99999" \
  -H "Content-Type: application/json" \
  -d '{"capital": "Desconhecida"}'
```

#### Delete (Remover país por ID)
```bash
# Sucesso (200 OK)
curl -i -X DELETE "http://127.0.0.1:5000/api/countries/255"

# Não encontrado (404 Not Found)
curl -i -X DELETE "http://127.0.0.1:5000/api/countries/99999"
```

---

### 4. Endpoints Específicos de Filtro

#### Filtro 1: Região Geográfica
```bash
# Sucesso (200 OK)
curl -i "http://127.0.0.1:5000/api/countries/filter/region?region=Americas"

# Parâmetro ausente (400 Bad Request)
curl -i "http://127.0.0.1:5000/api/countries/filter/region"

# Região inexistente (404 Not Found)
curl -i "http://127.0.0.1:5000/api/countries/filter/region?region=Inexistente123"
```

#### Filtro 2: Faixa Populacional (Min / Max)
```bash
# Sucesso (200 OK - entre 10 e 50 milhões)
curl -i "http://127.0.0.1:5000/api/countries/filter/population?min=10000000&max=50000000"

# Somente mínimo (200 OK - acima de 100 milhões)
curl -i "http://127.0.0.1:5000/api/countries/filter/population?min=100000000"

# Parâmetros ausentes (400 Bad Request)
curl -i "http://127.0.0.1:5000/api/countries/filter/population"

# Min maior que Max (400 Bad Request)
curl -i "http://127.0.0.1:5000/api/countries/filter/population?min=50000000&max=10000000"

# Faixa sem resultados (404 Not Found)
curl -i "http://127.0.0.1:5000/api/countries/filter/population?min=9999999999"
```
