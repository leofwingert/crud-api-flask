import os
import requests
from database import get_db

DEFAULT_API_URL = "https://api.restcountries.com/countries/v5"
DEFAULT_API_KEY = "rc_live_a530a34d4e4e450dbafc0239d5738c52"


class ExternalAPIError(Exception):
    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def fetch_external_countries(api_url=None, api_key=None, timeout=15):
    url = api_url or os.getenv("RESTCOUNTRIES_API_URL", DEFAULT_API_URL)
    token = api_key or os.getenv("RESTCOUNTRIES_API_KEY", DEFAULT_API_KEY)

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "Flask-RestCountries-Client/1.0",
    }

    all_objects = []
    offset = 0
    limit = 100

    try:
        while True:
            params = {"limit": limit, "offset": offset}
            response = requests.get(url, headers=headers, params=params, timeout=timeout)

            # Verifica erros HTTP da API externa
            if response.status_code == 401 or response.status_code == 403:
                raise ExternalAPIError(
                    f"Falha de autenticação na API externa: Chave de API inválida ou não autorizada (HTTP {response.status_code}).",
                    status_code=502,
                )
            elif response.status_code == 429:
                raise ExternalAPIError(
                    "Limite de requisições excedido na API externa (Rate Limit HTTP 429).",
                    status_code=502,
                )
            elif response.status_code >= 500:
                raise ExternalAPIError(
                    f"A API externa restcountries.com retornou erro interno do servidor (HTTP {response.status_code}).",
                    status_code=502,
                )
            elif response.status_code != 200:
                raise ExternalAPIError(
                    f"Erro inesperado da API externa restcountries.com (HTTP {response.status_code}): {response.text}",
                    status_code=502,
                )

            data = response.json()
            if "errors" in data and data["errors"]:
                error_msg = "; ".join([e.get("message", "Erro desconhecido") for e in data["errors"]])
                raise ExternalAPIError(f"A API externa retornou erros: {error_msg}", status_code=502)

            data_body = data.get("data", {})
            objects = data_body.get("objects", [])
            all_objects.extend(objects)

            meta = data_body.get("meta", {})
            has_more = meta.get("more", False)
            if not has_more or len(objects) == 0:
                break

            offset += limit

    except requests.exceptions.Timeout:
        raise ExternalAPIError(
            f"Tempo limite de conexão esgotado ({timeout}s) ao contatar a API externa restcountries.com.",
            status_code=504,
        )
    except requests.exceptions.ConnectionError as ce:
        raise ExternalAPIError(
            f"Falha de conexão com a API externa restcountries.com: Não foi possível estabelecer conexão de rede ({ce}).",
            status_code=502,
        )
    except requests.exceptions.RequestException as re:
        raise ExternalAPIError(
            f"Erro na requisição para a API externa: {str(re)}",
            status_code=502,
        )

    return all_objects


def parse_country_object(obj):
    """Converte o objeto retornado pela API externa no formato do schema local."""
    names = obj.get("names", {})
    common_name = names.get("common") or names.get("official") or "Desconhecido"
    official_name = names.get("official", "")

    codes = obj.get("codes", {})
    alpha2 = codes.get("alpha_2", "")
    alpha3 = codes.get("alpha_3", "")

    capitals_list = [c.get("name") for c in obj.get("capitals", []) if c.get("name")]
    capital = ", ".join(capitals_list) if capitals_list else ""

    region = obj.get("region") or "Outro"
    subregion = obj.get("subregion", "")

    population = int(obj.get("population") or 0)
    area = float(obj.get("area", {}).get("kilometers", 0.0) or 0.0)

    langs_list = [l.get("name") for l in obj.get("languages", []) if l.get("name")]
    languages = ", ".join(langs_list)

    currs_list = [c.get("code") for c in obj.get("currencies", []) if c.get("code")]
    currencies = ", ".join(currs_list)

    external_uuid = obj.get("uuid") or None

    return {
        "external_uuid": external_uuid,
        "name": common_name,
        "official_name": official_name,
        "alpha2_code": alpha2,
        "alpha3_code": alpha3,
        "capital": capital,
        "region": region,
        "subregion": subregion,
        "population": population,
        "area": area,
        "languages": languages,
        "currencies": currencies,
    }


def sync_countries_to_db(db_path=None, api_url=None, api_key=None):
    """
    Consome os dados da API externa e insere/atualiza no banco SQLite local.
    Retorna o número de países sincronizados e o total no banco local.
    """
    objects = fetch_external_countries(api_url=api_url, api_key=api_key)
    conn = get_db(db_path)
    cursor = conn.cursor()

    synced_count = 0
    for obj in objects:
        c = parse_country_object(obj)
        cursor.execute(
            """
            INSERT INTO countries (
                external_uuid, name, official_name, alpha2_code, alpha3_code,
                capital, region, subregion, population, area, languages, currencies,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(external_uuid) DO UPDATE SET
                name=excluded.name,
                official_name=excluded.official_name,
                alpha2_code=excluded.alpha2_code,
                alpha3_code=excluded.alpha3_code,
                capital=excluded.capital,
                region=excluded.region,
                subregion=excluded.subregion,
                population=excluded.population,
                area=excluded.area,
                languages=excluded.languages,
                currencies=excluded.currencies,
                updated_at=CURRENT_TIMESTAMP;
            """,
            (
                c["external_uuid"],
                c["name"],
                c["official_name"],
                c["alpha2_code"],
                c["alpha3_code"],
                c["capital"],
                c["region"],
                c["subregion"],
                c["population"],
                c["area"],
                c["languages"],
                c["currencies"],
            ),
        )
        synced_count += 1

    conn.commit()

    cursor.execute("SELECT COUNT(*) as total FROM countries;")
    total_local = cursor.fetchone()["total"]
    conn.close()

    return {
        "synced_count": synced_count,
        "total_local": total_local,
    }
