"""
Consolidação dos boletos da Claro para lançamento no Contas a Pagar.

Não há cálculo de rateio aqui: o valor de cada linha já vem do boleto. O que
este módulo faz é o CASAMENTO (linha -> centro de custo, pelo cadastro de
telefonia) e a CONSOLIDAÇÃO por centro de custo — cada boleto vira um título, e
cada centro de custo vira um item desse título.

Nada é enviado ao ERP enquanto houver linha fora do cadastro: sem centro de
custo, o valor não tem para onde ir. Essas linhas saem em `pendencias`, para o
usuário resolvê-las na própria prévia.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .parser import BoletoClaro, LinhaBoleto

# Centro de custo exibido enquanto a linha não tem cadastro.
SEM_CADASTRO = ""

_CENTAVOS = Decimal("0.01")


def _cadastro_da_linha(
    linha: LinhaBoleto, cadastro: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    return cadastro.get(linha.numero)


def _linha_consolidada(
    linha: LinhaBoleto,
    cadastro: dict[str, dict[str, Any]],
    conta_boleto: str,
) -> dict[str, Any]:
    """Uma linha do boleto já casada com o cadastro, pronta para a prévia."""
    registro = _cadastro_da_linha(linha, cadastro)
    conta_cadastro = (registro or {}).get("conta", "")
    centro_custo = (registro or {}).get("centro_custo", SEM_CADASTRO)
    classe_valor = (registro or {}).get("classe_valor", "")
    return {
        "numero": linha.numero,
        "numero_exibicao": linha.numero_exibicao,
        "centro_custo": centro_custo,
        "classe_valor": classe_valor,
        "colaborador_cpf": (registro or {}).get("colaborador_cpf", ""),
        "colaborador_nome": (registro or {}).get("colaborador_nome", ""),
        "cadastrada": registro is not None,
        # O ERP recusa lançamento sem centro de custo OU sem classe de valor, e
        # há registros antigos gravados antes de a classe virar obrigatória —
        # por isso `completa` não é sinônimo de `cadastrada`.
        "completa": bool(registro and centro_custo and classe_valor),
        # Conta do cadastro × conta do boleto onde a linha apareceu. Divergência
        # não impede nada (a cobrança é o fato); só avisa que a linha migrou de
        # conta e o cadastro está defasado. Cadastro sem conta = nada a conferir.
        "conta_cadastro": conta_cadastro,
        "conta_divergente": bool(conta_cadastro and conta_boleto and conta_cadastro != conta_boleto),
        # Linha inativa no cadastro que volta a ser cobrada: o valor entra
        # normalmente, mas o usuário precisa saber (pode ser linha esquecida).
        "ativa": bool((registro or {}).get("ativo", True)),
        "valor": linha.valor,
        "valor_mensalidades": linha.valor_mensalidades,
        "valor_uso": linha.valor_uso,
        "servicos": [
            {"descricao": s.descricao, "categoria": s.categoria, "valor": s.valor}
            for s in linha.servicos
        ],
    }


def _por_centro_custo(linhas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Agrupa as linhas por (centro de custo, classe) — é o que vira item do título.

    Linhas incompletas ficam de fora: elas ainda não têm destino contábil.
    """
    grupos: dict[tuple[str, str], dict[str, Any]] = {}
    for linha in linhas:
        if not linha["completa"]:
            continue
        chave = (linha["centro_custo"], linha["classe_valor"])
        grupo = grupos.setdefault(
            chave,
            {
                "centro_custo": chave[0],
                "classe_valor": chave[1],
                "qtd_linhas": 0,
                "valor": Decimal("0"),
            },
        )
        grupo["qtd_linhas"] += 1
        grupo["valor"] += linha["valor"]
    # Grupo que soma zero não vira item: a linha existe no boleto mas não está
    # sendo cobrada, e um item de R$ 0,00 no título é recusado pelo ERP. As
    # linhas seguem visíveis no detalhamento do boleto.
    return sorted(
        (g for g in grupos.values() if g["valor"] != 0),
        key=lambda g: (-g["valor"], g["centro_custo"]),
    )


def _distribuir_ajuste(grupos: list[dict[str, Any]], ajuste: Decimal) -> list[dict[str, Any]]:
    """
    Rateia um lançamento de conta (ex.: crédito de meses anteriores) entre os
    itens do título, proporcionalmente ao valor de cada um.

    O boleto não diz a qual linha o ajuste pertence — só que ele existe na conta.
    Distribuir na proporção é o mesmo critério que a plataforma já usa para os
    estornos do plano de saúde (`services/erp.py`). O resíduo de arredondamento
    vai para o maior item, garantindo que a soma feche EXATAMENTE com o boleto.

    Cada grupo ganha `valor_bruto` (o que as linhas somam) e `ajuste`, para a
    prévia poder explicar de onde veio a diferença.
    """
    total = sum((g["valor"] for g in grupos), Decimal("0"))
    for grupo in grupos:
        grupo["valor_bruto"] = grupo["valor"]
        grupo["ajuste"] = Decimal("0")
    if not grupos or ajuste == 0 or total <= 0:
        return grupos

    acumulado = Decimal("0")
    for grupo in grupos:
        parte = (ajuste * grupo["valor_bruto"] / total).quantize(_CENTAVOS, ROUND_HALF_UP)
        grupo["ajuste"] = parte
        grupo["valor"] = grupo["valor_bruto"] + parte
        acumulado += parte
    residuo = ajuste - acumulado
    if residuo != 0:
        maior = max(grupos, key=lambda g: g["valor_bruto"])
        maior["ajuste"] += residuo
        maior["valor"] += residuo
    return grupos


def _data(valor: Any) -> str:
    return valor.isoformat() if valor else ""


def consolidar_boleto(boleto: BoletoClaro, cadastro: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Um boleto consolidado = um título a lançar no Contas a Pagar."""
    linhas = [_linha_consolidada(l, cadastro, boleto.conta) for l in boleto.linhas]
    linhas.sort(key=lambda l: (-l["valor"], l["numero"]))
    incompletas = [l for l in linhas if not l["completa"]]

    return {
        "arquivo": boleto.nome_arquivo,
        "conta": boleto.conta,
        "cliente": boleto.cliente,
        "razao_social": boleto.razao_social,
        "cnpj_tomador": boleto.cnpj_tomador,
        "competencia": boleto.competencia,
        "periodo": f"{_data(boleto.periodo_inicio)} a {_data(boleto.periodo_fim)}",
        "vencimento": _data(boleto.vencimento),
        "emissao": _data(boleto.emissao),
        "linha_digitavel": boleto.linha_digitavel,
        "nfcom_numero": boleto.nfcom_numero,
        "nfcom_serie": boleto.nfcom_serie,
        "nfcom_chave": boleto.nfcom_chave,
        # Valor do título = o total impresso no boleto (o que será pago).
        "valor_total": boleto.valor_total or Decimal("0"),
        "valor_linhas": boleto.valor_linhas,
        "diferenca": boleto.diferenca,
        "confere": boleto.confere,
        "qtd_linhas": len(linhas),
        "qtd_incompletas": len(incompletas),
        "qtd_conta_divergente": sum(1 for l in linhas if l["conta_divergente"]),
        "valor_incompleto": sum((l["valor"] for l in incompletas), Decimal("0")),
        # Lançamentos da conta (não pertencem a linha nenhuma) e o efeito deles.
        "ajustes": [{"descricao": a.descricao, "valor": a.valor} for a in boleto.ajustes],
        "valor_ajustes": boleto.valor_ajustes,
        "linhas": linhas,
        # Itens do título: já com o ajuste rateado, para somarem o valor do boleto.
        "por_centro_custo": _distribuir_ajuste(_por_centro_custo(linhas), boleto.valor_ajustes),
    }


def consolidar(
    boletos: list[BoletoClaro],
    cadastro: dict[str, dict[str, Any]],
    contabil: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Consolida todos os boletos da execução.

    Cada boleto é independente (um título cada), mas as pendências de cadastro
    são reunidas num só lugar: a linha aparece uma vez, com os boletos em que
    foi cobrada, para o usuário resolver tudo de uma vez.

    `contabil` traz as contas de débito/crédito do processo (fixas, iguais para
    todas as linhas). Elas NÃO compõem mais o lançamento — o título é uma AE
    sobre o contrato de parceria, e o destino contábil vem do item do contrato —,
    então seguem apenas no detalhamento/CSV, sem bloquear o envio.
    """
    contabil = contabil or {}
    consolidados = [consolidar_boleto(b, cadastro) for b in boletos]

    pendencias: dict[str, dict[str, Any]] = {}
    for boleto in consolidados:
        for linha in boleto["linhas"]:
            if linha["completa"]:
                continue
            pendencia = pendencias.setdefault(
                linha["numero"],
                {
                    "numero": linha["numero"],
                    "numero_exibicao": linha["numero_exibicao"],
                    "valor": Decimal("0"),
                    "boletos": [],
                    # Só contas reais (sem cair no nome do arquivo): é o valor que
                    # o cadastro inline grava, então não pode ser um rótulo.
                    "contas": [],
                    # O que já existe do cadastro — o modal pré-preenche e o
                    # usuário só completa o que falta.
                    "cadastrada": linha["cadastrada"],
                    "centro_custo": linha["centro_custo"],
                    "classe_valor": linha["classe_valor"],
                    "colaborador_nome": linha["colaborador_nome"],
                },
            )
            pendencia["valor"] += linha["valor"]
            pendencia["boletos"].append(boleto["conta"] or boleto["arquivo"])
            if boleto["conta"] and boleto["conta"] not in pendencia["contas"]:
                pendencia["contas"].append(boleto["conta"])
    pendentes = sorted(pendencias.values(), key=lambda p: -p["valor"])

    # Linha sem cadastro mas COBRADA A ZERO não tem para onde ir porque não vai a
    # lugar nenhum: não entra em nenhum item do título e a soma continua batendo
    # com o boleto. Travar o lançamento por causa dela obrigaria a TI a inventar
    # um centro de custo para algo que não está sendo cobrado. Ela permanece na
    # lista de pendências (o usuário pode cadastrá-la agora, antes de a operadora
    # começar a cobrar), mas não bloqueia.
    for pendencia in pendentes:
        pendencia["bloqueia"] = pendencia["valor"] > 0

    # Motivos que impedem o lançamento, em texto — a UI lista, não interpreta.
    # Separa quem não existe no cadastro de quem existe mas está incompleto: são
    # ações diferentes para o usuário.
    bloqueios: list[str] = []
    bloqueantes = [p for p in pendentes if p["bloqueia"]]
    sem_cadastro = [p for p in bloqueantes if not p["cadastrada"]]
    incompletas = [p for p in bloqueantes if p["cadastrada"]]
    if sem_cadastro:
        valor = sum((p["valor"] for p in sem_cadastro), Decimal("0"))
        bloqueios.append(
            f"{len(sem_cadastro)} linha(s) fora do cadastro, somando R$ {valor}."
        )
    if incompletas:
        valor = sum((p["valor"] for p in incompletas), Decimal("0"))
        bloqueios.append(
            f"{len(incompletas)} linha(s) cadastrada(s) sem centro de custo ou sem classe "
            f"de valor, somando R$ {valor} — o ERP recusa o lançamento sem esses campos."
        )
    return {
        "boletos": consolidados,
        "pendencias": pendentes,
        # Contas fixas do processo: entram em todo título montado a partir daqui.
        "contabil": {
            "conta_debito": contabil.get("conta_debito", ""),
            "conta_credito": contabil.get("conta_credito", ""),
        },
        "bloqueios": bloqueios,
        "bloqueado": bool(bloqueios),
        "totais": {
            "qtd_boletos": len(consolidados),
            "valor_total": sum((b["valor_total"] for b in consolidados), Decimal("0")),
            "qtd_linhas": sum(b["qtd_linhas"] for b in consolidados),
            "qtd_incompletas": len(pendentes),
            "qtd_bloqueantes": len(bloqueantes),
            "valor_incompleto": sum((p["valor"] for p in pendentes), Decimal("0")),
            "qtd_conta_divergente": sum(b["qtd_conta_divergente"] for b in consolidados),
        },
    }


def totais_por_centro_custo(resultado: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Visão agregada de TODOS os boletos por centro de custo E CLASSE DE VALOR
    (leitura gerencial).

    A chave é o par, como nos itens do título: o mesmo centro de custo pode ter
    classes diferentes (linhas de naturezas distintas), e agregar só por centro
    de custo somaria destinos contábeis que o ERP recebe separados.

    Usa o valor JÁ ajustado de cada item, o mesmo que irá ao ERP — assim o
    consolidado fecha com a soma dos títulos, e não com a soma das linhas.
    """
    grupos: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"centro_custo": "", "classe_valor": "", "qtd_linhas": 0, "valor": Decimal("0")}
    )
    for boleto in resultado["boletos"]:
        for grupo in boleto["por_centro_custo"]:
            chave = (grupo["centro_custo"], grupo.get("classe_valor", ""))
            alvo = grupos[chave]
            alvo["centro_custo"], alvo["classe_valor"] = chave
            alvo["qtd_linhas"] += grupo["qtd_linhas"]
            alvo["valor"] += grupo["valor"]
    return sorted(grupos.values(), key=lambda g: (-g["valor"], g["centro_custo"]))
