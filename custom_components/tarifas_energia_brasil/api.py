"""API Client para a integração Tarifas de Energia Brasil."""
import asyncio
import csv
import io
import logging
import json
import aiohttp
from datetime import date, timedelta

from .database import DatabaseManager

_LOGGER = logging.getLogger(__name__)

# URL base da API da ANEEL para consultas SQL
URL_SQL_API = "https://dadosabertos.aneel.gov.br/api/3/action/datastore_search_sql"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_BANDEIRA_DATA_AGE_DAYS = 62
BANDEIRA_NAO_ENCONTRADA = "Bandeira não encontrada"

# IDs dos recursos (datasets) na ANEEL
RESOURCE_ID_TARIFAS = "fcf2906c-7c32-4b9b-a637-054e7a5234f4"
# Dataset de bandeiras tarifarias (Acionamento) solicitado para uso.
RESOURCE_ID_BANDEIRAS = "0591b8f6-fe54-437b-b72b-1aa2efd46e42"
URL_BANDEIRAS_CSV = (
    "https://dadosabertos.aneel.gov.br/dataset/"
    "7f43a020-6dc5-44b8-80b4-d97eaa94436c/resource/"
    "0591b8f6-fe54-437b-b72b-1aa2efd46e42/download/"
    "bandeira-tarifaria-acionamento.csv"
)


class TarifasEnergiaAPI:
    """Cliente para buscar dados de tarifas e gerenciar o banco de dados."""

    def __init__(self, hass, session: aiohttp.ClientSession, db_manager: DatabaseManager):
        """Inicializa o cliente da API."""
        self._hass = hass
        self._session = session
        self._db = db_manager

    @staticmethod
    def _parse_iso_date(date_str: str | None) -> date | None:
        """Converte string YYYY-MM-DD em date, retornando None em erro."""
        if not date_str:
            return None
        try:
            return date.fromisoformat(str(date_str)[:10])
        except (ValueError, TypeError):
            return None

    def _is_bandeira_record_stale(
        self,
        record_date_str: str | None,
        reference_date: date,
    ) -> bool:
        """Indica se registro de bandeira está defasado em relação à data de referência."""
        record_date = self._parse_iso_date(record_date_str)
        if record_date is None:
            return True
        age_days = (reference_date - record_date).days
        return age_days > MAX_BANDEIRA_DATA_AGE_DAYS

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

    async def _async_get_text_with_retry(
        self,
        url: str,
        request_name: str,
        max_attempts: int = 3,
    ) -> str:
        """Faz request HTTP de texto com retry para erros transitórios."""
        for attempt in range(1, max_attempts + 1):
            try:
                async with self._session.get(url) as response:
                    response.raise_for_status()
                    return await response.text()
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

    @staticmethod
    def _parse_decimal_br(value: str | None) -> float:
        """Converte decimal brasileiro para float."""
        if value is None:
            return 0.0
        text = str(value).strip()
        if text in {"", ",", ".", ",00", ".00"}:
            return 0.0
        return float(text.replace(".", "").replace(",", "."))

    def _default_valores_bandeiras(self) -> dict[str, float]:
        """Retorna estrutura padrão de valores de bandeira com adicional zero."""
        return {
            "Bandeira Verde": 0.0,
            "Bandeira Amarela": 0.0,
            "Bandeira Vermelha Patamar 1": 0.0,
            "Bandeira Vermelha Patamar 2": 0.0,
            BANDEIRA_NAO_ENCONTRADA: 0.0,
        }

    async def _async_get_latest_bandeira_from_csv(
        self,
        competencia: date,
    ) -> dict | None:
        """Lê o CSV da ANEEL e retorna a linha mais recente até a competência."""
        try:
            csv_text = await self._async_get_text_with_retry(
                URL_BANDEIRAS_CSV,
                "Download CSV de bandeiras",
            )
        except aiohttp.ClientError as err:
            _LOGGER.warning("Erro ao baixar CSV de bandeiras: %s", err)
            return None

        reader = csv.DictReader(io.StringIO(csv_text), delimiter=";")
        best_row: dict | None = None
        best_date: date | None = None

        for row in reader:
            row_date = self._parse_iso_date(row.get("DatCompetencia"))
            if row_date is None:
                continue
            if row_date > competencia:
                continue
            if best_date is None or row_date > best_date:
                best_date = row_date
                best_row = row

        if best_row is None:
            _LOGGER.error(
                "CSV de bandeiras não possui registros válidos até a competência %s.",
                competencia,
            )
            return None

        return best_row

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
        """Busca valores de bandeiras no CSV de acionamento da ANEEL."""
        record = await self._async_get_latest_bandeira_from_csv(competencia)
        if record is None:
            return None

        bandeira_acionada = record.get("NomBandeiraAcionada")
        dat_vigencia = record.get("DatCompetencia")

        if self._is_bandeira_record_stale(dat_vigencia, competencia):
            _LOGGER.warning(
                "CSV de bandeiras defasado (DatCompetencia=%s). "
                "Aplicando fallback de bandeira não encontrada com adicional 0.",
                dat_vigencia,
            )
            return self._default_valores_bandeiras()

        try:
            adicional = self._parse_decimal_br(
                record.get("VlrAdicionalBandeira"),
            )

            valores = self._default_valores_bandeiras()

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
                    "Bandeira acionada desconhecida no CSV: %s",
                    bandeira_acionada,
                )
                valores[BANDEIRA_NAO_ENCONTRADA] = 0.0

            _LOGGER.info(
                "Valores de bandeira calculados a partir de '%s' (%s): %s",
                bandeira_acionada,
                dat_vigencia,
                valores,
            )
            return valores
        except (ValueError, TypeError) as err:
            _LOGGER.warning(
                "Erro ao processar dados de bandeiras no CSV: %s.",
                err,
            )

        return None


    async def async_get_bandeira_vigente(self, competencia: date) -> str | None:
        """Busca a última bandeira vigente disponível no CSV da ANEEL."""
        record = await self._async_get_latest_bandeira_from_csv(competencia)
        if record is None:
            _LOGGER.error("Não foi possível obter bandeira vigente no CSV da ANEEL.")
            return BANDEIRA_NAO_ENCONTRADA

        bandeira_acionada = record.get("NomBandeiraAcionada")
        dat_vigencia = record.get("DatCompetencia")
        if self._is_bandeira_record_stale(dat_vigencia, competencia):
            _LOGGER.warning(
                "Bandeira vigente da ANEEL está defasada (DatCompetencia=%s). "
                "Usando fallback de bandeira não encontrada.",
                dat_vigencia,
            )
            return BANDEIRA_NAO_ENCONTRADA

        try:

            mapa_bandeiras = {
                "Verde": "Bandeira Verde",
                "Amarela": "Bandeira Amarela",
                "Vermelha P1": "Bandeira Vermelha Patamar 1",
                "Vermelha Patamar 1": "Bandeira Vermelha Patamar 1",
                "Vermelha P2": "Bandeira Vermelha Patamar 2",
                "Vermelha Patamar 2": "Bandeira Vermelha Patamar 2",
            }
            return mapa_bandeiras.get(
                bandeira_acionada,
                BANDEIRA_NAO_ENCONTRADA,
            )
        except Exception as err:
            _LOGGER.warning("Erro inesperado ao processar bandeira: %s", err)

        return BANDEIRA_NAO_ENCONTRADA


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
            BANDEIRA_NAO_ENCONTRADA: tarifa_base + valores_bandeiras[BANDEIRA_NAO_ENCONTRADA],
        }
        
        await self._db.async_update_tarifas(concessionaria_nome, tarifas_finais)
        _LOGGER.info(f"Tarifas finais para {concessionaria_nome} atualizadas com sucesso.")

        return await self._db.async_get_tarifas(concessionaria_nome)
