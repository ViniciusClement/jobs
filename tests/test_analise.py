"""Testes das fórmulas da seção 12 com números calculados à mão (4 vagas:
A, B, C, D) e da elegibilidade da seção 11.

Vaga A (BR): grupo g1 {Python, Go} obrigatório (peso 1.0) atendido por 1 só
  membro (Python); Burp Suite mencionado (peso 0.6) não atendido.
  Unidades: g1(1.0) + Burp Suite(0.6) = total 1.6; atendido = 1.0.
Vaga B (BR): Nmap obrigatório (peso 1.0, já resolvido como "classe de maior
  peso" entre seções) atendido; grupo g2 {OSCP, OSEP} diferencial (peso 0.4)
  NÃO atendido (nenhum membro no CV).
  Unidades: Nmap(1.0) + g2(0.4) = total 1.4; atendido = 1.0.
Vaga C (INT, cidadania US incompatível com perfil BR): sem skills.
  Unidades: nenhuma -> match_vaga = None (divisão por zero tratada).
Vaga D (INT, acessível, clearance 'secret' diferencial não atendido):
  MITRE ATT&CK mencionado (peso 0.6), não atendido.
  Unidades: MITRE ATT&CK(0.6) = total 0.6; atendido = 0.

skills_cv = {Python, Nmap}.
"""

import unittest
from datetime import date

from radar import analise

HOJE = date(2026, 10, 22)

PERFIL = {
    "cidadanias": ["BR"],
    "residencia": "BR",
    "clearances": [],
    "aceita_relocacao": False,
    "idiomas": {"pt": "nativo", "en": "intermediario"},
}

SKILLS_CV = {("Linguagens", "Python"), ("Ferramentas de pentest", "Nmap")}


def _skill(categoria, skill, classe, peso, grupo=None):
    return {"categoria": categoria, "skill": skill, "classe": classe, "peso": peso,
            "evidencia": "evidência de teste", "grupo_alternativo": grupo}


VAGA_A = {
    "id": "v-a", "mercado": "BR", "familia_cargo": "pentest",
    "restricoes": {"cidadania": None, "residencia": None, "clearance": None, "clearance_obrigatorio": None, "outras": []},
    "ingles_nivel": None,
    "skills": [
        _skill("Linguagens", "Python", "obrigatorio", 1.0, grupo="g1"),
        _skill("Linguagens", "Go", "obrigatorio", 1.0, grupo="g1"),
        _skill("Ferramentas de pentest", "Burp Suite", "mencionado", 0.6),
    ],
}

VAGA_B = {
    "id": "v-b", "mercado": "BR", "familia_cargo": "pentest",
    "restricoes": {"cidadania": None, "residencia": None, "clearance": None, "clearance_obrigatorio": None, "outras": []},
    "ingles_nivel": None,
    "skills": [
        _skill("Ferramentas de pentest", "Nmap", "obrigatorio", 1.0),
        _skill("Certificações ofensivas", "OSCP", "diferencial", 0.4, grupo="g2"),
        _skill("Certificações ofensivas", "OSEP", "diferencial", 0.4, grupo="g2"),
    ],
}

VAGA_C = {
    "id": "v-c", "mercado": "INT", "familia_cargo": "pentest",
    "restricoes": {"cidadania": ["US"], "residencia": None, "clearance": None, "clearance_obrigatorio": None, "outras": []},
    "ingles_nivel": None,
    "skills": [],
}

VAGA_D = {
    "id": "v-d", "mercado": "INT", "familia_cargo": "red_team",
    "restricoes": {"cidadania": None, "residencia": None, "clearance": "secret", "clearance_obrigatorio": False, "outras": []},
    "ingles_nivel": None,
    "skills": [
        _skill("Metodologias e frameworks", "MITRE ATT&CK", "mencionado", 0.6),
    ],
}

TODAS = [VAGA_A, VAGA_B, VAGA_C, VAGA_D]


class TestMatchVaga(unittest.TestCase):
    def test_grupo_atendido_por_um_membro(self):
        self.assertAlmostEqual(analise.match_vaga(VAGA_A, SKILLS_CV), 1.0 / 1.6)

    def test_grupo_nao_atendido(self):
        self.assertAlmostEqual(analise.match_vaga(VAGA_B, SKILLS_CV), 1.0 / 1.4)

    def test_vaga_sem_skills_retorna_none(self):
        self.assertIsNone(analise.match_vaga(VAGA_C, SKILLS_CV))

    def test_vaga_sem_match_retorna_zero(self):
        self.assertEqual(analise.match_vaga(VAGA_D, SKILLS_CV), 0.0)


class TestCoberturaGeral(unittest.TestCase):
    def test_cobertura_geral_quatro_vagas(self):
        # total = 1.6 + 1.4 + 0 + 0.6 = 3.6 ; atendido = 1.0 + 1.0 + 0 + 0 = 2.0
        self.assertAlmostEqual(analise.cobertura_geral(TODAS, SKILLS_CV), 2.0 / 3.6)

    def test_recorte_vazio_retorna_none(self):
        self.assertIsNone(analise.cobertura_geral([], SKILLS_CV))


class TestLacunas(unittest.TestCase):
    def test_score_lacuna_calculado_a_mao(self):
        lacunas = {(l["categoria"], l["skill"]): l for l in analise.calcular_lacunas(TODAS, SKILLS_CV)}
        n_total = 4

        # Go: grupo g1 atendido por Python -> NÃO é lacuna em A -> não aparece.
        self.assertNotIn(("Linguagens", "Go"), lacunas)

        # Burp Suite: lacuna só em A, peso 0.6 -> 0.6/4 = 0.15
        self.assertAlmostEqual(lacunas[("Ferramentas de pentest", "Burp Suite")]["score_lacuna"], 0.6 / n_total)

        # OSCP e OSEP: grupo g2 não atendido em B -> ambos lacuna, peso 0.4 cada -> 0.1
        self.assertAlmostEqual(lacunas[("Certificações ofensivas", "OSCP")]["score_lacuna"], 0.4 / n_total)
        self.assertAlmostEqual(lacunas[("Certificações ofensivas", "OSEP")]["score_lacuna"], 0.4 / n_total)

        # MITRE ATT&CK: lacuna em D, peso 0.6 -> 0.6/4 = 0.15
        self.assertAlmostEqual(lacunas[("Metodologias e frameworks", "MITRE ATT&CK")]["score_lacuna"], 0.6 / n_total)

    def test_lacunas_recorte_vazio(self):
        self.assertEqual(analise.calcular_lacunas([], SKILLS_CV), [])


class TestRankingSkills(unittest.TestCase):
    def test_ranking_cada_skill_conta_individualmente_mesmo_em_grupo(self):
        ranking = {(r["categoria"], r["skill"]): r for r in analise.ranking_skills(TODAS)}
        n_total = 4
        # Python e Go contam cada um com peso 1.0 em A, mesmo estando no mesmo grupo.
        self.assertAlmostEqual(ranking[("Linguagens", "Python")]["score"], 1.0 / n_total)
        self.assertAlmostEqual(ranking[("Linguagens", "Go")]["score"], 1.0 / n_total)
        self.assertAlmostEqual(ranking[("Ferramentas de pentest", "Burp Suite")]["score"], 0.6 / n_total)
        self.assertAlmostEqual(ranking[("Ferramentas de pentest", "Nmap")]["score"], 1.0 / n_total)
        self.assertAlmostEqual(ranking[("Certificações ofensivas", "OSCP")]["score"], 0.4 / n_total)
        self.assertEqual(ranking[("Linguagens", "Python")]["n_vagas"], 1)

    def test_ranking_recorte_vazio(self):
        self.assertEqual(analise.ranking_skills([]), [])


class TestRecortes(unittest.TestCase):
    def test_br(self):
        resultado = analise.filtrar_recorte(TODAS, "BR", PERFIL)
        self.assertEqual({v["id"] for v in resultado}, {"v-a", "v-b"})

    def test_int_acessivel(self):
        # D não tem restrição de cidadania/residência -> acessível (clearance não entra nesse recorte).
        resultado = analise.filtrar_recorte(TODAS, "INT_acessivel", PERFIL)
        self.assertEqual({v["id"] for v in resultado}, {"v-d"})

    def test_int_restrito(self):
        # C exige cidadania US, incompatível com perfil BR sem relocação.
        resultado = analise.filtrar_recorte(TODAS, "INT_restrito", PERFIL)
        self.assertEqual({v["id"] for v in resultado}, {"v-c"})

    def test_todos(self):
        resultado = analise.filtrar_recorte(TODAS, "todos", PERFIL)
        self.assertEqual(len(resultado), 4)

    def test_recorte_vazio_para_ranking_e_cobertura(self):
        # Só VAGA_C é INT, e exige cidadania US incompatível com este perfil (BR) -> INT_acessivel vazio.
        vazio = analise.filtrar_recorte([VAGA_C], "INT_acessivel", PERFIL)
        self.assertEqual(vazio, [])
        self.assertEqual(analise.ranking_skills(vazio), [])
        self.assertIsNone(analise.cobertura_geral(vazio, SKILLS_CV))


class TestElegibilidade(unittest.TestCase):
    def test_sim_sem_restricoes(self):
        status, _ = analise.calcular_elegibilidade(VAGA_A, PERFIL)
        self.assertEqual(status, "sim")

    def test_nao_por_cidadania_incompativel(self):
        status, motivos = analise.calcular_elegibilidade(VAGA_C, PERFIL)
        self.assertEqual(status, "nao")
        self.assertTrue(any("cidadania" in m for m in motivos))

    def test_talvez_por_clearance_diferencial(self):
        status, motivos = analise.calcular_elegibilidade(VAGA_D, PERFIL)
        self.assertEqual(status, "talvez")
        self.assertTrue(any("clearance" in m for m in motivos))

    def test_nao_por_clearance_obrigatorio(self):
        vaga = dict(VAGA_D)
        vaga["restricoes"] = dict(VAGA_D["restricoes"], clearance_obrigatorio=True)
        status, _ = analise.calcular_elegibilidade(vaga, PERFIL)
        self.assertEqual(status, "nao")

    def test_talvez_por_relocacao_aceita(self):
        vaga = {
            "restricoes": {"cidadania": None, "residencia": "US", "clearance": None, "clearance_obrigatorio": None, "outras": []},
            "ingles_nivel": None,
        }
        perfil_relocavel = dict(PERFIL, aceita_relocacao=True)
        status, _ = analise.calcular_elegibilidade(vaga, perfil_relocavel)
        self.assertEqual(status, "talvez")

    def test_nao_por_residencia_sem_relocacao(self):
        vaga = {
            "restricoes": {"cidadania": None, "residencia": "US", "clearance": None, "clearance_obrigatorio": None, "outras": []},
            "ingles_nivel": None,
        }
        status, _ = analise.calcular_elegibilidade(vaga, PERFIL)
        self.assertEqual(status, "nao")


class TestOutrasFormulas(unittest.TestCase):
    def test_qualidade_dados_recorte_vazio(self):
        q = analise.qualidade_dados([])
        self.assertEqual(q["n_vagas"], 0)
        self.assertEqual(q["possivelmente_expiradas"], 0)

    def test_qualidade_dados_conta_expiradas_e_estimadas(self):
        vagas = [
            {"possivelmente_expirada": True, "data_estimada": False, "anos_experiencia": None},
            {"possivelmente_expirada": False, "data_estimada": True, "anos_experiencia": {"ambiguo": True}},
        ]
        q = analise.qualidade_dados(vagas)
        self.assertEqual(q["possivelmente_expiradas"], 1)
        self.assertEqual(q["datas_estimadas"], 1)
        self.assertEqual(q["anos_ambiguos"], 1)

    def test_faixas_salariais_sem_converter_moeda(self):
        vagas = [
            {"salario": {"min": 100, "max": 200, "moeda": "USD", "periodo": "ano"}},
            {"salario": {"min": 300, "max": None, "moeda": "USD", "periodo": "ano"}},
            {"salario": {"min": 1000, "max": 2000, "moeda": "BRL", "periodo": "mes"}},
            {"salario": None},
        ]
        faixas = {(f["moeda"], f["periodo"]): f for f in analise.faixas_salariais(vagas)}
        usd = faixas[("USD", "ano")]
        # valores representativos: (100+200)/2=150 ; 300 -> min=150, mediana=225, max=300
        self.assertEqual(usd["n"], 2)
        self.assertEqual(usd["min"], 150)
        self.assertEqual(usd["max"], 300)
        self.assertIn(("BRL", "mes"), faixas)

    def test_coocorrencia_basica(self):
        vagas = [VAGA_A, VAGA_B]
        pares = analise.coocorrencia_skills(vagas)
        chaves = {(p["skill_a"], p["skill_b"]) for p in pares}
        self.assertIn(("Go", "Python"), chaves)

    def test_distribuicao_simples(self):
        dist = analise.distribuicao(TODAS, "mercado")
        self.assertEqual(dist["BR"]["n"], 2)
        self.assertEqual(dist["INT"]["n"], 2)

    def test_distribuicao_recorte_vazio(self):
        self.assertEqual(analise.distribuicao([], "mercado"), {})

    def test_tendencia_dados_insuficientes_com_poucas_vagas(self):
        resultado = analise.tendencia_skills(TODAS, HOJE)
        self.assertEqual(resultado["status"], "dados insuficientes")


if __name__ == "__main__":
    unittest.main()
