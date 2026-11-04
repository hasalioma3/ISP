from django.db import migrations, models
from django.db.models.functions import Lower, Trim


def make_existing_names_unique(apps, schema_editor):
    BillingPlan = apps.get_model('billing', 'BillingPlan')
    database = schema_editor.connection.alias
    used_names = set()

    plans = BillingPlan.objects.using(database).order_by('pk').values('pk', 'name')
    for plan in plans.iterator():
        original_name = plan['name'] or ''
        normalized_name = original_name.strip().lower()
        if normalized_name not in used_names:
            used_names.add(normalized_name)
            continue

        base_name = original_name.strip() or f"Plan {plan['pk']}"
        suffix = 2
        candidate = f"{base_name} ({suffix})"
        while candidate.strip().lower() in used_names:
            suffix += 1
            candidate = f"{base_name} ({suffix})"

        BillingPlan.objects.using(database).filter(pk=plan['pk']).update(name=candidate)
        used_names.add(candidate.strip().lower())


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0012_alter_billingplan_data_limit_gb_decimal'),
    ]

    operations = [
        migrations.RunPython(make_existing_names_unique, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='billingplan',
            constraint=models.UniqueConstraint(
                Lower(Trim('name')),
                name='billing_plan_name_ci_unique',
            ),
        ),
    ]