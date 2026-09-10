"""
Serviços de infraestrutura (integrações externas).

Aqui vivem os clientes de sistemas externos — hoje a API Protheus (colaboradores
e, futuramente, o POST de lançamentos). Esta camada é o que torna o router capaz
de montar o `dados_externos` que alimenta os módulos de rateio, mantendo os
módulos puros (sem rede nem banco).
"""
