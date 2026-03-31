"""DataUpdateCoordinator para a integração Tarifas de Energia Brasil."""
import logging
from datetime import timedelta, date

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.core import HomeAssistant

from .api import TarifasEnergiaAPI
from .const import DOMAIN, ICMS_POR_ESTADO, DEFAULT_PIS_COFINS

_LOGGER = logging.getLogger(__name__)


class TarifasEnergiaCoordinator(DataUpdateCoordinator):
    """Coordenador para buscar e gerenciar os dados de tarifas."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: TarifasEnergiaAPI,
        concessionaria: str,
        estado: str,
    ):
        """Inicializa o coordenador."""
        self.api = api
        self.concessionaria = concessionaria
        self.estado = estado
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(days=1),  # Atualiza uma vez por dia
        )

    def _calcular_tarifas_com_impostos(
        self,
        tarifas: dict[str, float],
    ) -> tuple[dict[str, float], dict[str, float | str]]:
        """Calcula tarifas com impostos estimados para a UF selecionada."""
        icms = ICMS_POR_ESTADO.get(self.estado, 0.18)
        pis_cofins = DEFAULT_PIS_COFINS
        fator = 1 + icms + pis_cofins

        tarifas_com_impostos = {
            bandeira: valor * fator for bandeira, valor in tarifas.items()
        }
        impostos_info = {
            "estado": self.estado,
            "icms": icms,
            "pis_cofins": pis_cofins,
            "total": icms + pis_cofins,
            "metodo": "estimado",
        }
        return tarifas_com_impostos, impostos_info

    async def _async_update_data(self) -> dict:
        """
        Busca os dados mais recentes da API.

        Esta função é chamada automaticamente pelo Home Assistant no intervalo definido.
        """
        try:
            # 1. Busca os valores calculados para todas as bandeiras
            tarifas = await self.api.async_fetch_and_update_data(self.concessionaria)
            if not tarifas:
                raise UpdateFailed("Não foi possível obter os valores das tarifas.")

            # 2. Busca o nome da bandeira vigente para o mês corrente
            bandeira_vigente = await self.api.async_get_bandeira_vigente(date.today())
            if not bandeira_vigente:
                if self.data and self.data.get("bandeira_vigente"):
                    bandeira_vigente = self.data["bandeira_vigente"]
                    _LOGGER.warning(
                        "Não foi possível obter a bandeira vigente na API; "
                        "mantendo último valor conhecido: '%s'.",
                        bandeira_vigente,
                    )
                else:
                    raise UpdateFailed(
                        "Não foi possível obter a bandeira tarifária vigente."
                    )

            _LOGGER.info(
                f"Atualização bem-sucedida. Bandeira vigente: '{bandeira_vigente}'."
            )

            tarifas_com_impostos, impostos_info = self._calcular_tarifas_com_impostos(
                tarifas
            )

            # 3. Retorna um dicionário com todos os dados necessários para os sensores
            return {
                "tarifas": tarifas,
                "tarifas_com_impostos": tarifas_com_impostos,
                "bandeira_vigente": bandeira_vigente,
                "impostos": impostos_info,
            }

        except UpdateFailed:
            raise
        except Exception as err:
            _LOGGER.error(f"Erro inesperado durante a atualização: {err}")
            raise UpdateFailed(f"Erro ao buscar dados: {err}")

