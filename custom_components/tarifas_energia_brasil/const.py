"""Constantes para a integração Tarifas de Energia Brasil."""

# Domínio da integração. Deve ser o mesmo nome da pasta.
DOMAIN = "tarifas_energia_brasil"

# Chaves de configuração
CONF_CONCESSIONARIA = "concessionaria"
CONF_ESTADO = "estado"

DEFAULT_ESTADO = "SP"
DEFAULT_PIS_COFINS = 0.0925

# Estimativas simplificadas de ICMS residencial por UF.
ICMS_POR_ESTADO = {
	"AC": 0.17,
	"AL": 0.19,
	"AP": 0.18,
	"AM": 0.20,
	"BA": 0.18,
	"CE": 0.18,
	"DF": 0.18,
	"ES": 0.17,
	"GO": 0.19,
	"MA": 0.20,
	"MT": 0.17,
	"MS": 0.17,
	"MG": 0.18,
	"PA": 0.19,
	"PB": 0.18,
	"PR": 0.18,
	"PE": 0.18,
	"PI": 0.18,
	"RJ": 0.22,
	"RN": 0.18,
	"RS": 0.17,
	"RO": 0.17,
	"RR": 0.17,
	"SC": 0.17,
	"SP": 0.18,
	"SE": 0.18,
	"TO": 0.18,
}

# Atributos e outros valores
ATTR_TARIFA_VERDE = "Tarifa Bandeira Verde"
ATTR_TARIFA_AMARELA = "Tarifa Bandeira Amarela"
ATTR_TARIFA_VERMELHA_1 = "Tarifa Bandeira Vermelha P1"
ATTR_TARIFA_VERMELHA_2 = "Tarifa Bandeira Vermelha P2"
