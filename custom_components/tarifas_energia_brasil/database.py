"""Módulo para gerenciar o banco de dados SQLite com aiosqlite."""
import logging

import aiosqlite

_LOGGER = logging.getLogger(__name__)


class DatabaseManager:
    """Gerencia a conexão e operações com o banco de dados."""

    def __init__(self, hass, db_path):
        """Inicializa o gerenciador do banco de dados."""
        self.db_path = db_path
        self.hass = hass

    async def async_setup_database(self):
        """Cria as tabelas no banco de dados se não existirem."""
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("PRAGMA foreign_keys = ON")
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS concessionarias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL UNIQUE
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tarifas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bandeira TEXT NOT NULL,
                    valor REAL NOT NULL,
                    unidade TEXT NOT NULL DEFAULT 'R$/kWh',
                    concessionaria_id INTEGER NOT NULL,
                    FOREIGN KEY (concessionaria_id)
                        REFERENCES concessionarias(id) ON DELETE CASCADE,
                    UNIQUE(concessionaria_id, bandeira)
                )
                """
            )
            await conn.commit()
        _LOGGER.info("Banco de dados e tabelas verificados/criados com sucesso.")

    async def async_update_concessionarias(self, nomes_concessionarias: set[str]):
        """
        Atualiza a lista de concessionárias sem duplicar registros existentes.
        """
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute("SELECT nome FROM concessionarias")
            existentes = {row[0] for row in await cursor.fetchall()}

            novas_para_adicionar = nomes_concessionarias - existentes
            if not novas_para_adicionar:
                _LOGGER.info("Nenhuma nova concessionária para adicionar.")
                return

            _LOGGER.info(
                "Adicionando %s novas concessionárias.",
                len(novas_para_adicionar),
            )
            await conn.executemany(
                "INSERT OR IGNORE INTO concessionarias (nome) VALUES (?)",
                [(nome,) for nome in novas_para_adicionar],
            )
            await conn.commit()

    async def async_update_tarifas(self, concessionaria_nome, tarifas_data):
        """
        Atualiza ou insere as tarifas de uma concessionária.
        'tarifas_data' deve ser um dicionário, ex: {'Bandeira Verde': 0.50}.
        """
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("PRAGMA foreign_keys = ON")

            # Garante que a concessionaria exista.
            await conn.execute(
                "INSERT OR IGNORE INTO concessionarias (nome) VALUES (?)",
                (concessionaria_nome,),
            )

            cursor = await conn.execute(
                "SELECT id FROM concessionarias WHERE nome = ?",
                (concessionaria_nome,),
            )
            row = await cursor.fetchone()
            if row is None:
                _LOGGER.error(
                    "Falha ao obter concessionária '%s' no banco.",
                    concessionaria_nome,
                )
                return

            concessionaria_id = row[0]

            for bandeira, valor in tarifas_data.items():
                await conn.execute(
                    """
                    INSERT INTO tarifas (bandeira, valor, unidade, concessionaria_id)
                    VALUES (?, ?, 'R$/kWh', ?)
                    ON CONFLICT(concessionaria_id, bandeira)
                    DO UPDATE SET valor = excluded.valor
                    """,
                    (bandeira, valor, concessionaria_id),
                )

            await conn.commit()

    async def async_get_tarifas(self, concessionaria_nome):
        """Busca todas as tarifas de uma concessionária."""
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                """
                SELECT t.bandeira, t.valor
                FROM tarifas t
                JOIN concessionarias c ON c.id = t.concessionaria_id
                WHERE c.nome = ?
                """,
                (concessionaria_nome,),
            )
            rows = await cursor.fetchall()
            return dict(rows)

    async def async_get_all_concessionarias(self) -> list[str]:
        """Busca o nome de todas as concessionárias no banco de dados."""
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT nome FROM concessionarias ORDER BY nome"
            )
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

