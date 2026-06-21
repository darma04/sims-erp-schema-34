# Generated manually for performance optimization

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_alter_rolepermission_sub_module'),
    ]

    operations = [
        # Add index on 'role' field for faster filtering
        migrations.AlterField(
            model_name='rolepermission',
            name='role',
            field=models.CharField(max_length=50, db_index=True, verbose_name='Role'),
        ),
        
        # Add index on 'module' field
        migrations.AlterField(
            model_name='rolepermission',
            name='module',
            field=models.CharField(max_length=100, db_index=True, verbose_name='Module'),
        ),
        
        # Add composite index for (role, can_view) - most common query
        migrations.AddIndex(
            model_name='rolepermission',
            index=models.Index(fields=['role', 'can_view'], name='role_view_idx'),
        ),
        
        # Add composite index for (module, sub_module) - sidebar queries
        migrations.AddIndex(
            model_name='rolepermission',
            index=models.Index(fields=['module', 'sub_module'], name='module_sub_idx'),
        ),
    ]
