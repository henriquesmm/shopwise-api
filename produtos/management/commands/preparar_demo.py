from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from produtos.models import Preco, Produto, Supermercado


class Command(BaseCommand):
    help = 'Prepara as contas, mercados e preços da demonstração local.'

    def add_arguments(self, parser):
        parser.add_argument('--senha', required=True, help='Senha das contas novas da demonstração.')

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('Este comando é apenas para a demonstração local.')

        with transaction.atomic():
            usuarios = {}
            for nome in ('felipe', 'jorge_super', 'quaresma'):
                email = f'{nome}@example.com'
                usuario, criado = get_user_model().objects.get_or_create(
                    username=nome, defaults={'email': email}
                )
                if criado:
                    usuario.set_password(options['senha'])
                    usuario.save(update_fields=['password'])
                elif usuario.email.lower() != email or usuario.is_staff:
                    raise CommandError(f'A conta {nome} já existe com outros dados.')
                usuarios[nome] = usuario

            mercados = {}
            for nome, endereco, responsavel in (
                ('Jorge Super', 'Rua Exemplo, 100', 'jorge_super'),
                ('Quaresma', 'Rua Exemplo, 200', 'quaresma'),
            ):
                mercado, criado = Supermercado.objects.get_or_create(
                    nome=nome,
                    defaults={'endereco': endereco, 'responsavel': usuarios[responsavel]},
                )
                if not criado and mercado.responsavel_id != usuarios[responsavel].pk:
                    raise CommandError(f'O supermercado {nome} pertence a outra conta.')
                mercados[nome] = mercado

            produto = Produto.objects.filter(nome__iexact='Arroz 1 kg').first()
            if produto is None:
                produto = Produto.objects.create(nome='Arroz 1 kg', categoria='Mercearia')

            for nome, valor in (('Jorge Super', '6.49'), ('Quaresma', '5.99')):
                Preco.objects.get_or_create(
                    produto=produto,
                    supermercado=mercados[nome],
                    defaults={'valor': Decimal(valor)},
                )

        self.stdout.write(self.style.SUCCESS('Dados da demonstracao prontos.'))
        self.stdout.write('Contas existentes mantiveram suas senhas; precos existentes foram mantidos.')
