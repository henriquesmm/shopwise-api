from decimal import Decimal

import django.core.validators
import django.utils.timezone
from django.db import migrations, models
from django.db.models import Count, Q


def verificar_precos_existentes(apps, schema_editor):
    Preco = apps.get_model('produtos', 'Preco')
    existem_duplicados = (
        Preco.objects.values('produto_id', 'supermercado_id')
        .annotate(total=Count('id'))
        .filter(total__gt=1)
        .exists()
    )
    if existem_duplicados or Preco.objects.filter(valor__lte=0).exists():
        raise RuntimeError(
            'Existem preços duplicados ou não positivos. Corrija os dados '
            'antes de aplicar a migração 0004; nenhum registro será apagado.'
        )


class Migration(migrations.Migration):
    dependencies = [
        ('produtos', '0003_alter_produto_id_alter_supermercado_id_preco'),
    ]

    operations = [
        migrations.AddField(
            model_name='preco',
            name='atualizado_em',
            field=models.DateTimeField(default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.RunPython(verificar_precos_existentes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='preco',
            name='valor',
            field=models.DecimalField(
                decimal_places=2,
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(Decimal('0.01'))],
            ),
        ),
        migrations.AlterField(
            model_name='preco',
            name='atualizado_em',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddConstraint(
            model_name='preco',
            constraint=models.UniqueConstraint(
                fields=('produto', 'supermercado'),
                name='preco_unico_produto_supermercado',
            ),
        ),
        migrations.AddConstraint(
            model_name='preco',
            constraint=models.CheckConstraint(
                condition=Q(valor__gt=0),
                name='preco_valor_positivo',
            ),
        ),
    ]
