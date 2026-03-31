"""API Client para a integração Tarifas de Energia Brasil."""
import asyncio
import logging
import json
import aiohttp
from datetime import date, timedelta

from .database import DatabaseManager

_LOGGER = logging.getLogger(__name__)

# URL base da API da ANEEL para consultas SQL
URL_SQL_API = "https://dadosabertos.aneel.gov.br/api/3/action/datastore_search_sql"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# IDs dos recursos (datasets) na ANEEL
RESOURCE_ID_TARIFAS = "fcf2906c-7c32-4b9b-a637-054e7a5234f4"
RESOURCE_ID_BANDEIRAS = "0591b8f6-fe54-437b-b72b-1aa2efd46e42"


class TarifasEnergiaAPI:
    """Cliente para buscar dados de tarifas e gerenciar o banco de dados."""

    def __init__(self, hass, session: aiohttp.ClientSession, db_manager: DatabaseManager):
        """Inicializa o cliente da API."""
        self._hass = hass
        self._session = session
        self._db = db_manager

    async def _async_get_json_with_retry(
        self,
        url: str,
        params: dict,
        request_name: str,
        max_attempts: int = 3,
    ) -> dict:
        """Faz request HTTP com retry para erros transitórios da API."""
        for attempt in range(1, max_attempts + 1):
            try:
                async with self._session.get(url, params=params) as response:
                    response.raise_for_status()
                    return await response.json()
            except aiohttp.ClientResponseError as err:
                should_retry = (
                    err.status in RETRYABLE_STATUS_CODES and attempt < max_attempts
                )
                if should_retry:
                    wait_seconds = attempt
                    _LOGGER.warning(
                        "%s falhou (tentativa %s/%s, status %s). "
                        "Nova tentativa em %ss.",
                        request_name,
                        attempt,
                        max_attempts,
                        err.status,
                        wait_seconds,
                    )
                    await asyncio.sleep(wait_seconds)
                    continue
                raise
            except aiohttp.ClientError:
                if attempt < max_attempts:
                    wait_seconds = attempt
                    _LOGGER.warning(
                        "%s falhou (tentativa %s/%s). Nova tentativa em %ss.",
                        request_name,
                        attempt,
                        max_attempts,
                        wait_seconds,
                    )
                    await asyncio.sleep(wait_seconds)
                    continue
                raise

    async def _async_get_cached_tarifas(
        self, concessionaria_nome: str
    ) -> dict[str, float] | None:
        """Retorna tarifas em cache para reduzir indisponibilidade em falhas temporárias."""
        tarifas = await self._db.async_get_tarifas(concessionaria_nome)
        if tarifas:
            _LOGGER.warning(
                "Usando tarifas em cache para '%s' devido a falha na atualização.",
                concessionaria_nome,
            )
            return tarifas

        _LOGGER.error(
            "Nenhuma tarifa em cache disponível para '%s'.",
            concessionaria_nome,
        )
        return None

    async def _async_get_valores_bandeiras(self, competencia: date) -> dict[str, float] | None:
        """Busca o adicional da última bandeira vigente no schema atual da ANEEL."""
        sql_query = (
            f'SELECT "DatCompetencia", "NomBandeiraAcionada", "VlrAdicionalBandeira" '
            f'FROM "{RESOURCE_ID_BANDEIRAS}" '
            f'ORDER BY "DatCompetencia" DESC '
            f'LIMIT 1'
        )
        params = {"sql": sql_query}

        try:
            data = await self._async_get_json_with_retry(
                URL_SQL_API,
                params,
                "Consulta de valores da bandeira vigente",
            )

            if not data.get("success"):
                _LOGGER.error(
                    "Consulta de valores de bandeiras sem sucesso: %s",
                    data.get("error"),
                )
                return None

            records = data.get("result", {}).get("records", [])
            if not records:
                _LOGGER.error(
                    "Recurso de bandeiras sem registros disponíveis na ANEEL."
                )
                return None

            record = records[0]
            bandeira_acionada = record.get("NomBandeiraAcionada")
            adicional = float(
                str(record.get("VlrAdicionalBandeira", 0.0)).replace(",", ".")
            )

            valores = {
                "Bandeira Verde": 0.0,
                "Bandeira Amarela": 0.0,
                "Bandeira Vermelha Patamar 1": 0.0,
                "Bandeira Vermelha Patamar 2": 0.0,
            }

            mapa_bandeiras = {
                "Verde": "Bandeira Verde",
                "Amarela": "Bandeira Amarela",
                "Vermelha P1": "Bandeira Vermelha Patamar 1",
                "Vermelha Patamar 1": "Bandeira Vermelha Patamar 1",
                "Vermelha P2": "Bandeira Vermelha Patamar 2",
                "Vermelha Patamar 2": "Bandeira Vermelha Patamar 2",
            }

            chave_bandeira = mapa_bandeiras.get(bandeira_acionada)
            if chave_bandeira:
                valores[chave_bandeira] = adicional
            else:
                _LOGGER.warning(
                    "Bandeira acionada desconhecida no dataset: %s",
                    bandeira_acionada,
                )

            _LOGGER.info(
                "Valores de bandeira calculados a partir de '%s' (%s): %s",
                bandeira_acionada,
                record.get("DatCompetencia"),
                valores,
            )
            return valores

        except aiohttp.ClientError as err:
            _LOGGER.warning(
                "Erro ao acessar API SQL de bandeiras: %s.",
                err,
            )
        except (ValueError, TypeError) as err:
            _LOGGER.warning(
                "Erro ao processar dados de bandeiras no novo schema: %s.",
                err,
            )

        return None


    async def async_get_bandeira_vigente(self, competencia: date) -> str | None:
        """Busca a última bandeira vigente disponível no dataset da ANEEL."""
        sql_query = (
            f'SELECT "DatCompetencia", "NomBandeiraAcionada" '
            f'FROM "{RESOURCE_ID_BANDEIRAS}" '
            f'ORDER BY "DatCompetencia" DESC '
            f'LIMIT 1'
        )
        params = {"sql": sql_query}

        try:
            data = await self._async_get_json_with_retry(
                URL_SQL_API,
                params,
                "Consulta da última bandeira vigente",
            )

            if not data.get("success"):
                _LOGGER.error(
                    "Consulta de bandeira vigente sem sucesso: %s",
                    data.get("error"),
                )
                return None

            records = data.get("result", {}).get("records", [])
            if not records:
                _LOGGER.error("Dataset de bandeiras sem registros para bandeira vigente.")
                return None

            bandeira_acionada = records[0].get("NomBandeiraAcionada")
            mapa_bandeiras = {
                "Verde": "Bandeira Verde",
                "Amarela": "Bandeira Amarela",
                "Vermelha P1": "Bandeira Vermelha Patamar 1",
                "Vermelha Patamar 1": "Bandeira Vermelha Patamar 1",
                "Vermelha P2": "Bandeira Vermelha Patamar 2",
                "Vermelha Patamar 2": "Bandeira Vermelha Patamar 2",
            }
            return mapa_bandeiras.get(bandeira_acionada, bandeira_acionada)

        except aiohttp.ClientError as err:
            _LOGGER.warning("Erro ao acessar API SQL de bandeiras: %s", err)
        except Exception as err:
            _LOGGER.warning("Erro inesperado ao processar bandeira: %s", err)

        return None


    async def async_fetch_concessionarias(self) -> bool:
        """
        Busca a lista de concessionárias via API SQL da ANEEL e atualiza o banco de dados.
        Retorna True se bem-sucedido.
        """
        _LOGGER.info("Iniciando a busca da lista de concessionárias via API SQL da ANEEL.")
        sql_query = f'SELECT "SigAgente" from "{RESOURCE_ID_TARIFAS}" group by "SigAgente"'
        params = {"sql": sql_query}

        try:
            async with self._session.get(URL_SQL_API, params=params) as response:
                response.raise_for_status()
                data = await response.json()

                if not data.get("success"):
                    _LOGGER.error(f"A API de concessionárias da ANEEL retornou um erro: {data.get('error')}")
                    return False

                records = data.get("result", {}).get("records", [])
                if not records:
                    _LOGGER.warning("Nenhuma concessionária encontrada na resposta da API.")
                    return False
                
                nomes_concessionarias = {record["SigAgente"] for record in records if "SigAgente" in record}

                if not nomes_concessionarias:
                    _LOGGER.warning("Os registros da API não continham a chave 'SigAgente'.")
                    return False

                await self._db.async_update_concessionarias(nomes_concessionarias)
                return True

        except aiohttp.ClientError as err:
            _LOGGER.error(f"Erro ao acessar a API da ANEEL: {err}")
            return False
        except (KeyError, json.JSONDecodeError) as err:
            _LOGGER.error(f"Erro ao processar o JSON da lista de concessionárias: {err}")
            return False
        except Exception as err:
            _LOGGER.error(f"Erro inesperado ao buscar a lista de concessionárias: {err}")
            return False

    async def async_fetch_and_update_data(self, concessionaria_nome: str):
        """
        Busca a tarifa base usando uma query SQL e os valores das bandeiras, 
        calcula as tarifas finais e atualiza o banco de dados.
        """
        hoje = date.today()
        _LOGGER.info(f"Iniciando atualização de tarifas para '{concessionaria_nome}' via SQL em {hoje}.")

        valores_bandeiras = await self._async_get_valores_bandeiras(hoje)
        if valores_bandeiras is None:
            _LOGGER.error("Não foi possível obter os valores das bandeiras. Abortando atualização.")
            return await self._async_get_cached_tarifas(concessionaria_nome)

        tarifa_base = None
        
        # Monta a query SQL com os filtros especificados e busca a data mais recente
        sql_query = (
            f'WITH ultima_data AS ('
            f'  SELECT MAX("DatFimVigencia") as data_max '
            f'  FROM "{RESOURCE_ID_TARIFAS}" '
            f'  WHERE "SigAgente" = \'{concessionaria_nome}\' '
            f'  AND "DscBaseTarifaria" = \'Tarifa de Aplicação\' '
            f'  AND "DscSubGrupo" = \'B1\' '
            f'  AND "DscClasse" = \'Residencial\' '
            f') '
            f'SELECT "VlrTUSD", "VlrTE" '
            f'FROM "{RESOURCE_ID_TARIFAS}" '
            f'WHERE "SigAgente" = \'{concessionaria_nome}\' '
            f'AND "DscBaseTarifaria" = \'Tarifa de Aplicação\' '
            f'AND "DscSubGrupo" = \'B1\' '
            f'AND "DscClasse" = \'Residencial\' '
            f'AND "DscModalidadeTarifaria" = \'Convencional\' '
            f'AND "DscSubClasse" = \'Residencial\' '
            f'AND "DscDetalhe" = \'Não se aplica\' '
            f'AND "DatFimVigencia" = (SELECT data_max FROM ultima_data) '
            f'LIMIT 1'
        )        
        
        params = {"sql": sql_query}
        
        try:
            _LOGGER.debug(f"Executando SQL na API da ANEEL: {sql_query}")
            data = await self._async_get_json_with_retry(
                URL_SQL_API,
                params,
                f"Consulta de tarifa base ({concessionaria_nome})",
            )

            if not data.get("success"):
                _LOGGER.error(
                    f"A API de tarifas da ANEEL retornou um erro: {data.get('error')}"
                )
                return await self._async_get_cached_tarifas(concessionaria_nome)

            records = data.get("result", {}).get("records", [])
            if not records:
                _LOGGER.error(
                    f"Nenhuma tarifa base vigente encontrada para '{concessionaria_nome}' com os filtros aplicados via SQL."
                )
                return await self._async_get_cached_tarifas(concessionaria_nome)

            record = records[0]

            vlr_tusd_raw = record.get("VlrTUSD", "0")
            vlr_te_raw = record.get("VlrTE", "0")

            vlr_tusd = float(str(vlr_tusd_raw).replace(",", "."))
            vlr_te = float(str(vlr_te_raw).replace(",", "."))

            tarifa_base = vlr_tusd + vlr_te
            _LOGGER.info(
                f"Tarifa base encontrada para {concessionaria_nome}: {tarifa_base:.4f}"
            )

        except aiohttp.ClientError as err:
            _LOGGER.error(f"Erro ao acessar a API SQL de tarifas: {err}")
            return await self._async_get_cached_tarifas(concessionaria_nome)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as err:
            _LOGGER.error(f"Erro ao processar o JSON da tarifa: {err}")
            return await self._async_get_cached_tarifas(concessionaria_nome)
        
        if tarifa_base is None:
            _LOGGER.error(f"Falha ao determinar a tarifa base para '{concessionaria_nome}'.")
            return await self._async_get_cached_tarifas(concessionaria_nome)

        # Calcula os valores finais e atualiza o banco de dados
        tarifas_finais = {
            "Bandeira Verde": tarifa_base + valores_bandeiras["Bandeira Verde"],
            "Bandeira Amarela": tarifa_base + valores_bandeiras["Bandeira Amarela"],
            "Bandeira Vermelha Patamar 1": tarifa_base + valores_bandeiras["Bandeira Vermelha Patamar 1"],
            "Bandeira Vermelha Patamar 2": tarifa_base + valores_bandeiras["Bandeira Vermelha Patamar 2"],
        }
        
        await self._db.async_update_tarifas(concessionaria_nome, tarifas_finais)
        _LOGGER.info(f"Tarifas finais para {concessionaria_nome} atualizadas com sucesso.")

        return await self._db.async_get_tarifas(concessionaria_nome)
