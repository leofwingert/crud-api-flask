import os
from flask import Flask, jsonify, request
from database import get_db, init_db, row_to_dict
from services import sync_countries_to_db, ExternalAPIError

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

with app.app_context():
    init_db()
    # Verifica se o banco local possui registros; se estiver vazio, tenta sincronizar
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as total FROM countries;")
    count = cur.fetchone()["total"]
    conn.close()

    if count == 0:
        print("[INFO] Banco de dados local vazio. Executando sincronização inicial com a API externa...")
        try:
            sync_countries_to_db()
            print("[INFO] Sincronização inicial concluída com sucesso.")
        except Exception as e:
            print(f"[AVISO] Não foi possível sincronizar na inicialização: {e}")



@app.errorhandler(400)
def bad_request(error):
    message = getattr(error, "description", "Requisição inválida.")
    return jsonify({
        "error": "Bad Request",
        "message": message,
        "status_code": 400
    }), 400


@app.errorhandler(404)
def not_found(error):
    message = getattr(error, "description", "Recurso não encontrado.")
    return jsonify({
        "error": "Not Found",
        "message": message,
        "status_code": 404
    }), 404


@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({
        "error": "Method Not Allowed",
        "message": f"O método {request.method} não é permitido para esta rota.",
        "status_code": 405
    }), 405


@app.errorhandler(ExternalAPIError)
def handle_external_api_error(error):
    return jsonify({
        "error": "Bad Gateway",
        "message": f"Falha na comunicação com a API externa na etapa de coleta: {error.message}",
        "status_code": error.status_code
    }), error.status_code


@app.errorhandler(500)
def internal_server_error(error):
    return jsonify({
        "error": "Internal Server Error",
        "message": "Ocorreu um erro interno no servidor.",
        "status_code": 500
    }), 500


@app.route("/api/countries/sync", methods=["POST"])
def sync_countries():
    """
    Consome os dados da API restcountries.com e armazena localmente no SQLite.
    Trata falhas de comunicação com status 502/504 através de ExternalAPIError.
    """
    result = sync_countries_to_db()
    return jsonify({
        "status": "success",
        "message": "Dados sincronizados com sucesso a partir da API externa restcountries.com.",
        "synced_count": result["synced_count"],
        "total_local": result["total_local"]
    }), 200


# 1. READ ALL - Listar países locais com paginação opcional
@app.route("/api/countries", methods=["GET"])
def get_all_countries():
    """
    Retorna a lista de países armazenados no banco local.
    Parâmetros opcionais:
      - page (int, padrão 1)
      - limit (int, padrão 50; se for 'all', retorna todos)
      - search (string para filtrar por nome ou capital)
    """
    page_param = request.args.get("page", 1)
    limit_param = request.args.get("limit", 50)
    search_param = request.args.get("search", "").strip()

    conn = get_db()
    cursor = conn.cursor()

    # Validação de paginação
    try:
        page = int(page_param)
        if page < 1:
            page = 1
    except ValueError:
        conn.close()
        return jsonify({
            "error": "Bad Request",
            "message": "O parâmetro 'page' deve ser um número inteiro positivo.",
            "status_code": 400
        }), 400

    where_clause = ""
    params = []

    if search_param:
        where_clause = "WHERE name LIKE ? OR official_name LIKE ? OR capital LIKE ?"
        query_pattern = f"%{search_param}%"
        params.extend([query_pattern, query_pattern, query_pattern])

    # Contagem total
    count_sql = f"SELECT COUNT(*) as total FROM countries {where_clause}"
    cursor.execute(count_sql, params)
    total_records = cursor.fetchone()["total"]

    if str(limit_param).lower() == "all":
        select_sql = f"SELECT * FROM countries {where_clause} ORDER BY name ASC"
        cursor.execute(select_sql, params)
        limit = total_records
        offset = 0
    else:
        try:
            limit = int(limit_param)
            if limit < 1:
                limit = 50
        except ValueError:
            conn.close()
            return jsonify({
                "error": "Bad Request",
                "message": "O parâmetro 'limit' deve ser um número inteiro positivo ou 'all'.",
                "status_code": 400
            }), 400

        offset = (page - 1) * limit
        select_sql = f"SELECT * FROM countries {where_clause} ORDER BY name ASC LIMIT ? OFFSET ?"
        cursor.execute(select_sql, params + [limit, offset])

    rows = cursor.fetchall()
    countries = [row_to_dict(r) for r in rows]
    conn.close()

    return jsonify({
        "status": "success",
        "total": total_records,
        "page": page,
        "limit": limit,
        "count": len(countries),
        "data": countries
    }), 200


# 2. READ ONE - Obter detalhes de um país por ID
@app.route("/api/countries/<int:country_id>", methods=["GET"])
def get_country_by_id(country_id):
    """Retorna os dados de um país específico a partir do seu ID local."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM countries WHERE id = ?", (country_id,))
    row = cursor.fetchone()
    conn.close()

    if row is None:
        return jsonify({
            "error": "Not Found",
            "message": f"País com ID {country_id} não foi encontrado no banco de dados local.",
            "status_code": 404
        }), 404

    return jsonify({
        "status": "success",
        "data": row_to_dict(row)
    }), 200


# 3. CREATE - Cadastrar novo país
@app.route("/api/countries", methods=["POST"])
def create_country():
    """
    Cadastra um novo país no banco local.
    Exige payload JSON com pelo menos 'name' e 'region'.
    """
    if not request.is_json:
        return jsonify({
            "error": "Bad Request",
            "message": "O corpo da requisição deve ser um JSON válido com cabeçalho 'Content-Type: application/json'.",
            "status_code": 400
        }), 400

    data = request.get_json()
    if not isinstance(data, dict):
        return jsonify({
            "error": "Bad Request",
            "message": "O payload JSON deve ser um objeto.",
            "status_code": 400
        }), 400

    # Validação de campos obrigatórios
    name = data.get("name", "").strip() if isinstance(data.get("name"), str) else ""
    region = data.get("region", "").strip() if isinstance(data.get("region"), str) else ""

    if not name:
        return jsonify({
            "error": "Bad Request",
            "message": "O campo 'name' é obrigatório e não pode ser vazio.",
            "status_code": 400
        }), 400

    if not region:
        return jsonify({
            "error": "Bad Request",
            "message": "O campo 'region' é obrigatório e não pode ser vazio.",
            "status_code": 400
        }), 400

    # Validação de tipos numéricos
    population = data.get("population", 0)
    try:
        population = int(population)
        if population < 0:
            return jsonify({
                "error": "Bad Request",
                "message": "O campo 'population' deve ser um número inteiro maior ou igual a zero.",
                "status_code": 400
            }), 400
    except (ValueError, TypeError):
        return jsonify({
            "error": "Bad Request",
            "message": "O campo 'population' deve ser um valor numérico inteiro válido.",
            "status_code": 400
        }), 400

    area = data.get("area", 0.0)
    try:
        area = float(area)
        if area < 0:
            return jsonify({
                "error": "Bad Request",
                "message": "O campo 'area' deve ser um número maior ou igual a zero.",
                "status_code": 400
            }), 400
    except (ValueError, TypeError):
        return jsonify({
            "error": "Bad Request",
            "message": "O campo 'area' deve ser um número válido.",
            "status_code": 400
        }), 400

    official_name = str(data.get("official_name", "") or "")
    alpha2_code = str(data.get("alpha2_code", "") or "").upper()
    alpha3_code = str(data.get("alpha3_code", "") or "").upper()
    capital = str(data.get("capital", "") or "")
    subregion = str(data.get("subregion", "") or "")
    languages = str(data.get("languages", "") or "")
    currencies = str(data.get("currencies", "") or "")
    external_uuid = str(data.get("external_uuid", "") or None) if data.get("external_uuid") else None

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO countries (
            external_uuid, name, official_name, alpha2_code, alpha3_code,
            capital, region, subregion, population, area, languages, currencies
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            external_uuid, name, official_name, alpha2_code, alpha3_code,
            capital, region, subregion, population, area, languages, currencies
        )
    )
    conn.commit()
    new_id = cursor.lastrowid

    cursor.execute("SELECT * FROM countries WHERE id = ?", (new_id,))
    new_record = row_to_dict(cursor.fetchone())
    conn.close()

    response = jsonify({
        "status": "success",
        "message": "País cadastrado com sucesso no banco de dados local.",
        "data": new_record
    })
    response.status_code = 201
    response.headers["Location"] = f"/api/countries/{new_id}"
    return response


# 4. UPDATE - Atualizar dados de um país
@app.route("/api/countries/<int:country_id>", methods=["PUT", "PATCH"])
def update_country(country_id):
    """
    Atualiza um país existente no banco de dados local.
    Aceita atualização total ou parcial dos campos.
    """
    if not request.is_json:
        return jsonify({
            "error": "Bad Request",
            "message": "O corpo da requisição deve ser um JSON válido com cabeçalho 'Content-Type: application/json'.",
            "status_code": 400
        }), 400

    data = request.get_json()
    if not isinstance(data, dict) or len(data) == 0:
        return jsonify({
            "error": "Bad Request",
            "message": "Forneça os campos a serem atualizados no objeto JSON.",
            "status_code": 400
        }), 400

    conn = get_db()
    cursor = conn.cursor()

    # Verifica existência do país
    cursor.execute("SELECT * FROM countries WHERE id = ?", (country_id,))
    existing = cursor.fetchone()
    if existing is None:
        conn.close()
        return jsonify({
            "error": "Not Found",
            "message": f"País com ID {country_id} não foi encontrado para atualização.",
            "status_code": 404
        }), 404

    # Mapeamento de campos atualizáveis
    allowed_fields = [
        "name", "official_name", "alpha2_code", "alpha3_code",
        "capital", "region", "subregion", "population", "area",
        "languages", "currencies"
    ]

    updates = []
    values = []

    for field in allowed_fields:
        if field in data:
            val = data[field]
            if field == "population":
                try:
                    val = int(val)
                    if val < 0:
                        conn.close()
                        return jsonify({
                            "error": "Bad Request",
                            "message": "O campo 'population' deve ser um número inteiro >= 0.",
                            "status_code": 400
                        }), 400
                except (ValueError, TypeError):
                    conn.close()
                    return jsonify({
                        "error": "Bad Request",
                        "message": "O campo 'population' deve ser um inteiro válido.",
                        "status_code": 400
                    }), 400
            elif field == "area":
                try:
                    val = float(val)
                    if val < 0:
                        conn.close()
                        return jsonify({
                            "error": "Bad Request",
                            "message": "O campo 'area' deve ser um número >= 0.",
                            "status_code": 400
                        }), 400
                except (ValueError, TypeError):
                    conn.close()
                    return jsonify({
                        "error": "Bad Request",
                        "message": "O campo 'area' deve ser um número válido.",
                        "status_code": 400
                    }), 400
            elif field in ("name", "region") and (not isinstance(val, str) or not val.strip()):
                conn.close()
                return jsonify({
                    "error": "Bad Request",
                    "message": f"O campo '{field}' não pode ser vazio.",
                    "status_code": 400
                }), 400

            updates.append(f"{field} = ?")
            values.append(val)

    if not updates:
        conn.close()
        return jsonify({
            "error": "Bad Request",
            "message": "Nenhum campo válido fornecido para atualização.",
            "status_code": 400
        }), 400

    updates.append("updated_at = CURRENT_TIMESTAMP")
    sql = f"UPDATE countries SET {', '.join(updates)} WHERE id = ?"
    values.append(country_id)

    cursor.execute(sql, values)
    conn.commit()

    cursor.execute("SELECT * FROM countries WHERE id = ?", (country_id,))
    updated_record = row_to_dict(cursor.fetchone())
    conn.close()

    return jsonify({
        "status": "success",
        "message": f"País com ID {country_id} atualizado com sucesso.",
        "data": updated_record
    }), 200


# 5. DELETE - Remover um país do banco local
@app.route("/api/countries/<int:country_id>", methods=["DELETE"])
def delete_country(country_id):
    """Remove um país específico do banco de dados local através do ID."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM countries WHERE id = ?", (country_id,))
    row = cursor.fetchone()
    if row is None:
        conn.close()
        return jsonify({
            "error": "Not Found",
            "message": f"País com ID {country_id} não foi encontrado para exclusão.",
            "status_code": 404
        }), 404

    country_name = row["name"]
    cursor.execute("DELETE FROM countries WHERE id = ?", (country_id,))
    conn.commit()
    conn.close()

    return jsonify({
        "status": "success",
        "message": f"País '{country_name}' (ID {country_id}) foi removido com sucesso do banco de dados local."
    }), 200


# FILTRO 1: Filtrar por Região / Continente
@app.route("/api/countries/filter/region", methods=["GET"])
def filter_by_region():
    """
    Endpoint de Filtro 1: Retorna países pertencentes a uma região geográfica informada.
    Parâmetro obrigatório via query string: 'region' (ex: ?region=Americas)
    """
    region = request.args.get("region")

    # Tratamento de parâmetro ausente ou em branco
    if region is None or not region.strip():
        return jsonify({
            "error": "Bad Request",
            "message": "O parâmetro de consulta 'region' é obrigatório. Exemplo: /api/countries/filter/region?region=Americas",
            "status_code": 400
        }), 400

    region = region.strip()

    conn = get_db()
    cursor = conn.cursor()

    # Busca insensível a maiúsculas/minúsculas
    cursor.execute(
        "SELECT * FROM countries WHERE LOWER(region) = LOWER(?) ORDER BY name ASC",
        (region,)
    )
    rows = cursor.fetchall()
    conn.close()

    # Tratamento para registro não encontrado
    if not rows:
        return jsonify({
            "error": "Not Found",
            "message": f"Nenhum país encontrado para a região informada: '{region}'. Regiões comuns incluem: Americas, Europe, Asia, Africa, Oceania.",
            "status_code": 404
        }), 404

    countries = [row_to_dict(r) for r in rows]

    return jsonify({
        "status": "success",
        "filter": "region",
        "value": region,
        "count": len(countries),
        "data": countries
    }), 200


# FILTRO 2: Filtrar por Faixa de População
@app.route("/api/countries/filter/population", methods=["GET"])
def filter_by_population():
    """
    Endpoint de Filtro 2: Retorna países dentro de uma faixa populacional específica.
    Parâmetros via query string:
      - min (int, opcional se max for fornecido)
      - max (int, opcional se min for fornecido)
    Exemplo: /api/countries/filter/population?min=10000000&max=50000000
    """
    min_param = request.args.get("min")
    max_param = request.args.get("max")

    # Tratamento de parâmetros ausentes
    if min_param is None and max_param is None:
        return jsonify({
            "error": "Bad Request",
            "message": "Informe pelo menos um parâmetro de filtro: 'min' ou 'max'. Exemplo: /api/countries/filter/population?min=10000000&max=50000000",
            "status_code": 400
        }), 400

    min_val = None
    max_val = None

    # Validação do parâmetro min
    if min_param is not None and min_param.strip() != "":
        try:
            min_val = int(min_param)
            if min_val < 0:
                return jsonify({
                    "error": "Bad Request",
                    "message": "O parâmetro 'min' deve ser um número inteiro maior ou igual a zero.",
                    "status_code": 400
                }), 400
        except ValueError:
            return jsonify({
                "error": "Bad Request",
                "message": f"O valor '{min_param}' para o parâmetro 'min' é inválido. Deve ser um número inteiro.",
                "status_code": 400
            }), 400

    # Validação do parâmetro max
    if max_param is not None and max_param.strip() != "":
        try:
            max_val = int(max_param)
            if max_val < 0:
                return jsonify({
                    "error": "Bad Request",
                    "message": "O parâmetro 'max' deve ser um número inteiro maior ou igual a zero.",
                    "status_code": 400
                }), 400
        except ValueError:
            return jsonify({
                "error": "Bad Request",
                "message": f"O valor '{max_param}' para o parâmetro 'max' é inválido. Deve ser um número inteiro.",
                "status_code": 400
            }), 400

    # Validação de coerência entre min e max
    if min_val is not None and max_val is not None and min_val > max_val:
        return jsonify({
            "error": "Bad Request",
            "message": f"O parâmetro 'min' ({min_val}) não pode ser maior do que o parâmetro 'max' ({max_val}).",
            "status_code": 400
        }), 400

    conditions = []
    params = []

    if min_val is not None:
        conditions.append("population >= ?")
        params.append(min_val)

    if max_val is not None:
        conditions.append("population <= ?")
        params.append(max_val)

    where_clause = " AND ".join(conditions)
    sql = f"SELECT * FROM countries WHERE {where_clause} ORDER BY population DESC"

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()

    # Tratamento para registro não encontrado
    if not rows:
        return jsonify({
            "error": "Not Found",
            "message": f"Nenhum país encontrado na faixa de população informada (min: {min_val}, max: {max_val}).",
            "status_code": 404
        }), 404

    countries = [row_to_dict(r) for r in rows]

    return jsonify({
        "status": "success",
        "filter": "population",
        "filters_applied": {
            "min": min_val,
            "max": max_val
        },
        "count": len(countries),
        "data": countries
    }), 200


if __name__ == "__main__":
    # Porta padrão 5000 em ambiente local
    app.run(host="0.0.0.0", port=5000, debug=True)