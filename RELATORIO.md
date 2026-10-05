# Relatório Técnico: Consumo de API e CRUD com Flask

**Disciplina / Laboratório:** Desenvolvimento Web / Consumo de APIs e Arquitetura REST  
**Tecnologias Utilizadas:** Python 3, Flask, SQLite 3, Requests  
**Base de Dados Local:** `countries.db` (SQLite)  

---

### 1. API Escolhida e Justificativa
A API pública escolhida para este laboratório foi a **RestCountries API (v5)** (`https://api.restcountries.com/countries/v5`), acessada via autenticação por token Bearer.  
**Justificativa:** A base de dados de países fornece uma estrutura rica e padronizada de informações geopolíticas e socioeconômicas (nome comum, oficial, códigos ISO Alpha-2 e Alpha-3, capitais, regiões, sub-regiões, população, área territorial, idiomas e moedas). Essa diversidade de atributos torna a base ideal para demonstrar:
1. Modelagem relacional e normalização de dados complexos;
2. Paginação em lotes (*batch retrieval*) na coleta inicial com controle de limites da chave de acesso;
3. Criação de filtros semânticos naturais e práticos (como agrupamentos geográficos e intervalos numéricos contínuos de população).

---

### 2. Modelagem e Armazenamento Local dos Dados
Para atender ao requisito de persistência e garantir que a aplicação opere de forma autônoma após a coleta inicial, foi adotado o **SQLite** como banco de dados local (`countries.db`), dispensando requisições contínuas à API externa.

**Esquema Relacional (`countries`):**
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT): Identificador numérico interno para operações RESTful locais.
- `external_uuid` (TEXT UNIQUE): Identificador único originário da API externa (permite idempotência e atualização via UPSERT).
- `name` (TEXT NOT NULL) e `official_name` (TEXT): Nomes comum e formal do país.
- `alpha2_code` (TEXT) e `alpha3_code` (TEXT): Códigos internacionais ISO 3166-1.
- `capital` (TEXT), `region` (TEXT NOT NULL) e `subregion` (TEXT): Informações geográficas.
- `population` (INTEGER NOT NULL DEFAULT 0) e `area` (REAL DEFAULT 0.0): Métricas quantitativas.
- `languages` (TEXT) e `currencies` (TEXT): Cadeias descritivas de idiomas e moedas.
- `created_at` e `updated_at` (TIMESTAMP): Rastreabilidade temporal dos registros.

**Otimizações:** Foram criados índices B-tree nos campos `region`, `population` e `name` (`CREATE INDEX`), garantindo consultas e ordenações de alta performance nas rotas de CRUD e filtros.

---

### 3. Especificação dos Endpoints Desenvolvidos

Todas as rotas retornam payload em formato **JSON** e operam diretamente sobre o banco de dados SQLite local (com exceção da rota administrativa de sincronização):

| Método | Endpoint | Descrição e Comportamento | Status HTTP |
| :--- | :--- | :--- | :--- |
| **POST** | `/api/countries/sync` | Coleta paginada da API externa e gravação/atualização local no SQLite via UPSERT. | `200 OK` / `502 Bad Gateway` |
| **GET** | `/api/countries` | **Read (Todos):** Lista países locais com suporte a paginação (`?page=1&limit=20`) e busca textual (`?search=bra`). | `200 OK` / `400 Bad Request` |
| **GET** | `/api/countries/<id>` | **Read (Unitário):** Recupera todos os atributos do país correspondente ao ID local. | `200 OK` / `404 Not Found` |
| **POST** | `/api/countries` | **Create:** Cadastra novo país. Valida payload JSON, exigindo campos `name` e `region`. Retorna o registro criado e o cabeçalho `Location`. | `201 Created` / `400 Bad Request` |
| **PUT** | `/api/countries/<id>` | **Update:** Atualiza campos existentes do país com validação estrita de dados numéricos e textuais. | `200 OK` / `400 Bad Request` / `404 Not Found` |
| **DELETE** | `/api/countries/<id>` | **Delete:** Remove o registro correspondente do banco SQLite local. | `200 OK` / `404 Not Found` |
| **GET** | `/api/countries/filter/region` | **Filtro 1 (Região):** Filtra países pela região geográfica informada via query string (`?region=Americas`). | `200 OK` / `400 Bad Request` / `404 Not Found` |
| **GET** | `/api/countries/filter/population` | **Filtro 2 (População):** Filtra países pela faixa populacional via query string (`?min=10000000&max=50000000`). | `200 OK` / `400 Bad Request` / `404 Not Found` |

---

### 4. Tratamento de Erros, Casos de Exceção e Status HTTP
A aplicação implementa manipuladores globais (`@app.errorhandler`) e validações de entrada que garantem respostas JSON padronizadas no formato:
```json
{
  "error": "<Tipo_do_Erro>",
  "message": "<Descrição_Clara_da_Exceção>",
  "status_code": <Código_HTTP>
}
```

- **Falha de Comunicação com a API Externa (Status 502 / 504):** A classe customizada `ExternalAPIError` intercepta quedas de rede (`ConnectionError`), limites de tempo (`Timeout -> 504`), credenciais inválidas (HTTP 401/403) ou instabilidade no provedor upstream (HTTP 5xx), impedindo a quebra da aplicação e retornando mensagem clara ao usuário.
- **Registro Não Encontrado (Status 404):** Disparado em consultas por ID inexistente (`/api/countries/9999`), na tentativa de atualizar ou remover registros inexistentes, ou quando os filtros de região ou faixa populacional não produzem nenhum resultado.
- **Parâmetro Ausente ou Inválido (Status 400):** 
  - Ausência do parâmetro obrigatório `region` ou quando enviado vazio;
  - Ausência de ambos os parâmetros `min` e `max` no filtro de população;
  - Envio de dados alfanuméricos em campos numéricos (`min=abc`);
  - Envio de valores negativos para população ou área;
  - Incoerência lógica onde `min > max` (ex: `min=50000000&max=10000000`);
  - Payload POST sem campos mandatórios (`name` ou `region`).

---

### 5. Aderência aos Princípios da Arquitetura REST
1. **Identificação de Recursos com Substantivos:** Todas as URLs foram desenhadas exclusivamente em torno do substantivo representativo do recurso (`/api/countries`, `/api/countries/<id>`), evitando o uso de verbos nas rotas (como `/getCountries` ou `/saveCountry`).
2. **Uso Semântico dos Verbos HTTP:** Aplicação estrita dos métodos `GET` para operações seguras de leitura, `POST` para criação e sincronização, `PUT` para atualização de estado e `DELETE` para exclusão.
3. **Status HTTP Coerentes:** Retorno de `201 Created` acompanhado do cabeçalho `Location` para inserções, `200 OK` para consultas e mutações bem-sucedidas, `400 Bad Request` para erros do cliente, `404 Not Found` para ausência de recursos e `502 Bad Gateway` para falhas do serviço upstream.
4. **Desacoplamento e Armazenamento Local:** Conforme solicitado na especificação, a aplicação não depende da API externa a cada requisição de cliente; opera de forma autônoma sobre o seu estado local persistente.
