from django.contrib import admin
from .models import Glossary

# Register your models here


class GlossaryAdmin(admin.ModelAdmin):
    """
    GlossaryAdmin class to render the youtube admin panel.
    """

    list_display = ("source_language",)


admin.site.register(Glossary, GlossaryAdmin)
