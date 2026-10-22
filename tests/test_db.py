import tempfile
import unittest
from pathlib import Path

from radar import db


class TestVagas(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.conn = db.conectar(Path(self.tmpdir.name) / "radar.db")

    def tearDown(self):
        self.conn.close()
        self.tmpdir.cleanup()

    def test_vazio_no_inicio(self):
        self.assertEqual(db.contar_vagas(self.conn), 0)
        self.assertEqual(db.listar_vagas(self.conn), [])

    def test_salvar_e_listar(self):
        vaga = {"id": "v-1", "chave_dedup": "k1", "titulo": "Pentester"}
        db.salvar_vagas_em_lote(self.conn, [vaga])
        self.assertEqual(db.contar_vagas(self.conn), 1)
        self.assertEqual(db.listar_vagas(self.conn), [vaga])
        self.assertEqual(db.obter_vaga(self.conn, "v-1"), vaga)

    def test_upsert_por_id_atualiza_em_vez_de_duplicar(self):
        db.salvar_vagas_em_lote(self.conn, [{"id": "v-1", "chave_dedup": "k1", "titulo": "A"}])
        db.salvar_vagas_em_lote(self.conn, [{"id": "v-1", "chave_dedup": "k1", "titulo": "B"}])
        self.assertEqual(db.contar_vagas(self.conn), 1)
        self.assertEqual(db.obter_vaga(self.conn, "v-1")["titulo"], "B")

    def test_chave_dedup_e_unica(self):
        db.salvar_vagas_em_lote(self.conn, [{"id": "v-1", "chave_dedup": "k1", "titulo": "A"}])
        with self.assertRaises(Exception):
            db.salvar_vagas_em_lote(self.conn, [{"id": "v-2", "chave_dedup": "k1", "titulo": "B"}])

    def test_substituir_todas_as_vagas(self):
        db.salvar_vagas_em_lote(self.conn, [{"id": "v-1", "chave_dedup": "k1", "titulo": "A"}])
        db.substituir_todas_as_vagas(self.conn, [{"id": "v-2", "chave_dedup": "k2", "titulo": "B"}])
        self.assertEqual(db.contar_vagas(self.conn), 1)
        self.assertIsNone(db.obter_vaga(self.conn, "v-1"))
        self.assertIsNotNone(db.obter_vaga(self.conn, "v-2"))

    def test_substituir_por_lista_vazia_esvazia(self):
        db.salvar_vagas_em_lote(self.conn, [{"id": "v-1", "chave_dedup": "k1", "titulo": "A"}])
        db.substituir_todas_as_vagas(self.conn, [])
        self.assertEqual(db.contar_vagas(self.conn), 0)

    def test_obter_vaga_inexistente_retorna_none(self):
        self.assertIsNone(db.obter_vaga(self.conn, "nao-existe"))


class TestPerfil(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.conn = db.conectar(Path(self.tmpdir.name) / "radar.db")

    def tearDown(self):
        self.conn.close()
        self.tmpdir.cleanup()

    def test_sem_perfil_retorna_none(self):
        self.assertIsNone(db.obter_perfil(self.conn))

    def test_salvar_e_obter(self):
        perfil = {"cidadanias": ["BR"], "residencia": "BR"}
        db.salvar_perfil(self.conn, perfil)
        self.assertEqual(db.obter_perfil(self.conn), perfil)

    def test_salvar_duas_vezes_sobrescreve(self):
        db.salvar_perfil(self.conn, {"cidadanias": ["BR"]})
        db.salvar_perfil(self.conn, {"cidadanias": ["US"]})
        self.assertEqual(db.obter_perfil(self.conn), {"cidadanias": ["US"]})


class TestPerfilProfissional(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.conn = db.conectar(Path(self.tmpdir.name) / "radar.db")

    def tearDown(self):
        self.conn.close()
        self.tmpdir.cleanup()

    def test_sem_perfil_profissional_retorna_none(self):
        self.assertIsNone(db.obter_perfil_profissional(self.conn))

    def test_salvar_e_obter(self):
        perfil = {"nome": "Fulano", "headline": "Pentester", "experiencias": []}
        db.salvar_perfil_profissional(self.conn, perfil)
        self.assertEqual(db.obter_perfil_profissional(self.conn), perfil)

    def test_salvar_duas_vezes_sobrescreve(self):
        db.salvar_perfil_profissional(self.conn, {"nome": "A"})
        db.salvar_perfil_profissional(self.conn, {"nome": "B"})
        self.assertEqual(db.obter_perfil_profissional(self.conn), {"nome": "B"})


class TestElegibilidade(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.conn = db.conectar(Path(self.tmpdir.name) / "radar.db")

    def tearDown(self):
        self.conn.close()
        self.tmpdir.cleanup()

    def test_vazio_no_inicio(self):
        self.assertEqual(db.obter_elegibilidade(self.conn), {})

    def test_salvar_substitui_tudo(self):
        db.salvar_elegibilidade(self.conn, {"v-1": {"elegivel": "sim", "motivos": []}})
        db.salvar_elegibilidade(self.conn, {"v-2": {"elegivel": "nao", "motivos": ["x"]}})
        self.assertEqual(db.obter_elegibilidade(self.conn), {"v-2": {"elegivel": "nao", "motivos": ["x"]}})


class TestHistorico(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.conn = db.conectar(Path(self.tmpdir.name) / "radar.db")

    def tearDown(self):
        self.conn.close()
        self.tmpdir.cleanup()

    def test_registrar_e_listar(self):
        db.registrar_historico(self.conn, {"data": "2026-10-20", "recorte": "todos", "n_vagas_ativas": 3, "cobertura_geral": 0.5})
        self.assertEqual(len(db.listar_historico(self.conn)), 1)

    def test_sobrescreve_mesmo_dia_e_recorte(self):
        db.registrar_historico(self.conn, {"data": "2026-10-20", "recorte": "todos", "n_vagas_ativas": 3, "cobertura_geral": 0.5})
        db.registrar_historico(self.conn, {"data": "2026-10-20", "recorte": "todos", "n_vagas_ativas": 5, "cobertura_geral": 0.7})
        entradas = db.listar_historico(self.conn)
        self.assertEqual(len(entradas), 1)
        self.assertEqual(entradas[0]["n_vagas_ativas"], 5)

    def test_dias_diferentes_nao_se_sobrescrevem(self):
        db.registrar_historico(self.conn, {"data": "2026-10-20", "recorte": "todos", "n_vagas_ativas": 3, "cobertura_geral": 0.5})
        db.registrar_historico(self.conn, {"data": "2026-10-21", "recorte": "todos", "n_vagas_ativas": 4, "cobertura_geral": 0.6})
        self.assertEqual(len(db.listar_historico(self.conn)), 2)

    def test_recortes_diferentes_mesmo_dia_nao_se_sobrescrevem(self):
        db.registrar_historico(self.conn, {"data": "2026-10-20", "recorte": "BR", "n_vagas_ativas": 1, "cobertura_geral": None})
        db.registrar_historico(self.conn, {"data": "2026-10-20", "recorte": "todos", "n_vagas_ativas": 3, "cobertura_geral": 0.5})
        self.assertEqual(len(db.listar_historico(self.conn)), 2)


if __name__ == "__main__":
    unittest.main()
