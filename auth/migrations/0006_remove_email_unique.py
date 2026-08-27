from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_alter_profile_role'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE accounts_profile
                DROP CONSTRAINT IF EXISTS accounts_profile_email_key;
            """,
            reverse_sql="""
                ALTER TABLE accounts_profile
                ADD CONSTRAINT accounts_profile_email_key UNIQUE (email);
            """
        ),
        migrations.AlterField(
            model_name='profile',
            name='email',
            field=models.EmailField(max_length=100, null=True, blank=True),
        ),
    ]
