"""
Interface abstrata de um módulo de rateio.

Todo rateio da plataforma (ex.: plano de saúde, vale-transporte, telefonia)
é implementado como uma classe que herda de `RateioModule`. O `registry`
descobre essas classes automaticamente, e os routers as acionam de forma
genérica — sem conhecer os detalhes de cada rateio.

Este arquivo define apenas o CONTRATO. A implementação concreta de cada
rateio vive em seu próprio pacote dentro de `app/modules/` (use `_template/`
como ponto de partida).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass
class ValidationResult:
    """
    Resultado da validação dos arquivos/dados de entrada de um rateio.

    Atributos:
        valido: True se não há erros bloqueantes (o processamento pode seguir).
        erros: mensagens de erro CRÍTICAS que impedem o processamento.
        alertas: avisos NÃO bloqueantes (ex.: colaborador sem centro de custo
                 que cairá em um default) — o processamento segue, mas o
                 usuário deve revisar.
    """

    valido: bool
    erros: list[str]
    alertas: list[str]


@dataclass
class ItemRateio:
    """
    Uma linha do resultado do rateio: o valor atribuído a um colaborador.

    É a unidade de saída comum a todos os módulos. A lista de `ItemRateio`
    produzida por `processar()` é o que será serializado para CSV e,
    futuramente, enviado ao Protheus.

    Atributos:
        colaborador_cpf: CPF do colaborador (somente dígitos, sem máscara).
        colaborador_nome: nome completo do colaborador.
        departamento: departamento ao qual o colaborador pertence.
        centro_de_custo: centro de custo de destino do rateio (código Protheus).
        valor: valor monetário atribuído (Decimal para evitar erros de ponto
               flutuante em moeda).
        historico: texto do histórico contábil do lançamento.
        extras: campos adicionais específicos de cada rateio (ex.: classe_valor,
                matricula, operadora). É o ponto de extensão genérico — mantém o
                contrato enxuto e agnóstico à natureza do rateio; a serialização
                (CSV/ERP) anexa colunas conforme as chaves presentes.
    """

    colaborador_cpf: str
    colaborador_nome: str
    departamento: str
    centro_de_custo: str
    valor: Decimal
    historico: str
    extras: dict[str, str] = field(default_factory=dict)


class RateioModule(ABC):
    """
    Contrato que todo módulo de rateio deve implementar.

    Atributos de classe (devem ser definidos por cada subclasse):
        tipo: identificador único e estável do rateio, usado nas rotas
              (ex.: "plano-saude"). É a chave no registry e na URL
              /api/rateio/{tipo}/processar.
        nome: rótulo CURTO para UI (chips, badges, títulos) — ex.: "Pagamento
              UNIMED". Se vazio, os consumidores derivam um fallback do `tipo`.
        descricao: descrição legível e completa, usada em tooltips e na listagem
                   detalhada de módulos (/api/modulos).

    Capacidades (declaradas por cada subclasse; os routers as consultam em vez
    de inspecionar o NOME do tipo — ex.: `"pagamento" in tipo`):
        lanca_no_erp: o rateio gera título no ERP (pré-nota/AE). Habilita o
                      endpoint de envio ao ERP. Default False.
        notifica_fiscal: após o envio, o rateio notifica o dep. fiscal por
                         e-mail (NF/boleto + títulos). Default False.
        usa_colaboradores: o rateio precisa do cadastro de colaboradores do
                           Protheus em `dados_externos`. Default True. Marque
                           False quando o casamento não for por pessoa (ex.:
                           telefonia casa por número de linha) — assim o rateio
                           não depende da disponibilidade do Protheus.

    Fluxo de uso pelos routers:
        1. validar_inputs(...) -> ValidationResult
        2. se válido, processar(...) -> list[ItemRateio]
    """

    tipo: str
    nome: str = ""
    descricao: str
    lanca_no_erp: bool = False
    notifica_fiscal: bool = False
    # Fornecedor do rateio (chave em `protheus_fornecedor_cnpj`): é o CNPJ dele
    # que busca o contrato de parceria. Vazio -> o serviço deduz pelo tipo, como
    # fazia antes de a declaração existir.
    fornecedor: str = ""
    usa_colaboradores: bool = True

    @abstractmethod
    def validar_inputs(
        self,
        arquivos: dict[str, bytes],
        dados_externos: dict[str, Any],
    ) -> ValidationResult:
        """
        Valida os arquivos recebidos antes de processar.

        Deve verificar estrutura, colunas obrigatórias e integridade dos dados.
        Retorna ValidationResult com erros críticos e alertas não bloqueantes.

        Args:
            arquivos: mapa nome_do_arquivo -> conteúdo em bytes (uploads).
            dados_externos: dados de outras fontes (ex.: cadastro vindo do
                            Protheus) necessários à validação cruzada.

        Returns:
            ValidationResult — `valido=False` deve impedir a chamada a
            `processar()` no router.
        """
        # NOTA: implementar na subclasse (ver _template/module.py).
        raise NotImplementedError

    @abstractmethod
    def processar(
        self,
        arquivos: dict[str, bytes],
        dados_externos: dict[str, Any],
    ) -> list[ItemRateio]:
        """
        Executa o cálculo do rateio.

        Recebe arquivos das operadoras e dados externos (ex.: Protheus).
        Retorna lista de ItemRateio com um item por colaborador.

        Deve ser chamado apenas após `validar_inputs` indicar `valido=True`.

        Args:
            arquivos: mapa nome_do_arquivo -> conteúdo em bytes (uploads).
            dados_externos: dados de apoio (ex.: cadastro/centros de custo).

        Returns:
            list[ItemRateio] — o resultado do rateio, pronto para serialização.
        """
        # NOTA: implementar na subclasse (ver _template/module.py).
        raise NotImplementedError
