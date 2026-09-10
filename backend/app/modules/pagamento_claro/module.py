"""
Pagamento da telefonia móvel Claro — lançamento no Contas a Pagar.

Processo da área de TI: chegam N boletos da Claro (a quantidade varia todo mês),
cada um cobrindo uma parte das linhas da empresa. Cada boleto vira UM título no
Contas a Pagar, com os valores distribuídos pelos centros de custo das linhas.

Não há NF a reconciliar (a entrada não passa por pré-nota) e não há cálculo de
rateio: a Claro já entrega o valor por linha. O trabalho da plataforma é ler,
casar cada linha com seu centro de custo e conferir os totais antes de lançar.

Peças: `parser` (lê o PDF) e `calculator` (casa com o cadastro e consolida).
"""

from datetime import date
from decimal import Decimal
from typing import Any

from app.modules.base import ItemRateio, RateioModule, ValidationResult

from . import calculator, parser


class PagamentoClaroRateio(RateioModule):
    """Faturas Claro: um título de Contas a Pagar por boleto, rateado por CC."""

    tipo: str = "pagamento-claro"
    nome: str = "Telefonia Claro"
    descricao: str = (
        "Pagamento das faturas da Claro, com um título por boleto e rateio pelo "
        "centro de custo de cada linha."
    )
    lanca_no_erp: bool = True
    # Notifica o fiscal: boletos em anexo + nº dos títulos, num envio só, depois
    # que TODOS os boletos foram lançados.
    notifica_fiscal: bool = True
    fornecedor: str = "claro"
    # O casamento é por número de linha (cadastro próprio), não por CPF: não há
    # motivo para consultar o Protheus e ficar refém dele neste processo.
    usa_colaboradores: bool = False

    # -----------------------------------------------------------------
    # Contrato base
    # -----------------------------------------------------------------
    def validar_inputs(
        self, arquivos: dict[str, bytes], dados_externos: dict[str, Any]
    ) -> ValidationResult:
        """
        Confere que todo PDF enviado é um boleto legível e que FECHA.

        Erro (bloqueia): nenhum arquivo, arquivo que não é PDF, PDF ilegível, um
        boleto cuja soma das linhas não bate com o total impresso, ou o mesmo
        boleto enviado duas vezes.

        Alerta (não bloqueia): linhas fora do cadastro. É de propósito — a prévia
        precisa ser exibida para o usuário cadastrá-las ali mesmo. O bloqueio do
        envio ao ERP fica em `resultado["bloqueado"]`.
        """
        erros: list[str] = []
        alertas: list[str] = []

        pdfs = {n: c for n, c in arquivos.items() if n.lower().endswith(parser.EXTENSOES_BOLETO)}
        if not arquivos:
            return ValidationResult(False, ["Envie ao menos um boleto da Claro (PDF)."], [])
        for nome in arquivos:
            if nome not in pdfs:
                erros.append(f"'{nome}' não é um PDF — envie os boletos da Claro em PDF.")

        contas_vistas: dict[str, str] = {}
        for nome, conteudo in pdfs.items():
            try:
                boleto = parser.ler_boleto(nome, conteudo)
            except parser.BoletoInvalido as exc:
                erros.append(str(exc))
                continue

            if boleto.valor_total is None:
                erros.append(f"'{nome}': não foi possível ler o 'Total a pagar' do boleto.")
            elif not boleto.confere:
                # A mensagem carrega a decomposição declarada na pág. 1 e o que
                # conseguimos ler: assim uma cobrança de tipo novo se identifica
                # sozinha, em vez de virar uma investigação do zero.
                erros.append(
                    f"'{nome}': o boleto não fecha. Total a pagar R$ {boleto.valor_total}; "
                    f"lemos R$ {boleto.valor_linhas} nas linhas e R$ {boleto.valor_ajustes} "
                    f"em lançamentos da conta — sobra R$ {boleto.diferenca}. "
                    f"O boleto declara: {boleto.resumo_categorias() or 'sem resumo legível'}. "
                    "Há uma cobrança que ainda não sabemos ler; o boleto não será lançado."
                )

            chave = f"{boleto.conta}|{boleto.competencia}"
            if boleto.conta and chave in contas_vistas:
                erros.append(
                    f"'{nome}' e '{contas_vistas[chave]}' são o mesmo boleto "
                    f"(conta {boleto.conta}, competência {boleto.competencia}) — envie só um."
                )
            elif boleto.conta:
                contas_vistas[chave] = nome

            alertas.extend(self._alertas_do_boleto(boleto, dados_externos))

        return ValidationResult(valido=not erros, erros=erros, alertas=alertas)

    def processar(
        self, arquivos: dict[str, bytes], dados_externos: dict[str, Any]
    ) -> list[ItemRateio]:
        """Uma linha telefônica por item (contrato base; usado no CSV)."""
        return self.resultado_para_itens(self.processar_completo(arquivos, dados_externos))

    # -----------------------------------------------------------------
    # Resultado rico (prévia) — protocolo processar_completo/resumo
    # -----------------------------------------------------------------
    def processar_completo(
        self, arquivos: dict[str, bytes], dados_externos: dict[str, Any]
    ) -> dict[str, Any]:
        """Consolida os boletos: um título por boleto, itens por centro de custo."""
        boletos = [
            parser.ler_boleto(nome, conteudo)
            for nome, conteudo in arquivos.items()
            if nome.lower().endswith(parser.EXTENSOES_BOLETO)
        ]
        # Boleto mais antigo primeiro: a ordem da prévia acompanha o vencimento.
        # Sem data legível vai para o fim (`date.max`) — nunca misture date e str
        # na chave, senão a comparação estoura quando um boleto vier sem data.
        boletos.sort(key=lambda b: (b.vencimento or b.emissao or date.max, b.conta))
        return calculator.consolidar(
            boletos, self._cadastro(dados_externos), self._contabil(dados_externos)
        )

    def resultado_para_itens(self, resultado: dict[str, Any]) -> list[ItemRateio]:
        """
        Achata a consolidação num item por linha telefônica.

        `departamento` recebe o centro de custo: a telefonia não tem departamento
        próprio no cadastro, e é o CC que o lançamento persegue.
        """
        itens: list[ItemRateio] = []
        # Contas fixas do processo: repetidas em cada linha para o CSV ficar
        # autocontido na mão da contabilidade.
        contabil = resultado.get("contabil") or {}
        for boleto in resultado["boletos"]:
            for linha in boleto["linhas"]:
                itens.append(
                    ItemRateio(
                        colaborador_cpf=linha["colaborador_cpf"],
                        colaborador_nome=linha["colaborador_nome"],
                        departamento=linha["centro_custo"],
                        centro_de_custo=linha["centro_custo"],
                        valor=linha["valor"],
                        historico=(
                            f"Telefonia Claro {boleto['competencia']} - "
                            f"linha {linha['numero_exibicao']}"
                        ),
                        extras={
                            "linha": linha["numero_exibicao"],
                            "classe_valor": linha["classe_valor"],
                            "conta_debito": contabil.get("conta_debito", ""),
                            "conta_credito": contabil.get("conta_credito", ""),
                            "boleto_conta": boleto["conta"],
                            "boleto_arquivo": boleto["arquivo"],
                            "vencimento": boleto["vencimento"],
                            "competencia": boleto["competencia"],
                            "valor_mensalidades": str(linha["valor_mensalidades"]),
                            "valor_excedente": str(linha["valor_uso"]),
                            "cadastro_completo": "sim" if linha["completa"] else "nao",
                        },
                    )
                )
        return itens

    def titulos_erp(self, resultado: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Títulos a lançar no ERP: UM por boleto (regra do processo).

        Cada título traz a `referencia` que o identifica (a conta da Claro — é ela
        que aparece no boleto e amarra o título de volta a ele), a observação que
        vai no lançamento e as `linhas` por centro de custo, já com os lançamentos
        de conta rateados, de modo que somem o valor do boleto.

        Puro: só reorganiza o snapshot. Quem sabe de contrato, AE e HTTP é o
        serviço — aqui fica a regra de o que compõe cada título.
        """
        titulos: list[dict[str, Any]] = []
        for boleto in resultado.get("boletos") or []:
            referencia = str(boleto.get("conta") or boleto.get("arquivo") or "").strip()
            competencia = str(boleto.get("competencia") or "").strip()
            titulos.append({
                "referencia": referencia,
                "competencia": competencia,
                "valor": boleto.get("valor_total"),
                # Rastro do título até o boleto, dentro do ERP: numa execução com
                # vários boletos, é o que diz de qual conta veio cada título.
                "observacao": f"Telefonia Claro {competencia} · conta {referencia}".strip(),
                "linhas": [
                    {
                        "centro_custo": item["centro_custo"],
                        "classe_valor": item["classe_valor"],
                        "valor": item["valor"],
                    }
                    for item in boleto.get("por_centro_custo") or []
                ],
            })
        return titulos

    def resumo(self, resultado: dict[str, Any]) -> dict[str, Any]:
        """Snapshot devolvido ao frontend para montar a prévia."""
        return {
            **resultado,
            "por_centro_custo": calculator.totais_por_centro_custo(resultado),
        }

    # -----------------------------------------------------------------
    # Apoio
    # -----------------------------------------------------------------
    @staticmethod
    def _cadastro(dados_externos: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return dados_externos.get("linhas_telefonicas") or {}

    @staticmethod
    def _contabil(dados_externos: dict[str, Any]) -> dict[str, str]:
        """Contas de débito/crédito — fixas do processo, não variam por linha."""
        return dados_externos.get("parametros_telefonia") or {}

    def _alertas_do_boleto(
        self, boleto: parser.BoletoClaro, dados_externos: dict[str, Any]
    ) -> list[str]:
        """Avisos não bloqueantes de um boleto (cadastro incompleto/desatualizado)."""
        cadastro = self._cadastro(dados_externos)
        alertas: list[str] = []

        # Cobradas: travam o lançamento. Zeradas: só avisam — não entram em item
        # nenhum do título, então não há o que travar (ver `calculator`).
        sem_cadastro = [l for l in boleto.linhas if l.numero not in cadastro and l.valor > 0]
        if sem_cadastro:
            valor = sum((l.valor for l in sem_cadastro), Decimal("0"))
            alertas.append(
                f"'{boleto.nome_arquivo}': {len(sem_cadastro)} linha(s) fora do cadastro, "
                f"somando R$ {valor}. Cadastre-as para liberar o lançamento."
            )

        zeradas = [l for l in boleto.linhas if l.numero not in cadastro and l.valor == 0]
        if zeradas:
            numeros = ", ".join(l.numero_exibicao for l in zeradas)
            alertas.append(
                f"'{boleto.nome_arquivo}': linha(s) fora do cadastro sem valor cobrado neste "
                f"boleto. Não travam o lançamento, mas convém cadastrar: {numeros}."
            )

        # Cadastradas antes de a classe de valor virar obrigatória: o ERP recusa
        # o lançamento sem ela, então precisam ser completadas do mesmo jeito.
        incompletas = [
            l for l in boleto.linhas
            if (reg := cadastro.get(l.numero))
            and not (reg.get("centro_custo") and reg.get("classe_valor"))
        ]
        if incompletas:
            numeros = ", ".join(l.numero_exibicao for l in incompletas)
            alertas.append(
                f"'{boleto.nome_arquivo}': linha(s) cadastrada(s) sem centro de custo ou sem "
                f"classe de valor — complete o cadastro: {numeros}."
            )

        inativas = [
            l for l in boleto.linhas
            if l.numero in cadastro and not cadastro[l.numero].get("ativo", True)
        ]
        if inativas:
            numeros = ", ".join(l.numero_exibicao for l in inativas)
            alertas.append(
                f"'{boleto.nome_arquivo}': linha(s) marcada(s) como inativa(s) no cadastro "
                f"continuam sendo cobradas: {numeros}."
            )

        # Linha cobrada num boleto diferente do que o cadastro aponta: ela migrou
        # de conta. Não muda o lançamento (o CC é o que importa), mas o cadastro
        # precisa ser corrigido, senão a conferência por conta perde o valor.
        migradas = [
            l for l in boleto.linhas
            if (conta := cadastro.get(l.numero, {}).get("conta", ""))
            and boleto.conta
            and conta != boleto.conta
        ]
        if migradas:
            numeros = ", ".join(
                f"{l.numero_exibicao} (cadastrada na conta {cadastro[l.numero]['conta']})"
                for l in migradas
            )
            alertas.append(
                f"'{boleto.nome_arquivo}': linha(s) cobrada(s) na conta {boleto.conta} mas "
                f"cadastrada(s) em outra — atualize o cadastro: {numeros}."
            )
        return alertas
