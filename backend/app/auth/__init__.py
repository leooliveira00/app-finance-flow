"""
Autenticação e segregação por área.

Login com usuário/senha (JWT) e controle de quais rateios cada usuário enxerga,
segundo as áreas às quais pertence. Hoje os usuários e o mapa área↔rateios vêm
de um seed em código (`seed.py`); a interface de `service.py` foi desenhada para
migrar esse seed para Postgres + telas de cadastro sem alterar os chamadores.
"""
