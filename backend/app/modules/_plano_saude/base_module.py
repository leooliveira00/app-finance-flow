"""
Base compartilhada dos rateios de pagamento de plano de saúde.

Contém a orquestração comum a UNIMED e Bradesco. Cada operadora é exposta como
um rateio próprio (pacotes `pagamento_unimed` e `pagamento_bradesco`), que
herdam desta base e apenas definem `tipo`, `descricao` e `operadora`. Assim a
lógica de leitura/cálculo/reconciliação (parser/calculator/validators) é
totalmente reaproveitada — sem duplicação.

Este pacote começa com `_`, então o registry NÃO o descobre como rateio: ele é
só a biblioteca compartilhada. Os módulos concretos vivem nos pacotes sem `_`.

A base filtra tudo pela sua `operadora`: valida que a planilha daquela operadora
veio, processa apenas as linhas dela e reconcilia apenas o documento dela.

Puro: recebe `arquivos` (uploads) e `dados_externos` (colaboradores da API);
não acessa banco nem rede.
"""

from typing import Any

from app.modules.base import ItemRateio, RateioModule, ValidationResult

from . import calculator, parser, validators
from .calculator import ItemColaborador, ResultadoRateio

EXTENSAO_PDF = ".pdf"


class PagamentoPlanoSaudeBase(RateioModule):
    """Base de um rateio de pagamento de plano de saúde de UMA operadora."""

    # Definidos pela subclasse concreta (ver pagamento_unimed / pagamento_bradesco).
    tipo: str = ""
    descricao: str = ""
    operadora: str = ""  # "unimed" | "bradesco"
    # Todo pagamento de plano de saúde lança no ERP e notifica o fiscal.
    lanca_no_erp: bool = True
    notifica_fiscal: bool = True

    def validar_inputs(
        self,
        arquivos: dict[str, bytes],
        dados_externos: dict[str, Any],
    ) -> ValidationResult:
        """
        Valida os arquivos de forma ciente da operadora deste rateio.

        Erros (bloqueiam): não há planilha da operadora; a planilha da operadora
        tem colunas obrigatórias faltando. Alertas (não bloqueiam): arquivos de
        outra operadora, arquivos não reconhecidos e ausência de NF/boleto —
        todos são explicitamente sinalizados em vez de ignorados em silêncio.
        """
        op = self.operadora
        erros: list[str] = []
        alertas: list[str] = []

        planilhas = parser.classificar_planilhas(arquivos)        # {nome: op|None}
        documentos = validators.classificar_documentos(arquivos)  # {nome: (op,tipo)|None}
        extensoes_ok = parser.EXTENSOES_PLANILHA + (EXTENSAO_PDF,)

        # 1. Planilha da operadora presente e com colunas ok (bloqueante).
        if op not in planilhas.values():
            erros.append(
                f"Nenhuma planilha da operadora {op.upper()} foi enviada "
                "(a assinatura das colunas não corresponde a esta operadora)."
            )
        else:
            erros.extend(parser.colunas_faltando(arquivos, op))

        # 2. Planilhas de outra operadora / não reconhecidas (alerta, ignoradas).
        for nome, detectada in planilhas.items():
            if detectada and detectada != op:
                alertas.append(
                    f"Planilha '{nome}' é da operadora {detectada.upper()} e será "
                    "ignorada neste rateio."
                )
            elif detectada is None:
                alertas.append(
                    f"Planilha '{nome}' não foi reconhecida (colunas não batem com "
                    "nenhuma operadora) e será ignorada."
                )

        # 3. NF/boleto da operadora (alerta) + PDFs de outra operadora / não reconhecidos.
        if not any(v and v[0] == op for v in documentos.values()):
            alertas.append(
                f"Nenhuma NF/boleto da {op.upper()} enviado — a reconciliação dos "
                "valores faturados não será possível."
            )
        for nome, info in documentos.items():
            if info and info[0] != op:
                alertas.append(
                    f"Documento '{nome}' é da operadora {info[0].upper()} e será "
                    "ignorado neste rateio."
                )
            elif info is None:
                alertas.append(
                    f"Arquivo '{nome}' (PDF) não foi reconhecido como NF/boleto e "
                    "será ignorado."
                )

        # 4. Arquivos de formato não suportado (alerta, ignorados).
        for nome in arquivos:
            if not nome.lower().endswith(extensoes_ok):
                alertas.append(
                    f"Arquivo '{nome}' tem formato não suportado e será ignorado."
                )

        # 5. Colaboradores da API.
        if not (dados_externos or {}).get(calculator.CHAVE_COLABORADORES):
            alertas.append(
                "Lista de colaboradores da API ausente — todos os titulares "
                "cairão em divergência."
            )

        return ValidationResult(valido=not erros, erros=erros, alertas=alertas)

    def processar_completo(
        self,
        arquivos: dict[str, bytes],
        dados_externos: dict[str, Any],
    ) -> ResultadoRateio:
        """Executa o rateio e a reconciliação SOMENTE da operadora deste rateio."""
        planilhas = [
            p
            for p in parser.ler(arquivos, dados_externos)
            if p.operadora == self.operadora
        ]
        resultado = calculator.calcular(planilhas, dados_externos)

        documentos = [
            d
            for d in validators.extrair_documentos(arquivos)
            if d.operadora == self.operadora
        ]
        resultado.reconciliacao = validators.reconciliar(resultado, documentos)
        return resultado

    def processar(
        self,
        arquivos: dict[str, bytes],
        dados_externos: dict[str, Any],
    ) -> list[ItemRateio]:
        """Adaptador para o contrato da base: detalhe por colaborador."""
        return self.resultado_para_itens(self.processar_completo(arquivos, dados_externos))

    def resultado_para_itens(self, resultado: ResultadoRateio) -> list[ItemRateio]:
        """Converte o ResultadoRateio rico em `list[ItemRateio]` (base/CSV).

        Público para o router reaproveitar o resultado já processado (via
        `processar_completo`) sem reexecutar o pipeline.
        """
        return [self._para_item_rateio(item) for item in resultado.itens]

    def resumo(self, resultado: ResultadoRateio) -> dict[str, Any]:
        """Resumo JSON-able do resultado (Decimais serializados pelo router)."""
        return {
            "itens": [vars(i) for i in resultado.itens],
            "agregado": [vars(a) for a in resultado.agregado],
            "divergencias": [vars(d) for d in resultado.divergencias],
            "estornos": [vars(e) for e in resultado.estornos],
            "reconciliacao": [vars(r) for r in resultado.reconciliacao],
            "totais": [vars(t) for t in resultado.totais],
            "avisos": resultado.avisos,
        }

    @staticmethod
    def _para_item_rateio(item: ItemColaborador) -> ItemRateio:
        historico = (
            f"Plano de saúde {item.operadora} {item.competencia} "
            f"({item.num_vidas} vida(s))"
        )
        return ItemRateio(
            colaborador_cpf=item.cpf,
            colaborador_nome=item.nome,
            departamento="",  # não fornecido pela API; o destino é o centro de custo
            centro_de_custo=item.centro_custo,
            valor=item.valor,
            historico=historico,
            extras={
                "operadora": item.operadora,
                "empresa": item.empresa,
                "classe_valor": item.classe_valor,
                "matricula": item.matricula,
                "competencia": item.competencia,
                "num_vidas": str(item.num_vidas),
                "situacao": item.situacao,
            },
        )
