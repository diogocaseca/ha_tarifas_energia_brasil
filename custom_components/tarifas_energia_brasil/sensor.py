"""Define as entidades de sensor para a integração Tarifas de Energia Brasil."""
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_CONCESSIONARIA
from .coordinator import TarifasEnergiaCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configura as entidades de sensor a partir de uma entrada de configuração."""
    coordinator: TarifasEnergiaCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Passa a entrada de configuração (entry) inteira para os sensores
    # para garantir um vínculo forte e único.
    entities = [
        TarifaVigenteSensor(coordinator, entry),
        TarifaComImpostosEstimadosSensor(coordinator, entry),
        BandeiraVigenteSensor(coordinator, entry),
    ]

    async_add_entities(entities)


class TarifasEnergiaBaseSensor(CoordinatorEntity[TarifasEnergiaCoordinator], SensorEntity):
    """Classe base para os sensores da integração."""

    def __init__(self, coordinator: TarifasEnergiaCoordinator, entry: ConfigEntry):
        """Inicializa o sensor base, recebendo a ConfigEntry."""
        super().__init__(coordinator)
        self.entry = entry
        self._attr_has_entity_name = True

    @property
    def device_info(self):
        """Retorna as informações do dispositivo, usando o entry_id como identificador."""
        concessionaria_nome = self.entry.options.get(
            CONF_CONCESSIONARIA,
            self.entry.data.get(CONF_CONCESSIONARIA),
        )
        return {
            # Usa o entry_id para um identificador único e estável para o dispositivo.
            # Esta é a mudança principal para garantir que cada entrada crie um novo dispositivo.
            "identifiers": {(DOMAIN, self.entry.entry_id)},
            "name": f"Tarifas {concessionaria_nome}",
            "manufacturer": "ANEEL",
            "model": "Tarifas de Energia Elétrica",
            "entry_type": "service",
        }


class TarifaVigenteSensor(TarifasEnergiaBaseSensor):
    """Sensor que representa o valor da tarifa vigente."""

    _attr_name = "Tarifa Vigente"
    _attr_device_class = SensorDeviceClass.MONETARY
    # A linha abaixo foi removida para corrigir o erro de incompatibilidade.
    # Um sensor 'monetary' não pode ter a state_class 'measurement'.
    # _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:cash-multiple"
    _attr_native_unit_of_measurement = "R$/kWh"

    def __init__(self, coordinator: TarifasEnergiaCoordinator, entry: ConfigEntry):
        """Inicializa o sensor de tarifa vigente."""
        super().__init__(coordinator, entry)
        # Garante um ID único estável para a entidade, vinculado ao entry_id.
        self._attr_unique_id = f"{self.entry.entry_id}_tarifa_vigente"

    @property
    def native_value(self) -> float | None:
        """Retorna o valor da tarifa correspondente à bandeira vigente."""
        if not self.coordinator.data:
            return None
            
        bandeira = self.coordinator.data.get("bandeira_vigente")
        tarifas = self.coordinator.data.get("tarifas")

        if bandeira and tarifas:
            return tarifas.get(bandeira) / 1000
        
        return None

    @property
    def extra_state_attributes(self) -> dict[str, str | float] | None:
        """Expõe informações de impostos estimados usados pela integração."""
        if not self.coordinator.data:
            return None

        impostos = self.coordinator.data.get("impostos")
        if not impostos:
            return None

        return {
            "estado": impostos.get("estado"),
            "icms_estimado": impostos.get("icms"),
            "pis_cofins_estimado": impostos.get("pis_cofins"),
            "carga_tributaria_total_estimada": impostos.get("total"),
            "metodo_impostos": impostos.get("metodo"),
        }


class TarifaComImpostosEstimadosSensor(TarifasEnergiaBaseSensor):
    """Sensor com tarifa estimada incluindo impostos para a UF configurada."""

    _attr_name = "Tarifa com Impostos Estimados"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_icon = "mdi:cash-plus"
    _attr_native_unit_of_measurement = "R$/kWh"

    def __init__(self, coordinator: TarifasEnergiaCoordinator, entry: ConfigEntry):
        """Inicializa o sensor de tarifa com impostos estimados."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self.entry.entry_id}_tarifa_com_impostos_estimados"

    @property
    def native_value(self) -> float | None:
        """Retorna o valor da tarifa com impostos para a bandeira vigente."""
        if not self.coordinator.data:
            return None

        bandeira = self.coordinator.data.get("bandeira_vigente")
        tarifas = self.coordinator.data.get("tarifas_com_impostos")

        if bandeira and tarifas:
            valor = tarifas.get(bandeira)
            if valor is not None:
                return valor / 1000

        return None

    @property
    def extra_state_attributes(self) -> dict[str, str | float] | None:
        """Expõe detalhes dos impostos estimados aplicados ao cálculo."""
        if not self.coordinator.data:
            return None

        impostos = self.coordinator.data.get("impostos")
        if not impostos:
            return None

        return {
            "estado": impostos.get("estado"),
            "icms_estimado": impostos.get("icms"),
            "pis_cofins_estimado": impostos.get("pis_cofins"),
            "carga_tributaria_total_estimada": impostos.get("total"),
            "metodo_impostos": impostos.get("metodo"),
        }


class BandeiraVigenteSensor(TarifasEnergiaBaseSensor):
    """Sensor que representa qual bandeira tarifária está vigente."""

    _attr_name = "Bandeira Vigente"
    _attr_icon = "mdi:flag"

    def __init__(self, coordinator: TarifasEnergiaCoordinator, entry: ConfigEntry):
        """Inicializa o sensor da bandeira vigente."""
        super().__init__(coordinator, entry)
        # Garante um ID único estável para a entidade, vinculado ao entry_id.
        self._attr_unique_id = f"{self.entry.entry_id}_bandeira_vigente"

    @property
    def native_value(self) -> str | None:
        """Retorna o nome da bandeira tarifária vigente."""
        if self.coordinator.data:
            return self.coordinator.data.get("bandeira_vigente")
        return None

