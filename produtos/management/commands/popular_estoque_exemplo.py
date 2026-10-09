from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from produtos.models import Preco, Produto, Supermercado


# Valores de demonstração para a apresentação. O comando nunca substitui
# preços nem estoques que um supermercado já informou.
OFERTAS = {
    'Jorge Super': [
        ('Arroz', '6.49', 20),
        ('Feijão carioca', '6.79', 15),
        ('Leite', '4.99', 30),
        ('Café', '9.89', 12),
    ],
    'Quaresma': [
        ('Arroz', '5.99', 24),
        ('Feijão', '3.50', 16),
        ('Feijão carioca', '6.49', 18),
        ('Refrigerante', '8.49', 24),
        ('Detergente', '2.29', 32),
    ],
}


class Command(BaseCommand):
    help = 'Adiciona algumas ofertas de exemplo a Jorge Super e Quaresma sem alterar ofertas já preenchidas.'

    @transaction.atomic
    def handle(self, *args, **options):
        criados = 0
        estoques_preenchidos = 0
        for nome_mercado, ofertas in OFERTAS.items():
            mercado = Supermercado.objects.filter(nome=nome_mercado).first()
            if mercado is None:
                self.stdout.write(self.style.WARNING(f'{nome_mercado}: cadastre o supermercado antes de popular o estoque.'))
                continue
            for nome_produto, valor, estoque in ofertas:
                produto = Produto.objects.filter(nome=nome_produto).first()
                if produto is None:
                    self.stdout.write(self.style.WARNING(f'Produto não encontrado: {nome_produto}. Execute as migrações.'))
                    continue
                preco, criado = Preco.objects.get_or_create(
                    supermercado=mercado,
                    produto=produto,
                    defaults={'valor': Decimal(valor), 'estoque': estoque},
                )
                if criado:
                    criados += 1
                elif preco.estoque is None:
                    preco.estoque = estoque
                    preco.save(update_fields=['estoque', 'atualizado_em'])
                    estoques_preenchidos += 1
        self.stdout.write(self.style.SUCCESS(
            f'Ofertas criadas: {criados}. Estoques antigos preenchidos: {estoques_preenchidos}.'
        ))
