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
        """Busca os valores das bandeiras via SQL, com fallback para meses anteriores."""
        data_tentativa = competencia.replace(day=1)

        # Busca no mês atual e até 11 meses para trás.
        for _ in range(12):
            mes_ano = data_tentativa.strftime("%Y-%m")
            sql_query = (
                f'SELECT "DatCompetencia", '
                f'"VlrBandeiraAmarela", '
                f'"VlrBandeiraVermelhaPatamar1", '
                f'"VlrBandeiraVermelhaPatamar2" '
                f'FROM "{RESOURCE_ID_BANDEIRAS}" '
                f'WHERE "DatCompetencia" LIKE \'{mes_ano}%\' '
                f'ORDER BY "DatCompetencia" DESC '
                f'LIMIT 1'
            )
            params = {"sql": sql_query}
            _LOGGER.info("Buscando valores das bandeiras para %s via SQL.", mes_ano)

            try:
                data = await self._async_get_json_with_retry(
                    URL_SQL_API,
                    params,
                    f"Consulta de bandeiras ({mes_ano})",
                )

                if data.get("success"):
                    records = data.get("result", {}).get("records", [])
                    if records:
                        record = records[0]
                        valores = {
                            "Bandeira Verde": 0.0,
                            "Bandeira Amarela": float(
                                str(record.get("VlrBandeiraAmarela", 0.0)).replace(",", ".")
                            ),
                            "Bandeira Vermelha Patamar 1": float(
                                str(record.get("VlrBandeiraVermelhaPatamar1", 0.0)).replace(",", ".")
                            ),
                            "Bandeira Vermelha Patamar 2": float(
                                str(record.get("VlrBandeiraVermelhaPatamar2", 0.0)).replace(",", ".")
                            ),
                        }
                        _LOGGER.info(
                            "Valores das bandeiras encontrados para %s: %s",
                            mes_ano,
                            valores,
                        )
                        return valores

            except aiohttp.ClientError as err:
                _LOGGER.warning(
                    "Erro ao acessar API SQL de bandeiras para %s: %s. "
                    "Tentando mês anterior.",
                    mes_ano,
                    err,
                )
            except (ValueError, TypeError) as err:
                _LOGGER.warning(
                    "Erro ao processar dados das bandeiras para %s: %s. "
                    "Tentando mês anterior.",
                    mes_ano,
                    err,
                )

            data_tentativa = data_tentativa - timedelta(days=1)
            data_tentativa = data_tentativa.replace(day=1)

        _LOGGER.error(
            "Não foi possível obter os valores das bandeiras nos últimos 12 meses."
        )
        return None


    async def async_get_bandeira_vigente(self, competencia: date) -> str | None:
        """Busca a bandeira tarifária vigente, com fallback para o mês anterior."""
        datas_para_tentar = [
            competencia,
            (competencia.replace(day=1) - timedelta(days=1))  # Mês anterior
        ]

        for data_tentativa in datas_para_tentar:
            mes_ano = data_tentativa.strftime("%Y-%m")
            sql_query = f'SELECT "NomBandeiraAcionada" from "{RESOURCE_ID_BANDEIRAS}" WHERE "DatCompetencia" LIKE \'{mes_ano}%\' LIMIT 1'
            params = {"sql": sql_query}
            
            _LOGGER.info(f"Buscando bandeira tarifária para {mes_ano} via SQL.")

            try:
                data = await self._async_get_json_with_retry(
                    URL_SQL_API,
                    params,
                    f"Consulta de bandeira vigente ({mes_ano})",
                )

                if data.get("success"):
                    records = data.get("result", {}).get("records", [])
                    if records:
                        bandeira_acionada = records[0].get("NomBandeiraAcionada")
                        _LOGGER.info(
                            "Bandeira acionada encontrada para %s: %s",
                            mes_ano,
                            bandeira_acionada,
                        )

                        mapa_bandeiras = {
                            "Verde": "Bandeira Verde",
                            "Amarela": "Bandeira Amarela",
                            "Vermelha P1": "Bandeira Vermelha Patamar 1",
                            "Vermelha P2": "Bandeira Vermelha Patamar 2",
                        }
                        return mapa_bandeiras.get(
                            bandeira_acionada,
                            bandeira_acionada,
                        )
            
            except aiohttp.ClientError as err:
                _LOGGER.warning(
                    "Erro ao acessar API SQL de bandeiras para %s: %s. "
                    "Tentando próxima data.",
                    mes_ano,
                    err,
                )
            except Exception as err:
                _LOGGER.warning(f"Erro inesperado ao processar bandeira para {mes_ano}: {err}. Tentando próxima data.")

        _LOGGER.error("Não foi possível obter a bandeira vigente para o mês atual ou anterior.")
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
